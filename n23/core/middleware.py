"""Edition middleware.

Only ``ImpersonationMiddleware`` remains here — it writes the ``ImpersonationLog``
edition model. The edition-agnostic middleware moved to ``gyrinx.middleware``.
"""

from datetime import datetime

from django.contrib.auth import get_user_model
from django.utils import timezone

from gyrinx.impersonation import (
    IMPERSONATE_KEY,
    IMPERSONATE_LOG_KEY,
    IMPERSONATE_MAX_AGE_SECONDS,
    IMPERSONATE_SESSION_KEYS,
    IMPERSONATE_STARTED_KEY,
    can_impersonate,
)


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
        except (TypeError, ValueError):
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
