from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from n26.core.advancements import (
    _fighter_state,
    _stat_gainable,
    advancement_options,
    recorded_skill,
    skill_options,
)
from n26.core.card import build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.models import (
    ActionAllowance,
    ActionRecord,
    AdvancementSelection,
    Gang,
    LedgerEvent,
    SkillSelection,
)
from n26.core.operations import Refusal, operation
from n26.core.render import build_model_card
from n26.library import authoring
from n26.library.models import (
    Action,
    Category,
    CollectionSection,
    Counter,
    CounterAtLeast,
    Pickable,
    PicklistMember,
    Skill,
    Slot,
    Stat,
)
from n26.library.standard_content import STANDARD_CONTENT
from n26.tests.sandbox.actions import (
    adds,
    changes_stat,
    modifier,
    places,
    targets_model,
)

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.core,
    pytest.mark.usefixtures("counter_tracking"),
]


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
        source=fighter.membership,
        source_kind=ActionAllowance.Source.RANK,
        threshold=4,
        rank_table=action.rank_allowance_rule.counter.rank_tables.get(),
    )
    return action, outcome, allowance


def _rendered_card(fighter):
    card = build_card(fighter, with_statlines=True)
    return build_model_card(
        fighter,
        card=card,
        computed=compute(card, build_modifier_index(carriers(card))),
    )


def _primary_agility(fighter):
    category = Category.objects.get(name="Agility", section__name="Skills")
    primary = CollectionSection.objects.get(
        collection__name="Skills & Powers", name="Primary"
    )
    modifier(
        "Hunter learns Agility",
        targets_model(),
        places(category, primary),
        carried_by=fighter.membership.profile,
    )
    return category


def _secondary_cunning(fighter):
    category = Category.objects.get(name="Cunning", section__name="Skills")
    secondary = CollectionSection.objects.get(
        collection__name="Skills & Powers", name="Secondary"
    )
    modifier(
        "Hunter selects Cunning as secondary",
        targets_model(),
        places(category, secondary),
        carried_by=fighter.membership.profile,
    )
    return category


def _ensure_stat_result(name, stat):
    from n26.library.models import ChangesStat

    result = Pickable.objects.get(name=name, qualifier="")
    if not any(
        isinstance(row.effect, ChangesStat) and row.effect.stat_id == stat.pk
        for row in result.modifiers.all()
    ):
        modifier(
            f"Test advancement: {name}",
            targets_model(),
            changes_stat(stat, "improve", 1),
            carried_by=result,
        )
    return result


def test_advancement_roll_is_saved_and_full_checkout_uses_it(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        first = op.record_action_roll(record, configured, uuid4(), rolled=7)
        again = op.record_action_roll(record, configured, uuid4(), rolled=12)
        assert first.pk == again.pk
        assert first.roll_event.roll == 7
        choice = next(
            option
            for option in advancement_options(record, configured)
            if option.gainable
        )
        terms = {
            "pickable_id": choice.id,
            "advancement_table": {"untrusted": True},
            "action_roll_request": "untrusted",
        }
        op.save_action_choices(record, outcome=outcome, terms=terms)
        reviewed = op.review_action(record, outcome=outcome, terms=terms)
        reviewed.refresh_from_db()
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


def test_advancement_slot_refuses_a_different_die(fighter):
    from n26.library.models import Dice

    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        with pytest.raises(Refusal, match="uses a 2D6, not a D6"):
            op.roll(
                configured.slot,
                miniature=fighter,
                rolled=6,
                dice=Dice.D6,
                action_record=record,
            )

    assert not LedgerEvent.objects.filter(
        action_record=record, kind=LedgerEvent.Kind.ROLLED
    ).exists()


def test_advancement_roll_refuses_a_changed_action_contract(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)

    action.rank_allowance_rule = None
    action.save(update_fields=["rank_allowance_rule", "modified"])

    with operation(fighter.gang) as op:
        with pytest.raises(Refusal, match="allowance belongs to another action use"):
            op.record_action_roll(record, configured, uuid4(), rolled=7)

    assert not LedgerEvent.objects.filter(
        action_record=record, kind=LedgerEvent.Kind.ROLLED
    ).exists()


def test_advancement_roll_refuses_a_fighter_no_longer_in_the_gang(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)

    fighter.membership.archived = True
    fighter.membership.save(update_fields=["archived", "modified"])

    with operation(fighter.gang) as op:
        with pytest.raises(Refusal, match="fighter is no longer in this gang"):
            op.record_action_roll(record, configured, uuid4(), rolled=7)

    assert not LedgerEvent.objects.filter(
        action_record=record, kind=LedgerEvent.Kind.ROLLED
    ).exists()


def test_earned_advancement_with_a_roll_cannot_be_cancelled(fighter):
    action, outcome, allowance = _advancement(fighter)
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, outcome.resolve_advancement, uuid4(), rolled=7)
        with pytest.raises(Refusal, match="must be resumed"):
            op.cancel_action(record)


