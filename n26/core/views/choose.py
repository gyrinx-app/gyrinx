"""Making a choice a modifier offered.

A slot is computed — it exists while its carrier does, and only what was
chosen is ever stored — so there is nothing to open until a reader
clicks Choose. Choose leads here: the slot's question, and what this
gang or this fighter may choose for it.

The whole flow is one page because the difference between a skill, an
pick and an affiliation is data. The offer itself says what may be
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

from dataclasses import dataclass, replace

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
    from n26.core.card import (
        build_card,
        build_gang_card,
        build_modifier_index,
        carriers,
    )
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

    index = build_modifier_index(carriers(card))
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


def _settled(found):
    """The picks that answer this question, as the card reads them.

    The card is the one authority on what answers what: it scopes a
    question broadcast onto many cards to the one whose card was
    clicked, and it adopts an answer that names no question — or names
    one this card no longer asks — rather than leaving it stranded. A
    query written here would have to repeat all of that and would drift
    from it, so the card is asked instead.
    """
    return [pick for pick in found.slot.picks if pick.assignment is not None]


def _pick_of(found, wanted):
    """The pick behind one option on the list, or None if it is not there."""
    from n26.core.render import option_key

    return next(
        (pick for pick in _settled(found) if option_key(pick.assignable) == wanted),
        None,
    )


def _roll_table(found):
    """The die behind this choice, where its list names one — or None,
    which draws no roll controls at all."""
    from n26.core.render import RollTable
    from n26.library.models import Dice

    slot = found.slot.slot
    if slot is None or not slot.picklist.dice:
        return None
    dice = Dice(slot.picklist.dice)
    rolls = Dice.rolls(dice)
    return RollTable(dice_label=dice.label, lowest=rolls[0], highest=rolls[-1])


def _roll_at(key, gang, found, select_related=()):
    """The roll a key names, or None for no key — a 404 for a key that
    names no roll made for this very choice on this very card.

    Scoped to the gang, the slot and the model whose card was clicked
    (or to no model, for the gang's own choice). One Slot row serves
    every fighter of the gang, so the slot alone would let a roll made
    for one fighter be drawn on, and spent from, another's page.
    """
    from n26.core.models import LedgerEvent

    if not key or found.slot.slot is None:
        return None
    try:
        return get_object_or_404(
            LedgerEvent.objects.select_related(*select_related),
            pk=key,
            gang=gang,
            kind=LedgerEvent.Kind.ROLLED,
            slot=found.slot.slot,
            miniature=found.miniature,
        )
    except ValidationError:
        raise Http404("No such roll") from None


def _roll_named(request, gang, found):
    """The roll the page was opened on, or None when it was opened plain.

    The pick that spent the roll, where one has, comes back on the event
    so the page can say so and stop offering it.
    """
    return _roll_at(request.GET.get("roll", ""), gang, found, ("pick",))


def _roll_posted(request, gang, found):
    """The roll a pick says it came from, or None for a pick made plain."""
    return _roll_at(request.POST.get("roll", ""), gang, found)


def _roll_result(event, found, offer):
    """One roll, as the page draws it, and the keys of the rows it reached."""
    from n26.core.render import RollResult, option_key
    from n26.library.models import Dice, RollSelects

    picklist = found.slot.slot.picklist
    members = picklist.members.select_related("pickable")
    landed = picklist.landing(event.roll, members)
    keys = {option_key(member.pickable) for member in landed}
    named = {
        option.key: option.name for group in offer.groups for option in group.options
    }
    spent = getattr(event, "pick", None)
    # The die as the record holds it; a die the library no longer names
    # reads as the table's, since the figure is what the page is about.
    try:
        dice = Dice(event.dice) if event.dice else Dice(picklist.dice)
    except ValueError:
        dice = Dice(picklist.dice)
    result = RollResult(
        key=str(event.pk),
        total=event.roll,
        dice_label=dice.label,
        faces=Dice.faces(dice, event.roll),
        landed=tuple(named.get(option_key(m.pickable), m.label) for m in landed),
        entered=bool(event.note),
        applied=str(spent.assignable) if spent is not None else "",
        threshold=picklist.roll_selects == RollSelects.THRESHOLD,
    )
    return result, keys


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

    A choice whose list is a roll table is rolled for here too. A Roll
    click writes the roll to the gang's history and comes back at
    ``?roll=<event>``, which draws that roll and lifts the rows it landed
    on; a pick posted from there names the roll, and a roll is applied
    once. The roll is on the record from the moment it is made, whether
    or not anything is ever picked for it — which is what makes a second
    roll visible to whoever reads the history.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation
    from n26.core.render import NONE_KEY, build_choice_offer

    gang = _own_gang_or_404(request, pk)
    found = _find_slot(gang, slot)
    offer = build_choice_offer(found.slot, found.computed)
    back = reverse("n26-gang", args=[gang.pk])
    here = reverse("n26-choose", args=[gang.pk, slot])

    if request.method == "POST" and request.POST.get("act") in {"roll", "enter"}:
        # Rolling writes before anything is picked: the roll is on the
        # record from this moment, and the page comes back at it. A roll
        # made at the table and entered here goes the same way, with the
        # record saying it was entered.
        if _roll_table(found) is None:
            raise Http404("Nothing to roll here")
        rolled = None
        if request.POST["act"] == "enter":
            try:
                rolled = int(request.POST.get("rolled", ""))
            except ValueError:
                messages.error(request, "Enter the number you rolled.")
                return redirect(here)
        try:
            with operation(gang, actor=request.user) as op:
                fresh = _find_slot(gang, slot)
                event = op.roll(
                    fresh.slot.slot, miniature=fresh.miniature, rolled=rolled
                )
        except Refusal as refusal:
            messages.error(request, str(refusal))
            return redirect(here)
        record(
            request,
            N26Noun.CHOICE,
            EventVerb.UPDATE,
            gang,
            offer=offer.label,
            action="roll",
            entered=rolled is not None,
        )
        return redirect(f"{here}?roll={event.pk}")

    if request.method == "POST":
        dropped = request.POST.get("remove", "")
        wanted = dropped or request.POST.get("thing", "")
        rolled_on = _roll_posted(request, gang, found)
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
                return redirect(here)
            with operation(gang, actor=request.user) as op:
                for pick in _settled(_find_slot(gang, slot)):
                    op.remove(pick.assignment)
            record(
                request,
                N26Noun.CHOICE,
                EventVerb.ARCHIVE,
                gang,
                offer=offer.label,
                picked="None",
            )
            messages.success(request, f"Chose none — {offer.label}.")
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
        if picked is None or (dropped and _pick_of(found, wanted) is None):
            # Nothing on the list, or nothing behind the option a click
            # asked to take back — a stale page either way, and the list
            # itself is the reply.
            messages.error(request, "That is not one of the things available to pick.")
            return redirect(here)
        # A worked-at choice comes back to itself; a settled one leaves.
        landing = here if offer.takes_several else back
        try:
            with operation(gang, actor=request.user) as op:
                # The page named the picks it drew, but it was drawn
                # before this answer and before any other in flight. The
                # card is computed again with the gang held, so what
                # settles the question is what stands at the moment of
                # writing — and a question that has since gone stops
                # resolving here rather than growing an answer nobody
                # asked for.
                fresh = _find_slot(gang, slot)
                if dropped:
                    taken = _pick_of(fresh, wanted)
                    if taken is not None:
                        op.remove(taken.assignment)
                elif (
                    offer.takes_several
                    and _pick_of(fresh, wanted) is not None
                    and not (
                        fresh.slot.slot is not None
                        and fresh.slot.slot.slot_type.allows_repeats
                    )
                ):
                    # A worked-at choice, and this pick is already among
                    # them: the click has landed once already, and once is
                    # what it asked for. Where the slot type allows
                    # repeats a second click is a second pick, and falls
                    # through to be written like any other.
                    pass
                else:
                    if not offer.takes_several:
                        # One pick, already made: the new pick replaces it.
                        for standing in _settled(fresh):
                            op.remove(standing.assignment)
                    elif fresh.slot.is_full:
                        # Filled while this page stood open. The way to
                        # something else is to take a pick back, never to
                        # have one pushed out unasked.
                        raise Refusal(
                            f"{offer.label} holds all the picks it will "
                            "take. Take one back to make room."
                        )
                    op.choose(
                        fresh.anchor,
                        picked.thing,
                        slot=fresh.slot.slot,
                        offer=fresh.slot.offer,
                        roll=rolled_on,
                        **_host(fresh),
                    )
        except Refusal as refusal:
            messages.error(request, str(refusal))
            return redirect(here)
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
        # The confirmation says what happened in the choice's own terms: a
        # several-pick choice has picks added to it, a choice of one is
        # chosen — whatever the button that sent it was called.
        if dropped:
            said = "Removed"
        elif offer.takes_several:
            said = "Added"
        else:
            said = "Chose"
        messages.success(request, f"{said} {picked.name} — {offer.label}.")
        return redirect(landing)

    from n26.core.render import lift_landing

    roll = None
    roll_table = _roll_table(found)
    event = _roll_named(request, gang, found)
    if event is not None:
        roll, landed = _roll_result(event, found, offer)
        addable = [
            option
            for group in offer.groups
            for option in group.options
            if option.key in landed and option.control in {"choose", "both", ""}
        ]
        if not roll.is_spent and len(addable) == 1 and len(landed) == 1:
            # One result, still open: the panel carries the Add, and the
            # list below stays the whole table, unlifted.
            roll = replace(roll, add=addable[0])
        elif not roll.is_spent:
            offer = lift_landing(offer, landed, threshold=roll.threshold)

    bearer = found.miniature.name if found.miniature is not None else gang.name
    return render(
        request,
        "n26/choose.html",
        {
            "gang": gang,
            "miniature": found.miniature,
            "offer": offer,
            # The die behind the choice, drawn as Roll controls — or, when
            # the page was opened on a roll, that roll in their place.
            "roll_table": roll_table if roll is None or roll.is_spent else None,
            "roll": roll,
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
