"""Making a choice a modifier offered.

A slot is computed — it exists while its carrier does, and only what was
chosen is ever stored — so there is nothing to open until a reader
clicks Choose. Choose leads here: the slot's question, and what this
gang or this fighter may choose for it.

The whole flow is one page because the difference between a skill, an
archetype and an affiliation is data. The offer itself says what may be
chosen (``n26.core.browse.offered_by``) and the pick screen is built
from that list (``n26.core.render.build_choice_offer``), so nothing
here asks what kind of thing is being chosen.

The address holds the slot::

    /gangs/<gang>/choose/<card>:<carrier>:<offer>/

``card`` is the model whose card was clicked, or ``gang`` for the gang's
own card; ``carrier`` is the assignment offering the choice; ``offer`` is
which of its offers. Everything the page needs is in the URL, so it is a
link, it survives a reload, and it works with scripting off.
"""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from n26.core.views.permissions import _own_gang_or_404


@dataclass(frozen=True)
class _Found:
    """One slot, located: the computed slot, the card it sits on, and the
    stored assignment carrying the offer."""

    slot: object
    computed: object
    anchor: object
    #: The model whose card the slot was drawn on, or None for the gang's.
    miniature: object = None


def link_slots(gang, *holders):
    """Point every choice slot on these structures at its picker.

    Costs no queries: a slot's address is already on the line, and this
    only turns it into a URL. A slot with no address keeps an empty href
    and draws as a fact with nothing to click — which is right for a card
    depicting nobody.

    A card files some of its questions into rows of their own — the ones
    drawn beside the skills and the powers the model already has — so what
    is asked for here is the holder's whole run of questions rather than
    each list by name. Where a question is drawn is the holder's business;
    every one of them is chosen for at the same address, and a holder that
    grows another row is linked by the same line.
    """
    for holder in holders:
        for line in holder.questions:
            if line.key:
                line.href = reverse("n26-choose", args=[gang.pk, line.key])


def _find_slot(gang, key):
    """The slot an address names, on the card it was drawn on.

    Rebuilt rather than remembered: a slot is computed, so the honest
    answer to "does this slot still exist" is to compute the card again
    and look. A carrier that has since been removed takes its slot with
    it, and the address stops resolving — a 404, because the question no
    longer exists rather than because the reader may not ask it.
    """
    from n26.core.card import build_card, build_gang_card, build_modifier_index
    from n26.core.effects import compute, compute_gang
    from n26.core.models import Miniature
    from n26.core.render import GANG_SLOT_HOST

    where, _, rest = key.partition(":")
    anchor_pk, _, offer_pk = rest.partition(":")
    if not (where and anchor_pk and offer_pk):
        raise Http404("No such choice")

    miniature = None
    if where == GANG_SLOT_HOST:
        card = build_gang_card(gang)
    else:
        try:
            miniature = get_object_or_404(
                Miniature,
                pk=where,
                membership__gang=gang,
                membership__archived=False,
            )
        except ValidationError:
            # A pk that is not a ULID at all is only ever a bad link.
            raise Http404("No such fighter") from None
        card = build_card(miniature)

    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    computed = compute_gang(card, index) if miniature is None else compute(card, index)

    for slot in computed.choices:
        anchor = getattr(slot.anchor, "assignment", None)
        if anchor is None or slot.identity is None:
            continue
        if str(anchor.pk) == anchor_pk and str(slot.identity.pk) == offer_pk:
            return _Found(
                slot=slot, computed=computed, anchor=anchor, miniature=miniature
            )
    raise Http404("No such choice")


def _host(found):
    """Whose choice this is, when the carrier cannot say.

    A carrier held by the gang and echoed onto a member's card offers the
    slot to that member — "Leaders and Champions each select a skill" —
    and the assignment it echoed from belongs to nobody in particular, so what
    is chosen has to name the fighter whose card was clicked. Every other
    slot lets the offer decide: a fighter's own carrier lands on the
    fighter, and an offer that says the gang holds what is chosen still
    does.
    """
    if found.miniature is not None and found.slot.anchor.broadcast:
        return {"miniature": found.miniature}
    return {}


