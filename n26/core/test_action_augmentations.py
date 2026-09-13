"""Typed item augmentation outcomes and corrections."""

import uuid

import pytest
from django.contrib.auth.models import User

from n26.core.augmentations import (
    apply_augmentation,
    augmentation_options,
    correct_augmentation,
    preview_augmentation,
)
from n26.core.models import ActionRecord, Assignment, AugmentationSelection, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.library.authoring import (
    add_built_in,
    add_picklist_member,
    create_action,
    create_gang_type,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    create_wargear,
    create_weapon,
)
from n26.library.models import AugmentCarriedItem, Slot
from n26.tests.sandbox.actions import buy, found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def action_record(default_pack, fighter_type):
    gang_type = create_gang_type("Hunters", starting_credits=1000)
    owner = User.objects.create_user("augmentation-player")
    gang = found_gang("The Hunt", gang_type, owner=owner, budget=1000)
    fighter = hire(
        gang, create_profile("Hunter", fighter_type, gang_type, price=100), "Vex"
    )
    action = create_action("Evolve suit", "post_cycle")
    return ActionRecord.objects.create(
        gang=gang,
        fighter=fighter,
        action=action,
        request_key=uuid.uuid4(),
    )


@pytest.fixture
def augmentation(default_pack):
    return create_slot_type("Augmentation", allows_repeats=False)


def ladder(item, augmentation, levels):
    members = [
        create_pickable(
            f"{item.name} tier {level}",
            augmentation,
            rating_contribution=level,
        )
        for level in levels
    ]
    picklist = create_picklist(f"{item.name} tiers", augmentation)
    for level, member in zip(levels, members, strict=True):
        add_picklist_member(picklist, member, level=level)
    slot = create_slot(
        f"{item.name} augmentation",
        augmentation,
        picklist,
        min_picks=0,
        max_picks=1,
        mode=Slot.Mode.TIER_LADDER,
    )
    add_built_in(item, slot)
    return members


def configured(augmentation):
    return AugmentCarriedItem.objects.create(slot_type=augmentation)


def test_preview_lists_each_repeated_wargear_assignment_separately(
    action_record, augmentation
):
    rig = create_wargear("Hunting rig", price=0)
    (tier,) = ladder(rig, augmentation, [1])
    first = buy(action_record.fighter, thing=rig, paid=0)
    second = buy(action_record.fighter, thing=rig, paid=0)

    preview = augmentation_options(action_record, configured(augmentation))

    assert [choice.item_assignment_id for choice in preview.candidates] == [
        str(first.pk),
        str(second.pk),
    ]
    assert {choice.candidate_pick_id for choice in preview.candidates} == {str(tier.pk)}


def test_preview_query_count_is_flat_as_items_grow(
    action_record, augmentation, django_assert_max_num_queries
):
    items = []
    for number in range(4):
        rig = create_wargear(f"Rig {number}", price=0)
        ladder(rig, augmentation, [1, 2, 3])
        items.append(buy(action_record.fighter, thing=rig, paid=0))
    outcome = configured(augmentation)

    # The fixed card hydration and modifier-index passes may be broad, but
    # previewing another item must not add a query per item or per tier.
    with django_assert_max_num_queries(45):
        preview = augmentation_options(action_record, outcome)

    assert len(preview.candidates) == len(items)


@pytest.mark.parametrize("kind", ["weapon", "wargear"])
def test_preview_reads_the_next_numeric_level_for_weapon_or_wargear(
    action_record, augmentation, kind
):
    item = (
        create_weapon("Launcher", profiles=())
        if kind == "weapon"
        else create_wargear("Rig", price=0)
    )
    tiers = ladder(item, augmentation, [1, 2, 3])
    buy(action_record.fighter, thing=item, paid=0)

    outcome = configured(augmentation)
    preview = augmentation_options(action_record, outcome)

    (choice,) = preview.candidates
    assert choice.current_level == 0
    assert choice.candidate_level == 1
    assert choice.candidate_pick_id == str(tiers[0].pk)
    assert choice.rating_after == choice.rating_before + 1
    snapshot = preview_augmentation(
        action_record,
        outcome,
        {
            "item_assignment": str(choice.item_assignment_id),
            "intended_pick": str(choice.candidate_pick_id),
        },
    )
    assert snapshot["slot_assignment"]
    assert snapshot["current_pick"] is None
    assert snapshot["selection"]["candidate_pick_id"] == str(tiers[0].pk)