def test_advancement_roll_reuses_the_unfilled_configured_slot(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        bound = op.assign(
            configured.slot,
            miniature=fighter,
            caused_by=fighter.membership,
        )
        selection = op.record_action_roll(record, configured, uuid4(), rolled=7)

    assert selection.slot_assignment_id == bound.pk
    assert fighter.assignments.filter(slot=configured.slot, archived=False).count() == 1


def test_advancement_roll_does_not_reuse_another_drafts_slot(fighter):
    action, outcome, first_allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    second_allowance = ActionAllowance.objects.create(
        action=action,
        fighter=fighter,
        source=fighter.membership,
        source_kind=ActionAllowance.Source.RANK,
        threshold=7,
        rank_table=first_allowance.rank_table,
    )
    with operation(fighter.gang) as op:
        first = op.start_action(fighter, action, uuid4(), first_allowance)
        first_selection = op.record_action_roll(first, configured, uuid4(), rolled=7)
        # Independent drafts retain their own recorded roll and slot.
        second = ActionRecord.objects.create(
            gang=fighter.gang,
            fighter=fighter,
            action=action,
            allowance=second_allowance,
            source_assignment=first.source_assignment,
            request_key=uuid4(),
        )
        second_selection = op.record_action_roll(second, configured, uuid4(), rolled=7)

    assert first_selection.slot_assignment_id != second_selection.slot_assignment_id
    assert fighter.assignments.filter(slot=configured.slot, archived=False).count() == 2


@pytest.mark.parametrize("entrypoint", ["save_action_choices", "review_action"])
def test_advancement_roll_refuses_switching_to_another_outcome(fighter, entrypoint):
    action, advancement, allowance = _advancement(fighter)
    resource = Counter.objects.create(name="Heat")
    alternative = authoring.create_outcome(
        "Vent heat",
        authoring.apply_changes(authoring.counter_change(resource, "set", 0)),
    )
    authoring.add_action_outcome(action, alternative)
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(
            record, advancement.resolve_advancement, uuid4(), rolled=7
        )

    with (
        operation(fighter.gang) as op,
        pytest.raises(Refusal, match="cannot change the outcome"),
    ):
        getattr(op, entrypoint)(record, outcome=alternative, terms={})

    record.refresh_from_db()
    assert record.outcome_id is None
    assert record.review == {}


def test_advancement_roll_refuses_a_different_selected_outcome(fighter):
    action, advancement, allowance = _advancement(fighter)
    alternative = authoring.create_outcome(
        "Do nothing",
        authoring.apply_changes(),
    )
    authoring.add_action_outcome(action, alternative)
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.save_action_choices(record, outcome=alternative, terms={})
        with pytest.raises(Refusal, match="does not match the selected outcome"):
            op.record_action_roll(
                record,
                advancement.resolve_advancement,
                uuid4(),
                rolled=7,
            )

    assert not AdvancementSelection.objects.filter(action_record=record).exists()


def test_advancement_roll_retry_refuses_a_different_configured_slot(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    other_slot = Slot.objects.create(
        name="Other advancement",
        slot_type=configured.slot.slot_type,
        picklist=configured.slot.picklist,
        min_picks=1,
        max_picks=1,
    )
    other_outcome = authoring.create_outcome(
        "Other advancement",
        authoring.resolve_advancement(other_slot),
    )
    authoring.add_action_outcome(action, other_outcome)
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        first = op.record_action_roll(record, configured, uuid4(), rolled=7)
        with pytest.raises(Refusal, match="roll for another advancement"):
            op.record_action_roll(
                record,
                other_outcome.resolve_advancement,
                uuid4(),
                rolled=8,
            )

    first.refresh_from_db()
    assert first.roll_event.roll == 7
    assert first.slot_assignment.slot_id == configured.slot_id


def test_first_available_random_skill_is_immutable_and_completes_checkout(fighter):
    action, outcome, allowance = _advancement(fighter)
    category = _primary_agility(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=2)
    random_primary = next(
        option
        for option in advancement_options(record, configured)
        if option.name == "Random Primary skill"
    )
    assert category in skill_options(record, configured, random_primary.id)

    with operation(fighter.gang) as op:
        accepted = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_primary.id,
            skill_set_id=category.pk,
            rolled=1,
        )
        replayed = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_primary.id,
            skill_set_id=category.pk,
            rolled=2,
        )

    assert replayed == accepted
    skill_event = LedgerEvent.objects.get(pk=accepted["event_id"])
    assert skill_event.slot_id is None
    assert recorded_skill(record, configured, random_primary.id) == category.skills.get(
        pk=accepted["skill_id"]
    )
    random_secondary = configured.slot.picklist.members.get(
        pickable__name="Random Secondary skill"
    ).pickable
    assert recorded_skill(record, configured, random_secondary.pk) is None
    assert (
        LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.ROLLED
        ).count()
        == 2
    )
    terms = {"pickable_id": random_primary.id}
    with operation(fighter.gang) as op:
        reviewed = op.review_action(record, outcome=outcome, terms=terms)
    with operation(fighter.gang) as op:
        completed = op.complete_action(
            reviewed,
            revision=reviewed.revision,
            review=reviewed.review,
            outcome=outcome,
        )

    skill_selection = SkillSelection.objects.get(action_record=completed)
    assert completed.state == completed.State.COMPLETED
    assert str(skill_selection.selected_skill_id) == accepted["skill_id"]
    assert str(skill_selection.skill_assignment.skill_id) == accepted["skill_id"]
    assert skill_selection.skill_assignment.caused_by_id == (
        completed.advancement_selection.pick_assignment_id
    )


