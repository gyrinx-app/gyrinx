"""Test to reproduce issue #1063 - vehicle cost in stash not using cost_for_house."""

import pytest
from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentFighterProfile,
    ContentFighter,
    ContentFighterHouseOverride,
    ContentHouse,
)
from gyrinx.core.models import List, ListFighter, ListFighterEquipmentAssignment


@pytest.mark.django_db
def test_vehicle_in_stash_uses_house_override_cost(user):
    house = ContentHouse.objects.create(name="Squats", short_name="SQT")

    vehicle_fighter = ContentFighter.objects.create(
        type="Svenotar Scout Trike",
        category="VEHICLE",
        base_cost=0,
        house=house,
    )

    ContentFighterHouseOverride.objects.create(
        fighter=vehicle_fighter, house=house, cost=100
    )

    vehicle_equipment = ContentEquipment.objects.create(
        name="Svenotar Scout Trike",
        category="VEHICLE",
        cost="0",
    )

    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_equipment, content_fighter=vehicle_fighter
    )

    gang_list = List.objects.create(name="Test Gang", content_house=house, owner=user)

    stash_fighter_content = ContentFighter.objects.create(
        type="Stash",
        category="STASH",
        base_cost=0,
        is_stash=True,
        house=house,
    )

    stash_fighter = ListFighter.objects.create(
        name="Gang Stash",
        content_fighter=stash_fighter_content,
        list=gang_list,
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
