"""Transactional lifecycle for fighter action records."""

from copy import deepcopy
from uuid import uuid4

from django.db.models import Q

from n26.core.access import actions_for
from n26.core.action_payments import Balance, Quote, QuotedLine, Resource
from n26.core.models import ActionAllowance, ActionRecord, Assignment, LedgerEvent
from n26.core.operations import LibraryError, Refusal


def _refuse_unless_owned(op, fighter):
    if fighter.membership_id is None or fighter.membership.gang_id != op.gang.pk:
        raise Refusal("That fighter is no longer in this gang.")


def _has_access(fighter, action):
    return any(access.action.pk == action.pk for access in actions_for(fighter))


def _source_assignment(fighter, action):
    return (
        Assignment.objects.filter(
            Q(miniature_root=fighter) | Q(gang=fighter.gang),
            action=action,
            archived=False,
        )
        .order_by("created", "pk")
        .first()
    )


def _counter_assignment(gang, fighter, counter, payer, action):
    assignments = Assignment.objects.filter(
        counter=counter, archived=False, gang_root=gang
    )
    if payer == "fighter":
        assignments = assignments.filter(miniature_root=fighter)
    else:
        assignments = assignments.filter(gang=gang)
    matches = list(assignments.select_related("counter_value")[:2])
    if len(matches) != 1 or not hasattr(matches[0], "counter_value"):
        raise LibraryError(f"{action} does not resolve one {counter} balance.")
    return matches[0]


def quote_action(op, fighter, action):
    """Resolve authored components to immutable current balances."""
    lines = []
    for component in action.use_price.select_related("counter").all():
        if component.resource == component.Resource.CREDITS:
            balance = Balance(Resource.CREDITS, str(op.gang.pk))
            available = op.gang.recompute_credits()
            name = "Credits"
        else:
            assignment = _counter_assignment(
                op.gang,
                fighter,
                component.counter,
                component.payer,
                component.action,
            )
            balance = Balance(Resource.COUNTER, str(op.gang.pk), str(assignment.pk))
            available = assignment.counter_value.value
            name = str(component.counter)
        lines.append(
            QuotedLine(
                balance=balance,
                amount=component.amount,
                available=available,
                position=component.position,
                name=name,
            )
        )
    return Quote.coalesce(lines)


def _content_snapshot(action):
    """Content facts whose change requires another player review."""
    outcomes = []
    for member in action.outcomes.select_related(
        "outcome__augment_carried_item",
        "outcome__resolve_advancement",
        "outcome__apply_changes",
    ):
        configured = member.outcome.operation
        if configured is None:
            raise LibraryError(f"{member.outcome} has no operation.")
        outcomes.append(
            {
                "membership": str(member.pk),
                "membership_modified": member.modified.isoformat(),
                "outcome": str(member.outcome_id),
                "outcome_modified": member.outcome.modified.isoformat(),
                "operation": type(configured).__name__,
                "operation_id": str(configured.pk),
                "operation_modified": configured.modified.isoformat(),
                "configuration": _operation_snapshot(configured),
            }
        )
    return {
        "action": str(action.pk),
        "action_modified": action.modified.isoformat(),
        "outcomes": outcomes,
    }


def _operation_snapshot(configured):
    from n26.library.models import ApplyChanges, AugmentCarriedItem, ResolveAdvancement

    if isinstance(configured, AugmentCarriedItem):
        return {"slot_type": str(configured.slot_type_id)}
    if isinstance(configured, ResolveAdvancement):
        return {"slot": str(configured.slot_id)}
    if isinstance(configured, ApplyChanges):
        values = []
        for member in configured.changes.select_related(
            "counter_change", "remove_picks"
        ):
            if member.counter_change_id:
                change = member.counter_change
                value = {
                    "kind": "counter",
                    "counter": str(change.counter_id),
                    "mode": change.mode,
                    "amount": change.amount,
                }
            else:
                change = member.remove_picks
                value = {"kind": "remove_picks", "slot_type": str(change.slot_type_id)}
            values.append(
                {
                    "membership": str(member.pk),
                    "membership_modified": member.modified.isoformat(),
                    "change": str(change.pk),
                    "change_modified": change.modified.isoformat(),
                    **value,
                }
            )
        return values
    raise LibraryError(f"{type(configured).__name__} is not handled yet.")


