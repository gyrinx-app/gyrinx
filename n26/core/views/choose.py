"""Resolve computed choices and record picks, rolls and dismissal state.

Assignment choice URLs identify the displayed card, carrier assignment and
offer. Status follow-ups add a status revision. Recompute the card to resolve
each address; removed carriers or changed revisions invalidate it.

Holding choices identify the holding, ownership revision and slot.
Lock affected campaigns before the gang, matching ownership operations.

Single-pick choices replace their existing answer. Multi-pick choices add or
remove one result per submission without evicting another pick when full.
Rolls are recorded before selection and scoped to the same card and choice.
"""

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from n26.core.arrivals import arriving, onward, toward
from n26.core.models.dismissed_offer import identity_key
from n26.core.owned import with_query
from n26.core.views.permissions import _own_gang_or_404, _safe_redirect, own_address
from n26.library.staged import sees_staged

#: URL state requesting dismissed offers and their restoration controls.
SHOW_DISMISSED = "dismissed"
SHOWING = "show"


@contextmanager
def choice_operation(gang, keys, *, actor=None):
    """Lock holding campaigns in stable order before the gang operation.

    Ordinary assignment choices require only the gang lock. Resolve choices again
    inside these locks before writing.
    """
    from n26.core.campaigns import campaign_operation
    from n26.core.models import CampaignAsset
    from n26.core.models.dismissed_offer import HOLDING_SLOT_HOST
    from n26.core.operations import operation

    campaigns = {}
    for key in keys:
        where, _, rest = key.partition(":")
        if where != HOLDING_SLOT_HOST:
            continue
        holding_pk = rest.partition(":")[0].partition("@")[0]
        try:
            holding = get_object_or_404(
                CampaignAsset.objects.select_related("campaign"), pk=holding_pk
            )
        except ValidationError:
            raise Http404("No such holding") from None
        campaigns[holding.campaign_id] = holding.campaign
    with ExitStack() as locks:
        for campaign_pk in sorted(campaigns, key=str):
            locks.enter_context(campaign_operation(campaigns[campaign_pk], actor=actor))
        with operation(gang, actor=actor) as op:
            yield op


def showing_dismissed(url):
    """Read dismissed-choice display state from an explicit source URL.

    Partial redraw requests may use an operation URL rather than the page URL.
    """
    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(url).query)
    return SHOWING in query.get(SHOW_DISMISSED, [])


def settle_dismissed(gang, *holders, hide_only=()):
    """Read dismissal keys once for all holders.

    Move model choices into their dismissed list; hide_only holders receive no
    restoration controls.
    """
    from n26.core.models import DismissedOffer
    from n26.core.render import hide_dismissed

    keys = DismissedOffer.keys_for(gang)
    for holder in holders:
        hide_dismissed(keys, holder, removed=holder.dismissed_choices)
    for holder in hide_only:
        hide_dismissed(keys, holder)


@dataclass(frozen=True)
class _Found:
    """A resolved computed choice, its computation, carrier and optional target model."""

    slot: object
    computed: object
    anchor: object
    #: The model whose card displays the choice; None for a gang choice.
    miniature: object = None


def link_slots(gang, *holders, back="", dismiss_back=None):
    """Link all addressable questions to their picker and permitted dismissal actions.

    Use the supplied source-page back destination rather than an operation request
    path. dismiss_back can independently choose where dismissal controls return.
    Preview questions without keys remain unlinked.
    """
    from n26.core.owned import with_query
    from n26.core.status import Status

    if dismiss_back is None:
        dismiss_back = back
    for holder in holders:
        # Dead models retain picker links but receive no dismissal or restoration controls.
        dead = getattr(holder, "status", None) == Status.DEAD
        for line in [*holder.questions, *getattr(holder, "dismissed_choices", ())]:
            if not line.key:
                continue
            if line.is_full and not line.is_resolved:
                # Zero-capacity choices remain plain facts; resolved choices keep links for editing.
                continue
            line.href = reverse("n26-choose", args=[gang.pk, line.key])
            if back:
                line.href = with_query(line.href, **{"return": back})
            if dead:
                continue
            # Add dismissal controls only to eligible unresolved, non-full owner questions.
            # Dismissed questions offer restoration instead.
            line.back = dismiss_back
            if not line.allow_dismissal:
                continue
            if line.dismissed:
                line.restore_href = reverse(
                    "n26-restore-offer", args=[gang.pk, line.key]
                )
            elif not line.is_resolved and not line.is_full:
                line.dismiss_href = reverse(
                    "n26-dismiss-offer", args=[gang.pk, line.key]
                )


