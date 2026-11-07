"""The CSRF failure view, wired up via ``settings.CSRF_FAILURE_VIEW``."""

from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from gyrinx.analytics.models import EventVerb, log_event
from gyrinx.analytics.nouns import PlatformNoun
from gyrinx.http import safe_redirect


@csrf_exempt
def csrf_failure(request, reason=""):
    """Return a JSON 403 for commands; redirect native forms with a message."""
    if hasattr(request, "user") and request.user.is_authenticated:
        log_event(
            user=request.user,
            noun=PlatformNoun.USER,
            verb=EventVerb.VIEW,
            request=request,
            page="csrf_failure",
            csrf_reason=reason,
        )

    if request.headers.get("Accept") == "application/json":
        return JsonResponse(
            {
                "error": "Your session could not be verified. Reload the page before saving."
            },
            status=403,
        )

    messages.error(
        request,
        "Your session has expired. Please try again. The form has been refreshed with a new security token.",
    )

    referer = request.META.get("HTTP_REFERER")

    # Keep the fallback at the shared site root instead of an edition-specific route.
    return safe_redirect(request, referer)