def test_preview_does_not_skip_a_non_clipped_ineffective_level(
    action_record, augmentation
):
    rig = create_wargear("Rig", price=0)
    tiers = ladder(rig, augmentation, [1, 2])
    tiers[0].rating_contribution = 0
    tiers[0].save(update_fields=["rating_contribution"])
    buy(action_record.fighter, thing=rig, paid=0)

    assert (
        augmentation_options(action_record, configured(augmentation)).candidates == ()
    )


def test_preview_never_jumps_more_than_one_ineffective_level(
    action_record, augmentation
):
    rig = create_wargear("Rig", price=0)
    tiers = ladder(rig, augmentation, [1, 2, 3])
    for tier in tiers[:2]:
        tier.rating_contribution = 0
        tier.save(update_fields=["rating_contribution"])
    buy(action_record.fighter, thing=rig, paid=0)

    assert (
        augmentation_options(action_record, configured(augmentation)).candidates == ()
    )


def _apply(record, configured_outcome, item, tier):
    terms = {"item_assignment": str(item.pk), "intended_pick": str(tier.pk)}
    with operation(record.gang) as op:
        return apply_augmentation(op, record, configured_outcome, terms)


def test_apply_replaces_the_tier_and_records_exact_assignments(
    action_record, augmentation
):
    item = create_weapon("Launcher", profiles=())
    tiers = ladder(item, augmentation, [1, 2])
    carried = buy(action_record.fighter, thing=item, paid=0)
    outcome = configured(augmentation)

    _apply(action_record, outcome, carried, tiers[0])
    selection = AugmentationSelection.objects.get(action_record=action_record)
    first = selection.new_pick
    _apply(action_record, outcome, carried, tiers[1])

    selection.refresh_from_db()
    first.refresh_from_db()
    assert first.archived
    assert selection.item_assignment == carried
    assert selection.slot_assignment.caused_by == carried
    assert selection.previous_pick == first
    assert selection.intended_pick == tiers[1]
    assert selection.new_pick.pickable == tiers[1]
    assert selection.new_pick.caused_by == selection.slot_assignment
    assert selection.new_pick.action_augmentation_slots.count() == 0


def test_apply_refuses_a_stale_tier_before_writing(action_record, augmentation):
    item = create_wargear("Rig", price=0)
    tiers = ladder(item, augmentation, [1, 2])
    carried = buy(action_record.fighter, thing=item, paid=0)
    outcome = configured(augmentation)

    with pytest.raises(Refusal, match="next effective tier"):
        _apply(action_record, outcome, carried, tiers[1])

    assert not AugmentationSelection.objects.filter(
        action_record=action_record
    ).exists()


def test_apply_refuses_an_item_moved_out_of_the_fighters_possession(
    action_record, augmentation
):
    item = create_wargear("Rig", price=0)
    (tier,) = ladder(item, augmentation, [1])
    carried = buy(action_record.fighter, thing=item, paid=0)
    outcome = configured(augmentation)
    with operation(action_record.gang) as op:
        op.move(carried, action_record.gang.stash)

    with pytest.raises(Refusal, match="no longer carried"):
        _apply(action_record, outcome, carried, tier)


