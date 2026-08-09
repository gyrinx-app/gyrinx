"""The CSRF failure view, wired up via ``settings.CSRF_FAILURE_VIEW``."""

from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt

from gyrinx.analytics.models import EventVerb, log_event
from gyrinx.analytics.nouns import PlatformNoun
from gyrinx.http import safe_redirect


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
            noun=PlatformNoun.USER,
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

    # Falls back to safe_redirect's default of "/" — the site root, which is what
    # the edition's index used to resolve to anyway. A platform view should not
    # reverse an edition URL name to find somewhere to send people.
    return safe_redirect(request, referer)