def find_slot(gang, key):
    """Recompute the addressed card and resolve the current choice, otherwise return 404."""
    from n26.core.card import (
        build_card,
        build_gang_card,
        build_modifier_index,
        carriers,
    )
    from n26.core.effects import compute, compute_gang
    from n26.core.models import Miniature
    from n26.core.models.dismissed_offer import HOLDING_SLOT_HOST, holding_slot_key
    from n26.core.render import GANG_SLOT_HOST

    where, _, rest = key.partition(":")
    anchor_pk, _, offer_pk = rest.partition(":")
    if not (where and anchor_pk and offer_pk):
        raise Http404("No such choice")

    miniature = None
    if where in (GANG_SLOT_HOST, HOLDING_SLOT_HOST):
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
            # Convert malformed model identifiers into missing-choice responses.
            raise Http404("No such fighter") from None
        card = build_card(miniature)

    index = build_modifier_index(carriers(card))
    computed = compute_gang(card, index) if miniature is None else compute(card, index)

    for slot in computed.choices:
        if slot.holding is not None:
            if holding_slot_key(slot.holding, slot.identity.pk) == key:
                return _Found(slot=slot, computed=computed, anchor=slot.holding)
            continue
        anchor = getattr(slot.anchor, "assignment", None)
        if anchor is None or slot.identity is None:
            continue
        identity = identity_key(slot.identity.pk, slot.status_revision)
        if str(anchor.pk) == anchor_pk and identity == offer_pk:
            return _Found(
                slot=slot, computed=computed, anchor=anchor, miniature=miniature
            )
    raise Http404("No such choice")


def _landing(request, gang, key, offer, op, here, back, found):
    """Choose the post-selection destination, including newly introduced interstitials.

    Single picks continue back. Multi-pick choices return to the picker when no
    follow-up screen arrives, even when full. When a screen arrives, recompute the
    choice and return there only while it remains open; otherwise continue back.
    Lasting-effect choices return to the affected model's edit page.
    """
    if (
        found.slot.slot
        and found.slot.slot.slot_type.is_lasting_effect
        and found.miniature
    ):
        return onward(
            request, gang, op, reverse("n26-edit-fighter", args=[found.miniature.pk])
        )
    if not offer.takes_several:
        return onward(request, gang, op, back)
    keys = arriving(request, gang, op)
    if not keys:
        return here
    try:
        working = not find_slot(gang, key).slot.is_full
    except Http404:
        working = False
    return toward(gang, keys, here if working else back)


def find_slots(gang, keys):
    """Resolve many choice addresses through one gang-card derivation.

    Return a key-to-Found mapping, omitting malformed, missing and vanished choices.
    Canonicalise model identifiers for lookup without rewriting the requested keys.
    """
    from n26.core.card import build_gang_card, build_modifier_index, carriers
    from n26.core.effects import compute, compute_gang
    from n26.core.models import Miniature
    from n26.core.models.dismissed_offer import HOLDING_SLOT_HOST, holding_slot_key
    from n26.core.render import GANG_SLOT_HOST

    wanted = {}
    for key in keys:
        where, _, rest = key.partition(":")
        anchor_pk, _, offer_pk = rest.partition(":")
        if not (where and anchor_pk and offer_pk):
            continue
        if where not in (GANG_SLOT_HOST, HOLDING_SLOT_HOST):
            try:
                # Canonicalise model ULIDs for dictionary lookup because the field also accepts UUID spelling.
                # Match carrier and offer identifiers exactly, preserving the original URL key.
                where = str(Miniature._meta.pk.to_python(where))
            except ValidationError:
                # Convert malformed model identifiers into missing-choice responses.
                continue
        wanted.setdefault(where, {})[(anchor_pk, offer_pk)] = key
    if not wanted:
        return {}

    gang_card = build_gang_card(gang)
    cards = gang_card.members
    index = build_modifier_index(carriers(gang_card, *cards.values()))
    computed = {}
    if GANG_SLOT_HOST in wanted or HOLDING_SLOT_HOST in wanted:
        done = compute_gang(gang_card, index)
        for where in (GANG_SLOT_HOST, HOLDING_SLOT_HOST):
            if where in wanted:
                computed[where] = (done, None)
    named = [
        where for where in wanted if where not in (GANG_SLOT_HOST, HOLDING_SLOT_HOST)
    ]
    if named:
        miniatures = Miniature.objects.filter(
            pk__in=named, membership__gang=gang, membership__archived=False
        )
        members = {str(m.pk): m for m in miniatures}
        for where, miniature in members.items():
            card = cards.get(miniature.pk)
            if card is not None:
                computed[where] = (compute(card, index), miniature)

    found = {}
    for where, (done, miniature) in computed.items():
        for slot in done.choices:
            if slot.holding is not None:
                if where == HOLDING_SLOT_HOST:
                    _, anchor_key, identity = holding_slot_key(
                        slot.holding, slot.identity.pk
                    ).split(":")
                    key = wanted[where].get((anchor_key, identity))
                    if key is not None:
                        found[key] = _Found(
                            slot=slot, computed=done, anchor=slot.holding
                        )
                continue
            anchor = getattr(slot.anchor, "assignment", None)
            if anchor is None or slot.identity is None:
                continue
            identity = identity_key(slot.identity.pk, slot.status_revision)
            key = wanted[where].get((str(anchor.pk), identity))
            if key is not None:
                found[key] = _Found(
                    slot=slot, computed=done, anchor=anchor, miniature=miniature
                )
    return found


