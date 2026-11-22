"""Resolve a gang's phase entry credits from recorded transitions and membership dates."""

from collections import defaultdict
from dataclasses import dataclass
from random import SystemRandom

from django.core.exceptions import ValidationError
from django.db.models import Q

from n26 import flags
from n26.core.cycle_context import PhaseEntryContext
from n26.core.cycle_data import credits_from_data
from n26.core.models import (
    CampaignCycleTransition,
    CampaignEvent,
    LedgerEvent,
    PhaseCreditReceipt,
)
from n26.core.operations import Refusal, operation
from n26.core.schedule import CreditAmount


@dataclass
class Offer:
    entry: CampaignCycleTransition
    name: str
    terms: CreditAmount
    eligible: bool = False

    @property
    def amount_label(self):
        dice = self.terms.dice
        if dice is None:
            return f"{self.terms.fixed}¢"
        expression = f"{dice.count}D{dice.sides}"
        if dice.multiplier != 1:
            expression += f" × {dice.multiplier}"
        if self.terms.fixed:
            expression += f" + {self.terms.fixed}"
        return expression + "¢"


def can_manage(campaign, gang, actor):
    return (
        actor.is_authenticated
        and flags.enabled(flags.CYCLE_TRACKING, actor)
        and not (campaign.archived or gang.archived or gang.credits_unlimited)
        and actor.pk in (campaign.owner_id, gang.owner_id)
        and campaign.memberships.filter(gang=gang, left__isnull=True).exists()
    )


def offers(campaign, gang):
    memberships = list(
        campaign.memberships.filter(gang=gang).values_list("created", "left")
    )
    return _offers(_phase_windows(campaign), memberships)


def _phase_windows(campaign):
    entries = campaign.cycle_transitions.filter(
        Q(receipt__enters_phase=True) | Q(kind=CampaignCycleTransition.Kind.FINISHED)
    ).order_by("occurred_at", "id")
    changes = [
        (e.occurred_at, e, e.kind != CampaignCycleTransition.Kind.FINISHED)
        for e in entries
    ]
    if not changes:
        return []
    # Status changes can stop and resume the same phase without cycle tracking.
    # Their notes preserve the previous and next status labels.
    statuses = campaign.events.filter(kind=CampaignEvent.Kind.STATUS_CHANGED).order_by(
        "created", "id"
    )
    changes.extend(
        (at, None, note.endswith(" → In progress"))
        for at, note in statuses.values_list("created", "note")
    )
    windows = []
    current = start = None
    for at, transition, playing in sorted(changes, key=lambda change: change[0]):
        if current is not None and start is not None and start < at:
            windows.append((current, start, at))
        if (
            transition is not None
            and transition.kind != CampaignCycleTransition.Kind.FINISHED
        ):
            current = transition
        start = at if playing else None
    if current is not None and start is not None:
        windows.append((current, start, None))
    return windows


def _offers(windows, memberships):
    awards = {}
    for entry, start, end in windows:
        phase = entry.receipt.get("current_phase", {})
        if not isinstance(phase, dict):
            continue
        key = (
            entry.phase_occurrence_id,
            None if entry.phase_occurrence_id else entry.pk,
        )
        if key not in awards:
            terms = credits_from_data(phase.get("rewards", {}).get("entry_credits", {}))
            awards[key] = Offer(entry, phase.get("name", ""), terms)
        awards[key].eligible |= entry.phase_occurrence_id is not None and any(
            (end is None or joined < end) and (left is None or left > start)
            for joined, left in memberships
        )
    return [award for award in awards.values() if award.terms.fixed or award.terms.dice]


def adjustments(campaign, gang):
    return LedgerEvent.objects.filter(
        gang=gang,
        campaign=campaign,
        kind=LedgerEvent.Kind.CREDITS_ADJUSTED,
        credits_delta__lt=0,
        phasecreditreceipt__isnull=True,
    ).order_by("-created", "-id")


