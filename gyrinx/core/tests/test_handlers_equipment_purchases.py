"""
Tests for equipment purchase handlers.

These tests directly test the handler functions in gyrinx.core.handlers.equipment_purchases,
ensuring that business logic works correctly without involving HTTP machinery.
"""

import pytest
from django.core.exceptions import ValidationError

from gyrinx.core.handlers.equipment_purchases import (
    handle_accessory_purchase,
    handle_equipment_purchase,
    handle_equipment_upgrade,
    handle_weapon_profile_purchase,
)
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_handle_equipment_purchase_campaign_mode(
    user, list_with_campaign, content_fighter, make_equipment
):
    """Test equipment purchase in campaign mode creates actions and spends credits."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    equipment = make_equipment("Test Weapon", cost="50")

    # Create assignment (mimicking what the form does)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    # Call the handler
    result = handle_equipment_purchase(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
    )

    # Verify result
    assert result.total_cost == 50
    assert result.assignment == assignment
    assert "Bought Test Weapon for Test Fighter" in result.description

    # Verify ListAction created
    assert result.list_action is not None
    assert result.list_action.action_type == ListActionType.ADD_EQUIPMENT
    assert result.list_action.rating_delta == 50
    assert result.list_action.credits_delta == -50
    assert result.list_action.rating_before == 500
    assert result.list_action.credits_before == 1000

    # Verify CampaignAction created
    assert result.campaign_action is not None
    assert "Bought Test Weapon for Test Fighter" in result.campaign_action.description

    # Verify credits spent (no refresh needed - handler modifies the same object)
    assert lst.credits_current == 950


@pytest.mark.django_db
def test_handle_equipment_purchase_list_building_mode(
    user, make_list, content_house, content_fighter, make_equipment
):
    """Test equipment purchase in list building mode (no credits)."""
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

    result = handle_equipment_purchase(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
    )

    # Verify result
    assert result.total_cost == 50
    assert "Added Test Weapon to Test Fighter" in result.description

    # Verify ListAction created
    assert result.list_action.rating_delta == 50
    assert result.list_action.credits_delta == 0  # No credits in list building mode

    # Verify no CampaignAction
    assert result.campaign_action is None


@pytest.mark.django_db
def test_handle_equipment_purchase_stash_fighter(
    user, list_with_campaign, content_house, make_content_fighter, make_equipment
):
    """Test equipment purchase for stash fighter affects stash, not rating."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.stash_current = 100
    lst.rating_current = 500
    lst.save()

    # Create a stash fighter
    stash_fighter_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    fighter = ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_fighter_type,
        list=lst,
        owner=user,
    )
    assert fighter.is_stash

    equipment = make_equipment("Test Equipment", cost="50")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    result = handle_equipment_purchase(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
    )

    # Verify stash delta, not rating delta
    assert result.list_action.stash_delta == 50
    assert result.list_action.rating_delta == 0
    assert result.list_action.credits_delta == -50


@pytest.mark.django_db
def test_handle_equipment_purchase_insufficient_credits(
    user, list_with_campaign, content_fighter, make_equipment
):
    """Test equipment purchase fails with insufficient credits."""
    lst = list_with_campaign
    lst.credits_current = 25  # Not enough for 50 credit weapon
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    equipment = make_equipment("Expensive Weapon", cost="50")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    # Should raise ValidationError due to insufficient credits
    with pytest.raises(ValidationError, match="Insufficient credits"):
        handle_equipment_purchase(
            user=user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
        )

    # Verify no new actions created (only the initial CREATE action exists)
    assert ListAction.objects.count() == 1  # Only the initial CREATE action
    assert ListAction.objects.first().action_type == ListActionType.CREATE
    assert CampaignAction.objects.count() == 0


@pytest.mark.django_db
def test_handle_accessory_purchase_campaign_mode(
    user, list_with_campaign, content_fighter, make_weapon_with_accessory
):
    """Test weapon accessory purchase in campaign mode."""
    lst = list_with_campaign
    lst.credits_current = 1000
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

    result = handle_accessory_purchase(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        accessory=accessory,
    )

    # Verify result
    assert result.accessory_cost == 25
    assert accessory in assignment.weapon_accessories_field.all()

    # Verify ListAction
    assert result.list_action.action_type == ListActionType.UPDATE_EQUIPMENT
    assert result.list_action.rating_delta == 25
    assert result.list_action.credits_delta == -25
    assert result.list_action.rating_before == 500
    assert result.list_action.credits_before == 1000

    # Verify CampaignAction
    assert result.campaign_action is not None

    # Verify credits spent (no refresh needed - handler modifies the same object)
    assert lst.credits_current == 975