def test_select_skill_result_refuses_a_random_roll_without_writing(fighter):
    action, outcome, allowance = _advancement(fighter)
    _primary_agility(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=5)
    select_primary = next(
        option
        for option in advancement_options(record, configured)
        if option.name == "Select Primary skill"
    )

    with operation(fighter.gang) as op:
        with pytest.raises(Refusal, match="does not use a random skill roll"):
            op.record_skill_roll(
                record,
                configured,
                uuid4(),
                pickable_id=select_primary.id,
                skill_set_id=uuid4(),
                rolled=1,
            )

    assert not SkillSelection.objects.filter(action_record=record).exists()
    assert (
        LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.ROLLED
        ).count()
        == 1
    )


def test_switching_random_skill_access_reuses_the_recorded_die(fighter):
    action, outcome, allowance = _advancement(fighter)
    primary = _primary_agility(fighter)
    secondary = _secondary_cunning(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=12)
    options = advancement_options(record, configured)
    random_primary = next(row for row in options if row.name == "Random Primary skill")
    random_secondary = next(
        row for row in options if row.name == "Random Secondary skill"
    )

    with operation(fighter.gang) as op:
        first = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_primary.id,
            skill_set_id=primary.pk,
            rolled=1,
        )
        switched = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_secondary.id,
            skill_set_id=secondary.pk,
            rolled=6,
        )
        replayed = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_secondary.id,
            skill_set_id=secondary.pk,
            rolled=6,
        )

    assert switched["roll"] == first["roll"] == 1
    assert switched["event_id"] == first["event_id"]
    assert replayed == switched
    assert recorded_skill(record, configured, random_primary.id) is None
    assert recorded_skill(
        record, configured, random_secondary.id
    ) == secondary.skills.get(position=1)
    assert (
        LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.ROLLED
        ).count()
        == 2
    )


def test_revisiting_random_access_restores_its_accepted_attempt(fighter):
    action, outcome, allowance = _advancement(fighter)
    primary = _primary_agility(fighter)
    secondary = _secondary_cunning(fighter)
    secondary_one = secondary.skills.get(position=1)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        op.assign(secondary_one, miniature=fighter)
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=12)
    options = advancement_options(record, configured)
    random_primary = next(row for row in options if row.name == "Random Primary skill")
    random_secondary = next(
        row for row in options if row.name == "Random Secondary skill"
    )

    with operation(fighter.gang) as op:
        primary_attempt = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_primary.id,
            skill_set_id=primary.pk,
            rolled=1,
        )
        unavailable_secondary = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_secondary.id,
            skill_set_id=secondary.pk,
            rolled=6,
        )
        accepted_secondary = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_secondary.id,
            skill_set_id=secondary.pk,
            rolled=5,
        )
        restored_primary = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_primary.id,
            skill_set_id=primary.pk,
            rolled=6,
        )

    assert unavailable_secondary["roll"] == primary_attempt["roll"] == 1
    assert unavailable_secondary["is_available"] is False
    assert accepted_secondary["roll"] == 5
    assert restored_primary == primary_attempt
    assert recorded_skill(record, configured, random_primary.id) == primary.skills.get(
        position=1
    )
    assert (
        LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.ROLLED
        ).count()
        == 3
    )


