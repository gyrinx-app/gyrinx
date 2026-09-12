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
from django.views.decorators.http import require_POST

from n26.core.owned import with_query
from n26.core.views.permissions import _own_gang_or_404, _safe_redirect
from n26.library.staged import sees_staged

#: The query that asks a screen to draw the offers the owner has dismissed,
#: each with a way to bring it back. In the address, so the screen is a
#: link and a reload draws it again.
SHOW_DISMISSED = "dismissed"
SHOWING = "show"


def showing_dismissed(url):
    """Whether an address asks for the dismissed offers to be drawn.

    Asked of a URL rather than a request, because the address a card is
    redrawn under after an act arrives in the act's form, not on the
    request that redraws it.
    """
    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(url).query)
    return SHOWING in query.get(SHOW_DISMISSED, [])


def settle_dismissed(gang, *holders, at="", showing=False, hide_only=()):
    """Take the gang's dismissed offers off these cards and sheets, or keep
    them on marked when the screen at ``at`` is showing them — and point
    each holder that had any at ``at`` with the query the other way, so
    the control sits beside where the offers were.

    One query for every holder together. ``at`` empty draws no control,
    which is what a reader who does not own the gang gets: the offers
    still go, and nothing is offered. ``hide_only`` holders lose their
    dismissed offers whatever ``showing`` says and get no control — a
    dead model's card is drawn with nothing to click, so a line kept on
    it to be restored would be a line with no way to restore it.
    """
    from n26.core.models import DismissedOffer
    from n26.core.render import hide_dismissed

    keys = DismissedOffer.keys_for(gang)
    toggle = dismissed_toggle(at, showing) if at else ""
    for holder in holders:
        holder.dismissed_count = hide_dismissed(keys, holder, reveal=showing)
        holder.dismissed_shown = showing
        holder.dismissed_href = toggle if holder.dismissed_count else ""
    for holder in hide_only:
        hide_dismissed(keys, holder)