@pytest.mark.django_db
def test_handle_accessory_purchase_stash_fighter(
    user,
    list_with_campaign,
    content_house,
    make_content_fighter,
    make_weapon_with_accessory,
):
    """Test accessory purchase for stash fighter affects stash, not rating."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.stash_current = 100
    lst.save()

    stash_fighter_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    fighter = ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_fighter_type,
        list=lst,
        owner=user,
    )

    weapon, accessory = make_weapon_with_accessory(cost=50, accessory_cost=25)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )

    result = handle_accessory_purchase(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        accessory=accessory,
    )

    # Verify stash delta
    assert result.list_action.stash_delta == 25
    assert result.list_action.rating_delta == 0


@pytest.mark.django_db
def test_handle_weapon_profile_purchase_campaign_mode(
    user, list_with_campaign, content_fighter, make_weapon_with_profile
):
    """Test weapon profile purchase in campaign mode."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    weapon, profile = make_weapon_with_profile(cost=50, profile_cost=30)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )

    result = handle_weapon_profile_purchase(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        profile=profile,
    )

    # Verify result
    assert result.profile_cost == 30
    assert profile in assignment.weapon_profiles_field.all()

    # Verify ListAction
    assert result.list_action.action_type == ListActionType.UPDATE_EQUIPMENT
    assert result.list_action.rating_delta == 30
    assert result.list_action.credits_delta == -30

    # Verify credits spent (no refresh needed - handler modifies the same object)
    assert lst.credits_current == 970


@pytest.mark.django_db
def test_handle_equipment_upgrade_add_upgrades(
    user, list_with_campaign, content_fighter, make_equipment_with_upgrades
):
    """Test adding equipment upgrades in campaign mode."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    equipment, upgrade = make_equipment_with_upgrades(cost=50, upgrade_cost=20)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    result = handle_equipment_upgrade(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        new_upgrades=[upgrade],
    )

    # Verify result
    assert result.cost_difference == 20
    assert upgrade in assignment.upgrades_field.all()

    # Verify ListAction
    assert result.list_action.action_type == ListActionType.UPDATE_EQUIPMENT
    assert result.list_action.rating_delta == 20
    assert result.list_action.credits_delta == -20

    # Verify credits spent (no refresh needed - handler modifies the same object)
    assert lst.credits_current == 980


@pytest.mark.django_db
def test_handle_equipment_upgrade_remove_upgrades(
    user, list_with_campaign, content_fighter, make_equipment_with_upgrades
):
    """Test removing equipment upgrades (negative cost delta)."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 520  # Includes fighter + equipment + upgrade
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    equipment, upgrade = make_equipment_with_upgrades(cost=50, upgrade_cost=20)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )
    assignment.upgrades_field.add(upgrade)

    # Remove the upgrade
    result = handle_equipment_upgrade(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        new_upgrades=[],  # Empty list removes all upgrades
    )

    # Verify result
    assert result.cost_difference == -20
    assert assignment.upgrades_field.count() == 0

    # Verify ListAction
    assert result.list_action.rating_delta == -20
    assert result.list_action.credits_delta == 0  # No credits returned

    # Verify no CampaignAction (no credits spent)
    assert result.campaign_action is None

    # Verify description indicates removal
    assert "Removed upgrades" in result.description


@pytest.mark.django_db
def test_handle_equipment_upgrade_stash_fighter(
    user,
    list_with_campaign,
    content_house,
    make_content_fighter,
    make_equipment_with_upgrades,
):
    """Test upgrade for stash fighter affects stash, not rating."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.stash_current = 100
    lst.save()

    stash_fighter_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    fighter = ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_fighter_type,
        list=lst,
        owner=user,
    )

    equipment, upgrade = make_equipment_with_upgrades(cost=50, upgrade_cost=20)

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    result = handle_equipment_upgrade(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        new_upgrades=[upgrade],
    )

    # Verify stash delta
    assert result.list_action.stash_delta == 20
    assert result.list_action.rating_delta == 0


@pytest.mark.django_db
def test_actions_have_correct_before_values(
    user, list_with_campaign, content_fighter, make_equipment
):
    """Test that ListAction records correct before values."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.stash_current = 100
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

    result = handle_equipment_purchase(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
    )

    # Verify before values match original list state
    assert result.list_action.rating_before == 500
    assert result.list_action.stash_before == 100
    assert result.list_action.credits_before == 1000


@pytest.mark.django_db
def test_transaction_rollback_on_insufficient_credits(
    user, list_with_campaign, content_fighter, make_equipment
):
    """Test that transaction rolls back completely on error."""
    lst = list_with_campaign
    lst.credits_current = 25
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    equipment = make_equipment("Expensive Weapon", cost="50")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    initial_assignment_count = ListFighterEquipmentAssignment.objects.count()

    with pytest.raises(ValidationError):
        handle_equipment_purchase(
            user=user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
        )

    # Verify no new ListAction or CampaignAction created (only the initial CREATE action exists)
    assert ListAction.objects.count() == 1  # Only the initial CREATE action
    assert ListAction.objects.first().action_type == ListActionType.CREATE
    assert CampaignAction.objects.count() == 0

    # Verify list credits unchanged (no refresh needed - ValidationError raised before modification)
    assert lst.credits_current == 25

    # Assignment still exists (was created before handler call)
    assert ListFighterEquipmentAssignment.objects.count() == initial_assignment_count
