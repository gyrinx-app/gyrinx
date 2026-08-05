"""Platform context processors."""

import logging

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError, InterfaceError, OperationalError

from gyrinx.site.models import (
    BANNER_CACHE_KEY,
    BANNER_CACHE_TIMEOUT,
    Banner,
    Notification,
)

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


def impersonation(request):
    """Expose impersonation state to templates.

    Set by :class:`gyrinx.middleware.ImpersonationMiddleware`. When
    ``is_impersonating`` is true, ``request.user`` is the impersonated user and
    ``impersonator`` is the real admin.
    """
    return {
        "is_impersonating": getattr(request, "is_impersonating", False),
        "impersonator": getattr(request, "impersonator", None),
    }


def site_banner(request):
    """
    Add the current live banner to the context, if any exists and hasn't been dismissed.

    Note that this is disabled in tests by directly setting BANNER_CACHE_KEY to False
    """
    context = {"banner": None}

    # Try to get banner from cache first
    live_banner = cache.get(BANNER_CACHE_KEY)

    if live_banner is None:
        # Banner not in cache, fetch from database
        try:
            live_banner = Banner.objects.filter(is_live=True).first()
            # Cache the result (even if None) to avoid repeated DB queries
            cache.set(BANNER_CACHE_KEY, live_banner or False, BANNER_CACHE_TIMEOUT)
        except Banner.DoesNotExist:
            # This is expected when no banner exists
            live_banner = None
            cache.set(BANNER_CACHE_KEY, False, BANNER_CACHE_TIMEOUT)
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
