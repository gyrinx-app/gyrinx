import uuid

import pytest

from n26.core.action_records import action_changes
from n26.core.models import ActionAllowance, ActionRecord, Gang, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.library import authoring
from n26.library.models import Action, ApplyChange, Counter, Pickable, SlotType

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def gang(user, gang_type):
    return Gang.objects.create(
        name="The Long Hunt",
        owner=user,
        gang_type=gang_type,
        starting_credits=1000,
        credits=1000,
    )


@pytest.fixture
def fighter(user, gang, make_profile, make_statline):
    profile = make_profile("Hunter", price=100)
    make_statline(profile)
    with operation(gang, actor=user) as op:
        return op.hire(profile, "Kara", paid=100)


def configured_action(
    user, gang, fighter, *, counter_value=5, credits=20, counter_price=True
):
    resource = Counter.objects.create(name="Glitches")
    configured = authoring.apply_changes(authoring.counter_change(resource, "set", 0))
    outcome = authoring.create_outcome("Clear glitches", configured)
    use_price = [{"resource": "credits", "payer": "gang", "amount": credits}]
    if counter_price:
        use_price += [
            {
                "resource": "counter",
                "payer": "fighter",
                "counter": resource,
                "amount": 2,
            },
            {
                "resource": "counter",
                "payer": "fighter",
                "counter": resource,
                "amount": 1,
            },
        ]
    action = authoring.create_action(
        "Maintain suit",
        Action.Timing.POST_CYCLE,
        outcomes=[outcome],
        use_price=use_price,
    )
    with operation(gang, actor=user) as op:
        access = op.assign(action, miniature=fighter)
        held = op.assign(resource, miniature=fighter)
        op.tally(held, counter_value)
    return action, outcome, access, held


def start_and_review(user, gang, fighter, action, outcome):
    with operation(gang, actor=user) as op:
        record = op.start_action(fighter, action, uuid.uuid4())
    with operation(gang, actor=user) as op:
        return op.review_action(record, outcome=outcome, terms={"screen": "confirm"})


def test_mixed_repeated_price_is_paid_atomically(user, gang, fighter):
    action, outcome, _, held = configured_action(user, gang, fighter)
    record = start_and_review(user, gang, fighter, action, outcome)
    assert [(line["resource"], line["amount"]) for line in record.review["price"]] == [
        ("credits", 20),
        ("counter", 3),
    ]

    with operation(gang, actor=user) as op:
        completed = op.complete_action(
            record,
            revision=record.revision,
            review=record.review,
            outcome=outcome,
        )

    held.counter_value.refresh_from_db()
    gang.refresh_from_db()
    assert completed.state == ActionRecord.State.COMPLETED
    assert held.counter_value.value == 0
    assert gang.credits == 880
    payments = LedgerEvent.objects.filter(payment_id=completed.payment_id)
    assert payments.count() == 2
    assert sum(event.credits_delta for event in payments) == 20
    assert sum(event.counter_delta or 0 for event in payments) == -3
    changes = action_changes(completed)
    assert changes.credits_paid == 20
    assert changes.rating_delta == 0
    assert [
        (change.before, change.after, change.payment) for change in changes.counters
    ] == [
        (5, 2, True),
        (2, 0, False),
    ]


def test_insufficient_coalesced_counter_rolls_back_everything(user, gang, fighter):
    action, outcome, _, held = configured_action(user, gang, fighter, counter_value=2)
    record = start_and_review(user, gang, fighter, action, outcome)
    with pytest.raises(Refusal, match="enough Glitches"):
        with operation(gang, actor=user) as op:
            op.complete_action(
                record,
                revision=record.revision,
                review=record.review,
                outcome=outcome,
            )
    record.refresh_from_db()
    held.counter_value.refresh_from_db()
    assert record.state == ActionRecord.State.STARTED
    assert held.counter_value.value == 2
    assert not LedgerEvent.objects.filter(
        action_record=record, payment_id__isnull=False
    )