@login_required
def choose(request, pk, slot):
    """The pick screen for one slot, and the click that settles it.

    GET asks and writes nothing. POST names one thing from the list the
    server has just re-derived — never a price and never a free-text
    identity — and writes what was chosen as an assignment caused by the
    carrier's, so removing the carrier takes it with it.

    A choice that holds one pick is settled in one go: the list is a set
    of radios, clicking again replaces what was chosen, and the reader
    lands back on the gang. One that holds several is worked at instead —
    every option carries its own control, a click adds or takes back one
    pick, and the page comes back so the next one is a click away. It
    stops offering the rest when it is full: the way to something else is
    to take a pick back, never to have one pushed out unasked. A choice
    that holds none offers nothing and writes nothing.

    Nothing here withholds a pick. The list is short because the offer is
    narrow, and leaving the slot open costs nothing — the way back is the
    gang. The operation may still refuse the click: a pick that would
    settle nothing, or a gang with no room in its budget. Either way the
    reader is told and lands back on the list, because a page that drew
    the button owes a reply rather than a traceback.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation
    from n26.core.render import NONE_KEY, build_choice_offer, option_key

    gang = _own_gang_or_404(request, pk)
    found = _find_slot(gang, slot)
    offer = build_choice_offer(found.slot, found.computed)
    back = reverse("n26-gang", args=[gang.pk])

    if request.method == "POST":
        dropped = request.POST.get("remove", "")
        wanted = dropped or request.POST.get("thing", "")
        if wanted == NONE_KEY and not dropped:
            # The None row on an optional choice: nothing is written —
            # the standing pick, if any, is taken back, and the choice
            # reads open again. Only honoured where the page drew the
            # row, so a hand-built post cannot reset a required choice.
            offered_none = any(
                option.key == NONE_KEY
                for group in offer.groups
                for option in group.options
            )
            if not offered_none:
                messages.error(
                    request, "That is not one of the things available to pick."
                )
                return redirect(request.path)
            standing = [
                pick for pick in found.slot.picks if pick.assignment is not None
            ]
            with operation(gang, actor=request.user) as op:
                for pick in standing:
                    op.remove(pick.assignment)
            record(
                request,
                N26Noun.CHOICE,
                EventVerb.ARCHIVE,
                gang,
                offer=offer.label,
                picked="None",
            )
            messages.success(request, f"Chose None — {offer.label}.")
            return redirect(back)
        picked = next(
            (
                option
                for group in offer.groups
                for option in group.options
                if option.key == wanted
            ),
            None,
        )
        held = next(
            (
                pick
                for pick in found.slot.picks
                if option_key(pick.assignable) == wanted and pick.assignment is not None
            ),
            None,
        )
        if picked is None or (dropped and held is None):
            # Nothing on the list, or nothing behind the option a click
            # asked to take back — a stale page either way, and the list
            # itself is the reply.
            messages.error(request, "That is not one of the things available to pick.")
            return redirect(request.path)
        # A worked-at choice comes back to itself; a settled one leaves.
        landing = request.path if offer.takes_several else back
        try:
            with operation(gang, actor=request.user) as op:
                if dropped:
                    op.remove(held.assignment)
                else:
                    if (
                        not offer.takes_several
                        and found.slot.is_full
                        and found.slot.picks
                    ):
                        # One pick, already made: the new pick replaces it.
                        standing = found.slot.picks[0]
                        if standing.assignment is not None:
                            op.remove(standing.assignment)
                    op.choose(
                        found.anchor,
                        picked.thing,
                        slot=found.slot.slot,
                        offer=found.slot.offer,
                        **_host(found),
                    )
        except Refusal as refusal:
            messages.error(request, str(refusal))
            return redirect(request.path)
        # Which choice was made and with what. Changing your mind
        # records a second choice rather than editing the first: what a
        # player picked and then dropped is a thing worth being able to ask
        # about.
        record(
            request,
            N26Noun.CHOICE,
            EventVerb.ARCHIVE if dropped else EventVerb.CONFIRM,
            gang,
            offer=offer.label,
            picked=picked.name,
        )
        said = "Removed" if dropped else "Chose"
        messages.success(request, f"{said} {picked.name} — {offer.label}.")
        return redirect(landing)

    bearer = found.miniature.name if found.miniature is not None else gang.name
    return render(
        request,
        "n26/choose.html",
        {
            "gang": gang,
            "miniature": found.miniature,
            "offer": offer,
            "bearer": bearer,
            "back": back,
            # A choice worked at a pick at a time has no one act to end
            # it: every option carries its own, and a Save at the bottom
            # would be a second way to settle what is already settled.
            "submit_label": "" if offer.takes_several else "Save",
            # Not "lead". A cotton slot is a context variable, and any
            # component on the page with a slot of that name — the site
            # footer's columns have one — draws whatever the page happens
            # to have under it.
            "pick_lead": f"For {bearer}.",
        },
    )
