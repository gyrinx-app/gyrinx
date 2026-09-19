"""Transactional lifecycle for fighter action records."""

from copy import deepcopy
from dataclasses import dataclass
from uuid import uuid4

from django.db.models import Q

from n26.core.access import actions_for
from n26.core.action_payments import Balance, Quote, QuotedLine, Resource
from n26.core.models import (
    ActionAllowance,
    ActionRecord,
    AdvancementSelection,
    Assignment,
    LedgerEvent,
    Miniature,
)
from n26.core.operations import LibraryError, Refusal


@dataclass(frozen=True)
class CounterMovement:
    assignment_id: str
    name: str
    before: int
    after: int
    payment: bool

    @property
    def delta(self):
        return self.after - self.before


@dataclass(frozen=True)
class PickMovement:
    before_assignment_id: str | None
    after_assignment_id: str | None


@dataclass(frozen=True)
class ActionChanges:
    credits_paid: int
    rating_delta: int
    counters: tuple[CounterMovement, ...]
    picks: tuple[PickMovement, ...]


def action_changes(record):
    """Fold one action's linked ledger rows into receipt-ready facts."""
    events = list(
        record.ledger_events.select_related(
            "assignment__counter", "before_pick", "after_pick"
        ).order_by("created", "pk")
    )
    counter_groups = {}
    for event in events:
        if event.counter_before is None or event.assignment_id is None:
            continue
        key = (event.assignment_id, event.payment_id is not None)
        group = counter_groups.get(key)
        if group is None:
            counter_groups[key] = [event, event]
        else:
            group[1] = event
    counters = tuple(
        CounterMovement(
            assignment_id=str(first.assignment_id),
            name=str(first.assignment.counter),
            before=first.counter_before,
            after=last.counter_after,
            payment=payment,
        )
        for (_, payment), (first, last) in counter_groups.items()
    )
    amended_before = {
        event.before_pick_id
        for event in events
        if event.kind == LedgerEvent.Kind.AMENDED and event.before_pick_id
    }
    pick_events = [
        event
        for event in events
        if (
            event.kind == LedgerEvent.Kind.AMENDED
            and (event.before_pick_id or event.after_pick_id)
        )
        or (
            event.kind == LedgerEvent.Kind.REMOVED
            and event.before_pick_id
            and event.assignment_id == event.before_pick_id
            and event.before_pick_id not in amended_before
        )
    ]
    picks = tuple(
        PickMovement(
            before_assignment_id=(
                str(event.before_pick_id) if event.before_pick_id else None
            ),
            after_assignment_id=(
                str(event.after_pick_id) if event.after_pick_id else None
            ),
        )
        for event in pick_events
    )
    return ActionChanges(
        credits_paid=sum(
            event.credits_delta for event in events if event.payment_id is not None
        ),
        rating_delta=sum(
            event.rating_delta
            for event in events
            if event.kind
            in {
                LedgerEvent.Kind.ACTION_USE_COMPLETED,
                LedgerEvent.Kind.ACTION_USE_CORRECTED,
            }
        ),
        counters=counters,
        picks=picks,
    )


def _refuse_unless_owned(op, fighter):
    if (
        fighter.membership_id is None
        or fighter.membership.archived
        or fighter.membership.gang_id != op.gang.pk
    ):
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


def _allowance_source_kind(action):
    if action.recruitment_allowance_rule_id is not None:
        return ActionAllowance.Source.RECRUITMENT
    if action.rank_allowance_rule_id is not None:
        return ActionAllowance.Source.RANK
    return None


def _counter_assignment(gang, fighter, counter, payer, action):
    assignments = Assignment.objects.filter(
        counter=counter, archived=False, gang_root=gang
    )
    if payer == "fighter":
        assignments = assignments.filter(miniature_root=fighter)
    else:
        assignments = assignments.filter(gang=gang)
    matches = list(assignments.select_related("counter_value")[:2])
    if not matches:
        raise Refusal("That counter is no longer available.")
    if len(matches) != 1 or not hasattr(matches[0], "counter_value"):
        raise LibraryError(f"{action} does not resolve one {counter} balance.")
    return matches[0]


