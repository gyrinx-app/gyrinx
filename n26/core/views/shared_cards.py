"""One fighter's card on a page of its own, for other websites to frame.

The owner's Share control copies an iframe pointing here, so a fighter
can sit on a club's Google Site or blog and stay up to date as the gang
changes. The address needs no secret: a roster is already anyone's to
read, and this page shows no more than the roster does to a reader who
does not own the gang.
"""

from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.clickjacking import xframe_options_exempt

from n26.flags import SHARE_FIGHTER_CARD, switched_on


def _shared_card_or_404(request, pk):
    """The fighter's card as a reader who does not own the gang sees it.

    The whole roster is drawn and this fighter's card taken from it, so
    the card is the roster's card exactly, in the roster's fixed number of
    queries. Archived fighters and gangs are not found, as on the roster.
    """
    from n26.core.models import Miniature
    from n26.core.render import render_gang
    from n26.core.views.permissions import _any_gang_or_404

    try:
        miniature = get_object_or_404(
            Miniature.objects.select_related("membership"),
            pk=pk,
            membership__archived=False,
        )
    except ValidationError:
        raise Http404("No such fighter") from None
    gang = _any_gang_or_404(request, miniature.membership.gang_id)
    # No owner links: a pet's owner is named in words, because the
    # owner's card is not on this page for a link to land on.
    sheet = render_gang(gang)
    card = next(
        (
            card
            for card in (*sheet.models, *sheet.dead)
            if str(card.id) == str(miniature.pk)
        ),
        None,
    )
    if card is None:
        raise Http404("No such fighter")
    return gang, card


@xframe_options_exempt
def shared_fighter_card(request, pk):
    """The card alone: its header and its Card tab, with nothing to click.

    Not ``requires_flag``: that asks about the signed-in reader, and the
    readers of a framed card are rarely signed in to Gyrinx. It asks
    whether the feature is switched on at all instead.
    """
    if not switched_on(SHARE_FIGHTER_CARD):
        raise Http404("Sharing fighter cards is not switched on")
    gang, card = _shared_card_or_404(request, pk)
    theme = request.GET.get("theme", "system")
    if theme not in {"light", "dark", "system"}:
        theme = "system"
    response = render(
        request,
        "n26/shared_fighter_card.html",
        {"gang": gang, "card": card, "share_theme": theme},
    )
    # A short cache keeps a busy page from rebuilding the roster on every
    # view, and still shows a change within the minute.
    response["Cache-Control"] = "public, max-age=60"
    # Any site may frame this page. X-Frame-Options has no value for that,
    # so the exemption above drops it and this header says so instead.
    response["Content-Security-Policy"] = "frame-ancestors *"
    return response
