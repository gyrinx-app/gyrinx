"""Grant durable fighter-action allowances at their two rule boundaries."""

from django.db import transaction

from n26.core.access import actions_for, rank_table_for
from n26.core.models import ActionAllowance, CounterValue, LedgerEvent


def _membership(fighter):
    membership = fighter.membership
    if membership is None:
        raise ValueError("An action allowance needs a recruited fighter.")
    return membership


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
def grant_rank_allowances(op, counter_assignment, before, after):
    """Grant allowances for strictly crossed thresholds of the current table."""
    if after <= before or not op.counter_tracking_active:
        return []
    fighter = counter_assignment.miniature_root
    if fighter is None:
        return []
    counter = counter_assignment.counter
    table_access = rank_table_for(fighter, counter)
    if table_access is None:
        return []
    table = table_access.rank_table
    recruitment = _membership(fighter)
    actions = [
        access.action
        for access in actions_for(fighter)
        if access.action.rank_allowance_rule_id
        and access.action.rank_allowance_rule.counter_id == counter.pk
    ]
    thresholds = list(
        table.thresholds.filter(threshold__gt=before, threshold__lte=after)
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
        records__state__in=["started", "completed"]
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