def quote_action(op, fighter, action):
    """Resolve a quote inside an operation; final checkout remains authoritative."""
    return quote_for(fighter, action, gang=op.gang)


def quote_for(fighter, action, *, gang=None):
    """Read a display quote without starting or mutating an action record."""
    gang = gang or fighter.gang
    if gang is None:
        raise Refusal("That fighter is no longer in a gang.")
    lines = []
    credits_available = None
    credits_quoted = False
    for component in action.use_price.select_related("counter").all():
        if component.resource == component.Resource.CREDITS:
            balance = Balance(Resource.CREDITS, str(gang.pk))
            if not credits_quoted:
                credits_available = gang.recompute_credits()
                credits_quoted = True
            available = credits_available
            name = "Credits"
        else:
            assignment = _counter_assignment(
                gang,
                fighter,
                component.counter,
                component.payer,
                component.action,
            )
            balance = Balance(Resource.COUNTER, str(gang.pk), str(assignment.pk))
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
        "recruitment_allowance_rule": (
            str(action.recruitment_allowance_rule_id)
            if action.recruitment_allowance_rule_id
            else None
        ),
        "rank_allowance_rule": (
            str(action.rank_allowance_rule_id)
            if action.rank_allowance_rule_id
            else None
        ),
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


def _post_payment_counters(quote):
    """Counter balances after the reviewed coalesced price is paid."""
    return {
        line.balance.assignment_id: line.after_payment
        for line in quote.lines
        if line.balance.resource == Resource.COUNTER
    }


def _target_snapshot(record, configured, terms, *, quote=None):
    """Exact player state a typed outcome will read when it writes."""
    from n26.library.models import ApplyChanges, AugmentCarriedItem, ResolveAdvancement

    if isinstance(configured, ApplyChanges):
        values = []
        simulated = {}
        # A normal review supplies its final quote and previews the state after
        # payment. Correction previews omit it because corrections never repay.
        projected = _post_payment_counters(quote) if quote is not None else {}
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
                before = simulated.setdefault(
                    assignment.pk,
                    projected.get(str(assignment.pk), assignment.counter_value.value),
                )
                after = before + _counter_change_delta(member.counter_change, before)
                simulated[assignment.pk] = after
                values.append(
                    {
                        "kind": "counter",
                        "assignment": str(assignment.pk),
                        "name": str(member.counter_change.counter),
                        "before": before,
                        "after": after,
                    }
                )
            else:
                picks = Assignment.objects.filter(
                    miniature_root=record.fighter,
                    archived=False,
                    pickable__slot_type=member.remove_picks.slot_type,
                ).order_by("created", "pk")
                values.append(
                    {
                        "kind": "picks",
                        "slot_type": str(member.remove_picks.slot_type),
                        "slot_type_id": str(member.remove_picks.slot_type_id),
                        "removed_count": len(picks),
                        "assignments": [str(row.pk) for row in picks],
                    }
                )
        return values
    if isinstance(configured, AugmentCarriedItem):
        try:
            from n26.core.augmentations import preview_augmentation
        except ModuleNotFoundError as error:
            if error.name != "n26.core.augmentations":
                raise
            raise Refusal(
                "Item augmentation is not available in this build."
            ) from error

        return preview_augmentation(
            record,
            configured,
            deepcopy(terms),
            projected=_post_payment_counters(quote) if quote is not None else None,
        )
    if isinstance(configured, ResolveAdvancement):
        try:
            from n26.core.advancements import preview_advancement
        except ModuleNotFoundError as error:
            if error.name != "n26.core.advancements":
                raise
            raise Refusal(
                "Fighter advancement is not available in this build."
            ) from error

        return preview_advancement(record, configured, deepcopy(terms))
    raise LibraryError(f"{type(configured).__name__} is not handled yet.")


