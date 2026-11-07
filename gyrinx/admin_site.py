"""Route admin authentication through allauth, including its MFA checks.

The admin login redirects to allauth instead of accepting credentials itself.
When ADMIN_REQUIRE_MFA applies, staff must configure a second factor and
complete its challenge in the current session before accessing admin pages.
"""

from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.apps import AdminConfig
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

#: Message shown when a staff user has no second factor configured at all.
MFA_SETUP_MESSAGE = (
    "Two-factor authentication is required to use the Gyrinx admin. "
    "Set up an authenticator app to continue."
)

#: Message shown when a staff user has a second factor, but this session was
#: signed in without using it (e.g. a session that predates the setup).
MFA_CHALLENGE_MESSAGE = (
    "Enter your two-factor authentication code to continue to the Gyrinx admin."
)


_UNSET = object()


def admin_requires_mfa() -> bool:
    """Return the configured MFA requirement, defaulting to enabled outside DEBUG.

    Local worktrees may omit second-factor setup; admin login still uses
    allauth in every environment.
    """
    configured = getattr(settings, "ADMIN_REQUIRE_MFA", None)
    if configured is not None:
        return bool(configured)
    return not settings.DEBUG


def session_authenticated_with_mfa(request) -> bool:
    """Return whether allauth recorded an MFA challenge for this user's session."""
    from allauth.account.authentication import get_authentication_records

    return any(
        record.get("method") == "mfa"
        for record in get_authentication_records(request, request.user)
    )


def mfa_gate_url(request):
    """The allauth URL this staff user must visit to satisfy 2FA, or ``None``.

    ``None`` means the request already satisfies the requirement (or the
    requirement is switched off).

    Cached on the request: ``has_permission`` is consulted several times while
    rendering an admin page, and the authenticator lookup is a query.
    """
    cached = getattr(request, "_admin_mfa_gate_url", _UNSET)
    if cached is not _UNSET:
        return cached

    request._admin_mfa_gate_url = _mfa_gate_url(request)
    return request._admin_mfa_gate_url


def _mfa_gate_url(request):
    from allauth.mfa.utils import is_mfa_enabled

    if not admin_requires_mfa():
        return None
    if not is_mfa_enabled(request.user):
        return reverse("mfa_activate_totp")
    if not session_authenticated_with_mfa(request):
        return reverse("mfa_reauthenticate")
    return None


def admin_second_factor_required(user) -> bool:
    """Whether this user must prove a second factor to reach the admin."""
    from allauth.mfa.utils import is_mfa_enabled

    return (
        admin_requires_mfa()
        and user.is_authenticated
        and user.is_active
        and user.is_staff
        and is_mfa_enabled(user)
    )


def is_admin_bound_request(request) -> bool:
    """Return whether a validated next parameter points into the admin.

    This also identifies allauth pages handling an admin-bound login.
    """
    if request is None:
        return False

    next_url = request.GET.get(REDIRECT_FIELD_NAME)
    if not next_url and request.method == "POST":
        next_url = request.POST.get(REDIRECT_FIELD_NAME)
    if not next_url:
        return False
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return False
    return next_url.startswith(reverse("admin:index"))


def admin_gated_patterns(url_patterns):
    """Apply the admin's authentication checks to adjacent URL patterns.

    Pages such as admindocs otherwise check only staff status and could omit
    the admin's second-factor requirement.
    """
    from django.urls import URLPattern

    return [
        URLPattern(
            pattern.pattern,
            _admin_access_required(pattern.callback),
            pattern.default_args,
            pattern.name,
        )
        for pattern in url_patterns
    ]


def _admin_access_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        from django.contrib import admin
        from django.contrib.auth.views import redirect_to_login

        if not admin.site.has_permission(request):
            return redirect_to_login(
                request.get_full_path(),
                reverse("admin:login", current_app=admin.site.name),
                REDIRECT_FIELD_NAME,
            )
        return view(request, *args, **kwargs)

    return wrapper


class GyrinxAdminSite(AdminSite):
    def has_permission(self, request):
        """Staff-and-active, plus the second-factor requirement."""
        if not super().has_permission(request):
            return False
        return mfa_gate_url(request) is None

    def login(self, request, extra_context=None):
        """Redirect into allauth instead of rendering the admin's login form.

        Every admin view routes here when :meth:`has_permission` says no, so this
        is the single place that decides where an under-authenticated visitor
        goes: the allauth login page, TOTP setup, or a TOTP challenge.
        """
        next_url = self._admin_next_url(request)

        if not request.user.is_authenticated:
            return self._redirect_with_next(settings.LOGIN_URL, next_url)

        if not (request.user.is_active and request.user.is_staff):
            raise PermissionDenied

        gate_url = mfa_gate_url(request)
        if gate_url:
            from allauth.mfa.utils import is_mfa_enabled

            messages.warning(
                request,
                MFA_CHALLENGE_MESSAGE
                if is_mfa_enabled(request.user)
                else MFA_SETUP_MESSAGE,
            )
            return self._redirect_with_next(gate_url, next_url)

        # Fully authorised — they only landed here via a stale bookmark or a
        # redirect chain that has since been satisfied.
        return HttpResponseRedirect(next_url)

    def _admin_next_url(self, request):
        """Where to send the visitor once they are authenticated.

        Falls back to the admin index, and never points back at the login view
        itself (which would bounce the visitor around in a loop).
        """
        index_url = reverse("admin:index", current_app=self.name)
        login_url = reverse("admin:login", current_app=self.name)

        next_url = request.GET.get(REDIRECT_FIELD_NAME) or request.POST.get(
            REDIRECT_FIELD_NAME
        )
        if not next_url:
            return index_url
        if not url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return index_url
        if next_url.split("?")[0] == login_url:
            return index_url
        return next_url

    @staticmethod
    def _redirect_with_next(url, next_url):
        # Imported here, not at module scope: this module is loaded while
        # INSTALLED_APPS is still being resolved, before the app registry (and
        # so the models django.contrib.auth.views imports) is ready.
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(next_url, url, REDIRECT_FIELD_NAME)


class GyrinxAdminConfig(AdminConfig):
    """Installed in place of ``django.contrib.admin`` to swap in the site above."""

    default_site = "gyrinx.admin_site.GyrinxAdminSite"
