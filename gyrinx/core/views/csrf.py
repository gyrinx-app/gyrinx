from django.contrib import messages
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.utils import safe_redirect


@csrf_exempt
def csrf_failure(request, reason=""):
    """
    Custom view to handle CSRF failures by redirecting back to the form
    with an error message instead of showing a 403 page.
    """
    # Log the CSRF failure
    if hasattr(request, "user") and request.user.is_authenticated:
        log_event(
            user=request.user,
            noun=EventNoun.USER,
            verb=EventVerb.VIEW,
            request=request,
            page="csrf_failure",
            csrf_reason=reason,
        )

    # Add a user-friendly error message
    messages.error(
        request,
        "Your session has expired. Please try again. The form has been refreshed with a new security token.",
    )

    # Get the referer URL to redirect back to the form
    referer = request.META.get("HTTP_REFERER")

    # Use safe redirect with home page as fallback
    return safe_redirect(request, referer, fallback_url=reverse("core:index"))
