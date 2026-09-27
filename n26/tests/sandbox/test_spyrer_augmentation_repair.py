"""The live Spyrer repair keeps choices and action history already earned."""

from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from n26 import maintenance
from n26.core.card import build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.models import (
    ActionAllowance,
    ActionRecord,
    Assignment,
    CounterTracking,
    SlotSelection,
)
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.core.spyrer_augmentation_repair import Refused, apply_one, find, prepare
from n26.library import authoring as a
from n26.library.models import Rule, Stat
from n26.tests.sandbox.actions import buy, choose, found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def live_spyrers(default_pack, counter_tracking, owner, person_type):
    gang_type = a.create_gang_type("Spyre Hunters", starting_credits=1000)
    profile = a.create_profile("Hunt Master", person_type, gang_type, price=100)
    a.set_statline(profile, movement=5, weapon_skill=3, toughness=3)
    action = a.create_action(
        "Recruitment augmentation",
        "recruitment",
        allowance_rule=a.recruitment_allowance_rule(),
    )
    evolution = a.create_action("Suit Evolution", "post_cycle")
    augmentation = a.create_slot_type("Augmentation", allows_repeats=False)

    malcadon = a.create_wargear("Malcadon hunting rig")
    malcadon_tier = a.create_pickable(
        "Tier 1", augmentation, qualifier="Malcadon hunting rig"
    )
    malcadon_list = a.create_picklist("Malcadon rig tiers", augmentation)
    a.add_picklist_member(malcadon_list, malcadon_tier, level=1)
    malcadon_slot = a.create_slot(
        "Malcadon hunting rig augmentation",
        augmentation,
        malcadon_list,
        min_picks=0,
        mode="tier_ladder",
    )
    member = a.add_built_in(malcadon, malcadon_slot)

    movement = Stat.objects.get(short_name="M")
    yeld_tier1 = a.create_pickable(
        "Tier 1",
        augmentation,
        qualifier="Yeld hunting rig",
        effects=[(a.targets_model(), a.ef_changes_stat(movement, "improve", 1))],
    )
    yeld_tier2 = a.create_pickable("Tier 2", augmentation, qualifier="Yeld hunting rig")
    yeld = a.create_wargear("Yeld hunting rig")
    yeld_list = a.create_picklist("Yeld rig tiers", augmentation)
    a.add_picklist_member(yeld_list, yeld_tier1, level=1)
    a.add_picklist_member(yeld_list, yeld_tier2, level=2)
    yeld_slot = a.create_slot(
        "Yeld hunting rig augmentation",
        augmentation,
        yeld_list,
        min_picks=0,
        mode="tier_ladder",
    )
    a.add_built_in(yeld, yeld_slot)

    gang = found_gang("The Hunt", gang_type, owner=owner)
    fighter = hire(gang, profile, "Kara", paid=100)
    with operation(gang, actor=owner) as op:
        op.assign(action, miniature=fighter)
    bought_malcadon = buy(fighter, thing=malcadon, paid=0)
    bought_yeld = buy(fighter, thing=yeld, paid=0)
    empty_slot = Assignment.objects.get(
        materialised_from=member, materialised_for=bought_malcadon
    )
    yeld_question = Assignment.objects.get(slot=yeld_slot, materialised_for=bought_yeld)
    pick = choose(yeld_question, yeld_tier2)
    with operation(gang, actor=owner):
        completed = ActionRecord.objects.create(
            gang=gang,
            fighter=fighter,
            action=evolution,
            request_key=uuid4(),
            state=ActionRecord.State.COMPLETED,
        )
        SlotSelection.objects.create(
            action_record=completed,
            item_assignment=bought_yeld,
            slot_assignment=yeld_question,
            intended_pick=yeld_tier2,
            new_pick=pick,
        )
    return gang, fighter, action, member, empty_slot, pick, completed, yeld_tier2


def test_repair_withdraws_empty_malcadon_slots_and_restores_hunt_master_use(
    live_spyrers,
):
    gang, fighter, action, member, empty_slot, pick, completed, tier2 = live_spyrers
    plan = find()
    assert plan.ok
    assert plan.empty_slots == 1
    assert plan.missing_uses == 1
    assert plan.repair_yeld

    prepare()
    apply_one(gang.pk)

    member.refresh_from_db()
    empty_slot.refresh_from_db()
    pick.refresh_from_db()
    completed.refresh_from_db()
    assert member.archived
    assert empty_slot.archived
    assert not pick.archived
    assert completed.state == ActionRecord.State.COMPLETED
    assert completed.slot_selection.new_pick_id == pick.pk
    assert (
        ActionAllowance.objects.filter(
            fighter=fighter, action=action, source=fighter.membership
        ).count()
        == 1
    )
    assert tier2.modifiers.filter(changes_stat__stat__short_name="M").count() == 1
    assert (
        Rule.objects.get(
            name="Chameleonic protection", qualifier="Yeld hunting rig Tier 2"
        ).annotation
        == "Ranged attacks targeting this model suffer −1 to hit, even after it moves."
    )
    card = build_card(fighter)
    computed = compute(card, build_modifier_index(carriers(card)))
    drawn = build_model_card(fighter, card=card, computed=computed)
    assert any(rule.name.startswith("Chameleonic protection") for rule in drawn.rules)
    assert drawn.statline.get("M").value == '6"'
    assert_reconciled(gang)