def settle(campaign, gang, actor, entry, method, note="", payment_id=""):
    context = PhaseEntryContext(
        str(campaign.pk), str(entry.current_cycle_id), str(entry.pk)
    )
    with operation(gang, actor=actor, cycle_context=context) as op:
        gang.refresh_from_db(fields=["owner", "archived", "credits"])
        campaign.refresh_from_db(fields=["owner", "archived"])
        if not can_manage(campaign, gang, actor):
            raise Refusal("You can no longer manage this gang’s phase credits.")
        award = next(
            (a for a in offers(campaign, gang) if a.entry.pk == entry.pk), None
        )
        if award is None or (not award.eligible and campaign.owner_id != actor.pk):
            raise Refusal("This award is unavailable for this gang.")
        previous = PhaseCreditReceipt.objects.filter(entry=entry, gang=gang).first()
        if previous:
            return previous
        note = note.strip()
        if len(note) > 255:
            raise Refusal("Keep the note to 255 characters.")
        if method != "collect" and (actor.pk != campaign.owner_id or not note):
            raise Refusal("An arbitrator must enter a note for this action.")
        if method == "collect" and not award.eligible:
            raise Refusal("Use Grant credits to record an exception.")
        rolls = []
        if method == "paid":
            try:
                payment = adjustments(campaign, gang).filter(pk=payment_id).first()
            except ValidationError:
                payment = None
            if payment is None:
                raise Refusal("Select an unused credit adjustment for this gang.")
        elif method in ("grant", "collect"):
            dice = award.terms.dice
            amount = award.terms.fixed
            if dice:
                if amount + dice.count * dice.multiplier + gang.credits > 2147483647:
                    raise Refusal("This award exceeds the gang credit limit.")
                # Sampling the count of each face keeps large pools bounded in memory.
                remaining = dice.count
                rng = SystemRandom()
                for sides_left in range(dice.sides, 1, -1):
                    count = rng.binomialvariate(remaining, 1 / sides_left)
                    rolls.append(count)
                    remaining -= count
                rolls.append(remaining)
                amount += (
                    sum(face * count for face, count in enumerate(rolls, 1))
                    * dice.multiplier
                )
            if amount + gang.credits > 2147483647:
                raise Refusal("This award exceeds the gang credit limit.")
            reason = f"{award.name} entry credits"
            payment = op.receive_credits(
                amount, f"{reason} · {note}" if note else reason
            )
        else:
            raise Refusal("Select a phase credit action.")
        return PhaseCreditReceipt.objects.create(
            entry=entry,
            gang=gang,
            actor=actor,
            payment=payment,
            method=method,
            rolls=rolls,
            note=note,
        )


def table_actions(campaign, gang_ids, *, arbitrator):
    """Use the same eligibility windows for every visible gang in the campaign table."""
    windows = _phase_windows(campaign)
    if not windows:
        return {}
    memberships = defaultdict(list)
    for gang_id, joined, left in campaign.memberships.filter(
        gang_id__in=gang_ids
    ).values_list("gang_id", "created", "left"):
        memberships[str(gang_id)].append((joined, left))
    paid = defaultdict(set)
    for gang_id, entry_id in PhaseCreditReceipt.objects.filter(
        entry__campaign=campaign, gang_id__in=gang_ids
    ).values_list("gang_id", "entry_id"):
        paid[str(gang_id)].add(entry_id)
    actions = {}
    for gang_id, periods in memberships.items():
        unpaid = [
            offer
            for offer in _offers(windows, periods)
            if offer.entry.pk not in paid[gang_id]
        ]
        if any(offer.eligible for offer in unpaid):
            actions[gang_id] = "Collect phase credits"
        elif arbitrator and unpaid:
            actions[gang_id] = "Review phase credits"
        elif paid[gang_id]:
            actions[gang_id] = "View phase receipts"
    return actions