def start_action(op, fighter, action, request_key, allowance=None):
    fighter = Miniature.objects.select_related("membership").get(pk=fighter.pk)
    _refuse_unless_owned(op, fighter)
    existing = ActionRecord.objects.filter(
        gang=op.gang, request_key=request_key
    ).first()
    if existing is not None:
        if existing.fighter_id != fighter.pk or existing.action_id != action.pk:
            raise Refusal("That request key belongs to another action use.")
        return existing
    if not op.counter_tracking_active:
        raise Refusal(
            "Fighter actions are unavailable until counter tracking is active."
        )

    rule = action.allowance_rule
    source_kind = _allowance_source_kind(action)
    if allowance is not None:
        allowance = ActionAllowance.objects.select_for_update().get(pk=allowance.pk)
        if (
            rule is None
            or allowance.fighter_id != fighter.pk
            or allowance.action_id != action.pk
            or allowance.source_id != fighter.membership_id
            or allowance.source_kind != source_kind
        ):
            raise Refusal("That allowance belongs to another action use.")
        if allowance.records.filter(
            state__in=[ActionRecord.State.STARTED, ActionRecord.State.COMPLETED]
        ).exists():
            raise Refusal("That allowance is already being used.")
    elif rule is not None:
        allowance = (
            ActionAllowance.objects.select_for_update()
            .filter(
                action=action,
                fighter=fighter,
                source=fighter.membership,
                source_kind=source_kind,
            )
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


def _validate_draft_definition(record):
    """Reject a draft whose free/earned-use contract changed after it began."""
    if record.allowance_id is None:
        if record.action.allowance_rule is not None:
            raise Refusal(
                "That action now requires an earned allowance. Start it again."
            )
        if not _has_access(record.fighter, record.action):
            raise Refusal("That fighter can no longer use this action.")
        return
    allowance = record.allowance
    source_kind = _allowance_source_kind(record.action)
    if (
        source_kind is None
        or allowance.source_kind != source_kind
        or allowance.fighter_id != record.fighter_id
        or allowance.action_id != record.action_id
        or allowance.source_id != record.fighter.membership_id
    ):
        raise Refusal("That allowance belongs to another action use.")


def _validate_recorded_outcome(record, outcome):
    from n26.library.models import ResolveAdvancement

    selection = (
        AdvancementSelection.objects.filter(
            action_record=record, roll_event__isnull=False
        )
        .select_related("slot_assignment")
        .first()
    )
    if selection is None:
        return
    configured = outcome.operation
    if (
        (record.outcome_id is not None and record.outcome_id != outcome.pk)
        or not isinstance(configured, ResolveAdvancement)
        or configured.slot_id != selection.slot_assignment.slot_id
    ):
        raise Refusal(
            "You cannot change the outcome after recording its advancement roll."
        )


def review_action(op, record, *, outcome, terms=None):
    record = _locked(op, record)
    _refuse_unless_owned(op, record.fighter)
    if record.state != ActionRecord.State.STARTED:
        raise Refusal("That action use is no longer awaiting confirmation.")
    _validate_draft_definition(record)
    _validate_recorded_outcome(record, outcome)
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
        "target": _target_snapshot(record, configured, record.terms, quote=quote),
        "terms": record.terms,
    }
    record.outcome = outcome
    record.save(update_fields=["outcome", "revision", "terms", "review", "modified"])
    return record