def _target_snapshot(record, configured, terms):
    """Exact player state a typed outcome will read when it writes."""
    from n26.library.models import ApplyChanges, AugmentCarriedItem, ResolveAdvancement

    if isinstance(configured, ApplyChanges):
        values = []
        for member in configured.changes.select_related(
            "counter_change__counter", "remove_picks__slot_type"
        ):
            if member.counter_change_id:
                assignment = _counter_assignment(
                    record.gang,
                    record.fighter,
                    member.counter_change.counter,
                    "fighter",
                    record.action,
                )
                values.append(
                    {
                        "kind": "counter",
                        "assignment": str(assignment.pk),
                        "value": assignment.counter_value.value,
                    }
                )
            else:
                picks = Assignment.objects.filter(
                    miniature_root=record.fighter,
                    archived=False,
                    pickable__slot_type=member.remove_picks.slot_type,
                ).order_by("created", "pk")
                values.append(
                    {"kind": "picks", "assignments": [str(row.pk) for row in picks]}
                )
        return values
    if isinstance(configured, AugmentCarriedItem):
        from n26.core.augmentations import preview_augmentation

        return preview_augmentation(record, configured, deepcopy(terms))
    if isinstance(configured, ResolveAdvancement):
        from n26.core.advancements import preview_advancement

        return preview_advancement(record, configured, deepcopy(terms))
    raise LibraryError(f"{type(configured).__name__} is not handled yet.")


def start_action(op, fighter, action, request_key, allowance=None):
    _refuse_unless_owned(op, fighter)
    existing = ActionRecord.objects.filter(
        gang=op.gang, request_key=request_key
    ).first()
    if existing is not None:
        if existing.fighter_id != fighter.pk or existing.action_id != action.pk:
            raise Refusal("That request key belongs to another action use.")
        return existing

    rule = action.allowance_rule
    if allowance is not None:
        allowance = ActionAllowance.objects.select_for_update().get(pk=allowance.pk)
        if (
            rule is None
            or allowance.fighter_id != fighter.pk
            or allowance.action_id != action.pk
            or allowance.recruitment_id != fighter.membership_id
        ):
            raise Refusal("That allowance belongs to another action use.")
        if allowance.records.filter(
            state__in=[ActionRecord.State.STARTED, ActionRecord.State.COMPLETED]
        ).exists():
            raise Refusal("That allowance is already being used.")
    elif rule is not None:
        allowance = (
            ActionAllowance.objects.select_for_update()
            .filter(action=action, fighter=fighter, recruitment=fighter.membership)
            .exclude(
                records__state__in=[
                    ActionRecord.State.STARTED,
                    ActionRecord.State.COMPLETED,
                ]
            )
            .order_by("created", "pk")
            .first()
        )
        if allowance is None:
            raise Refusal("This fighter has no unused allowance for that action.")
    elif not _has_access(fighter, action):
        raise Refusal("That fighter can no longer use this action.")

    source_assignment = _source_assignment(fighter, action)
    record = ActionRecord.objects.create(
        gang=op.gang,
        fighter=fighter,
        action=action,
        allowance=allowance,
        request_key=request_key,
        source_assignment=source_assignment,
        source={
            "action": str(action.pk),
            "name": str(action),
            "assignment": str(source_assignment.pk) if source_assignment else None,
        },
    )
    record.started_event = op.event(
        fighter,
        LedgerEvent.Kind.ACTION_USE_STARTED,
        action_record=record,
        note=str(action),
    )
    record.save(update_fields=["started_event", "modified"])
    return record


