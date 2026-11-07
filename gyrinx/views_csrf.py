"""The CSRF failure view, wired up via ``settings.CSRF_FAILURE_VIEW``."""

from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from gyrinx.http import safe_redirect
from gyrinx.security_events import record_security_event


@csrf_exempt
def csrf_failure(request, reason=""):
    """Return a JSON 403 for commands; redirect native forms with a message."""
    # Django's reason can include attacker-controlled details; log a fixed code.
    status = 403 if request.headers.get("Accept") == "application/json" else 302
    record_security_event(
        request, "csrf", "token_or_origin_rejected", response_status=status
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

    # The fallback is shared by both editions.
    return safe_redirect(request, referer)
