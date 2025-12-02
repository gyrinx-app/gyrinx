"""
Tests for equipment cost override handlers.

These tests directly test the handler functions in gyrinx.core.handlers.equipment.cost_override,
ensuring that business logic works correctly without involving HTTP machinery.

The handler API expects:
1. The assignment already has NEW value applied (e.g., by ModelForm's is_valid())
2. OLD value is passed to the handler for comparison
"""

import pytest

from gyrinx.core.handlers.equipment import handle_equipment_cost_override
from gyrinx.core.models.action import ListActionType
from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_handle_equipment_cost_override_no_change(
    user, make_list, content_fighter, make_equipment, settings
):
    """Test that handler returns None when override doesn't change."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    equipment = make_equipment("Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    # No override set, passing None for both (no change)
    result = handle_equipment_cost_override(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        old_total_cost_override=None,
        new_total_cost_override=None,
    )

    assert result is None


@pytest.mark.django_db
def test_handle_equipment_cost_override_set(
    user, make_list, content_fighter, make_equipment, settings
):
    """Test that setting total_cost_override creates ListAction with correct delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    equipment = make_equipment("Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    # Simulate form applying new value
    assignment.total_cost_override = 75

    # Set override to 75 (delta = 75 - 50 = +25)
    result = handle_equipment_cost_override(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        old_total_cost_override=None,
        new_total_cost_override=75,
    )

    assert result is not None
    assert result.old_total_cost == 50
    assert result.new_total_cost == 75
    assert result.cost_delta == 25

    # Verify ListAction
    assert result.list_action.action_type == ListActionType.UPDATE_EQUIPMENT
    assert result.list_action.rating_delta == 25
    assert result.list_action.stash_delta == 0
    assert result.list_action.credits_delta == 0
    assert "+25" in result.description

    # Verify assignment updated
    assignment.refresh_from_db()
    assert assignment.total_cost_override == 75


@pytest.mark.django_db
def test_handle_equipment_cost_override_clear(
    user, make_list, content_fighter, make_equipment, settings
):
    """Test that clearing total_cost_override creates ListAction with negative delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 575
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    equipment = make_equipment("Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        total_cost_override=75,  # Was overridden to 75
    )

    # Simulate form clearing the value
    assignment.total_cost_override = None

    # Clear override (delta = 50 - 75 = -25)
    result = handle_equipment_cost_override(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        old_total_cost_override=75,
        new_total_cost_override=None,
    )

    assert result is not None
    assert result.old_total_cost == 75
    assert result.new_total_cost == 50
    assert result.cost_delta == -25

    # Verify ListAction
    assert result.list_action.rating_delta == -25
    assert "-25" in result.description

    # Verify assignment updated
    assignment.refresh_from_db()
    assert assignment.total_cost_override is None


@pytest.mark.django_db
def test_handle_equipment_cost_override_change(
    user, make_list, content_fighter, make_equipment, settings
):
    """Test that changing total_cost_override value creates correct delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 600
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    equipment = make_equipment("Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
        total_cost_override=75,
    )

    # Simulate form changing value from 75 to 100
    assignment.total_cost_override = 100

    # Change override from 75 to 100 (delta = 100 - 75 = +25)
    result = handle_equipment_cost_override(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        old_total_cost_override=75,
        new_total_cost_override=100,
    )

    assert result is not None
    assert result.old_total_cost == 75
    assert result.new_total_cost == 100
    assert result.cost_delta == 25


@pytest.mark.django_db
def test_handle_equipment_cost_override_stash_fighter(
    user, make_list, make_content_fighter, content_house, make_equipment, settings
):
    """Test that cost changes for stash fighter equipment go to stash_delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.stash_current = 100
    lst.save()

    # Create a stash fighter type
    stash_fighter_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )

    stash_fighter = ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_fighter_type,
        list=lst,
        owner=user,
    )

    equipment = make_equipment("Stash Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash_fighter,
        content_equipment=equipment,
    )

    # Simulate form applying new value
    assignment.total_cost_override = 75

    # Set override on stash equipment (should go to stash_delta)
    result = handle_equipment_cost_override(
        user=user,
        lst=lst,
        fighter=stash_fighter,
        assignment=assignment,
        old_total_cost_override=None,
        new_total_cost_override=75,
    )

    assert result is not None
    assert result.cost_delta == 25
    assert result.list_action.stash_delta == 25
    assert result.list_action.rating_delta == 0


@pytest.mark.django_db
def test_handle_equipment_cost_override_with_profiles_and_accessories(
    user, make_list, content_fighter, make_weapon_with_accessory, settings
):
    """Test that cost delta is correct when equipment has profiles and accessories."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    weapon, accessory = make_weapon_with_accessory(cost=50, accessory_cost=25)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )
    assignment.weapon_accessories_field.add(accessory)

    # Simulate form applying new value
    assignment.total_cost_override = 100

    # Equipment base=50, accessory=25, total=75
    # Set override to 100 (delta = 100 - 75 = +25)
    result = handle_equipment_cost_override(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        old_total_cost_override=None,
        new_total_cost_override=100,
    )

    assert result is not None
    assert result.old_total_cost == 75
    assert result.new_total_cost == 100
    assert result.cost_delta == 25


@pytest.mark.django_db
def test_handle_equipment_cost_override_zero_delta(
    user, make_list, content_fighter, make_equipment, settings
):
    """Test setting override to same as calculated cost results in zero delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    equipment = make_equipment("Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    # Simulate form applying new value
    assignment.total_cost_override = 50

    # Set override to same as calculated cost (delta = 50 - 50 = 0)
    result = handle_equipment_cost_override(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        old_total_cost_override=None,
        new_total_cost_override=50,
    )

    assert result is not None
    assert result.cost_delta == 0
    assert result.list_action.rating_delta == 0
