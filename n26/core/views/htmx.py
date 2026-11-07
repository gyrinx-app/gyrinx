"""Return partial view updates and queued messages for htmx requests.

Servers select updated elements through matching IDs and ``hx-swap-oob``.
Only pages containing every required update host may enable these controls;
htmx silently discards updates targeting absent elements.

Deliver messages as one ``n26-toasts`` event in ``HX-Trigger``.
``no_update`` returns 204 with those messages, preserving live editors.
Ordinary submissions use full-page responses or redirects.

Use ``HX-Replace-Url`` when changing panel state so reloads reproduce it.
Use ``HX-Redirect`` for full navigation from a partial request.
"""

import json

from django.contrib.messages import get_messages
from django.http import HttpResponse
from django.shortcuts import redirect, resolve_url

#: Normal toasts expire after this duration; errors remain until dismissed.
TOAST_DURATION = 4000


def is_htmx(request):
    """Require HX-Request to equal true, ignoring case; header presence alone is insufficient."""
    return request.headers.get("HX-Request", "").lower() == "true"


def with_toasts(request, response):
    """Consume queued messages and attach them as one n26-toasts HX-Trigger event."""
    toasts = [
        {
            "variant": message.level_tag if message.level_tag else "info",
            "message": str(message),
            "duration": 0 if message.level_tag == "error" else TOAST_DURATION,
        }
        for message in get_messages(request)
    ]
    if toasts:
        response["HX-Trigger"] = json.dumps({"n26-toasts": toasts})
    return response


def no_update(request):
    """Return 204 with queued toast messages and preserve the current page DOM."""
    return with_toasts(request, HttpResponse(status=204))


def stay_or_redirect(request, to):
    """Preserve htmx pages with a toast-only response, otherwise redirect.

    Notes and lore editors use this to keep unsaved content in the other editor.
    """
    if is_htmx(request):
        return no_update(request)
    return redirect(to)


def redirect_page(request, to, *args, **kwargs):
    """Navigate the full page using HX-Redirect for htmx or an ordinary redirect.

    An ordinary redirect inside XMLHttpRequest could insert a whole page into
    the partial target.
    """
    to = resolve_url(to, *args, **kwargs)
    if not is_htmx(request):
        return redirect(to)
    response = HttpResponse(status=204)
    response["HX-Redirect"] = to
    return response
