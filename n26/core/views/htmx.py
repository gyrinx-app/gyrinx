"""Shared helpers for views that respond to htmx with partial updates.

The pattern, end to end:

- A control that changes what the gang holds is an ordinary link or form.
  When htmx submits it (the request carries ``HX-Request: true``), the view
  responds with only the elements the act changed instead of a full page;
  without JavaScript the same control gets the whole page, so nothing works
  only one way.
- The response targets nothing from the control's side. Each element in it
  carries ``hx-swap-oob`` and the id of the element on the page it replaces,
  so which parts of the page an act updates is decided by the server and can
  grow without any call site changing.
- Only a page that contains every id such a response uses may opt in: htmx
  drops an out-of-band element whose id is missing, silently, so on any other
  page the act would run and nothing on screen would change. Opting in means
  rendering the shared host elements and passing ``:htmx="True"`` to the
  controls — see ``n26/includes/equip_hosts.html``.
- Queued messages cannot be drawn into a page that is not re-rendered, so
  :func:`with_toasts` drains them into the ``HX-Trigger`` response header as
  one ``n26-toasts`` event; the client shows them as toasts
  (``n26/core/static/n26/htmx_support.js``). A response that changes nothing
  on the page is :func:`no_update` — a 204 carrying only that header. That is
  also the answer when the page must keep a live editor: swapping the box
  out would rebuild TinyMCE and throw away whatever is typed in the other
  one. :func:`stay_or_redirect` is that 204, or a redirect without htmx.
- The URL stays the authority on UI state. A response that opens or closes a
  panel sets ``HX-Replace-Url`` to the address that renders that state, so a
  reload draws the same screen and links keep working.

The equip screens were the pattern's first use — ``n26.core.views.equip``
builds their update responses; notes and lore saves use :func:`no_update`
so the editors stay. This module holds only the parts any screen would need.
"""

import json

from django.contrib.messages import get_messages
from django.http import HttpResponse
from django.shortcuts import redirect

#: How long a toast stays before it dismisses itself. An error toast is
#: given no timeout at all: the reason a click did nothing is worth more
#: than the corner it is written in, and four seconds is long enough to
#: miss it entirely.
TOAST_DURATION = 4000


def is_htmx(request):
    """Whether htmx sent this request (``HX-Request: true``).

    Compared against the value rather than tested for presence, so a
    proxy or client setting the header to ``false`` is not mistaken for
    htmx and handed a partial response it cannot apply.
    """
    return request.headers.get("HX-Request", "").lower() == "true"


def with_toasts(request, response):
    """The same response, with any queued messages attached as toasts.

    The messages ride the ``HX-Trigger`` header as one ``n26-toasts``
    event holding the whole list. Reading the message storage is what
    empties it — these messages are delivered here, not deferred to the
    next full page.
    """
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
    """A response that changes nothing on the page.

    204, plus any queued messages as toasts — the one channel a refusal
    still has into a page that is not re-rendered, and the answer a
    successful save uses when the page must keep a live editor.
    """
    return with_toasts(request, HttpResponse(status=204))


def stay_or_redirect(request, to):
    """Finish an act: leave the page as drawn, or go ``to`` without htmx.

    The notes and lore boxes keep a live TinyMCE editor. Rebuilding the
    page would throw away whatever is typed in the other box, so a save
    that htmx sent answers with :func:`no_update` — the confirmation is
    a toast, the editors stay. Without JavaScript the same act is a
    redirect, as every other form on the site is.
    """
    if is_htmx(request):
        return no_update(request)
    return redirect(to)
