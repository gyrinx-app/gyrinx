"""Grant durable fighter-action allowances at their two rule boundaries."""

from django.db import transaction

from n26.core.access import actions_for, rank_table_for
from n26.core.card import build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.models import ActionAllowance, ActionRecord, CounterValue, LedgerEvent


def _membership(fighter):
    membership = fighter.membership
    if membership is None:
        raise ValueError("An action allowance needs a recruited fighter.")
    return membership


def missing_progression_counters(fighter, *, card=None, computed=None):
    """Counters required by the model's rank actions but never assigned to it."""
    from n26.core.access import rank_tables_for
    from n26.core.models import Assignment
    from n26.library.models import Counter, RankAllowanceRule

    if card is None:
        card = build_card(fighter)
    if computed is None:
        computed = compute(card, build_modifier_index(carriers(card)))
    held = {
        node.assignment.counter_id
        for node in card.all_nodes()
        if not node.broadcast and node.assignment and node.assignment.counter_id
    }
    rule_ids = {
        row.action.rank_allowance_rule_id
        for row in actions_for(fighter, card=card, computed=computed)
        if row.action.rank_allowance_rule_id
    }
    used = set(
        RankAllowanceRule.objects.filter(pk__in=rule_ids).values_list(
            "counter_id", flat=True
        )
    )
    missing = {
        row.rank_table.counter_id
        for row in rank_tables_for(fighter, card=card, computed=computed)
        if row.rank_table.counter_id in used - held
    }
    if not missing:
        return []
    return list(
        Counter.objects.unarchived()
        .filter(pk__in=missing)
        .exclude(
            pk__in=Assignment.objects.filter(
                miniature_root=fighter, counter_id__in=missing
            ).values("counter_id")
        )
    )


def track_progression_counter(op, fighter, counter_id):
    """Explicitly open a missing progression counter at zero, without backfill."""
    from n26.core.action_records import _refuse_unless_owned
    from n26.core.models import Assignment, Miniature
    from n26.core.operations import Refusal

    fighter = Miniature.objects.select_related("membership").get(pk=fighter.pk)
    _refuse_unless_owned(op, fighter)
    if not op.counter_tracking_active:
        raise Refusal("Counter history must be active before tracking progression.")
    counter = next(
        (
            row
            for row in missing_progression_counters(fighter)
            if str(row.pk) == str(counter_id)
        ),
        None,
    )
    if counter is None:
        raise Refusal("That progression counter is already tracked or is unavailable.")
    if Assignment.objects.filter(miniature_root=fighter, counter=counter).exists():
        raise Refusal("Restore the existing counter before tracking progression.")
    assignment = op.assign(counter, miniature=fighter, caused_by=fighter.membership)
    op.open_counter(assignment, 0)
    return assignment


@transaction.atomic
def grant_recruitment_allowances(op, fighter):
    """Grant each effective recruitment allowance once, after hire is complete."""
    if not op.counter_tracking_active:
        return []
    recruitment = _membership(fighter)
    granted = []
    for access in actions_for(fighter):
        action = access.action
        if action.recruitment_allowance_rule_id is None:
            continue
        allowance, created = ActionAllowance.objects.get_or_create(
            action=action,
            fighter=fighter,
            source=recruitment,
            source_kind=ActionAllowance.Source.RECRUITMENT,
            defaults={"threshold": None, "rank_table": None},
        )
        if created:
            allowance.granted_event = op.event(
                fighter,
                LedgerEvent.Kind.GRANTED,
                note=f"Earned one use of {action} at recruitment.",
            )
            allowance.save(update_fields=["granted_event", "modified"])
            granted.append(allowance)
    return granted


@transaction.atomic
def grant_rank_allowances(
    op,
    counter_assignment,
    before,
    after,
    *,
    action_accesses=None,
    table_access=None,
):
    """Grant allowances for strictly crossed thresholds of the current table."""
    if after <= before or not op.counter_tracking_active:
        return []
    fighter = counter_assignment.miniature_root
    if fighter is None:
        return []
    counter = counter_assignment.counter
    from n26.library.models import RankAllowanceRule

    if not RankAllowanceRule.objects.filter(counter=counter).exists():
        return []

    card = computed = None
    if table_access is None or action_accesses is None:
        card = build_card(fighter)
        computed = compute(card, build_modifier_index(carriers(card)))
    if table_access is None:
        table_access = rank_table_for(fighter, counter, card=card, computed=computed)
    if table_access is None:
        return []
    table = table_access.rank_table
    recruitment = _membership(fighter)
    accesses = (
        action_accesses
        if action_accesses is not None
        else actions_for(fighter, card=card, computed=computed)
    )
    actions = [
        access.action
        for access in accesses
        if access.action.rank_allowance_rule_id
        and access.action.rank_allowance_rule.counter_id == counter.pk
    ]
    thresholds = list(
        table.thresholds.filter(threshold__gt=before, threshold__lte=after).order_by(
            "threshold"
        )
    )
    granted = []
    for action in actions:
        for threshold in thresholds:
            allowance, created = ActionAllowance.objects.get_or_create(
                action=action,
                fighter=fighter,
                source=recruitment,
                source_kind=ActionAllowance.Source.RANK,
                threshold=threshold.threshold,
                defaults={"rank_table": table},
            )
            if created:
                allowance.granted_event = op.event(
                    fighter,
                    LedgerEvent.Kind.GRANTED,
                    note=f"Earned one use of {action} at {threshold.threshold} {counter}.",
                )
                allowance.save(update_fields=["granted_event", "modified"])
                granted.append(allowance)
    return granted


def starting_counter_value(counter_assignment):
    """Return a trustworthy legacy baseline, or None when none exists."""
    opening = (
        LedgerEvent.objects.filter(
            assignment=counter_assignment,
            kind=LedgerEvent.Kind.COUNTER_OPENED,
        )
        .order_by("created")
        .values_list("counter_after", flat=True)
        .first()
    )
    if opening is not None:
        return opening
    source = counter_assignment.materialised_from
    if source is not None and source.counter_id == counter_assignment.counter_id:
        return source.amount
    return None


@transaction.atomic
def bootstrap_rank_allowances(op, counter_assignment):
    """Grant unused legacy allowances from a trustworthy starting value."""
    if not op.counter_tracking_active:
        return []
    baseline = starting_counter_value(counter_assignment)
    if baseline is None:
        return []
    try:
        current = counter_assignment.counter_value.value
    except CounterValue.DoesNotExist:
        return []
    return grant_rank_allowances(op, counter_assignment, baseline, current)


@transaction.atomic
def clone_unused_allowances(op, source, clone):
    """Copy the earned uses that were unused in the source snapshot."""
    if not op.counter_tracking_active:
        return []
    copied = []
    unused = source.action_allowances.exclude(
        records__state__in=[ActionRecord.State.STARTED, ActionRecord.State.COMPLETED]
    ).order_by("created", "pk")
    for allowance in unused:
        duplicate = ActionAllowance.objects.create(
            action=allowance.action,
            fighter=clone,
            source=clone.membership,
            source_kind=allowance.source_kind,
            threshold=allowance.threshold,
            rank_table=allowance.rank_table,
        )
        duplicate.granted_event = op.event(
            clone,
            LedgerEvent.Kind.GRANTED,
            note=f"Copied one unused use of {allowance.action} with the fighter.",
        )
        duplicate.save(update_fields=["granted_event", "modified"])
        copied.append(duplicate)
    return copied
