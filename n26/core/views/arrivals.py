"""The screen shown after an act, for what the act brought.

Founding a gang, hiring a model or making a pick can put a slot on a
card, and an author may have attached a screen to that slot — a heading
and a few words on why the choice matters. When one does, the act sends
the reader here before wherever it was going, with every such slot
named in the address::

    /gangs/<gang>/next/?ask=<card:carrier:offer>&ask=…&next=<back>

Nothing is stored. Each question is located again from its address
(``find_slot``), so one that has since gone stops being asked rather
than failing the whole screen; the screens attached to what remains are
read from the library; and a screen with nothing left to say sends the
reader on to ``next``. The picker draws in place and posts back here,
through the same handling the pick screen uses, so a pick made on
either is one code path.

Skip is a link to this screen with that block's questions dropped from
the address. Continue is offered once every question still on the
screen holds a pick — leaving by the navigation is always open, and
nothing is policed.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from n26.core.arrivals import MAX_ASKS, asking, interstitials_on, next_url
from n26.core.owned import with_query
from n26.core.views.choose import find_slots, settle_pick
from n26.core.views.permissions import _own_gang_or_404, own_address
from n26.library.staged import sees_staged


def _asks(query):
    """The addresses the screen was asked about, each once, in order.
    Capped where the address was typed rather than built: ``next_url``
    never names more than a screenful."""
    seen = []
    for key in query.getlist("ask"):
        if key and key not in seen:
            seen.append(key)
    return seen[:MAX_ASKS]


def _question(request, gang, key, found, *, here, include_staged):
    """One arriving slot as the screen draws it."""
    from n26.core.render import ArrivalQuestion, build_choice_offer

    slot = found.slot
    offer = build_choice_offer(slot, found.computed, include_staged=include_staged)
    roll_href = ""
    if slot.slot is not None and slot.slot.picklist.dice and not slot.is_full:
        # Rolling lives on the pick screen, which offers it only while the
        # choice will take another pick; the link brings the reader back
        # here once the roll is made and the pick taken.
        roll_href = with_query(
            reverse("n26-choose", args=[gang.pk, key]), **{"return": here}
        )
    return ArrivalQuestion(
        key=key,
        label=slot.kind_label,
        bearer=found.miniature.name if found.miniature is not None else gang.name,
        chosen=slot.chosen_name,
        # Nothing to offer is settled too: a screen that withheld Continue
        # over a choice nobody can make would be policing, and the card's
        # own note still says the choice is open.
        settled=slot.is_resolved or slot.min_picks == 0 or offer.is_empty,
        offer=offer,
        roll_href=roll_href,
    )


@login_required
def gang_next(request, pk):
    """What just arrived, and the choices it brought.

    GET writes nothing. POST is one picker's click, handed to the pick
    screen's own handling, and comes back here with whatever the pick
    itself brought added to the address.
    """
    from n26.core.render import ArrivalBlock, ArrivalScreen

    gang = _own_gang_or_404(request, pk)
    shown = sees_staged(request.user)
    back = own_address(request, request.GET.get("next", "")) or reverse(
        "n26-gang", args=[gang.pk]
    )

    asks = _asks(request.GET)
    # One derivation of the gang for every address at once. A carrier
    # that has gone since the address was made is simply not found, and
    # what remains is still worth asking about. An offer rather than a
    # slot carries no screen, and a slot taking no picks has nothing to
    # draw.
    located = {
        key: found
        for key, found in find_slots(gang, asks).items()
        if found.slot.slot is not None and found.slot.max_picks > 0
    }
    located = {key: located[key] for key in asks if key in located}

    carrying = interstitials_on(
        {found.slot.slot.pk for found in located.values()}, include_staged=shown
    )
    # Each screen's questions in the order the author gave its slots,
    # then in address order for slots given the same place.
    grouped = {}
    for order, (key, found) in enumerate(located.items()):
        for attachment in carrying.get(found.slot.slot.pk, ()):
            interstitial = attachment.interstitial
            grouped.setdefault(interstitial.pk, (interstitial, []))[1].append(
                (attachment.position, order, key)
            )
    grouped = {
        pk: (interstitial, [key for _, _, key in sorted(placed)])
        for pk, (interstitial, placed) in grouped.items()
    }
    if not grouped:
        return redirect(back)
    # Only a question some screen draws is on this page: the address
    # self-cleans of the rest, and a post naming one settles nothing here.
    screened = {key for _interstitial, keys in grouped.values() for key in keys}
    located = {key: found for key, found in located.items() if key in screened}
    here = next_url(gang, list(located), back)

    if request.method == "POST":
        key = request.POST.get("ask", "")
        found = located.get(key)
        if found is None:
            messages.error(request, "That choice is no longer on this screen.")
            return redirect(here)
        question = _question(request, gang, key, found, here=here, include_staged=shown)

        def land(op):
            # What the pick itself brought joins the screen, after what
            # was already on it.
            brought = [
                more
                for more in asking(gang, op.written, include_staged=shown)
                if more not in located
            ]
            return next_url(gang, [*located, *brought], back)

        return settle_pick(
            request, gang, key, found, question.offer, here=here, land=land
        )

    # How many blocks ask each question: Skip on one block drops only
    # the questions no other block still asks, so a slot under two
    # screens is not waved through by skipping the one that allows it.
    asked_by = {}
    for _interstitial, keys in grouped.values():
        for key in keys:
            asked_by[key] = asked_by.get(key, 0) + 1
    blocks = []
    for interstitial, keys in sorted(
        grouped.values(),
        key=lambda pair: (pair[0].position, pair[0].name.lower()),
    ):
        blocks.append(
            ArrivalBlock(
                heading=interstitial.heading,
                description=interstitial.description,
                questions=tuple(
                    _question(
                        request,
                        gang,
                        key,
                        located[key],
                        here=here,
                        include_staged=shown,
                    )
                    for key in keys
                ),
                # Skip drops the block's own questions — the ones no other
                # block asks. A block with none of its own has nothing to
                # drop, so it draws no Skip rather than a link to here.
                skip_url=next_url(
                    gang,
                    [k for k in located if k not in keys or asked_by[k] > 1],
                    back,
                )
                if interstitial.skippable and any(asked_by[k] == 1 for k in keys)
                else "",
            )
        )
    screen = ArrivalScreen(blocks=tuple(blocks), next_url=back)
    return render(
        request,
        "n26/next.html",
        {"gang": gang, "screen": screen, "here": here},
    )
