"""Platform context processors."""

import logging

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, InterfaceError, OperationalError

from gyrinx.editions import N23, edition_for_path
from gyrinx.site.models import (
    BANNER_CACHE_KEYS,
    BANNER_CACHE_TIMEOUT,
    Banner,
    Notification,
)

logger = logging.getLogger(__name__)


def notifications(request):
    """Return the signed-in user's unread count without caching it.

    The cache is per-process and cannot reliably invalidate counts across
    workers. Log query failures without preventing page rendering.
    """
    context = {"unread_notification_count": 0}
    try:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
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


def gyrinx_debug(request):
    """Add gyrinx_debug flag to the context for debug UI elements."""
    return {"gyrinx_debug": settings.GYRINX_DEBUG}


def write_pause(request):
    pause = getattr(request, "write_pause", None)
    return {
        "write_pause": pause
        if pause is not None and pause.state == pause.State.PAUSED
        else None
    }


def impersonation(request):
    """Expose active impersonation and an eligible page owner to templates.

    An active session supplies the impersonated user and real admin. A page
    may call note_page_subject(request, user) for a direct account-menu action, which
    is unavailable during an existing impersonation session. Check for that
    subject before resolving request.user on error pages.
    """
    from gyrinx.impersonation import can_impersonate_target, page_subject

    is_impersonating = getattr(request, "is_impersonating", False)
    subject = page_subject(request)
    target = None
    if (
        subject is not None
        and not is_impersonating
        and can_impersonate_target(getattr(request, "user", None), subject)
    ):
        target = subject

    return {
        "is_impersonating": is_impersonating,
        "impersonator": getattr(request, "impersonator", None),
        "impersonate_target": target,
    }


def site_banner(request):
    """Return the undismissed live banner for the request's edition.

    Shared pages use the N23 banner to match their platform layout. Tests
    disable lookup by setting the edition cache entries to False.
    """
    context = {"banner": None}

    edition = edition_for_path(request.path) or N23
    cache_key = BANNER_CACHE_KEYS[edition]

    # Try to get banner from cache first
    live_banner = cache.get(cache_key)

    if live_banner is None:
        # Banner not in cache, fetch from database
        try:
            live_banner = Banner.objects.filter(
                **{Banner.LIVE_FLAGS[edition]: True}
            ).first()
            # Cache the result (even if None) to avoid repeated DB queries
            cache.set(cache_key, live_banner or False, BANNER_CACHE_TIMEOUT)
        except Banner.DoesNotExist:
            # This is expected when no banner exists
            live_banner = None
            cache.set(cache_key, False, BANNER_CACHE_TIMEOUT)
        except (DatabaseError, OperationalError, InterfaceError) as e:
            # Database-related errors should be logged but not break the page
            # Use warning level instead of exception to reduce noise in logs
            logger.warning(
                f"Database error while fetching site banner: {type(e).__name__}: {e}"
            )
            # Don't cache on database errors - try again next request
            live_banner = None
        except Exception:
            # Log any unexpected errors but don't break page rendering
            logger.exception("Unexpected error in site_banner context processor")
            live_banner = None

    # Check for False cached value (meaning no banner exists)
    if live_banner is False:
        live_banner = None

    # Only show banner if user hasn't dismissed it
    if live_banner:
        # Check if session is available (may not be in ASGI error handling contexts)
        if hasattr(request, "session"):
            dismissed_banners = request.session.get("dismissed_banners", [])
            if str(live_banner.id) not in dismissed_banners:
                context["banner"] = live_banner
        else:
            # Show banner if we can't check dismissed status
            context["banner"] = live_banner

    return context
