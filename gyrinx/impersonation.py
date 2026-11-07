"""Shared impersonation session keys, permission checks and page-subject helpers.

Only superusers may impersonate. Middleware replaces request.user for each
request while leaving the authenticated session user unchanged.
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


# Shareable views record their content owner for the impersonation context processor.
PAGE_SUBJECT_ATTR = "impersonation_page_subject"


def note_page_subject(request, user) -> None:
    """Set the content owner used by impersonation controls on shareable pages."""
    setattr(request, PAGE_SUBJECT_ATTR, user)


def page_subject(request):
    """Return the recorded content owner, or None if the view supplied none."""
    return getattr(request, PAGE_SUBJECT_ATTR, None)