def _locked(op, record):
    locked = (
        ActionRecord.objects.select_for_update(of=("self",))
        .select_related("fighter", "fighter__membership", "action", "allowance")
        .filter(pk=record.pk, gang=op.gang)
        .first()
    )
    if locked is None:
        raise Refusal("That action use does not belong to this gang.")
    return locked


def review_action(op, record, *, outcome, terms=None):
    record = _locked(op, record)
    _refuse_unless_owned(op, record.fighter)
    if record.state != ActionRecord.State.STARTED:
        raise Refusal("That action use is no longer awaiting confirmation.")
    if record.allowance_id is None and not _has_access(record.fighter, record.action):
        raise Refusal("That fighter can no longer use this action.")
    if not record.action.outcomes.filter(outcome=outcome).exists():
        raise Refusal("That outcome is not available for this action.")
    quote = quote_action(op, record.fighter, record.action)
    record.revision += 1
    record.terms = {**deepcopy(terms or {}), "outcome": str(outcome.pk)}
    configured = outcome.operation
    if configured is None:
        raise LibraryError(f"{outcome} has no operation.")
    record.review = {
        "price": quote.snapshot(),
        "content": _content_snapshot(record.action),
        "target": _target_snapshot(record, configured, record.terms),
        "terms": record.terms,
    }
    record.save(update_fields=["revision", "terms", "review", "modified"])
    return record


def _plan_apply_changes(op, record, operation):
    changes = list(
        operation.changes.select_related(
            "counter_change__counter", "remove_picks__slot_type"
        )
    )
    planned = []
    meaningful = False
    for change in changes:
        if change.counter_change_id:
            configured = change.counter_change
            assignment = _counter_assignment(
                op.gang,
                record.fighter,
                configured.counter,
                "fighter",
                record.action,
            )
            before = assignment.counter_value.value
            delta = _counter_change_delta(configured, before)
            meaningful = meaningful or delta != 0
            planned.append(("counter", assignment.pk, configured))
        else:
            picks = list(
                Assignment.objects.filter(
                    miniature_root=record.fighter,
                    archived=False,
                    pickable__slot_type=change.remove_picks.slot_type,
                ).order_by("created", "pk")
            )
            meaningful = meaningful or bool(picks)
            planned.append(("picks", picks, None))
    if not meaningful:
        raise Refusal("That outcome would not change this fighter.")
    return planned


def _apply_changes(op, record, planned):
    for kind, target, configured in planned:
        if kind == "counter":
            assignment = Assignment.objects.select_related("counter_value").get(
                pk=target, gang_root=op.gang, archived=False
            )
            op.tally(
                assignment,
                _counter_change_delta(configured, assignment.counter_value.value),
                action_record=record,
            )
        else:
            for pick in target:
                op.remove(pick, action_record=record, before_pick=pick)


def _counter_change_delta(configured, before):
    if configured.amount < 0:
        raise LibraryError(f"{configured} has a negative counter amount.")
    if configured.mode == configured.Mode.SET:
        return configured.amount - before
    if configured.mode == configured.Mode.ADD:
        return configured.amount
    return -min(before, configured.amount)


def _prepare_outcome(op, record, configured):
    """Validate one typed outcome and return its transactional writer."""
    from n26.library.models import ApplyChanges, AugmentCarriedItem

    if isinstance(configured, ApplyChanges):
        planned = _plan_apply_changes(op, record, configured)
        return lambda: _apply_changes(op, record, planned)
    if isinstance(configured, AugmentCarriedItem):
        from n26.core.augmentations import apply_augmentation

        return lambda: apply_augmentation(
            op, record, configured, deepcopy(record.terms)
        )
    raise LibraryError(f"{type(configured).__name__} is not handled yet.")