def test_changed_balance_requires_a_new_review(user, gang, fighter):
    action, outcome, _, held = configured_action(user, gang, fighter)
    record = start_and_review(user, gang, fighter, action, outcome)
    with operation(gang, actor=user) as op:
        op.tally(held, 1)
    with pytest.raises(Refusal, match="price changed"):
        with operation(gang, actor=user) as op:
            op.complete_action(
                record,
                revision=record.revision,
                review=record.review,
                outcome=outcome,
            )


def test_duplicate_confirmation_returns_the_same_receipt(user, gang, fighter):
    action, outcome, _, _ = configured_action(user, gang, fighter)
    record = start_and_review(user, gang, fighter, action, outcome)
    with operation(gang, actor=user) as op:
        first = op.complete_action(
            record,
            revision=record.revision,
            review=record.review,
            outcome=outcome,
        )
    before = LedgerEvent.objects.filter(action_record=first).count()
    with operation(gang, actor=user) as op:
        second = op.complete_action(record, revision=0, review={}, outcome=outcome)
    assert second.pk == first.pk
    assert LedgerEvent.objects.filter(action_record=first).count() == before


def test_unpaid_draft_rechecks_removed_access(user, gang, fighter):
    action, outcome, access, _ = configured_action(user, gang, fighter)
    record = start_and_review(user, gang, fighter, action, outcome)
    with operation(gang, actor=user) as op:
        op.remove(access)
    with pytest.raises(Refusal, match="no longer use"):
        with operation(gang, actor=user) as op:
            op.complete_action(
                record,
                revision=record.revision,
                review=record.review,
                outcome=outcome,
            )


def test_earned_allowance_survives_removed_access(user, gang, fighter):
    action, outcome, access, _ = configured_action(user, gang, fighter)
    action.use_price.all().delete()
    action.recruitment_allowance_rule = authoring.recruitment_allowance_rule()
    action.save(update_fields=["recruitment_allowance_rule", "modified"])
    allowance = ActionAllowance.objects.create(
        action=action,
        fighter=fighter,
        recruitment=fighter.membership,
        source_kind=ActionAllowance.Source.RECRUITMENT,
    )
    with operation(gang, actor=user) as op:
        record = op.start_action(fighter, action, uuid.uuid4(), allowance=allowance)
        op.remove(access)
    with operation(gang, actor=user) as op:
        record = op.review_action(record, outcome=outcome)
    with operation(gang, actor=user) as op:
        completed = op.complete_action(
            record,
            revision=record.revision,
            review=record.review,
            outcome=outcome,
        )
    assert completed.state == ActionRecord.State.COMPLETED


def test_allowance_action_refuses_an_unearned_use(user, gang, fighter):
    action, _, _, _ = configured_action(user, gang, fighter)
    action.use_price.all().delete()
    action.recruitment_allowance_rule = authoring.recruitment_allowance_rule()
    action.save(update_fields=["recruitment_allowance_rule", "modified"])
    with pytest.raises(Refusal, match="no unused allowance"):
        with operation(gang, actor=user) as op:
            op.start_action(fighter, action, uuid.uuid4())


def test_ordered_counter_changes_with_the_same_final_value_are_refused(
    user, gang, fighter
):
    counter = Counter.objects.create(name="Heat")
    configured = authoring.apply_changes(
        authoring.counter_change(counter, "add", 1),
        authoring.counter_change(counter, "subtract", 1),
    )
    outcome = authoring.create_outcome("Cycle heat", configured)
    action = authoring.create_action(
        "Cycle", Action.Timing.POST_CYCLE, outcomes=[outcome]
    )
    with operation(gang, actor=user) as op:
        op.assign(action, miniature=fighter)
        held = op.assign(counter, miniature=fighter)
        op.open_counter(held, 2)
        record = op.start_action(fighter, action, uuid.uuid4())
        record = op.review_action(record, outcome=outcome)
        with pytest.raises(Refusal, match="would not change"):
            op.complete_action(
                record,
                revision=record.revision,
                review=record.review,
                outcome=outcome,
            )