def test_random_attempts_are_bound_to_their_advancement_result(fighter):
    action, outcome, allowance = _advancement(fighter)
    primary = _primary_agility(fighter)
    configured = outcome.resolve_advancement
    original = configured.slot.picklist.members.get(
        pickable__name="Random Primary skill"
    ).pickable
    alternative = Pickable.objects.create(
        name="Another random Primary skill",
        slot_type=configured.slot.slot_type,
    )
    alternative.modifiers.add(*original.modifiers.all())
    PicklistMember.objects.create(
        picklist=configured.slot.picklist,
        pickable=alternative,
        position=configured.slot.picklist.members.count(),
        roll_low=12,
        roll_high=12,
    )
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=12)
    options = advancement_options(record, configured)
    original_option = next(row for row in options if row.id == str(original.pk))
    alternative_option = next(row for row in options if row.id == str(alternative.pk))

    with operation(fighter.gang) as op:
        first = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=original_option.id,
            skill_set_id=primary.pk,
            rolled=1,
        )
        second = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=alternative_option.id,
            skill_set_id=primary.pk,
            rolled=1,
        )

    assert first["pickable_id"] == original_option.id
    assert second["pickable_id"] == alternative_option.id
    assert first["event_id"] != second["event_id"]


def test_completed_correction_can_reuse_an_earlier_accepted_random_attempt(fighter):
    action, outcome, allowance = _advancement(fighter)
    primary = _primary_agility(fighter)
    secondary = _secondary_cunning(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=12)
    options = advancement_options(record, configured)
    random_primary = next(row for row in options if row.name == "Random Primary skill")
    random_secondary = next(
        row for row in options if row.name == "Random Secondary skill"
    )
    with operation(fighter.gang) as op:
        primary_attempt = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_primary.id,
            skill_set_id=primary.pk,
            rolled=1,
        )
        op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_secondary.id,
            skill_set_id=secondary.pk,
            rolled=1,
        )
        reviewed = op.review_action(
            record,
            outcome=outcome,
            terms={"pickable_id": random_secondary.id},
        )
    with operation(fighter.gang) as op:
        completed = op.complete_action(
            reviewed,
            revision=reviewed.revision,
            review=reviewed.review,
            outcome=outcome,
        )

    assert (
        str(recorded_skill(completed, configured, random_primary.id).pk)
        == primary_attempt["skill_id"]
    )
    with operation(fighter.gang) as op:
        correction = op.review_action_correction(
            completed, terms={"pickable_id": random_primary.id}
        )

    assert correction.review


def test_completed_select_can_reuse_an_earlier_accepted_random_attempt(fighter):
    action, outcome, allowance = _advancement(fighter)
    primary = _primary_agility(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=12)
    options = advancement_options(record, configured)
    random_primary = next(row for row in options if row.name == "Random Primary skill")
    select_primary = next(row for row in options if row.name == "Select Primary skill")
    with operation(fighter.gang) as op:
        random_attempt = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_primary.id,
            skill_set_id=primary.pk,
            rolled=1,
        )
        selected = next(
            skill
            for skill in skill_options(record, configured, select_primary.id)[primary]
            if str(skill.pk) != random_attempt["skill_id"]
        )
        reviewed = op.review_action(
            record,
            outcome=outcome,
            terms={"pickable_id": select_primary.id, "skill_id": str(selected.pk)},
        )
    with operation(fighter.gang) as op:
        completed = op.complete_action(
            reviewed,
            revision=reviewed.revision,
            review=reviewed.review,
            outcome=outcome,
        )

    assert completed.skill_selection.mode == "select"
    assert (
        str(recorded_skill(completed, configured, random_primary.id).pk)
        == random_attempt["skill_id"]
    )
    with operation(fighter.gang) as op:
        correction = op.review_action_correction(
            completed, terms={"pickable_id": random_primary.id}
        )

    assert correction.review


def test_completed_random_attempt_is_not_offered_after_skill_becomes_owned(fighter):
    action, outcome, allowance = _advancement(fighter)
    primary = _primary_agility(fighter)
    secondary = _secondary_cunning(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=12)
    options = advancement_options(record, configured)
    random_primary = next(row for row in options if row.name == "Random Primary skill")
    random_secondary = next(
        row for row in options if row.name == "Random Secondary skill"
    )
    with operation(fighter.gang) as op:
        primary_attempt = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_primary.id,
            skill_set_id=primary.pk,
            rolled=1,
        )
        op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_secondary.id,
            skill_set_id=secondary.pk,
            rolled=1,
        )
        reviewed = op.review_action(
            record,
            outcome=outcome,
            terms={"pickable_id": random_secondary.id},
        )
    with operation(fighter.gang) as op:
        completed = op.complete_action(
            reviewed,
            revision=reviewed.revision,
            review=reviewed.review,
            outcome=outcome,
        )
        op.assign(Skill.objects.get(pk=primary_attempt["skill_id"]), miniature=fighter)

    assert all(
        row.id != random_primary.id or not row.gainable
        for row in advancement_options(completed, configured)
    )
    with operation(fighter.gang) as op:
        with pytest.raises(Refusal, match="Choose an available advancement result"):
            op.review_action_correction(
                completed, terms={"pickable_id": random_primary.id}
            )


