from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from n26.core.advancements import (
    _stat_gainable,
    advancement_options,
    recorded_skill,
    skill_options,
)
from n26.core.models import ActionAllowance, AdvancementSelection, Gang, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.library import authoring
from n26.library.models import (
    Action,
    Category,
    CollectionSection,
    Counter,
    Pickable,
    PicklistMember,
    Skill,
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
        choice = advancement_options(record, configured)[0]
        op.save_action_choices(
            record, outcome=outcome, terms={"pickable_id": choice.id}
        )
        reviewed = op.review_action(
            record, outcome=outcome, terms={"pickable_id": choice.id}
        )
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
            caused_by=record.source_assignment,
        )
        selection = op.record_action_roll(record, configured, uuid4(), rolled=7)

    assert selection.slot_assignment_id == bound.pk
    assert fighter.assignments.filter(slot=configured.slot, archived=False).count() == 1


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


def test_first_available_random_skill_is_immutable_across_request_keys(fighter):
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
        replayed = op.record_skill_roll(
            record,
            configured,
            request_key,
            pickable_id=random_primary.id,
            skill_set_id=uuid4(),
            rolled=2,
        )

    assert unavailable["is_available"] is False
    assert replayed == unavailable


def test_advancement_option_queries_are_flat_for_18_or_36_results(fighter):
    action, outcome, allowance = _advancement(fighter)
    configured = outcome.resolve_advancement
    with operation(fighter.gang) as op:
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
        PicklistMember.objects.create(
            picklist=table,
            pickable=pick,
            position=position,
            roll_low=20,
            roll_high=20,
        )
    advancement_options(record, configured)
    with CaptureQueriesContext(connection) as thirty_six:
        advancement_options(record, configured)

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
