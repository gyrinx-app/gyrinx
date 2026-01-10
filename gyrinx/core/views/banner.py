"""Banner views."""

import json
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.site import Banner

logger = logging.getLogger(__name__)


@require_POST
def dismiss_banner(request):
    """
    Dismiss a banner by storing its ID in the session.

    **Request Body**

    ``banner_id`` (str)
        The ID of the banner to dismiss.

    **Returns**

    JSON response with success status.
    """
    try:
        data = json.loads(request.body)
        banner_id = data.get("banner_id")

        if banner_id:
            # Get or create the dismissed banners list in session
            dismissed_banners = request.session.get("dismissed_banners", [])

            # Add this banner ID if not already dismissed
            if banner_id not in dismissed_banners:
                dismissed_banners.append(banner_id)
                request.session["dismissed_banners"] = dismissed_banners
                request.session.modified = True

            # Log the banner dismissal
            if request.user.is_authenticated:
                log_event(
                    user=request.user,
                    noun=EventNoun.USER,
                    verb=EventVerb.UPDATE,
                    request=request,
                    action="dismiss_banner",
                    banner_id=banner_id,
                )

            return JsonResponse({"success": True})
        else:
            return JsonResponse(
                {"success": False, "error": "No banner ID provided"}, status=400
            )

    except json.JSONDecodeError:
        logger.exception("Invalid JSON received in banner dismissal request")
        return JsonResponse(
            {"success": False, "error": "Invalid JSON format"}, status=400
        )
    except KeyError:
        logger.exception("Missing required data in banner dismissal request")
        return JsonResponse(
            {"success": False, "error": "Missing required data"}, status=400
        )
    except Exception:
        # Log unexpected exceptions for debugging purposes
        logger.exception("Unexpected error during banner dismissal")
        return JsonResponse(
            {"success": False, "error": "An unexpected error occurred"}, status=500
        )


def track_banner_click(request, id):
    """
    Track a banner CTA click and redirect to the target URL.

    **URL Parameters**

    ``id`` (str)
        The ID of the banner that was clicked.

    **Returns**

    Redirects to the banner's CTA URL or to the home page if the banner is not found.
    """
    banner = get_object_or_404(Banner, id=id, is_live=True)

    # Log the banner click event
    log_event(
        user=request.user if request.user.is_authenticated else None,
        noun=EventNoun.BANNER,
        verb=EventVerb.CLICK,
        object=banner,
        request=request,
        banner_id=str(banner.id),
        banner_text=banner.text,
        cta_text=banner.cta_text,
        cta_url=banner.cta_url,
    )

    # Redirect to the CTA URL if available, otherwise to home
    if banner.cta_url:
        return redirect(banner.cta_url)
    else:
        return redirect("core:index")
