import logging

from django.db import DatabaseError, OperationalError
from django.db.utils import InterfaceError

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
    except Banner.DoesNotExist:
        # This is expected when no banner exists
        pass
    except (DatabaseError, OperationalError, InterfaceError):
        # Database-related errors should be logged but not break the page
        logger.exception("Database error while fetching site banner")
        pass
    except Exception:
        # Log any unexpected errors but don't break page rendering
        logger.exception("Unexpected error in site_banner context processor")
        pass

    return context