def test_exact_skill_roll_retry_survives_lost_access(fighter):
    action, outcome, allowance = _advancement(fighter)
    category = Category.objects.get(name="Agility", section__name="Skills")
    primary = CollectionSection.objects.get(
        collection__name="Skills & Powers", name="Primary"
    )
    access = modifier(
        "Hunter temporarily selects Agility",
        targets_model(),
        places(category, primary),
        carried_by=fighter.membership.profile,
    )
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=2)
    random_primary = next(
        row
        for row in advancement_options(record, configured)
        if row.name == "Random Primary skill"
    )
    request_key = uuid4()
    with operation(fighter.gang) as op:
        first = op.record_skill_roll(
            record,
            configured,
            request_key,
            pickable_id=random_primary.id,
            skill_set_id=category.pk,
            rolled=1,
        )
    access.delete()

    with operation(fighter.gang) as op:
        replayed = op.record_skill_roll(
            record,
            configured,
            request_key,
            pickable_id=random_primary.id,
            skill_set_id=category.pk,
            rolled=6,
        )

    assert replayed == first
    assert (
        LedgerEvent.objects.filter(
            action_record=record, kind=LedgerEvent.Kind.ROLLED
        ).count()
        == 2
    )


def test_new_skill_roll_retry_does_not_reuse_a_skill_now_owned(fighter):
    action, outcome, allowance = _advancement(fighter)
    category = _primary_agility(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=2)
    random_primary = next(
        row
        for row in advancement_options(record, configured)
        if row.name == "Random Primary skill"
    )
    with operation(fighter.gang) as op:
        first = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_primary.id,
            skill_set_id=category.pk,
            rolled=1,
        )
        op.assign(Skill.objects.get(pk=first["skill_id"]), miniature=fighter)
        retried = op.record_skill_roll(
            record,
            configured,
            uuid4(),
            pickable_id=random_primary.id,
            skill_set_id=category.pk,
            rolled=2,
        )

    assert retried["event_id"] != first["event_id"]
    assert retried["skill_id"] != first["skill_id"]
    assert retried["is_available"] is True


def test_computed_granted_skill_is_not_offered_again(fighter):
    action, outcome, allowance = _advancement(fighter)
    category = _primary_agility(fighter)
    granted = category.skills.get(position=1)
    modifier(
        "Hunter starts with a skill",
        targets_model(),
        adds(granted),
        carried_by=fighter.membership.profile,
    )
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=2)
    random_primary = next(
        option
        for option in advancement_options(record, configured)
        if option.name == "Random Primary skill"
    )

    offered = skill_options(record, configured, random_primary.id)

    assert granted not in offered[category]


def test_unavailable_skill_attempt_replays_before_rechecking_access(fighter):
    action, outcome, allowance = _advancement(fighter)
    category = _primary_agility(fighter)
    already_owned = category.skills.get(position=1)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        op.assign(already_owned, miniature=fighter)
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=2)
    random_primary = next(
        option
        for option in advancement_options(record, configured)
        if option.name == "Random Primary skill"
    )
    request_key = uuid4()
    with operation(fighter.gang) as op:
        unavailable = op.record_skill_roll(
            record,
            configured,
            request_key,
            pickable_id=random_primary.id,
            skill_set_id=category.pk,
            rolled=1,
        )
        with pytest.raises(Refusal, match="different skill roll"):
            op.record_skill_roll(
                record,
                configured,
                request_key,
                pickable_id=random_primary.id,
                skill_set_id=uuid4(),
                rolled=2,
            )

    assert unavailable["is_available"] is False


def test_noop_foundation_reseed_preserves_a_recorded_roll(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=7)
    snapshot = record.terms["advancement_table"]

    STANDARD_CONTENT["fighter-actions"].create()
    record.refresh_from_db()

    assert record.terms["advancement_table"] == snapshot
    assert advancement_options(record, configured)


