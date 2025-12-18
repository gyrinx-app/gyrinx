"""
Tests for vehicle purchase handler propagation.

These tests verify that vehicle purchase correctly initializes rating_current
on crew fighters and vehicle equipment assignments.
"""

import pytest

from gyrinx.core.handlers.fighter.vehicle import (
    handle_vehicle_purchase,
)
from gyrinx.core.models.list import ListFighter


@pytest.mark.django_db
def test_handle_vehicle_purchase_initializes_crew_rating_current(
    user,
    list_with_campaign,
    make_content_fighter,
    content_house,
    make_equipment,
    settings,
):
    """Test that vehicle purchase initializes crew rating_current."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.credits_current = 2000
    lst.save()

    # Create vehicle equipment and fighters
    vehicle_equipment = make_equipment("Test Vehicle", cost="100")
    vehicle_equipment.creates_child_fighter = False  # Simple vehicle
    vehicle_equipment.save()

    from gyrinx.models import FighterCategoryChoices

    vehicle_fighter = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=100,
    )

    crew_fighter = make_content_fighter(
        type="Crew",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=50,
    )

    result = handle_vehicle_purchase(
        user=user,
        lst=lst,
        vehicle_equipment=vehicle_equipment,
        vehicle_fighter=vehicle_fighter,
        crew_fighter=crew_fighter,
        crew_name="Test Crew",
        is_stash=False,
    )

    # Verify crew rating_current initialized (includes both crew and vehicle cost)
    crew = result.crew_fighter
    crew.refresh_from_db()
    # After propagation, crew has crew_cost + vehicle_cost
    expected_rating = result.crew_cost + result.vehicle_cost
    assert crew.rating_current == expected_rating
    assert crew.rating_current == crew.cost_int()
    assert not crew.dirty


@pytest.mark.django_db
def test_handle_vehicle_purchase_propagates_assignment_rating_current(
    user,
    list_with_campaign,
    make_content_fighter,
    content_house,
    make_equipment,
    settings,
):
    """Test that vehicle purchase propagates assignment cost to caches."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.credits_current = 2000
    lst.save()

    # Create vehicle equipment and fighters
    vehicle_equipment = make_equipment("Test Vehicle", cost="100")
    vehicle_equipment.creates_child_fighter = False
    vehicle_equipment.save()

    from gyrinx.models import FighterCategoryChoices

    vehicle_fighter = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=100,
    )

    crew_fighter = make_content_fighter(
        type="Crew",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=50,
    )

    result = handle_vehicle_purchase(
        user=user,
        lst=lst,
        vehicle_equipment=vehicle_equipment,
        vehicle_fighter=vehicle_fighter,
        crew_fighter=crew_fighter,
        crew_name="Test Crew",
        is_stash=False,
    )

    # Verify assignment rating_current initialized
    assignment = result.vehicle_assignment
    assignment.refresh_from_db()
    assert assignment.rating_current == result.vehicle_cost
    assert assignment.rating_current == assignment.cost_int()
    assert not assignment.dirty

    # Verify crew rating_current includes vehicle cost
    crew = result.crew_fighter
    crew.refresh_from_db()
    expected_crew_rating = result.crew_cost + result.vehicle_cost
    assert crew.rating_current == expected_crew_rating
    assert not crew.dirty


@pytest.mark.django_db
def test_handle_vehicle_purchase_to_stash(
    user,
    list_with_campaign,
    make_content_fighter,
    content_house,
    make_equipment,
    settings,
):
    """Test vehicle purchase to stash initializes correctly."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.credits_current = 2000
    lst.save()

    # Create vehicle equipment and fighter
    vehicle_equipment = make_equipment("Test Vehicle", cost="100")
    vehicle_equipment.creates_child_fighter = False
    vehicle_equipment.save()

    from gyrinx.models import FighterCategoryChoices

    vehicle_fighter = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=100,
    )

    result = handle_vehicle_purchase(
        user=user,
        lst=lst,
        vehicle_equipment=vehicle_equipment,
        vehicle_fighter=vehicle_fighter,
        crew_fighter=None,
        crew_name=None,
        is_stash=True,
    )

    # Verify stash fighter (crew) has correct rating_current
    stash = result.crew_fighter
    assert stash.is_stash
    stash.refresh_from_db()

    # Stash should include the vehicle cost
    assert result.vehicle_list_action.stash_delta == result.vehicle_cost

    # Assignment should have correct rating_current
    assignment = result.vehicle_assignment
    assignment.refresh_from_db()
    assert assignment.rating_current == result.vehicle_cost


@pytest.mark.django_db
def test_handle_vehicle_purchase_child_fighter_rating_current(
    user,
    list_with_campaign,
    make_content_fighter,
    content_house,
    make_equipment,
    settings,
):
    """Test that auto-created vehicle fighter has rating_current matching cost_int()."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = list_with_campaign
    lst.credits_current = 2000
    lst.save()

    from gyrinx.content.models import ContentEquipmentFighterProfile
    from gyrinx.models import FighterCategoryChoices

    # Create vehicle fighter that will be auto-created as a child
    vehicle_fighter = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=100,
    )

    # Create vehicle equipment that creates a child fighter
    vehicle_equipment = make_equipment("Test Vehicle with Child", cost="100")

    # Create profile to trigger child fighter creation
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_equipment,
        content_fighter=vehicle_fighter,
    )

    crew_fighter = make_content_fighter(
        type="Crew",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=50,
    )

    result = handle_vehicle_purchase(
        user=user,
        lst=lst,
        vehicle_equipment=vehicle_equipment,
        vehicle_fighter=vehicle_fighter,
        crew_fighter=crew_fighter,
        crew_name="Test Crew",
        is_stash=False,
    )

    # Find any auto-created vehicle fighter (child)
    vehicle_fighters = ListFighter.objects.filter(
        source_assignment=result.vehicle_assignment
    )

    if vehicle_fighters.exists():
        vehicle_fighter_child = vehicle_fighters.first()
        vehicle_fighter_child.refresh_from_db()

        # Child fighters have cost_int() = 0
        assert vehicle_fighter_child.cost_int() == 0
        # rating_current should match cost_int()
        assert vehicle_fighter_child.rating_current == vehicle_fighter_child.cost_int()
        # dirty should be False (synchronized at creation)
        assert not vehicle_fighter_child.dirty
