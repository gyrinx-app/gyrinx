"""Admin site that hands authentication to django-allauth.

Django's own admin login view authenticates against a username and password and
nothing else. It knows nothing about allauth's login stages, so a staff account
with TOTP configured could sign in at ``/admin/login/`` without ever being asked
for a second factor — the app's front door is protected, the admin's is not.

``GyrinxAdminSite`` closes that door. The admin login view never renders a form:
it only redirects into the allauth flow, so every admin session is created by the
same code path (and the same second-factor challenge) as every app session.

On top of that, when ``ADMIN_REQUIRE_MFA`` is on, reaching the admin requires
that the staff user actually *has* a second factor configured, and that the
current session was authenticated with it. Users who fall short are sent to
allauth to set up TOTP or to enter a code, rather than being locked out.
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
    """Whether the admin is gated on a completed second-factor challenge.

    An explicit ``ADMIN_REQUIRE_MFA`` wins. Left unset, the gate follows
    ``DEBUG``: on in production, off in local development, where each worktree
    has its own database and requiring TOTP would mean a separate authenticator
    per worktree. Note that this only relaxes the *second factor* — admin login
    still goes through allauth everywhere.
    """
    configured = getattr(settings, "ADMIN_REQUIRE_MFA", None)
    if configured is not None:
        return bool(configured)
    return not settings.DEBUG


def session_authenticated_with_mfa(request) -> bool:
    """Whether this session completed an allauth MFA challenge.

    allauth logs every authentication step it performs into the session, so this
    is a statement about *this* session rather than about the user's settings —
    a session created before the user enabled TOTP does not count.
    """
    from allauth.account.authentication import get_authentication_records

    return any(
        record.get("method") == "mfa" for record in get_authentication_records(request)
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
    """Whether this request is a step on the way into the admin.

    Reads the ``next`` target, so it holds for allauth's own pages while they
    are standing between the visitor and an admin URL.
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
    """Put ``url_patterns`` behind the same gate as the admin's own views.

    ``AdminSite.admin_view`` protects everything routed through the site itself,
    but admin-adjacent URLconfs (admindocs) are decorated with Django's
    ``staff_member_required``, which only knows about ``is_staff``. Wrapping
    their callbacks sends visitors through the admin login view instead, so
    there is one place that decides who gets in.
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