def save_action_choices(op, record, *, outcome, terms):
    """Save an explicit draft step without running its typed preview."""
    record = _locked(op, record)
    _refuse_unless_owned(op, record.fighter)
    if record.state != ActionRecord.State.STARTED:
        raise Refusal("That action use is no longer being selected.")
    _validate_draft_definition(record)
    if not record.action.outcomes.filter(outcome=outcome).exists():
        raise Refusal("That outcome is not available for this action.")
    supplied = deepcopy(terms)
    _validate_recorded_outcome(record, outcome)
    supplied.pop("outcome", None)
    previous = record.terms if record.outcome_id == outcome.pk else {}
    record.terms = {**previous, **supplied, "outcome": str(outcome.pk)}
    record.outcome = outcome
    record.revision += 1
    record.review = {}
    record.save(update_fields=["outcome", "terms", "revision", "review", "modified"])
    return record


def _plan_apply_changes(op, record, operation, quote):
    changes = list(
        operation.changes.select_related(
            "counter_change__counter", "remove_picks__slot_type"
        )
    )
    planned = []
    simulated = {}
    starting = {}
    projected = _post_payment_counters(quote)
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
            initial = projected.get(str(assignment.pk), assignment.counter_value.value)
            before = simulated.setdefault(assignment.pk, initial)
            starting.setdefault(assignment.pk, initial)
            delta = _counter_change_delta(configured, before)
            simulated[assignment.pk] = before + delta
            planned.append(("counter", assignment.pk, configured))
        else:
            picks = list(
                Assignment.objects.filter(
                    miniature_root=record.fighter,
                    archived=False,
                    pickable__slot_type=change.remove_picks.slot_type,
                ).order_by("created", "pk")
            )
            planned.append(("picks", picks, None))
    changed_counter = any(
        after != starting[assignment_id] for assignment_id, after in simulated.items()
    )
    if not changed_counter and not any(
        kind == "picks" and target for kind, target, _ in planned
    ):
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


def _prepare_outcome(op, record, configured, quote):
    """Validate one typed outcome and return its transactional writer."""
    from n26.library.models import ApplyChanges, AugmentCarriedItem, ResolveAdvancement

    if isinstance(configured, ApplyChanges):
        planned = _plan_apply_changes(op, record, configured, quote)
        return lambda: _apply_changes(op, record, planned)
    if isinstance(configured, AugmentCarriedItem):
        try:
            from n26.core.augmentations import apply_augmentation
        except ModuleNotFoundError as error:
            if error.name != "n26.core.augmentations":
                raise
            raise Refusal(
                "Item augmentation is not available in this build."
            ) from error

        return lambda: apply_augmentation(
            op, record, configured, deepcopy(record.terms)
        )
    if isinstance(configured, ResolveAdvancement):
        try:
            from n26.core.advancements import apply_advancement
        except ModuleNotFoundError as error:
            if error.name != "n26.core.advancements":
                raise
            raise Refusal(
                "Fighter advancement is not available in this build."
            ) from error

        return lambda: apply_advancement(op, record, configured, deepcopy(record.terms))
    raise LibraryError(f"{type(configured).__name__} is not handled yet.")