@pytest.mark.parametrize("edited", ["effect", "scope"])
def test_advancement_roll_fingerprints_modifier_configuration(fighter, edited):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=7)
    result = configured.slot.picklist.members.get(
        pickable__name="Random Primary skill"
    ).pickable
    modifier = result.modifiers.get()
    if edited == "effect":
        modifier.offers_choice.mode = modifier.offers_choice.Mode.SELECT
        modifier.offers_choice.save(update_fields=["mode"])
    else:
        modifier.scope.reach = modifier.scope.Reach.EVERY_MODEL
        modifier.scope.save(update_fields=["reach"])

    with pytest.raises(Refusal, match="table changed"):
        advancement_options(record, configured)


def test_advancement_roll_fingerprints_modifier_condition_rows(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    result = configured.slot.picklist.members.get(
        pickable__name="Random Primary skill"
    ).pickable
    condition = CounterAtLeast.objects.create(
        scope=result.modifiers.get().targets_miniature,
        counter=Counter.objects.create(name="Reputation"),
        at_least=1,
    )
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=7)
    condition.at_least = 2
    condition.save(update_fields=["at_least"])

    with pytest.raises(Refusal, match="table changed"):
        advancement_options(record, configured)


def test_advancement_previews_do_not_query_rank_display(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    result = _ensure_stat_result("Strength", Stat.objects.get(short_name="M"))
    with operation(fighter.gang) as op:
        op.assign(allowance.rank_table, miniature=fighter)
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=10)

    with CaptureQueriesContext(connection) as queries:
        _fighter_state(record)
        _stat_gainable(fighter, result)
        advancement_options(record, configured)

    assert not [
        query["sql"]
        for query in queries
        if 'FROM "library_rankthreshold"' in query["sql"]
        or (
            'FROM "library_ranktable"' in query["sql"]
            and 'JOIN "library_counter"' in query["sql"]
        )
    ]


def test_advancement_option_queries_are_flat_for_18_or_36_results(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    movement = Stat.objects.get(short_name="M")
    with operation(fighter.gang) as op:
        op.assign(allowance.rank_table, miniature=fighter)
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=7)
    advancement_options(record, configured)
    with CaptureQueriesContext(connection) as eighteen:
        advancement_options(record, configured)

    table = configured.slot.picklist
    for position in range(18, 36):
        pick = Pickable.objects.create(
            name=f"Extra result {position}",
            qualifier="Query growth",
            slot_type=configured.slot.slot_type,
        )
        modifier(
            f"Extra result {position} improves movement",
            targets_model(),
            changes_stat(movement, "improve", 1),
            carried_by=pick,
        )
        PicklistMember.objects.create(
            picklist=table,
            pickable=pick,
            position=position,
            roll_low=20,
            roll_high=20,
        )
    with pytest.raises(Refusal, match="table changed"):
        advancement_options(record, configured)
    second_allowance = ActionAllowance.objects.create(
        action=action,
        fighter=fighter,
        source=fighter.membership,
        source_kind=ActionAllowance.Source.RANK,
        threshold=7,
        rank_table=allowance.rank_table,
    )
    with operation(fighter.gang) as op:
        second = ActionRecord.objects.create(
            gang=fighter.gang,
            fighter=fighter,
            action=action,
            allowance=second_allowance,
            source_assignment=record.source_assignment,
            request_key=uuid4(),
        )
        op.record_action_roll(second, configured, uuid4(), rolled=10)
    advancement_options(second, configured)
    with CaptureQueriesContext(connection) as thirty_six:
        advancement_options(second, configured)

    assert len(thirty_six) == len(eighteen)


def test_stat_result_reaching_maximum_is_gainable_but_clipped_result_is_not(fighter):
    action, outcome, allowance = _advancement(fighter)
    strength = Stat.objects.get(short_name="M")
    toughness = Stat.objects.get(short_name="T")
    for stat in (strength, toughness):
        stat.minimum = 1
        stat.maximum = 10
        stat.save(update_fields=["minimum", "maximum", "modified"])
    _ensure_stat_result("Strength", strength)
    _ensure_stat_result("Toughness", toughness)
    type_stats = fighter.membership.profile.statline_type.stats
    with operation(fighter.gang) as op:
        op.set_stats(
            fighter,
            [
                (type_stats.get(stat=strength), "9", "Strength set to 9"),
                (type_stats.get(stat=toughness), "10", "Toughness set to 10"),
            ],
        )
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, outcome.resolve_advancement, uuid4(), rolled=10)

    assert _stat_gainable(fighter, _ensure_stat_result("Strength", strength)) is True
    assert _stat_gainable(fighter, _ensure_stat_result("Toughness", toughness)) is False


