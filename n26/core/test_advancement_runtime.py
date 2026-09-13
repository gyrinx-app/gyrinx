from uuid import uuid4

import pytest

from n26.core.advancements import advancement_options
from n26.core.models import ActionAllowance, AdvancementSelection, Gang, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.library.models import Action
from n26.library.standard_content import STANDARD_CONTENT

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def fighter(user, gang_type, make_profile, make_statline):
    gang = Gang.objects.create(name="The Hunt", owner=user, gang_type=gang_type)
    profile = make_profile("Hunter", price=100)
    make_statline(profile)
    with operation(gang, actor=user) as op:
        return op.hire(profile, "Kara", paid=100)


def _advancement(fighter):
    STANDARD_CONTENT["fighter-actions"].create()
    action = Action.objects.get(name="Advancement")
    outcome = (
        action.outcomes.select_related("outcome__resolve_advancement").get().outcome
    )
    with operation(fighter.gang) as op:
        op.assign(action, miniature=fighter)
    allowance = ActionAllowance.objects.create(
        action=action,
        fighter=fighter,
        recruitment=fighter.membership,
        source_kind=ActionAllowance.Source.RANK,
        threshold=4,
        rank_table=action.rank_allowance_rule.counter.rank_tables.get(),
    )
    return action, outcome, allowance


def test_advancement_roll_is_saved_and_full_checkout_uses_it(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        first = op.record_action_roll(record, configured, uuid4(), rolled=7)
        again = op.record_action_roll(record, configured, uuid4(), rolled=12)
        assert first.pk == again.pk
        assert first.roll_event.roll == 7
        choice = advancement_options(record, configured)[0]
        op.save_action_choices(
            record, outcome=outcome, terms={"pickable_id": choice.id}
        )
        reviewed = op.review_action(
            record, outcome=outcome, terms={"pickable_id": choice.id}
        )
        completed = op.complete_action(
            reviewed,
            revision=reviewed.revision,
            review=reviewed.review,
            outcome=outcome,
        )
    completed.refresh_from_db()
    selection = AdvancementSelection.objects.get(action_record=completed)
    assert completed.state == completed.State.COMPLETED
    assert selection.pick_assignment.archived is False
    assert selection.pick_assignment.chosen_for_id == selection.slot_assignment_id
    assert (
        LedgerEvent.objects.filter(
            action_record=completed, kind=LedgerEvent.Kind.ROLLED, roll=7
        ).count()
        == 1
    )


def test_earned_advancement_with_a_roll_cannot_be_cancelled(fighter):
    action, outcome, allowance = _advancement(fighter)
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, outcome.resolve_advancement, uuid4(), rolled=7)
        with pytest.raises(Refusal, match="must be resumed"):
            op.cancel_action(record)
