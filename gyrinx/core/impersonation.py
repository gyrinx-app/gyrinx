"""Admin impersonation: session keys and permission helpers.

Impersonation is a per-request overlay. The admin stays authenticated — the
session's ``_auth_user_id`` is unchanged — and the target user's id is stored in
the session. :class:`gyrinx.core.middleware.ImpersonationMiddleware` swaps
``request.user`` for the duration of each request, so everything derived from
``request.user`` (history attribution, audit ledgers, permissions, templates)
reflects the impersonated user without any per-feature changes.

Only superusers may impersonate.
"""

# Session keys.
IMPERSONATE_KEY = "impersonate_user_id"  # target user id (int)
IMPERSONATE_STARTED_KEY = "impersonate_started_at"  # ISO-8601 start timestamp
IMPERSONATE_LOG_KEY = "impersonate_log_id"  # ImpersonationLog id (str UUID)

# Session keys cleared together whenever impersonation ends.
IMPERSONATE_SESSION_KEYS = (
    IMPERSONATE_KEY,
    IMPERSONATE_STARTED_KEY,
    IMPERSONATE_LOG_KEY,
)

# Auto-expire an impersonation session after this long.
IMPERSONATE_MAX_AGE_SECONDS = 3 * 60 * 60  # 3 hours


def can_impersonate(user) -> bool:
    """Whether ``user`` is allowed to impersonate other users."""
    return bool(user is not None and user.is_authenticated and user.is_superuser)


def can_impersonate_target(admin, target) -> bool:
    """Whether ``admin`` may impersonate ``target``.

    Admins may impersonate other admins, but not themselves or inactive users.
    """
    return bool(
        can_impersonate(admin)
        and target is not None
        and target.is_active
        and target.pk != admin.pk
    )