def test_all_eighteen_results_are_fallback_when_none_landed_are_gainable(
    fighter, monkeypatch
):
    action, outcome, allowance = _advancement(fighter)
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, outcome.resolve_advancement, uuid4(), rolled=10)
    monkeypatch.setattr(
        "n26.core.advancements._gainable", lambda *args, **kwargs: False
    )

    options = advancement_options(record, outcome.resolve_advancement)

    assert len(options) == 18
    random = next(option for option in options if option.needs_skill)
    with pytest.raises(Refusal, match="not available for this advancement"):
        skill_options(record, outcome.resolve_advancement, random.id)
    assert all(option.gainable is False for option in options)


def test_skill_option_queries_are_flat_for_one_or_ten_owned_skills(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=12)
    select_any = next(
        option
        for option in advancement_options(record, configured)
        if option.name == "Select any skill"
    )
    skills = list(Skill.objects.exclude(category__name="Inherent")[:10])
    with operation(fighter.gang) as op:
        op.assign(skills[0], miniature=fighter)
    skill_options(record, configured, select_any.id)
    with CaptureQueriesContext(connection) as one:
        skill_options(record, configured, select_any.id)

    with operation(fighter.gang) as op:
        for skill in skills[1:]:
            op.assign(skill, miniature=fighter)
    skill_options(record, configured, select_any.id)
    with CaptureQueriesContext(connection) as ten:
        skill_options(record, configured, select_any.id)

    assert len(ten) == len(one)


