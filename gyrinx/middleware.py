"""Platform middleware — edition-agnostic request handling."""

from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import RequestDataTooBig
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.template import TemplateDoesNotExist, TemplateSyntaxError
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers

from gyrinx.editions import (
    COOKIE_MAX_AGE,
    COOKIE_NAME,
    N23,
    N26,
    chosen_edition,
    edition_for_path,
    remembered_edition,
)
from gyrinx.impersonation import (
    IMPERSONATE_KEY,
    IMPERSONATE_LOG_KEY,
    IMPERSONATE_MAX_AGE_SECONDS,
    IMPERSONATE_SESSION_KEYS,
    IMPERSONATE_STARTED_KEY,
    can_impersonate,
)


class ClearLoggingRequestMiddleware:
    """
    Clear google.cloud.logging's per-thread request reference after each
    response.

    The upstream RequestMiddleware stores the request in a thread-local and
    never removes it. Under a threaded server (gunicorn gthread) threads are
    reused, so each pool thread would otherwise pin its most recent request —
    user, session, any in-memory upload buffer — indefinitely, and log records
    emitted on that thread outside a request would pick up the stale request
    for trace correlation. Must sit above RequestMiddleware in MIDDLEWARE so
    this clear runs after the response is fully generated.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        finally:
            from google.cloud.logging_v2.handlers.middleware.request import (
                _thread_locals,
            )

            _thread_locals.request = None


class RequestSizeExceptionMiddleware:
    """
    Middleware to catch RequestDataTooBig exceptions and return a 400 response.

    This ensures that overly large requests are properly handled as client errors
    (400 Bad Request) instead of server errors (500 Internal Server Error).

    The issue is that Django's default exception handling doesn't always properly
    convert RequestDataTooBig (a SuspiciousOperation) to a 400 response,
    especially when the exception is raised during middleware processing
    (like CSRF middleware) before the view is called.

    See: https://github.com/gyrinx-app/gyrinx/issues/1097
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        """
        Process exceptions raised during request handling.

        If the exception is RequestDataTooBig, return a 400 Bad Request response
        instead of letting it bubble up as a 500 error.
        """
        if isinstance(exception, RequestDataTooBig):
            context = {
                "error_code": 400,
                "error_message": "Request Too Large",
                "error_description": (
                    "The request body is too large. "
                    "Please reduce the size of your upload."
                ),
            }
            try:
                return render(request, "errors/error.html", context, status=400)
            except TemplateDoesNotExist, TemplateSyntaxError:
                # Fallback to simple response if template rendering fails
                return HttpResponse(
                    "400 Bad Request: The request body is too large.",
                    status=400,
                    content_type="text/plain",
                )
        return None


class EditionMiddleware:
    """Remember which edition a reader is in, and answer for them where the
    address cannot.

    Runs after ``AuthenticationMiddleware``: only signed-in readers are
    remembered, because the edition pill is theirs and a visitor should not
    collect a cookie they have no use for.

    Two things come out of it. ``request.edition`` is the edition to show as
    current — the address's own, or the remembered one on a page both editions
    share. And the site root, which belongs to neither edition, redirects a
    reader last seen in n26 to the n26 dashboard, so a trip out to the inbox or
    the account pages and back does not quietly land them in the classic app.

    Leaving n26 is a link to the root, which is the very address that redirects
    back into it, so ``?edition=n23`` on that link says the reader means it.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path_edition = edition_for_path(request.path)
        chosen = chosen_edition(request)
        user = getattr(request, "user", None)
        signed_in = user is not None and user.is_authenticated
        remembered = remembered_edition(request) if signed_in else None

        request.path_edition = path_edition
        request.edition = chosen or path_edition or remembered or N23

        if (
            signed_in
            and remembered == N26
            and chosen is None
            and request.path == "/"
            and request.method in ("GET", "HEAD")
        ):
            response = HttpResponseRedirect(reverse("n26-dashboard"))
            # The root answers differently depending on the cookie, so anything
            # caching it has to be told to key on one.
            patch_vary_headers(response, ("Cookie",))
            return response

        response = self.get_response(request)

        # Only an address or an explicit choice moves the memory. A shared page
        # must not: it would pin a reader to whichever edition they happened to
        # have been in the first time they opened their account settings.
        named = chosen or path_edition
        if signed_in and named is not None and named != remembered:
            response.set_cookie(
                COOKIE_NAME,
                named,
                max_age=COOKIE_MAX_AGE,
                samesite="Lax",
                secure=request.is_secure(),
                httponly=True,
            )
        return response


class ImpersonationMiddleware:
    """Swap ``request.user`` to an impersonated user when an admin is impersonating.

    Runs after ``AuthenticationMiddleware`` / allauth, so ``request.user`` is the
    real, authenticated admin when we check permission — and before the view, so the
    swap flows through everything derived from ``request.user`` (simple-history
    attribution, the ``CampaignAction`` / ``ListAction`` ledgers, permissions,
    notifications, templates). The admin's login is never touched; impersonation
    lives entirely in the session as a per-request overlay.

    Only the auth layer knows: ``request.impersonator`` holds the real admin and
    ``request.is_impersonating`` is set while the overlay is active.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.impersonator = None
        request.is_impersonating = False
        self._maybe_impersonate(request)
        return self.get_response(request)

    def _maybe_impersonate(self, request):
        session = getattr(request, "session", None)
        if session is None:
            return

        target_id = session.get(IMPERSONATE_KEY)
        if not target_id:
            return

        admin = getattr(request, "user", None)

        # The real principal must still be allowed to impersonate. If the admin
        # logged out or lost superuser, drop the overlay immediately.
        if not can_impersonate(admin):
            self._stop(session, "revoked")
            return

        # Never impersonate on the Django admin — the admin keeps admin access and
        # a guaranteed escape hatch even when the target isn't staff.
        if request.path.startswith("/admin/"):
            return

        # Auto-expire long-running sessions.
        if self._expired(session):
            self._stop(session, "expired")
            return

        target = get_user_model().objects.filter(pk=target_id, is_active=True).first()
        if target is None or target.pk == admin.pk:
            self._stop(session, "revoked")
            return

        request.impersonator = admin
        request.user = target
        request.is_impersonating = True

    @staticmethod
    def _expired(session):
        started = session.get(IMPERSONATE_STARTED_KEY)
        if not started:
            return False
        try:
            started_dt = datetime.fromisoformat(started)
        except TypeError, ValueError:
            # Unparseable timestamp — treat as expired so we fail closed.
            return True
        return (
            timezone.now() - started_dt
        ).total_seconds() > IMPERSONATE_MAX_AGE_SECONDS

    @staticmethod
    def _stop(session, reason):
        """Close the open log for this session and clear the overlay keys."""
        log_id = session.get(IMPERSONATE_LOG_KEY)
        if log_id:
            from gyrinx.site.models import ImpersonationLog

            ImpersonationLog.objects.filter(pk=log_id, ended_at__isnull=True).update(
                ended_at=timezone.now(), ended_reason=reason
            )
        for key in IMPERSONATE_SESSION_KEYS:
            session.pop(key, None)
