"""
Tests for equipment removal handlers.

These tests directly test the handler functions in gyrinx.core.handlers.equipment,
ensuring that business logic works correctly without involving HTTP machinery.
"""

import pytest

from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentFighterProfile,
)
from gyrinx.core.handlers.equipment import handle_equipment_removal
from gyrinx.core.models.action import ListActionType
from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_handle_equipment_removal_includes_child_fighter_cost(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
    settings,
):
    """
    Test that removing equipment with a linked fighter includes the child fighter's
    cost in the ListAction rating_delta.

    This is a regression test for a bug where only the equipment cost (e.g., 50)
    was recorded in the action, but not the cascaded-deleted child fighter's cost
    (e.g., 200+ for a vehicle with its own equipment).
    """
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    house = make_content_house("Test House")

    # Create the parent fighter type (crew)
    crew_cf = make_content_fighter(
        type="Crew",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    # Create the linked fighter type (vehicle)
    vehicle_cf = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=house,
        base_cost=200,
    )

    # Create equipment that links to the vehicle
    vehicle_equipment = make_equipment(
        "Vehicle Equipment",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # Create additional equipment to put on the vehicle
    vehicle_weapon = make_equipment(
        "Heavy Weapon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=75,
    )

    # Link the vehicle fighter to the equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_equipment, content_fighter=vehicle_cf
    )

    # Create the list and crew fighter
    lst = make_list("Test List", content_house=house, owner=user)
    crew_lf = make_list_fighter(lst, "Crew", content_fighter=crew_cf, owner=user)

    # Assign vehicle equipment to crew (this creates the linked vehicle fighter)
    vehicle_assign = ListFighterEquipmentAssignment.objects.create(
        list_fighter=crew_lf, content_equipment=vehicle_equipment
    )

    # Get the linked vehicle fighter
    vehicle_lf = vehicle_assign.child_fighter
    assert vehicle_lf is not None, "Vehicle child_fighter should be created"

    # Add weapon to the vehicle
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=vehicle_lf, content_equipment=vehicle_weapon
    )

    # Initialize the facts system - bootstrap rating_current values for list and fighters
    lst.facts_from_db(update=True)
    crew_lf.facts_from_db(update=True)
    lst.refresh_from_db()
    crew_lf.refresh_from_db()

    # Expected initial cost:
    # - Crew fighter: 100 (from content_fighter.base_cost)
    # - Vehicle equipment on crew: 50
    # - Vehicle fighter: NOT counted because it's a linked fighter (cost comes from equipment)
    # - Heavy Weapon on vehicle: 75
    # Total: 100 + 50 + 75 = 225
    assert lst.cost_int() == 225, (
        f"Initial list cost should be 225, got {lst.cost_int()}"
    )

    # Capture before values
    rating_before = lst.rating_current
    initial_rating = rating_before
    crew_rating_before = crew_lf.rating_current

    # Now remove the vehicle equipment from crew (this will cascade delete the vehicle)
    result = handle_equipment_removal(
        user=user,
        lst=lst,
        fighter=crew_lf,
        assignment=vehicle_assign,
        request_refund=False,
    )

    # The vehicle fighter should be deleted along with its equipment
    assert not ListFighter.objects.filter(pk=vehicle_lf.pk).exists()

    # The cost delta should include:
    # - Vehicle equipment: 50
    # - Vehicle fighter's total cost (including its equipment): 75
    # Total removal: 125
    expected_equipment_cost = 50  # The equipment itself
    expected_child_fighter_cost = (
        75  # The vehicle's cost (only the weapon, not base cost)
    )
    expected_total_cost = expected_equipment_cost + expected_child_fighter_cost

    assert result.equipment_cost == expected_total_cost
    assert result.child_fighter_cost == expected_child_fighter_cost

    # Check the ListAction has the correct rating_delta
    assert result.list_action is not None
    assert result.list_action.action_type == ListActionType.REMOVE_EQUIPMENT
    assert result.list_action.rating_delta == -expected_total_cost
    assert result.list_action.rating_before == initial_rating

    # Verify the description mentions the linked fighter
    assert "linked fighter" in result.description

    # CRITICAL: Verify the parent fighter's rating only changed by equipment cost,
    # NOT by the child fighter's cost (which is a separate entity)
    crew_lf.refresh_from_db()
    assert crew_lf.rating_current == crew_rating_before - expected_equipment_cost, (
        f"Crew fighter rating should decrease by equipment cost only ({expected_equipment_cost}), "
        f"not by total cost ({expected_total_cost}). "
        f"Before: {crew_rating_before}, After: {crew_lf.rating_current}"
    )

    # Final list should just have the crew fighter (100)
    lst.refresh_from_db()
    assert lst.cost_int() == 100


@pytest.mark.django_db
def test_handle_equipment_removal_without_child_fighter(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
    settings,
):
    """
    Test that removing normal equipment (without child_fighter) still works correctly.
    """
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    house = make_content_house("Test House")
    fighter_cf = make_content_fighter(
        type="Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    weapon = make_equipment(
        "Weapon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=50,
    )

    lst = make_list("Test List", content_house=house, owner=user)
    fighter_lf = make_list_fighter(
        lst, "Fighter", content_fighter=fighter_cf, owner=user
    )

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter_lf, content_equipment=weapon
    )

    lst.refresh_from_db()
    assert lst.cost_int() == 150

    result = handle_equipment_removal(
        user=user,
        lst=lst,
        fighter=fighter_lf,
        assignment=assignment,
        request_refund=False,
    )

    assert result.equipment_cost == 50
    assert result.child_fighter_cost == 0
    assert result.list_action is not None
    assert result.list_action.rating_delta == -50
    assert "linked fighter" not in result.description

    lst.refresh_from_db()
    assert lst.cost_int() == 100