def test_completed_advancement_correction_keeps_roll_and_allowance(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    _ensure_stat_result("Strength", Stat.objects.get(short_name="M"))
    with operation(fighter.gang) as op:
        movement = fighter.membership.profile.statline_type.stats.get(
            stat__short_name="M"
        )
        op.set_stats(fighter, [(movement, "6", 'Movement set to 6"')])
        record = op.start_action(fighter, action, uuid4(), allowance)
        selection = op.record_action_roll(record, configured, uuid4(), rolled=10)
    roll_event_id = selection.roll_event_id
    options = advancement_options(record, configured)
    strength = next(option for option in options if option.name == "Strength")
    toughness = next(option for option in options if option.name == "Toughness")
    with operation(fighter.gang) as op:
        reviewed = op.review_action(
            record, outcome=outcome, terms={"pickable_id": strength.id}
        )
    with operation(fighter.gang) as op:
        completed = op.complete_action(
            reviewed,
            revision=reviewed.revision,
            review=reviewed.review,
            outcome=outcome,
        )
    old_pick = AdvancementSelection.objects.get(action_record=completed).pick_assignment
    terms = {"pickable_id": toughness.id}
    with operation(fighter.gang) as op:
        correction = op.review_action_correction(completed, terms=terms)
    reviewed_revision = correction.revision
    reviewed_fingerprint = correction.review
    movement = fighter.membership.profile.statline_type.stats.get(stat__short_name="M")
    with operation(fighter.gang) as op:
        op.set_stats(fighter, [(movement, "7", 'Movement set to 7"')])
    with (
        operation(fighter.gang) as op,
        pytest.raises(Refusal, match="fighter changed"),
    ):
        op.correct_action(
            correction,
            revision=reviewed_revision,
            review=reviewed_fingerprint,
            terms=terms,
        )
    with operation(fighter.gang) as op:
        correction = op.review_action_correction(completed, terms=terms)
    with operation(fighter.gang) as op:
        corrected, _result = op.correct_action(
            correction,
            revision=correction.revision,
            review=correction.review,
            terms=terms,
        )

    selection = AdvancementSelection.objects.get(action_record=corrected)
    old_pick.refresh_from_db()
    assert old_pick.archived
    assert not selection.pick_assignment.archived
    assert selection.intended_pick_id == toughness.id
    assert selection.roll_event_id == roll_event_id
    assert selection.pick_assignment.roll_id == roll_event_id
    assert corrected.allowance_id == allowance.pk
    assert (
        LedgerEvent.objects.filter(
            action_record=corrected, kind=LedgerEvent.Kind.ROLLED
        ).count()
        == 1
    )


def test_completed_skill_is_available_to_its_own_correction(fighter):
    action, outcome, allowance = _advancement(fighter)
    category = _primary_agility(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=5)
    select_primary = next(
        option
        for option in advancement_options(record, configured)
        if option.name == "Select Primary skill"
    )
    skill = skill_options(record, configured, select_primary.id)[category][0]
    terms = {"pickable_id": select_primary.id, "skill_id": str(skill.pk)}
    with operation(fighter.gang) as op:
        reviewed = op.review_action(record, outcome=outcome, terms=terms)
    with operation(fighter.gang) as op:
        completed = op.complete_action(
            reviewed,
            revision=reviewed.revision,
            review=reviewed.review,
            outcome=outcome,
        )
        for other in category.skills.exclude(pk=skill.pk):
            op.assign(other, miniature=fighter)

    rendered = _rendered_card(fighter)
    assert str(skill) in {line.name for line in rendered.skills}
    gained = next(line for line in rendered.skills if line.name == str(skill))
    assert gained.provenance.source == "Select Primary skill"
    assert gained.provenance.source_kind == "advancement"
    assert gained.provenance.annotated
    assert not gained.provenance.computed
    assert "Select Primary skill" not in {line.kind_label for line in rendered.choices}

    assert skill_options(completed, configured, select_primary.id)[category] == [skill]
    with operation(fighter.gang) as op:
        correction = op.review_action_correction(completed, terms=terms)

    assert correction.review


def test_completed_characteristic_advancement_only_changes_the_statline(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    before = _rendered_card(fighter)
    before_toughness = next(
        cell.value for cell in before.statline.cells if cell.short_name == "T"
    )
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=10)
    toughness = next(
        option
        for option in advancement_options(record, configured)
        if option.name == "Toughness"
    )
    with operation(fighter.gang) as op:
        reviewed = op.review_action(
            record, outcome=outcome, terms={"pickable_id": toughness.id}
        )
    with operation(fighter.gang) as op:
        op.complete_action(
            reviewed,
            revision=reviewed.revision,
            review=reviewed.review,
            outcome=outcome,
        )

    rendered = _rendered_card(fighter)
    after_toughness = next(
        cell.value for cell in rendered.statline.cells if cell.short_name == "T"
    )
    assert after_toughness != before_toughness
    assert rendered.choices == []
    assert "Toughness" not in {line.name for line in rendered.equipment}


def test_completed_skill_moved_to_another_fighter_cannot_be_corrected(fighter):
    action, outcome, allowance = _advancement(fighter)
    category = _primary_agility(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        other = op.hire(fighter.membership.profile, "Other", paid=0)
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=5)
    select_primary = next(
        option
        for option in advancement_options(record, configured)
        if option.name == "Select Primary skill"
    )
    skill = skill_options(record, configured, select_primary.id)[category][0]
    terms = {"pickable_id": select_primary.id, "skill_id": str(skill.pk)}
    with operation(fighter.gang) as op:
        reviewed = op.review_action(record, outcome=outcome, terms=terms)
    with operation(fighter.gang) as op:
        completed = op.complete_action(
            reviewed,
            revision=reviewed.revision,
            review=reviewed.review,
            outcome=outcome,
        )
        op.move(completed.skill_selection.skill_assignment, other)

    with operation(fighter.gang) as op:
        with pytest.raises(Refusal, match="Later changes depend"):
            op.review_action_correction(completed, terms=terms)


def test_completed_skill_advancement_with_an_active_descendant_cannot_be_corrected(
    fighter,
):
    action, outcome, allowance = _advancement(fighter)
    category = _primary_agility(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
        record = op.start_action(fighter, action, uuid4(), allowance)
        op.record_action_roll(record, configured, uuid4(), rolled=5)
    select_primary = next(
        option
        for option in advancement_options(record, configured)
        if option.name == "Select Primary skill"
    )
    skill = skill_options(record, configured, select_primary.id)[category][0]
    terms = {"pickable_id": select_primary.id, "skill_id": str(skill.pk)}
    with operation(fighter.gang) as op:
        reviewed = op.review_action(record, outcome=outcome, terms=terms)
    with operation(fighter.gang) as op:
        completed = op.complete_action(
            reviewed,
            revision=reviewed.revision,
            review=reviewed.review,
            outcome=outcome,
        )
    assert "Random Secondary skill" not in {
        option.name for option in advancement_options(completed, configured)
    }
    selected = SkillSelection.objects.get(action_record=completed)
    intermediate = Counter.objects.create(name="Archived dependent")
    dependent = Counter.objects.create(name="Active descendant")
    with operation(fighter.gang) as op:
        archived = op.assign(
            intermediate,
            miniature=fighter,
            caused_by=selected.skill_assignment,
        )
        op.assign(dependent, miniature=fighter, caused_by=archived)
    archived.archived = True
    archived.save(update_fields=["archived", "modified"])

    with operation(fighter.gang) as op:
        with pytest.raises(Refusal, match="Later changes depend"):
            op.review_action_correction(completed, terms=terms)