def test_repair_is_idempotent_and_keeps_an_older_completed_action(live_spyrers):
    gang, fighter, action, _, _, pick, completed, tier2 = live_spyrers
    prepare()
    apply_one(gang.pk)
    before = (
        ActionAllowance.objects.filter(fighter=fighter, action=action).count(),
        tier2.modifiers.count(),
        ActionRecord.objects.filter(fighter=fighter).count(),
    )

    prepare()
    apply_one(gang.pk)

    assert before == (1, 2, 1)
    assert completed.slot_selection.new_pick_id == pick.pk
    assert ActionAllowance.objects.filter(fighter=fighter, action=action).count() == 1
    assert tier2.modifiers.count() == 2
    assert ActionRecord.objects.filter(fighter=fighter).count() == 1
    assert find().nothing_here


def test_repair_rolls_back_a_gang_if_recruitment_grant_stops(live_spyrers):
    gang, fighter, action, _, empty_slot, *_ = live_spyrers
    prepare()
    CounterTracking.objects.filter(pk=1).update(activated_at=None, activation_run=None)

    with pytest.raises(Refused, match="did not receive a recruitment use"):
        apply_one(gang.pk)

    empty_slot.refresh_from_db()
    assert not empty_slot.archived
    assert not ActionAllowance.objects.filter(fighter=fighter, action=action).exists()
    assert_reconciled(gang)


def test_repair_refuses_a_malcadon_slot_with_a_selection(live_spyrers):
    _, _, _, member, empty_slot, *_ = live_spyrers
    tier = member.slot.picklist.members.first().pickable
    choose(empty_slot, tier)

    plan = find()

    assert not plan.ok
    assert "selected tier" in plan.problems[0]
    assert not member.archived


def test_repair_refuses_a_recorded_malcadon_tier_even_if_the_slot_is_empty(
    live_spyrers,
):
    gang, fighter, _, member, empty_slot, _, completed, _ = live_spyrers
    tier = member.slot.picklist.members.first().pickable
    with operation(gang, actor=gang.owner):
        recorded = ActionRecord.objects.create(
            gang=gang,
            fighter=fighter,
            action=completed.action,
            request_key=uuid4(),
            state=ActionRecord.State.COMPLETED,
        )
        SlotSelection.objects.create(
            action_record=recorded,
            item_assignment=empty_slot.materialised_for,
            intended_pick=tier,
        )

    plan = find()

    assert not plan.ok
    assert "recorded action history" in plan.problems[0]
    assert not member.archived


def test_preview_query_count_stays_flat_as_hunt_masters_grow(live_spyrers):
    gang, fighter, *_ = live_spyrers
    profile = fighter.membership.profile
    with CaptureQueriesContext(connection) as one:
        assert find().missing_uses == 1
    assert all(query["sql"].lstrip().upper().startswith("SELECT") for query in one)
    for number in range(5):
        hire(gang, profile, f"Hunter {number}", paid=100)
    with CaptureQueriesContext(connection) as six:
        assert find().missing_uses == 6

    assert len(six) <= len(one) + 1
    assert_reconciled(gang)


def test_empty_slot_is_removed_from_an_archived_gang_without_granting_a_use(
    live_spyrers,
):
    gang, fighter, action, _, empty_slot, *_ = live_spyrers
    gang.archive()
    plan = find()
    assert plan.empty_slots == 1
    assert plan.missing_uses == 0

    prepare()
    apply_one(gang.pk)

    empty_slot.refresh_from_db()
    assert empty_slot.archived
    assert not ActionAllowance.objects.filter(fighter=fighter, action=action).exists()
    assert_reconciled(gang)


def test_maintenance_page_previews_and_runs_the_repair(
    client, admin_user, live_spyrers
):
    gang, fighter, action, member, *_ = live_spyrers
    client.force_login(admin_user)
    address = reverse("admin:maintenance_n26_finish_spyrer_augmentations")
    page = client.get(address)
    assert page.status_code == 200
    assert "Remove 1 empty Malcadon slot" in page.content.decode()

    response = client.post(address)
    assert response.status_code == 302
    record = Backfill.objects.get(
        operation=maintenance.Operation.FINISH_SPYRER_AUGMENTATIONS
    )
    record.refresh_from_db()
    member.refresh_from_db()
    assert record.status == Backfill.Status.DONE
    assert member.archived
    assert ActionAllowance.objects.filter(fighter=fighter, action=action).count() == 1
    assert_reconciled(gang)
