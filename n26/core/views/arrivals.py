"""Show authored interstitials for slots introduced by a completed operation.

The URL carries slot addresses and a validated next destination. Resolve slots
again on each request; missing slots are omitted and an empty screen redirects
onwards. Questions use the same settlement functions as the dedicated picker.

Continue saves answered single-pick questions together. Multi-pick controls
settle one change and remain on this screen. Newly introduced interstitials
are added to the next destination. Skippable blocks do not require answers;
leaving through navigation remains available.
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
    """Deduplicate requested slot addresses in order and cap them at MAX_ASKS."""
    seen = []
    for key in query.getlist("ask"):
        if key and key not in seen:
            seen.append(key)
    return seen[:MAX_ASKS]


def _question(request, gang, key, found, *, here, include_staged, under=""):
    """Build one arriving choice and its roll link for the containing block.

    Treat minimum picks met or an empty offer as settled.
    """
    from n26.core.render import ArrivalQuestion, build_choice_offer

    slot = found.slot
    offer = build_choice_offer(slot, found.computed, include_staged=include_staged)
    roll_href = ""
    if slot.slot is not None and slot.slot.picklist.dice and not slot.is_full:
        # Use the dedicated picker for rolls and return here after selection.
        roll_href = with_query(
            reverse("n26-choose", args=[gang.pk, key]), **{"return": here}
        )
    return ArrivalQuestion(
        key=key,
        label=slot.kind_label,
        bearer=found.miniature.name if found.miniature is not None else gang.name,
        chosen=slot.chosen_name,
        # Continue requires minimum picks unless the offer is empty.
        # Keep empty choices non-blocking while the card can still show its shortfall note.
        settled=len(slot.picks) >= slot.min_picks or offer.is_empty,
        offer=offer,
        roll_href=roll_href,
        under=under,
    )


@login_required
def gang_next(request, pk):
    """Render current arrival screens or settle submitted choices through shared picker functions.

    Discard vanished slots and submissions for questions absent from the screen.
    GET writes nothing.
    """
    from n26.core.render import ArrivalBlock, ArrivalScreen, is_tier_ladder

    gang = _own_gang_or_404(request, pk)
    shown = sees_staged(request.user)
    back = own_address(request, request.GET.get("next", "")) or reverse(
        "n26-gang", args=[gang.pk]
    )

    asks = _asks(request.GET)
    # Resolve all requested slots in one gang-card derivation, dropping vanished slots,
    # modifier offers and slots with no displayed picks.
    located = {
        key: found
        for key, found in find_slots(gang, asks).items()
        if found.slot.slot is not None
        and found.slot.max_picks > 0
        and not is_tier_ladder(found.slot)
    }
    located = {key: located[key] for key in asks if key in located}

    carrying = interstitials_on(
        {found.slot.slot.pk for found in located.values()}, include_staged=shown
    )
    # Order questions by attachment position, then slot name, then URL order.
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
    # Keep only questions attached to a displayed interstitial in both URL and POST scope.
    screened = {key for _interstitial, keys in grouped.values() for key in keys}
    located = {key: found for key, found in located.items() if key in screened}
    here = next_url(gang, list(located), back)

    if request.method == "POST":

        def brought_by(op):
            """Find newly written slots requiring interstitials, excluding those already displayed."""
            if op is None:
                return []
            return [
                more
                for more in asking(gang, op.written, include_staged=shown)
                if more not in located
            ]

        def stay(op):
            """Reopen this screen with any slots introduced by an individual pick."""
            return next_url(gang, [*located, *brought_by(op)], back)

        def leave(op):
            """Continue to newly introduced interstitials, otherwise to the original destination."""
            brought = brought_by(op)
            return next_url(gang, brought, back) if brought else back

        # Question-specific field names identify which slot a control updates.
        drawn = {
            key: _question(request, gang, key, found, here=here, include_staged=shown)
            for key, found in located.items()
        }
        # Reject submitted questions no longer displayed instead of silently dropping the write.
        named = {
            field.split(":", 1)[1]
            for field in request.POST
            if field.startswith(("thing:", "remove:"))
        }
        if named - set(drawn):
            messages.error(request, "That choice is no longer on this screen.")
            return redirect(here)

        # Multi-pick and removal controls settle one question without submitting the rest.
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

        # Settle answered single-pick questions together; blank controls do not clear existing picks.
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
                        # A slot displayed under two interstitials needs distinct heading identifiers.
                        under=str(order),
                    )
                    for key in keys
                ),
                # Skippable blocks never block Continue; entirely skippable screens also offer Skip.
                skippable=interstitial.skippable,
            )
        )
    screen = ArrivalScreen(blocks=tuple(blocks), next_url=back)
    return render(
        request,
        "n26/next.html",
        {"gang": gang, "screen": screen, "here": here},
    )
