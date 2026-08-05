"""Edition context processors.

``site_banner`` moved to ``gyrinx.context_processors`` with the ``Banner`` model.
``notifications`` stays here while ``Notification`` is an edition model.
"""

import logging

from django.db import DatabaseError, InterfaceError, OperationalError

logger = logging.getLogger(__name__)


def notifications(request):
    """Add the unread notification count for the navbar badge (authenticated only).

    A single COUNT backed by a partial index — cheap and always correct. We do not
    cache it: the cache backend is per-process ``LocMemCache``, so a cached per-user
    count couldn't be invalidated reliably across instances. Never raises — a failure
    here must not break page rendering.
    """
    context = {"unread_notification_count": 0}
    try:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            from n23.core.models import Notification

            context["unread_notification_count"] = (
                Notification.objects.unread_count_for(user)
            )
    except (DatabaseError, OperationalError, InterfaceError) as e:
        logger.warning(
            f"Database error while counting notifications: {type(e).__name__}: {e}"
        )
    except Exception:
        logger.exception("Unexpected error in notifications context processor")
    return context
