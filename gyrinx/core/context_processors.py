import logging

from django.db import DatabaseError, OperationalError, InterfaceError

from gyrinx.core.models import Banner

logger = logging.getLogger(__name__)


def site_banner(request):
    """Add the current live banner to the context, if any exists and hasn't been dismissed."""
    context = {"banner": None}

    # Check if there's a live banner
    try:
        live_banner = Banner.objects.filter(is_live=True).first()
        if live_banner:
            # Check if the user has dismissed this banner
            dismissed_banners = request.session.get("dismissed_banners", [])
            if str(live_banner.id) not in dismissed_banners:
                context["banner"] = live_banner
    except (DatabaseError, OperationalError, InterfaceError) as e:
        # Database-related errors should be logged but not break the page
        # Use warning level instead of exception to reduce noise in logs
        logger.warning(
            f"Database error while fetching site banner: {type(e).__name__}: {e}"
        )
    except Exception:
        # Log any unexpected errors but don't break page rendering
        logger.exception("Unexpected error in site_banner context processor")

    return context
