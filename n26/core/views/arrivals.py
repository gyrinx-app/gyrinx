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

The whole screen is one form and Continue submits it, so every choice
the reader made is written together. Continue is offered once every
compulsory question is settled — it holds every pick it asks for, asks
for none, or has nothing to offer; a question on a block the author
made skippable never holds anybody, and leaving it blank is the way
past it. Where no question is compulsory, Skip sits beside Continue and
goes on without writing anything. Leaving by the navigation is always
open, and nothing is policed.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from n26.core.arrivals import MAX_ASKS, asking, interstitials_on, next_url
from n26.core.owned import with_query
from n26.core.views.choose import find_slots, settle_pick, settle_picks
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


def _question(request, gang, key, found, *, here, include_staged, under=""):
    """One arriving slot as the screen draws it. ``under`` is which block
    draws it, for a page that draws it under several."""
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
        # Settled once it holds every pick it asks for — the count the
        # sheet's own shortfall note reads, so the screen and the card
        # agree on what is outstanding. A choice asking for none is
        # settled from the start. Nothing to offer is settled too: a
        # screen that withheld Continue over a choice nobody can make
        # would be policing, and the card's own note still says the
        # choice is open.
        settled=len(slot.picks) >= slot.min_picks or offer.is_empty,
        offer=offer,
        roll_href=roll_href,
        under=under,
    )


@login_required
def gang_next(request, pk):
    """What just arrived, and the choices it brought.

    GET writes nothing. POST is Continue, which writes every question
    the reader answered in one operation — or one click of a choice
    worked at a pick at a time, handed to the pick screen's own
    handling. Either comes back here with whatever the picks brought
    added to the address.
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
    # Each screen's questions in the order the author gave its slots —
    # position, then the slot's name, as the attachments themselves are
    # ordered — and only then in address order, so permuting the address
    # never reorders a screen.
    grouped = {}
    for order, (key, found) in enumerate(located.items()):
        for attachment in carrying.get(found.slot.slot.pk, ()):
            interstitial = attachment.interstitial
            grouped.setdefault(interstitial.pk, (interstitial, []))[1].append(
                (attachment.position, found.slot.slot.name.lower(), order, key)
            )
    grouped = {
        pk: (interstitial, [key for *_, key in sorted(placed)])
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

        def brought_by(op):
            """What the picks themselves brought that asks for a screen
            of its own — nothing, where the answer wrote nothing."""
            if op is None:
                return []
            return [
                more
                for more in asking(gang, op.written, include_staged=shown)
                if more not in located
            ]

        def stay(op):
            """Back to this screen with what the pick brought added:
            where one click of a choice worked at a pick at a time
            lands, because the rest of the page is still to answer."""
            return next_url(gang, [*located, *brought_by(op)], back)

        def leave(op):
            """Where Continue lands: on to what the act was going to,
            or first to a screen for whatever the answers themselves
            brought — never back to the questions just answered."""
            brought = brought_by(op)
            return next_url(gang, brought, back) if brought else back

        # Each question's controls are named after it, so a click says
        # which one it answered and a page of them cannot be confused
        # for one another.
        drawn = {
            key: _question(request, gang, key, found, here=here, include_staged=shown)
            for key, found in located.items()
        }
        # A post naming a question no screen here draws is a stale page
        # or a hand-built post; the screen says so rather than quietly
        # writing nothing.
        named = {
            field.split(":", 1)[1]
            for field in request.POST
            if field.startswith(("thing:", "remove:"))
        }
        if named - set(drawn):
            messages.error(request, "That choice is no longer on this screen.")
            return redirect(here)

        # A choice worked at a pick at a time acts on its own, the way it
        # does on the pick screen: one click is one pick, and the rest of
        # the page is left as it stands.
        for key, question in drawn.items():
            dropped = request.POST.get(question.remove_name, "")
            wanted = dropped or request.POST.get(question.field_name, "")
            if wanted and (dropped or question.offer.takes_several):
                return settle_pick(
                    request,
                    gang,
                    key,
                    located[key],
                    question.offer,
                    here=here,
                    land=stay,
                    wanted=wanted,
                    dropped=dropped,
                )

        # Continue: every question the reader answered, written together.
        # A blank one is left out rather than settled as nothing, so
        # Continue on an untouched screen writes nothing at all.
        answers = [
            (key, located[key], question.offer, request.POST[question.field_name])
            for key, question in drawn.items()
            if not question.offer.takes_several
            and not question.offer.is_empty
            and request.POST.get(question.field_name)
        ]
        return settle_picks(request, gang, answers, here=here, land=leave)

    blocks = []
    ordered = sorted(
        grouped.values(), key=lambda pair: (pair[0].position, pair[0].name.lower())
    )
    for order, (interstitial, keys) in enumerate(ordered, 1):
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
                        # A slot under two screens is asked under each,
                        # and the two drawings need headings of their own.
                        under=str(order),
                    )
                    for key in keys
                ),
                # What the author said: a block nobody has to answer
                # never holds Continue, and a screen of nothing but
                # those offers Skip beside it.
                skippable=interstitial.skippable,
            )
        )
    screen = ArrivalScreen(blocks=tuple(blocks), next_url=back)
    return render(
        request,
        "n26/next.html",
        {"gang": gang, "screen": screen, "here": here},
    )