def _pay(op, record, quote):
    payment_id = uuid4() if quote.lines else None
    if payment_id is not None:
        op.event(
            record.fighter,
            LedgerEvent.Kind.ACTION_USE_PAID,
            credits_delta=sum(
                line.amount
                for line in quote.lines
                if line.balance.resource == Resource.CREDITS
            ),
            action_record=record,
            payment_id=payment_id,
            note=str(record.action),
        )
    for line in quote.lines:
        if line.after_payment is not None and line.after_payment < 0:
            raise Refusal(f"There is not enough {line.name} to use this action.")
        if line.balance.resource == Resource.COUNTER:
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
    if record.state == ActionRecord.State.COMPLETED:
        return record
    _refuse_unless_owned(op, record.fighter)
    if not op.counter_tracking_active:
        raise Refusal(
            "Fighter actions are unavailable until counter tracking is active."
        )
    if record.state != ActionRecord.State.STARTED:
        raise Refusal("That action use is no longer awaiting confirmation.")
    if revision != record.revision or review != record.review:
        raise Refusal("Review this action again before confirming it.")
    _validate_draft_definition(record)
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
    if _target_snapshot(
        record, configured, record.terms, quote=quote
    ) != record.review.get("target"):
        raise Refusal("The fighter changed. Review this action again.")
    apply_outcome = _prepare_outcome(op, record, configured, quote)
    rating_before = record.fighter.recompute_rating()
    _pay(op, record, quote)
    apply_outcome()
    rating_after = record.fighter.recompute_rating()
    record.outcome = outcome
    record.state = ActionRecord.State.COMPLETED
    record.completed_event = op.event(
        record.fighter,
        LedgerEvent.Kind.ACTION_USE_COMPLETED,
        action_record=record,
        rating_delta=rating_after - rating_before,
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
    if AdvancementSelection.objects.filter(
        action_record=record, roll_event__isnull=False
    ).exists():
        raise Refusal("A recorded advancement roll must be resumed.")
    record.state = ActionRecord.State.CANCELLED
    op.event(
        record.fighter,
        LedgerEvent.Kind.ACTION_USE_CANCELLED,
        action_record=record,
        note=str(record.action),
    )
    record.save(update_fields=["state", "modified"])
    return record


def review_action_correction(op, record, *, terms):
    """Fingerprint the completed result a proposed correction would replace."""
    record = _locked(op, record)
    _refuse_unless_owned(op, record.fighter)
    if record.state != ActionRecord.State.COMPLETED or record.outcome_id is None:
        raise Refusal("That action use has no completed result to correct.")
    configured = record.outcome.operation
    from n26.library.models import AugmentCarriedItem, ResolveAdvancement

    if not isinstance(configured, (AugmentCarriedItem, ResolveAdvancement)):
        raise Refusal("That action result cannot be corrected here.")
    proposed = deepcopy(terms)
    record.revision += 1
    record.review = {
        "correction": True,
        "content": _content_snapshot(record.action),
        "target": _target_snapshot(record, configured, proposed),
        "terms": proposed,
    }
    record.save(update_fields=["revision", "review", "modified"])
    return record


def correct_action(op, record, *, revision, review, terms):
    """Verify and run a typed safe correction under both locks."""
    record = _locked(op, record)
    _refuse_unless_owned(op, record.fighter)
    if record.state != ActionRecord.State.COMPLETED or record.outcome_id is None:
        raise Refusal("That action use has no completed result to correct.")
    proposed = deepcopy(terms)
    if (
        revision != record.revision
        or review != record.review
        or record.review.get("correction") is not True
        or proposed != record.review.get("terms")
    ):
        raise Refusal("Review this correction again before confirming it.")
    configured = record.outcome.operation
    if _content_snapshot(record.action) != record.review.get("content"):
        raise Refusal("The action changed. Review this correction again.")
    if _target_snapshot(record, configured, proposed) != record.review.get("target"):
        raise Refusal("The fighter changed. Review this correction again.")
    from n26.library.models import AugmentCarriedItem, ResolveAdvancement

    rating_before = record.fighter.recompute_rating()
    if isinstance(configured, AugmentCarriedItem):
        from n26.core.augmentations import correct_augmentation

        result = correct_augmentation(op, record, configured, proposed)
    elif isinstance(configured, ResolveAdvancement):
        from n26.core.advancements import correct_advancement

        result = correct_advancement(op, record, configured, proposed)
    else:
        raise Refusal("That action result cannot be corrected here.")
    rating_after = record.fighter.recompute_rating()
    op.event(
        record.fighter,
        LedgerEvent.Kind.ACTION_USE_CORRECTED,
        action_record=record,
        rating_delta=rating_after - rating_before,
        note=str(record.outcome),
    )
    record.terms = proposed
    record.review = {"correction_completed": True, "revision": record.revision}
    record.save(update_fields=["terms", "review", "modified"])
    return record, result