def _settled(found):
    """Read stored answers from the computed choice's scoped and adopted picks."""
    return [pick for pick in found.slot.picks if pick.assignment is not None]


def _pick_of(found, wanted):
    """Find a stored settled pick matching an option identity, or return None."""
    from n26.core.render import option_key

    return next(
        (pick for pick in _settled(found) if option_key(pick.assignable) == wanted),
        None,
    )


def _roll_table(found):
    """Build roll controls for a non-full choice with an authored die."""
    from n26.core.render import RollTable
    from n26.library.models import Dice

    slot = found.slot.slot
    if slot is None or not slot.picklist.dice or found.slot.is_full:
        # Full choices cannot accept another roll until a pick is removed.
        return None
    dice = Dice(slot.picklist.dice)
    rolls = Dice.rolls(dice)
    return RollTable(dice_label=dice.label, lowest=rolls[0], highest=rolls[-1])


def _roll_at(key, gang, found, select_related=()):
    """Resolve a roll scoped to this gang, choice, model and revision context.

    Holding ownership and status-follow-up revisions prevent reuse after their
    context changes. Invalid or unrelated identifiers return 404.
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
            campaign_asset=found.slot.holding,
            holding_revision=found.slot.holding.ownership_revision
            if found.slot.holding
            else None,
            **(
                {"status_revision": found.slot.status_revision}
                if found.slot.slot.follows_status
                else {}
            ),
        )
    except ValidationError:
        raise Http404("No such roll") from None


def _roll_named(request, gang, found):
    """Resolve the GET roll parameter for display."""
    return _roll_at(request.GET.get("roll", ""), gang, found)


def _roll_posted(request, gang, found):
    """Resolve the POST roll parameter supplied with a selection."""
    return _roll_at(request.POST.get("roll", ""), gang, found)


def _roll_result(event, found, offer, *, include_staged=False):
    """Describe a recorded roll and identify the visible picklist results it reaches.

    Apply archive and staged visibility through picklist_lines. An archived pick
    releases its roll for reuse. Prefer the recorded die, falling back to the
    current table for unknown stored values.
    """
    from django.db.models import F

    from n26.core.browse import picklist_lines
    from n26.core.operations import ROLL_ENTERED, ROLL_ENTERED_BEFORE
    from n26.core.render import RollResult, option_key
    from n26.library.models import Dice, RollSelects

    picklist = found.slot.slot.picklist
    # Read visible results in the same roll order as the displayed picklist.
    members = picklist_lines(picklist, include_staged=include_staged).order_by(
        F("roll_low").asc(nulls_last=True), "position", "pickable__name"
    )
    landed = picklist.landing(event.roll, members)
    keys = {option_key(member.pickable) for member in landed}
    named = {
        option.key: option.name for group in offer.groups for option in group.options
    }
    # Only live picks consume a roll; removing a pick releases it.
    spent = event.picks.filter(archived=False).select_related("pickable").first()
    # Prefer the recorded die, falling back to the current table for unknown values.
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
    """Identify the target model for choices broadcast from gang-held assignments."""
    if (
        found.miniature is not None
        and found.slot.anchor is not None
        and found.slot.anchor.broadcast
    ):
        return {"miniature": found.miniature}
    return {}


def _campaign_label_or_404(gang, found):
    from n26.core.models import CampaignMembership

    membership = CampaignMembership.objects.filter(gang=gang, left__isnull=True).first()
    if membership is None or found.miniature is not None:
        raise Http404("No such campaign label")
    carriers = {membership.type_carrier_id, membership.additions_carrier_id}
    if found.slot.holding is not None:
        raise Http404("No such campaign label")
    anchor = found.anchor
    seen = set()
    while anchor is not None and anchor.pk not in seen:
        if anchor.pk in carriers:
            return
        seen.add(anchor.pk)
        anchor = anchor.caused_by
    raise Http404("No such campaign label")


def _campaign_label_update(request, gang, *, close=True):
    from n26.core.views.gangs import gang_sheet
    from n26.core.views.htmx import with_toasts

    context = gang_sheet(request, gang.pk).context_data
    context.update(redrawn=True, close_dialog=close)
    return with_toasts(
        request, render(request, "n26/includes/campaign_label_update.html", context)
    )


@login_required
def choose(request, pk, slot):
    """Display a computed choice or record one submitted pick or roll.

    Build offers under the user's staging access and validate return URLs.
    Rolls are written in the shared lock context and redisplayed by event ID.
    Single choices replace; multi-pick controls settle one change at a time.
    Campaign label dialogs return partial updates when requested by htmx.
    Earned battle-action choices redirect to their action flow.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal
    from n26.core.render import build_choice_offer

    gang = _own_gang_or_404(request, pk)
    found = find_slot(gang, slot)
    from n26.core.action_records import battle_action_for_slot

    battle_action = battle_action_for_slot(found.anchor)
    if battle_action is not None:
        return redirect(
            "n26-action-flow",
            pk=battle_action.fighter_id,
            record_id=battle_action.pk,
            step="resume",
        )
    # Use identical staged-content access for the offer, roll results and selection.
    shown = sees_staged(request.user)
    offer = build_choice_offer(found.slot, found.computed, include_staged=shown)
    # Validate return addresses and preserve them through picker submissions.
    returning = request.POST.get("return") or request.GET.get("return", "")
    back = own_address(request, returning) or reverse("n26-gang", args=[gang.pk])
    here = reverse("n26-choose", args=[gang.pk, slot])
    if returning:
        here = with_query(here, **{"return": returning})
    campaign_dialog = request.GET.get("dialog") == "campaign"
    if campaign_dialog:
        _campaign_label_or_404(gang, found)
        here = with_query(here, dialog="campaign")

    if request.method == "POST" and request.POST.get("act") in {"roll", "enter"}:
        # Record rolls immediately, including entered tabletop results, before any pick is made.
        if found.slot.slot is None or not found.slot.slot.picklist.dice:
            # Reject Roll submissions for choices without an authored die.
            raise Http404("Nothing to roll here")
        rolled = None
        if request.POST["act"] == "enter":
            try:
                rolled = int(request.POST.get("rolled", ""))
            except ValueError:
                messages.error(request, "Enter the number you rolled.")
                return redirect(here)
        try:
            with choice_operation(gang, [slot], actor=request.user) as op:
                fresh = find_slot(gang, slot)
                if fresh.slot.is_full:
                    # Recheck capacity under lock before recording a new roll.
                    raise Refusal(
                        f"{offer.label} holds all the picks it will take. "
                        "Take one back before rolling."
                    )
                event = op.roll(
                    fresh.slot.slot,
                    miniature=fresh.miniature,
                    campaign_asset=fresh.slot.holding,
                    rolled=rolled,
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
        response = settle_pick(
            request,
            gang,
            slot,
            found,
            offer,
            here=here,
            land=lambda op: _landing(request, gang, slot, offer, op, here, back, found),
        )
        from n26.core.views.htmx import is_htmx, no_update

        if not campaign_dialog or not is_htmx(request):
            return response
        if response.url == back:
            response = _campaign_label_update(request, gang)
            response["HX-Replace-Url"] = back
            return response
        if response.url != here:
            destination = response.url
            response = no_update(request)
            response["HX-Redirect"] = destination
            return response
        found = find_slot(gang, slot)
        offer = build_choice_offer(found.slot, found.computed, include_staged=shown)

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
            # For one addable multi-pick result, place Add on the roll panel and retain the full list.
            # Other unspent results highlight the corresponding options.
            roll = replace(roll, add=addable[0])
        elif not roll.is_spent:
            offer = lift_landing(offer, landed, threshold=roll.threshold)

    from n26.core.views.htmx import is_htmx, with_toasts

    dialog_request = campaign_dialog and is_htmx(request)
    response = render(
        request,
        "n26/includes/campaign_label_dialog.html"
        if dialog_request
        else "n26/choose.html",
        {
            "gang": gang,
            "miniature": found.miniature,
            "offer": offer,
            # Replace roll controls with an unspent recorded roll until it is applied.
            "roll_table": roll_table if roll is None or roll.is_spent else None,
            "roll": roll,
            "back": back,
            # Multi-pick options submit independently and need no additional Save action.
            "submit_label": "" if offer.takes_several else "Save",
            # Use a distinct Cotton slot name to avoid collisions with unrelated page components.
            "pick_lead": found.slot.slot.introduction if found.slot.slot else "",
            "returning": returning,
            "choice_action": here,
            "reopened": request.method == "POST",
        },
    )
    if dialog_request:
        if request.method == "POST":
            update = _campaign_label_update(request, gang, close=False)
            update.content += response.content
            response = update
        response["HX-Replace-Url"] = here
        return with_toasts(request, response)
    return response


@login_required
@require_POST
def dismiss_offer(request, pk, slot):
    """Hide an eligible unresolved offer under the shared choice locks.

    Resolve it again after locking and refuse resolved or zero-capacity choices.
    Repeated dismissal creates no duplicate record. Validate the return destination.
    """

    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.models import DismissedOffer

    gang = _own_gang_or_404(request, pk)
    label = find_slot(gang, slot).slot.kind_label
    fallback = reverse("n26-gang", args=[gang.pk])
    with choice_operation(gang, [slot], actor=request.user):
        found = find_slot(gang, slot)
        if not found.slot.allow_dismissal:
            messages.error(
                request, f"You cannot dismiss {label}. This choice must stay available."
            )
            return _safe_redirect(request, request.POST.get("back"), fallback)
        if found.slot.is_resolved:
            # Require all existing picks to be removed before dismissal.
            held = (
                "It has a pick. Take the pick back first."
                if len(found.slot.picks) == 1
                else "It has picks. Take them all back first."
            )
            messages.error(request, f"You cannot dismiss {label}. {held}")
            return _safe_redirect(request, request.POST.get("back"), fallback)
        if found.slot.is_full:
            # Refuse dismissal of zero-capacity choices, which have no interactive picker.
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
    where = (
        "Dismissed choices on the model’s Edit page"
        if found.miniature
        else "the Dismissed choices tab on the gang’s Edit page"
    )
    messages.success(request, f"Dismissed {label}. You can restore it from {where}.")
    return _safe_redirect(request, request.POST.get("back"), fallback)


@login_required
@require_POST
def restore_offer(request, pk, slot):
    """Remove dismissal state under the gang lock, including keys whose carrier is gone.

    Resolve the choice afterwards only to name the confirmation, then return to
    the validated source or the gang's dismissed-choices tab.
    """
    from django.db import transaction

    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.models import DismissedOffer
    from n26.core.operations import _hold
    from n26.write_pause import write_guard

    gang = _own_gang_or_404(request, pk)
    with transaction.atomic(), write_guard():
        _hold(gang)
        DismissedOffer.objects.filter(gang=gang, slot_key=slot).delete()
    try:
        label = find_slot(gang, slot).slot.kind_label
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
    fallback = with_query(reverse("n26-edit-gang", args=[gang.pk]), tab="dismissed")
    return _safe_redirect(request, request.POST.get("back"), fallback)


class NotOnTheList(Exception):
    """A stale or invalid submitted option requiring the current picker to be redisplayed."""


def _write_pick(op, request, gang, slot_key, found, offer, wanted, *, dropped=""):
    """Validate and write one choice inside an existing operation.

    Reject options absent from the supplied offer and rederive the choice under
    lock before replacing, adding or removing answers. Optional None clears the
    answer only when offered. Earned battle results require their action flow.
    """
    from n26.core.action_records import battle_action_for_slot
    from n26.core.allowances import require_allowance_available
    from n26.core.operations import Refusal
    from n26.core.render import NONE_KEY

    battle_action = battle_action_for_slot(found.anchor)
    if battle_action is not None:
        require_allowance_available(battle_action.allowance)
        raise Refusal("Choose this result through its earned action flow.")

    rolled_on = _roll_posted(request, gang, found)
    if wanted == NONE_KEY and not dropped:
        # Honour None only when explicitly offered; required choices cannot be cleared this way.
        offered_none = any(
            option.key == NONE_KEY for group in offer.groups for option in group.options
        )
        if not offered_none:
            raise NotOnTheList
        for pick in _settled(find_slot(gang, slot_key)):
            op.remove(pick.assignment)
        return None
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
        # Reject stale selections and removal requests for picks not currently held.
        raise NotOnTheList
    # Recompute the choice under lock before writing, including concurrent answers or carrier removal.
    fresh = find_slot(gang, slot_key)
    if dropped:
        taken = _pick_of(fresh, wanted)
        if taken is not None:
            op.remove(taken.assignment)
    elif (
        offer.takes_several
        and _pick_of(fresh, wanted) is not None
        and not (
            fresh.slot.slot is not None and fresh.slot.slot.slot_type.allows_repeats
        )
    ):
        # Ignore an already-held multi-pick result unless its slot type explicitly permits repeats.
        pass
    else:
        if not offer.takes_several:
            # Single-pick selection replaces all existing stored answers.
            for standing in _settled(fresh):
                op.remove(standing.assignment)
        elif fresh.slot.is_full:
            # Reject newly full multi-pick choices without removing an existing answer.
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
    return picked


def _said_about(picked, offer, dropped):
    """Describe choice, addition or removal using the offer's single- or multi-pick terms."""
    if picked is None:
        return f"Chose none — {offer.label}."
    if dropped:
        said = "Removed"
    elif offer.takes_several:
        said = "Added"
    else:
        said = "Chose"
    return f"{said} {picked.name} — {offer.label}."


def _record_pick(request, gang, offer, picked, dropped):
    """Record the submitted choice outcome without rewriting earlier analytics events."""
    from n26.analytics import EventVerb, N26Noun, record

    record(
        request,
        N26Noun.CHOICE,
        EventVerb.ARCHIVE if dropped or picked is None else EventVerb.CONFIRM,
        gang,
        offer=offer.label,
        picked="None" if picked is None else picked.name,
    )


def settle_pick(
    request, gang, slot_key, found, offer, *, here, land, wanted=None, dropped=None
):
    """Settle one picker submission and redirect through the supplied landing function.

    Use here after stale input or refusal. Refresh status for confirmation when
    the chosen result changed the model.
    """
    from n26.core.operations import Refusal

    # Multi-question screens pass question-specific values; the dedicated picker reads plain POST names.
    if dropped is None:
        dropped = request.POST.get("remove", "")
    if wanted is None:
        wanted = request.POST.get("thing", "")
    wanted = dropped or wanted
    status_before = found.miniature.status if found.miniature else None
    try:
        with choice_operation(gang, [slot_key], actor=request.user) as op:
            picked = _write_pick(
                op, request, gang, slot_key, found, offer, wanted, dropped=dropped
            )
    except NotOnTheList:
        messages.error(request, "That is not one of the things available to pick.")
        return redirect(here)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return redirect(here)
    _record_pick(request, gang, offer, picked, dropped)
    confirmation = _said_about(picked, offer, dropped)
    if found.miniature:
        found.miniature.refresh_from_db(fields=["status"])
        if found.miniature.status != status_before:
            from n26.core.status import label_for

            primary = next(
                (
                    n.assignable
                    for n in found.computed.card.all_nodes()
                    if n.is_primary_profile
                ),
                None,
            )
            vehicle = primary is not None and primary.profile_type.name == "Vehicle"
            confirmation += f" {found.miniature.name} is now {label_for(found.miniature.status, vehicle)}."
    messages.success(request, confirmation)
    return redirect(land(op))


def settle_picks(request, gang, answers, *, here, land):
    """Settle supplied answers together in one operation.

    Each answer is (slot_key, found, offer, wanted). Omitted questions remain open.
    Any refusal rolls back every answer; empty submissions write nothing.
    """
    from n26.core.operations import Refusal

    if not answers:
        return redirect(land(None))
    written = []
    try:
        with choice_operation(
            gang, [key for key, *_ in answers], actor=request.user
        ) as op:
            for slot_key, found, offer, wanted in answers:
                picked = _write_pick(op, request, gang, slot_key, found, offer, wanted)
                written.append((offer, picked))
    except NotOnTheList:
        messages.error(request, "That is not one of the things available to pick.")
        return redirect(here)
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return redirect(here)
    for offer, picked in written:
        _record_pick(request, gang, offer, picked, "")
        messages.success(request, _said_about(picked, offer, ""))
    return redirect(land(op))