def test_correction_moves_the_result_and_retains_original_history(
    action_record, augmentation
):
    first_item = create_wargear("First rig", price=0)
    second_item = create_wargear("Second rig", price=0)
    (first_tier,) = ladder(first_item, augmentation, [1])
    (second_tier,) = ladder(second_item, augmentation, [1])
    first = buy(action_record.fighter, thing=first_item, paid=0)
    second = buy(action_record.fighter, thing=second_item, paid=0)
    outcome = configured(augmentation)
    _apply(action_record, outcome, first, first_tier)
    selection = AugmentationSelection.objects.get(action_record=action_record)
    original_pick = selection.new_pick
    payment_id = uuid.uuid4()
    action_record.payment_id = payment_id
    action_record.state = ActionRecord.State.COMPLETED
    action_record.save(update_fields=["payment_id", "state"])
    payment = LedgerEvent.objects.create(
        gang=action_record.gang,
        kind=LedgerEvent.Kind.ACTION_USE_PAID,
        action_record=action_record,
        payment_id=payment_id,
        credits_delta=-10,
    )

    terms = {
        "item_assignment": str(second.pk),
        "intended_pick": str(second_tier.pk),
    }
    with operation(action_record.gang) as op:
        correct_augmentation(op, action_record, outcome, terms)

    action_record.refresh_from_db()
    selection.refresh_from_db()
    original_pick.refresh_from_db()
    payment.refresh_from_db()
    # The shared correction entrypoint owns the record revision; the typed
    # handler changes only its selection and assignments.
    assert action_record.revision == 0
    assert action_record.payment_id == payment_id
    assert payment.credits_delta == -10
    assert original_pick.archived
    assert selection.item_assignment == second
    assert selection.new_pick.pickable == second_tier
    amendments = list(
        action_record.ledger_events.filter(kind=LedgerEvent.Kind.AMENDED).order_by(
            "created"
        )
    )
    assert [(event.before_pick_id, event.after_pick_id) for event in amendments] == [
        (None, original_pick.pk),
        (original_pick.pk, None),
        (None, selection.new_pick_id),
    ]


def test_correction_refuses_a_later_tier_change(action_record, augmentation):
    item = create_wargear("Rig", price=0)
    tiers = ladder(item, augmentation, [1, 2])
    carried = buy(action_record.fighter, thing=item, paid=0)
    outcome = configured(augmentation)
    _apply(action_record, outcome, carried, tiers[0])
    selection = AugmentationSelection.objects.get(action_record=action_record)
    with operation(action_record.gang) as op:
        op.replace_slot_pick(
            selection.slot_assignment,
            selection.slot_assignment.slot,
            tiers[1],
            previous_pick=selection.new_pick,
            miniature=action_record.fighter,
            action_record=action_record,
        )

    with (
        operation(action_record.gang) as op,
        pytest.raises(Refusal, match="changed.*reviewed"),
    ):
        correct_augmentation(
            op,
            action_record,
            outcome,
            {
                "item_assignment": str(carried.pk),
                "intended_pick": str(tiers[1].pk),
            },
        )


def test_correction_restores_the_exact_previous_assignment(action_record, augmentation):
    original_item = create_wargear("Original rig", price=0)
    replacement_item = create_wargear("Replacement rig", price=0)
    original_tiers = ladder(original_item, augmentation, [1, 2])
    (replacement_tier,) = ladder(replacement_item, augmentation, [1])
    original = buy(action_record.fighter, thing=original_item, paid=0)
    replacement = buy(action_record.fighter, thing=replacement_item, paid=0)
    outcome = configured(augmentation)
    _apply(action_record, outcome, original, original_tiers[0])
    first_assignment = AugmentationSelection.objects.get(
        action_record=action_record
    ).new_pick
    _apply(action_record, outcome, original, original_tiers[1])

    with operation(action_record.gang) as op:
        correct_augmentation(
            op,
            action_record,
            outcome,
            {
                "item_assignment": str(replacement.pk),
                "intended_pick": str(replacement_tier.pk),
            },
        )

    first_assignment.refresh_from_db()
    assert not first_assignment.archived
    assert (
        Assignment.objects.get(
            chosen_for__caused_by=original,
            pickable=original_tiers[0],
            archived=False,
        ).pk
        == first_assignment.pk
    )


def test_correction_refuses_dependent_changes(action_record, augmentation):
    item = create_wargear("Rig", price=0)
    (tier,) = ladder(item, augmentation, [1])
    carried = buy(action_record.fighter, thing=item, paid=0)
    outcome = configured(augmentation)
    _apply(action_record, outcome, carried, tier)
    selection = AugmentationSelection.objects.get(action_record=action_record)
    with operation(action_record.gang) as op:
        op.assign(
            create_wargear("Dependent part", price=0),
            miniature=action_record.fighter,
            caused_by=selection.new_pick,
        )

    with (
        operation(action_record.gang) as op,
        pytest.raises(Refusal, match="dependent changes"),
    ):
        correct_augmentation(
            op,
            action_record,
            outcome,
            {"item_assignment": str(carried.pk), "intended_pick": str(tier.pk)},
        )