def dismissed_toggle(url, showing):
    """Where the control that shows or hides the dismissed offers leads:
    ``url`` with the query added, or with it taken off again."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)
    query = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name != SHOW_DISMISSED
    ]
    if not showing:
        query.append((SHOW_DISMISSED, SHOWING))
    return urlunsplit(parts._replace(query=urlencode(query)))


@dataclass(frozen=True)
class _Found:
    """One slot, located: the computed slot, the card it sits on, and the
    stored assignment carrying the offer."""

    slot: object
    computed: object
    anchor: object
    #: The model whose card the slot was drawn on, or None for the gang's.
    miniature: object = None


def link_slots(gang, *holders, back="", dismiss_back=None):
    """Point every choice slot on these structures at its picker.

    Costs no queries: a slot's address is already on the line, and this
    only turns it into a URL. A slot with no address keeps an empty href
    and draws as a fact with nothing to click — which is right for a card
    depicting nobody.

    ``back`` is the screen the card is drawn on, carried on every link
    so the picker returns the reader there once the choice is settled
    rather than to the gang. Passed rather than read off a request, as
    ``link_counters`` has it: a card redrawn after an act is rendered
    under that act's own address.

    A card files some of its questions into rows of their own — the ones
    drawn beside the skills and the powers the model already has — so what
    is asked for here is the holder's whole run of questions rather than
    each list by name. Where a question is drawn is the holder's business;
    every one of them is chosen for at the same address, and a holder that
    grows another row is linked by the same line.

    ``dismiss_back`` is where dismissing or restoring an offer lands,
    where that differs from where a settled choice does — the gang sheet
    sends a settled choice to the gang and a dismissal back to the sheet
    as it stood, showing the dismissed offers or not. Left unsaid, it is
    ``back``.
    """
    from n26.core.owned import with_query
    from n26.core.status import Status

    if dismiss_back is None:
        dismiss_back = back
    for holder in holders:
        # A dead model's card draws nothing to click, and its dismissed
        # offers are never shown on it (``settle_dismissed``): an X there
        # would offer an act the card cannot show the way back from.
        dead = getattr(holder, "status", None) == Status.DEAD
        for line in holder.questions:
            if not line.key:
                continue
            line.href = reverse("n26-choose", args=[gang.pk, line.key])
            if back:
                line.href = with_query(line.href, **{"return": back})
            if dead:
                continue
            # Only the owner's structures come through here, so the way
            # to dismiss an offer is drawn for nobody else. An open offer
            # can be dismissed; one holding a pick cannot, since what
            # was chosen is drawn and there is nothing to hide; one full
            # from the start — authored to take no picks — draws no
            # Choose, so it gets no X beside a control it does not have;
            # a dismissed one, kept on the structure to be shown, offers
            # only the way back.
            line.back = dismiss_back
            if line.dismissed:
                line.restore_href = reverse(
                    "n26-restore-offer", args=[gang.pk, line.key]
                )
            elif not line.is_resolved and not line.is_full:
                line.dismiss_href = reverse(
                    "n26-dismiss-offer", args=[gang.pk, line.key]
                )


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
    if slot is None or not slot.picklist.dice or found.slot.is_full:
        # A full choice takes no more picks, so a roll for it would be
        # one the next Add refuses; the way to another is to take a
        # pick back first.
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
    return _roll_at(request.GET.get("roll", ""), gang, found)


def _roll_posted(request, gang, found):
    """The roll a pick says it came from, or None for a pick made plain."""
    return _roll_at(request.POST.get("roll", ""), gang, found)


def _roll_result(event, found, offer, *, include_staged=False):
    """One roll, as the page draws it, and the keys of the rows it reached.

    The table is read as the pick screen offers it to this reader
    (``picklist_lines``): never an archived line or pickable, and a staged
    one only for a reader who may see staged content — the roll lands on
    nothing there rather than on a name they were never offered.
    """
    from django.db.models import F

    from n26.core.browse import picklist_lines
    from n26.core.operations import ROLL_ENTERED, ROLL_ENTERED_BEFORE
    from n26.core.render import RollResult, option_key
    from n26.library.models import Dice, RollSelects

    picklist = found.slot.slot.picklist
    # The lines the pick screen offers this reader, in the list's own roll
    # order, so what the panel names reads in the order the list beneath
    # it draws.
    members = picklist_lines(picklist, include_staged=include_staged).order_by(
        F("roll_low").asc(nulls_last=True), "position", "pickable__name"
    )
    landed = picklist.landing(event.roll, members)
    keys = {option_key(member.pickable) for member in landed}
    named = {
        option.key: option.name for group in offer.groups for option in group.options
    }
    # The standing pick this roll was spent on, where there is one. A pick
    # taken back frees its roll, so an archived one does not count.
    spent = event.picks.filter(archived=False).select_related("pickable").first()
    # The die as the record holds it; a die the library no longer names
    # reads as the table's, since the figure is what the page is about.
    dice = Dice(picklist.dice)
    try:
        dice = Dice(event.dice) if event.dice else dice
    except ValueError:
        pass
    result = RollResult(
        key=str(event.pk),
        total=event.roll,
        dice_label=dice.label,
        faces=Dice.faces(dice, event.roll),
        landed=tuple(named.get(option_key(m.pickable), m.label) for m in landed),
        entered=event.note in (ROLL_ENTERED, ROLL_ENTERED_BEFORE),
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
    # The list is built for this reader: staged picks are on it only for
    # somebody who may see staged content, and the click below and the
    # roll panel are read against the same list.
    shown = sees_staged(request.user)
    offer = build_choice_offer(found.slot, found.computed, include_staged=shown)
    # Where the reader came from, forwarded by the link that opened this
    # page and carried through the form, so settling the choice lands
    # them back on the screen they were reading. Only this site's own
    # addresses are honoured; anything else falls back to the gang.
    returning = request.POST.get("return") or request.GET.get("return", "")
    back = _own_address(request, returning) or reverse("n26-gang", args=[gang.pk])
    here = reverse("n26-choose", args=[gang.pk, slot])
    if returning:
        here = with_query(here, **{"return": returning})

    if request.method == "POST" and request.POST.get("act") in {"roll", "enter"}:
        # Rolling writes before anything is picked: the roll is on the
        # record from this moment, and the page comes back at it. A roll
        # made at the table and entered here goes the same way, with the
        # record saying it was entered.
        if found.slot.slot is None or not found.slot.slot.picklist.dice:
            # No die behind this choice: no page drew a Roll for it.
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
                if fresh.slot.is_full:
                    # Filled while this page stood open: a roll now would
                    # be one the next Add refuses, and a roll is on the
                    # record for good.
                    raise Refusal(
                        f"{offer.label} holds all the picks it will take. "
                        "Take one back before rolling."
                    )
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
        return redirect(with_query(here, roll=event.pk))

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
        roll, landed = _roll_result(event, found, offer, include_staged=shown)
        addable = [
            option
            for group in offer.groups
            for option in group.options
            if option.key in landed and option.control in {"choose", "both"}
        ]
        if not roll.is_spent and len(addable) == 1 and len(landed) == 1:
            # One result, still open, on a choice worked at a pick at a
            # time: the panel carries the Add, and the list below stays
            # the whole table, unlifted. A choice of one is settled by
            # its radios, which post under the same name a panel button
            # would, so that shape lifts the row instead.
            roll = replace(roll, add=addable[0])
        elif not roll.is_spent:
            offer = lift_landing(offer, landed, threshold=roll.threshold)

    bearer = found.miniature.name if found.miniature is not None else gang.name
    item = _item_behind(found)
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
            "pick_lead": f"{item}, for {bearer}." if item else f"For {bearer}.",
            "returning": returning,
        },
    )


@login_required
@require_POST
def dismiss_offer(request, pk, slot):
    """Put one open offer out of sight, everywhere the gang is drawn.

    The slot is found again rather than trusted from the address, the
    way the pick screen finds it: an offer that no longer exists is a
    404, and one holding a pick is refused in words — the page that
    drew the control was drawn before the pick landed. That second look
    is taken with the gang's line held, as every pick is written, so a
    pick landing at the same moment is read either before the row is
    written and refuses it, or after and takes the row off again. Nothing
    is written for a dismissal already on record; a second click is the
    same act.

    Lands back where the control was clicked, given as ``back`` and
    honoured only for this site's own addresses; the gang otherwise.
    """
    from django.db import transaction

    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.models import DismissedOffer
    from n26.core.operations import _hold

    gang = _own_gang_or_404(request, pk)
    label = _find_slot(gang, slot).slot.kind_label
    fallback = reverse("n26-gang", args=[gang.pk])
    with transaction.atomic():
        _hold(gang)
        found = _find_slot(gang, slot)
        if found.slot.is_resolved:
            # Counted, because a choice worked at a pick at a time may
            # hold several, and every one of them has to go first.
            held = (
                "It has a pick. Take the pick back first."
                if len(found.slot.picks) == 1
                else "It has picks. Take them all back first."
            )
            messages.error(request, f"You cannot dismiss {label}. {held}")
            return _safe_redirect(request, request.POST.get("back"), fallback)
        if found.slot.is_full:
            # Full with nothing chosen: a choice authored to take no
            # picks. No page draws an X for it, so this is a hand-built
            # post; it draws no Choose either, so there is nothing to hide.
            messages.error(
                request, f"You cannot dismiss {label}. It offers nothing to choose."
            )
            return _safe_redirect(request, request.POST.get("back"), fallback)
        DismissedOffer.objects.get_or_create(gang=gang, slot_key=slot)
    record(
        request,
        N26Noun.CHOICE,
        EventVerb.ARCHIVE,
        gang,
        offer=label,
        action="dismiss",
    )
    messages.success(
        request, f"Dismissed {label}. You can bring it back from Dismissed choices."
    )
    return _safe_redirect(request, request.POST.get("back"), fallback)


@login_required
@require_POST
def restore_offer(request, pk, slot):
    """Bring a dismissed offer back, so it draws as an open Choose again.

    The row is deleted whether or not the slot still exists: a key left
    behind by a carrier since sold hides nothing, and taking it off is
    harmless. Deleted with the gang's line held, as a dismissal is
    written, so a dismiss and a restore arriving together are read one
    after the other and the reply says what stands. The slot is then
    found again only to name the offer in the confirmation — the same
    derivation opening its pick screen pays. Lands where the control was
    clicked, or on the gang with its dismissed offers still showing,
    since the reader was in the middle of looking at them.
    """
    from django.db import transaction

    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.models import DismissedOffer
    from n26.core.operations import _hold

    gang = _own_gang_or_404(request, pk)
    with transaction.atomic():
        _hold(gang)
        DismissedOffer.objects.filter(gang=gang, slot_key=slot).delete()
    try:
        label = _find_slot(gang, slot).slot.kind_label
    except Http404:
        label = "the choice"
    record(
        request,
        N26Noun.CHOICE,
        EventVerb.RESTORE,
        gang,
        offer=label,
    )
    messages.success(request, f"Restored {label}.")
    fallback = dismissed_toggle(reverse("n26-gang", args=[gang.pk]), showing=False)
    return _safe_redirect(request, request.POST.get("back"), fallback)


def _own_address(request, url):
    """``url`` if it is one of this site's own pages, else an empty string.

    A return address arrives in the query and the form, so it is checked
    against this request's host before anything redirects to it."""
    from django.utils.http import url_has_allowed_host_and_scheme

    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return url
    return ""


def _item_behind(found):
    """The piece of kit whose own choice this is — the launchers an
    augmentation ladder is built into — or None for a choice the model
    or the gang carries itself. Read off the slot's cause: a choice
    built into an item is materialised beside the model and caused by
    the item's assignment."""
    from n26.library.models import Wargear, Weapon, WeaponAccessory

    if found.slot.slot is None:
        # An offer's cause is whatever brought the offerer, not an item
        # the choice is about.
        return None
    cause = getattr(found.anchor, "caused_by", None)
    if cause is None:
        return None
    thing = cause.assignable
    if isinstance(thing, (Weapon, Wargear, WeaponAccessory)):
        return str(thing)
    return None
