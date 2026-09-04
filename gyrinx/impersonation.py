"""Admin impersonation: session keys, permission helpers, and the page subject.

Impersonation is a per-request overlay. The admin stays authenticated — the
session's ``_auth_user_id`` is unchanged — and the target user's id is stored in
the session. :class:`gyrinx.middleware.ImpersonationMiddleware` swaps
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


# Attribute the view sets to say whose content the page is showing. Read by
# :func:`gyrinx.context_processors.impersonation` to offer the admin a way
# straight into that account.
PAGE_SUBJECT_ATTR = "impersonation_page_subject"


def note_page_subject(request, user) -> None:
    """Record that this page is showing ``user``'s content.

    Only pages that open for someone other than their owner have a subject
    worth naming — a page scoped to the viewer is already about them.
    """
    setattr(request, PAGE_SUBJECT_ATTR, user)


def page_subject(request):
    """Whose content the page is showing, or ``None`` if nothing said."""
    return getattr(request, PAGE_SUBJECT_ATTR, None)