def test_confirmation_is_bound_to_the_reviewed_outcome(user, gang, fighter):
    action, outcome, _, _ = configured_action(user, gang, fighter)
    other_operation = authoring.apply_changes(
        authoring.counter_change(
            outcome.apply_changes.changes.first().counter_change.counter, "add", 1
        )
    )
    other = authoring.create_outcome("Add glitch", other_operation)
    authoring.add_action_outcome(action, other)
    record = start_and_review(user, gang, fighter, action, outcome)
    with pytest.raises(Refusal, match="Review this outcome"):
        with operation(gang, actor=user) as op:
            op.complete_action(
                record,
                revision=record.revision,
                review=record.review,
                outcome=other,
            )


def test_incomplete_choices_are_saved_for_resume_and_invalidate_review(
    user, gang, fighter
):
    action, outcome, _, _ = configured_action(user, gang, fighter)
    with operation(gang, actor=user) as op:
        record = op.start_action(fighter, action, uuid.uuid4())
        record = op.save_action_choices(
            record,
            outcome=outcome,
            terms={"item_assignment": "first", "outcome": "tampered"},
        )
    assert record.outcome == outcome
    assert record.terms == {
        "item_assignment": "first",
        "outcome": str(outcome.pk),
    }
    first_revision = record.revision

    with operation(gang, actor=user) as op:
        record = op.save_action_choices(
            record, outcome=outcome, terms={"intended_pick": "second"}
        )
    assert record.terms["item_assignment"] == "first"
    assert record.terms["intended_pick"] == "second"
    assert record.review == {}
    assert record.revision == first_revision + 1


def test_no_effect_is_refused_before_payment(user, gang, fighter):
    action, outcome, _, _ = configured_action(
        user, gang, fighter, counter_value=0, counter_price=False
    )
    record = start_and_review(user, gang, fighter, action, outcome)
    with pytest.raises(Refusal, match="would not change"):
        with operation(gang, actor=user) as op:
            op.complete_action(
                record,
                revision=record.revision,
                review=record.review,
                outcome=outcome,
            )
    assert not LedgerEvent.objects.filter(
        action_record=record, payment_id__isnull=False
    )


def test_clear_is_meaningful_when_matching_picks_exist(user, gang, fighter):
    action, outcome, _, _ = configured_action(
        user, gang, fighter, counter_value=0, counter_price=False
    )
    slot_type = SlotType.objects.create(name="Status")
    pick = Pickable.objects.create(name="Glitched", slot_type=slot_type)
    ApplyChange.objects.create(
        apply_changes=outcome.apply_changes,
        remove_picks=authoring.remove_picks(slot_type),
        position=1,
    )
    with operation(gang, actor=user) as op:
        held_pick = op.assign(pick, miniature=fighter)
    record = start_and_review(user, gang, fighter, action, outcome)
    with operation(gang, actor=user) as op:
        op.complete_action(
            record,
            revision=record.revision,
            review=record.review,
            outcome=outcome,
        )
    held_pick.refresh_from_db()
    assert held_pick.archived
    assert action_changes(record).picks[0].before_assignment_id == str(held_pick.pk)


def test_another_gang_cannot_complete_the_record(user, gang, fighter, gang_type):
    action, outcome, _, _ = configured_action(user, gang, fighter)
    record = start_and_review(user, gang, fighter, action, outcome)
    other = Gang.objects.create(name="Outsiders", owner=user, gang_type=gang_type)
    with pytest.raises(Refusal, match="belong"):
        with operation(other, actor=user) as op:
            op.complete_action(
                record,
                revision=record.revision,
                review=record.review,
                outcome=outcome,
            )


def test_tally_ignores_a_counter_value_cached_before_the_lock(user, gang, fighter):
    counter = Counter.objects.create(name="XP")
    with operation(gang, actor=user) as op:
        held = op.assign(counter, miniature=fighter)
        op.tally(held, 2)
    stale = held.counter_value
    assert stale.value == 2
    with operation(gang, actor=user) as op:
        op.tally(held, 3)
    with operation(gang, actor=user) as op:
        assert op.tally(held, 4) == 9