def _pay(op, record, quote):
    payment_id = uuid4() if quote.lines else None
    for line in quote.lines:
        if line.after_payment < 0:
            raise Refusal(f"There is not enough {line.name} to use this action.")
        if line.balance.resource == Resource.CREDITS:
            op.event(
                None,
                LedgerEvent.Kind.ACTION_USE_PAID,
                credits_delta=line.amount,
                action_record=record,
                payment_id=payment_id,
                note=str(record.action),
            )
        else:
            assignment = Assignment.objects.select_related("counter_value").get(
                pk=line.balance.assignment_id, gang_root=op.gang, archived=False
            )
            if assignment.counter_value.value < line.amount:
                raise Refusal(f"There is not enough {line.name} to use this action.")
            op.tally(
                assignment,
                -line.amount,
                action_record=record,
                payment_id=payment_id,
                note=str(record.action),
            )
    record.payment_id = payment_id


def complete_action(op, record, *, revision, review, outcome):
    record = _locked(op, record)
    _refuse_unless_owned(op, record.fighter)
    if record.state == ActionRecord.State.COMPLETED:
        return record
    if record.state != ActionRecord.State.STARTED:
        raise Refusal("That action use is no longer awaiting confirmation.")
    if revision != record.revision or review != record.review:
        raise Refusal("Review this action again before confirming it.")
    if record.allowance_id is None and not _has_access(record.fighter, record.action):
        raise Refusal("That fighter can no longer use this action.")
    if record.terms.get("outcome") != str(outcome.pk):
        raise Refusal("Review this outcome again before confirming it.")
    outcome_member = (
        record.action.outcomes.select_related(
            "outcome__augment_carried_item",
            "outcome__resolve_advancement",
            "outcome__apply_changes",
        )
        .filter(outcome_id=outcome.pk)
        .first()
    )
    if outcome_member is None:
        raise Refusal("That outcome is not available for this action.")
    outcome = outcome_member.outcome
    quote = quote_action(op, record.fighter, record.action)
    if not quote.matches(record.review.get("price", [])):
        raise Refusal("The price changed. Review this action again.")
    if _content_snapshot(record.action) != record.review.get("content"):
        raise Refusal("The action changed. Review it again before confirming.")
    configured = outcome.operation
    if configured is None:
        raise LibraryError(f"{outcome} has no operation.")
    if _target_snapshot(record, configured, record.terms) != record.review.get(
        "target"
    ):
        raise Refusal("The fighter changed. Review this action again.")
    apply_outcome = _prepare_outcome(op, record, configured)
    _pay(op, record, quote)
    apply_outcome()
    record.outcome = outcome
    record.state = ActionRecord.State.COMPLETED
    record.completed_event = op.event(
        record.fighter,
        LedgerEvent.Kind.ACTION_USE_COMPLETED,
        action_record=record,
        note=str(outcome),
    )
    record.save(
        update_fields=[
            "outcome",
            "state",
            "payment_id",
            "completed_event",
            "modified",
        ]
    )
    return record


def cancel_action(op, record):
    record = _locked(op, record)
    _refuse_unless_owned(op, record.fighter)
    if record.state == ActionRecord.State.CANCELLED:
        return record
    if record.state != ActionRecord.State.STARTED or record.payment_id is not None:
        raise Refusal("That action use can no longer be cancelled.")
    record.state = ActionRecord.State.CANCELLED
    op.event(
        record.fighter,
        LedgerEvent.Kind.ACTION_USE_CANCELLED,
        action_record=record,
        note=str(record.action),
    )
    record.save(update_fields=["state", "modified"])
    return record


def correct_action(op, record, *, terms):
    """Run a typed safe correction under the action and gang locks."""
    record = _locked(op, record)
    _refuse_unless_owned(op, record.fighter)
    if record.state != ActionRecord.State.COMPLETED or record.outcome_id is None:
        raise Refusal("That action use has no completed result to correct.")
    configured = record.outcome.operation
    from n26.library.models import AugmentCarriedItem

    if isinstance(configured, AugmentCarriedItem):
        from n26.core.augmentations import correct_augmentation

        result = correct_augmentation(op, record, configured, deepcopy(terms))
    else:
        raise Refusal("That action result cannot be corrected here.")
    record.terms = deepcopy(terms)
    record.revision += 1
    record.save(update_fields=["terms", "revision", "modified"])
    return record, result
