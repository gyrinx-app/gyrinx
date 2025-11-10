"""Test to reproduce issue #1063 - vehicle cost in stash not using cost_for_house."""

import pytest
from gyrinx.content.models import (
    ContentEquipmentFighterProfile,
    ContentFighterHouseOverride,
)
from gyrinx.core.models import ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_vehicle_in_stash_uses_house_override_cost(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    house = make_content_house("Squats")

    vehicle_fighter = make_content_fighter(
        type="Svenotar Scout Trike",
        category=FighterCategoryChoices.VEHICLE,
        base_cost=0,
        house=house,
    )

    ContentFighterHouseOverride.objects.create(
        fighter=vehicle_fighter, house=house, cost=100
    )

    vehicle_equipment = make_equipment(
        "Svenotar Scout Trike",
        category="VEHICLE",
        cost=0,
    )

    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_equipment, content_fighter=vehicle_fighter
    )

    gang_list = make_list("Test Gang", content_house=house, owner=user)

    stash_fighter_content = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.STASH,
        base_cost=0,
        is_stash=True,
        house=house,
    )

    stash_fighter = make_list_fighter(
        gang_list,
        "Gang Stash",
        content_fighter=stash_fighter_content,
        owner=user,
    )

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash_fighter,
        content_equipment=vehicle_equipment,
    )

    assignment.refresh_from_db()
    assert assignment.child_fighter is not None, (
        "Child fighter (vehicle) should be created"
    )

    vehicle_list_fighter = assignment.child_fighter
    assert vehicle_list_fighter.content_fighter == vehicle_fighter, (
        "Child fighter should use the vehicle ContentFighter"
    )

    assert vehicle_list_fighter.cost_int() == 100, (
        f"Vehicle fighter cost should be 100 (from house override), but got {vehicle_list_fighter.cost_int()}"
    )

    stash_cost = stash_fighter.cost_int()
    assert stash_cost == 100, (
        f"Stash fighter cost should include vehicle cost (100), but got {stash_cost}"
    )
