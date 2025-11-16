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
    handle_equipment_reassignment,
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


# Regression tests for view cleanup bugs


@pytest.mark.django_db
def test_accessory_purchase_failure_preserves_existing_accessories(
    user, list_with_campaign, content_fighter, make_weapon_with_accessory
):
    """
    Test that when an accessory purchase fails (insufficient credits),
    any accessories already on the weapon are preserved.

    This is a regression test for a bug where view code would do:
        assignment.weapon_accessories_field.remove(accessory)
    after handler failure, which could incorrectly remove pre-existing accessories.

    The handler's @transaction.atomic decorator creates a savepoint. When the
    handler fails, the savepoint rolls back the .add(accessory) automatically.
    Manual cleanup in the view is unnecessary and harmful.
    """
    from gyrinx.content.models import ContentWeaponAccessory

    lst = list_with_campaign
    lst.credits_current = 100  # Enough for initial setup
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Create weapon with accessory A already attached
    weapon, accessory_a = make_weapon_with_accessory(cost=10, accessory_cost=10)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )
    assignment.weapon_accessories_field.add(accessory_a)

    # Reduce credits so we can't afford another accessory
    lst.credits_current = 5  # Not enough for accessory B
    lst.save()

    # Create accessory B (expensive)
    accessory_b = ContentWeaponAccessory.objects.create(
        name="Expensive Scope",
        cost=50,
    )

    # Try to add accessory B (should fail due to insufficient credits)
    with pytest.raises(ValidationError, match="Insufficient credits"):
        handle_accessory_purchase(
            user=user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
            accessory=accessory_b,
        )

    # CRITICAL: Accessory A should still be there
    # Bug would cause it to be removed by view's cleanup code
    assignment.refresh_from_db()
    assert accessory_a in assignment.weapon_accessories_field.all()
    assert accessory_b not in assignment.weapon_accessories_field.all()
    assert assignment.weapon_accessories_field.count() == 1


@pytest.mark.django_db
def test_profile_purchase_failure_preserves_existing_profiles(
    user, list_with_campaign, content_fighter, make_weapon_with_profile
):
    """
    Test that when a profile purchase fails, existing profiles are preserved.

    Regression test for bug where view would do:
        assignment.weapon_profiles_field.remove(profile)
    after handler failure.
    """
    from gyrinx.content.models import ContentWeaponProfile

    lst = list_with_campaign
    lst.credits_current = 100
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Create weapon with profile A already attached
    weapon, profile_a = make_weapon_with_profile(cost=10, profile_cost=10)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )
    assignment.weapon_profiles_field.add(profile_a)

    # Reduce credits
    lst.credits_current = 5
    lst.save()

    # Create profile B (expensive)
    profile_b = ContentWeaponProfile.objects.create(
        name="Expensive Profile",
        equipment=weapon,
        cost=50,
    )

    # Try to add profile B (should fail)
    with pytest.raises(ValidationError, match="Insufficient credits"):
        handle_weapon_profile_purchase(
            user=user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
            profile=profile_b,
        )

    # CRITICAL: Profile A should still be there
    assignment.refresh_from_db()
    assert profile_a in assignment.weapon_profiles_field.all()
    assert profile_b not in assignment.weapon_profiles_field.all()
    assert assignment.weapon_profiles_field.count() == 1


@pytest.mark.django_db
def test_upgrade_change_failure_preserves_existing_upgrades(
    user, list_with_campaign, content_fighter, make_equipment_with_upgrades
):
    """
    Test that when an upgrade change fails, original upgrades are preserved.

    Regression test for bug where view would do:
        assignment.upgrades_field.set(old_upgrades)
    after handler failure (redundant with transaction rollback).
    """
    from gyrinx.content.models import ContentEquipmentUpgrade

    lst = list_with_campaign
    lst.credits_current = 100
    lst.save()

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Create equipment with upgrade A (cheap)
    equipment, upgrade_a = make_equipment_with_upgrades(cost=10, upgrade_cost=5)
    # Set to MULTI mode so upgrades have independent costs, not cumulative
    from gyrinx.content.models import ContentEquipment

    equipment.upgrade_mode = ContentEquipment.UpgradeMode.MULTI
    equipment.save()

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )
    assignment.upgrades_field.add(upgrade_a)

    # Reduce credits to almost nothing
    lst.credits_current = 10  # Not enough for the cost difference
    lst.save()

    # Create upgrade B (much more expensive)
    upgrade_b = ContentEquipmentUpgrade.objects.create(
        name="Expensive Upgrade",
        cost=100,  # Very expensive - difference from upgrade_a is 95 credits
        equipment=equipment,
    )

    # Try to replace A with B (should fail - need 95 credits but only have 10)
    with pytest.raises(ValidationError, match="Insufficient credits"):
        handle_equipment_upgrade(
            user=user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
            new_upgrades=[upgrade_b],  # Replace A (5 credits) with B (100 credits)
        )

    # CRITICAL: Original upgrade A should still be there
    # Transaction rollback handles this, buggy manual restoration could cause issues
    assignment.refresh_from_db()
    assert upgrade_a in assignment.upgrades_field.all()
    assert upgrade_b not in assignment.upgrades_field.all()
    assert assignment.upgrades_field.count() == 1


# ===== Equipment Reassignment Tests =====


@pytest.mark.django_db
def test_handle_equipment_reassignment_stash_to_regular(
    user, list_with_campaign, content_fighter, make_equipment
):
    """Test reassigning equipment from stash to regular fighter."""
    lst = list_with_campaign
    lst.rating_current = 500
    lst.stash_current = 100
    lst.credits_current = 1000
    lst.save()

    # Create stash and regular fighter
    stash = lst.ensure_stash()
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Create equipment on stash
    equipment = make_equipment("Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=equipment,
    )
    equipment_cost = assignment.cost_int()

    # Call handler (handler will perform the reassignment)
    result = handle_equipment_reassignment(
        user=user,
        lst=lst,
        from_fighter=stash,
        to_fighter=fighter,
        assignment=assignment,
    )

    # Verify deltas: stash→regular means rating+, stash-
    assert result.list_action.rating_delta == equipment_cost
    assert result.list_action.stash_delta == -equipment_cost
    assert result.list_action.credits_delta == 0  # Reassignment is free

    # Verify before values
    assert result.list_action.rating_before == 500
    assert result.list_action.stash_before == 100
    assert result.list_action.credits_before == 1000

    # Verify description is user-friendly (mentions "from stash")
    assert "from stash" in result.description
    assert fighter.name in result.description
    assert equipment.name in result.description

    # Verify CampaignAction created
    assert result.campaign_action is not None
    assert result.campaign_action.description == result.description

    # Verify assignment updated
    assignment.refresh_from_db()
    assert assignment.list_fighter == fighter


@pytest.mark.django_db
def test_handle_equipment_reassignment_regular_to_stash(
    user, list_with_campaign, content_fighter, make_equipment
):
    """Test reassigning equipment from regular fighter to stash."""
    lst = list_with_campaign
    lst.rating_current = 500
    lst.stash_current = 100
    lst.credits_current = 1000
    lst.save()

    # Create stash and regular fighter
    stash = lst.ensure_stash()
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Create equipment on regular fighter
    equipment = make_equipment("Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )
    equipment_cost = assignment.cost_int()

    # Call handler (handler will perform the reassignment)
    result = handle_equipment_reassignment(
        user=user,
        lst=lst,
        from_fighter=fighter,
        to_fighter=stash,
        assignment=assignment,
    )

    # Verify deltas: regular→stash means rating-, stash+
    assert result.list_action.rating_delta == -equipment_cost
    assert result.list_action.stash_delta == equipment_cost
    assert result.list_action.credits_delta == 0

    # Verify description mentions "to stash"
    assert "to stash" in result.description
    assert fighter.name in result.description
    assert equipment.name in result.description

    # Verify CampaignAction created
    assert result.campaign_action is not None


@pytest.mark.django_db
def test_handle_equipment_reassignment_regular_to_regular(
    user, list_with_campaign, content_fighter, make_equipment
):
    """Test reassigning equipment between two regular fighters."""
    lst = list_with_campaign
    lst.rating_current = 500
    lst.stash_current = 100
    lst.save()

    # Create two regular fighters
    fighter1 = ListFighter.objects.create(
        name="Fighter One",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    fighter2 = ListFighter.objects.create(
        name="Fighter Two",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Create equipment on fighter1
    equipment = make_equipment("Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter1,
        content_equipment=equipment,
    )

    # Call handler (handler will perform the reassignment)
    result = handle_equipment_reassignment(
        user=user,
        lst=lst,
        from_fighter=fighter1,
        to_fighter=fighter2,
        assignment=assignment,
    )

    # Verify no deltas: regular→regular means same bucket
    assert result.list_action.rating_delta == 0
    assert result.list_action.stash_delta == 0
    assert result.list_action.credits_delta == 0

    # Verify description includes both fighter names
    assert "Fighter One" in result.description
    assert "Fighter Two" in result.description
    assert "Reassigned" in result.description


@pytest.mark.django_db
def test_handle_equipment_reassignment_list_building_mode(
    user, make_list, content_fighter, make_equipment
):
    """Test equipment reassignment in list building mode (no campaign)."""
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    # Create two fighters
    fighter1 = ListFighter.objects.create(
        name="Fighter One",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    fighter2 = ListFighter.objects.create(
        name="Fighter Two",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Create equipment
    equipment = make_equipment("Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter1,
        content_equipment=equipment,
    )

    # Call handler (handler will perform the reassignment)
    result = handle_equipment_reassignment(
        user=user,
        lst=lst,
        from_fighter=fighter1,
        to_fighter=fighter2,
        assignment=assignment,
    )

    # Verify no CampaignAction in list building mode
    assert result.campaign_action is None

    # ListAction should still be created
    assert result.list_action is not None
    assert result.list_action.action_type == ListActionType.UPDATE_EQUIPMENT


@pytest.mark.django_db
def test_handle_equipment_reassignment_with_upgrades(
    user, list_with_campaign, content_fighter, make_equipment, make_equipment_upgrade
):
    """Test reassignment of equipment with upgrades includes total cost."""
    lst = list_with_campaign
    lst.rating_current = 500
    lst.stash_current = 100
    lst.save()

    # Create stash and fighter
    stash = lst.ensure_stash()
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Create equipment with upgrade
    equipment = make_equipment("Test Weapon", cost="50")
    upgrade = make_equipment_upgrade(
        name="Test Upgrade", cost="25", equipment=equipment
    )

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=equipment,
    )
    assignment.upgrades_field.add(upgrade)

    # Get total cost (base + upgrade)
    total_cost = assignment.cost_int()
    assert total_cost > 50  # Should include upgrade cost

    # Call handler (handler will perform the reassignment)
    result = handle_equipment_reassignment(
        user=user,
        lst=lst,
        from_fighter=stash,
        to_fighter=fighter,
        assignment=assignment,
    )

    # Verify deltas use total cost including upgrades
    assert result.equipment_cost == total_cost
    assert result.list_action.rating_delta == total_cost
    assert result.list_action.stash_delta == -total_cost


@pytest.mark.django_db
def test_handle_equipment_reassignment_before_values(
    user, list_with_campaign, content_fighter, make_equipment
):
    """Test that before values are captured correctly."""
    lst = list_with_campaign
    lst.rating_current = 750
    lst.stash_current = 200
    lst.credits_current = 1500
    lst.save()

    # Create fighters
    fighter1 = ListFighter.objects.create(
        name="Fighter One",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )
    fighter2 = ListFighter.objects.create(
        name="Fighter Two",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Create equipment
    equipment = make_equipment("Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter1,
        content_equipment=equipment,
    )

    # Call handler (handler will perform the reassignment)
    result = handle_equipment_reassignment(
        user=user,
        lst=lst,
        from_fighter=fighter1,
        to_fighter=fighter2,
        assignment=assignment,
    )

    # Verify before values match list state before operation
    assert result.list_action.rating_before == 750
    assert result.list_action.stash_before == 200
    assert result.list_action.credits_before == 1500


@pytest.mark.django_db
def test_handle_equipment_reassignment_description_stash_to_regular(
    user, list_with_campaign, content_fighter, make_equipment
):
    """Test description format for stash to regular reassignment."""
    lst = list_with_campaign
    lst.rating_current = 100
    lst.stash_current = 100  # Ensure we have enough stash to move from
    lst.save()

    stash = lst.ensure_stash()
    fighter = ListFighter.objects.create(
        name="My Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    equipment = make_equipment("Lasgun", cost="15")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash,
        content_equipment=equipment,
    )

    result = handle_equipment_reassignment(
        user=user,
        lst=lst,
        from_fighter=stash,
        to_fighter=fighter,
        assignment=assignment,
    )

    # Verify user-friendly description
    assert result.description == "Equipped My Fighter with Lasgun from stash (15¢)"


@pytest.mark.django_db
def test_handle_equipment_reassignment_description_regular_to_stash(
    user, list_with_campaign, content_fighter, make_equipment
):
    """Test description format for regular to stash reassignment."""
    lst = list_with_campaign
    lst.rating_current = 100  # Ensure we have enough rating to move from
    lst.stash_current = 100
    lst.save()

    stash = lst.ensure_stash()
    fighter = ListFighter.objects.create(
        name="My Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    equipment = make_equipment("Lasgun", cost="15")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    result = handle_equipment_reassignment(
        user=user,
        lst=lst,
        from_fighter=fighter,
        to_fighter=stash,
        assignment=assignment,
    )

    # Verify user-friendly description
    assert result.description == "Moved Lasgun from My Fighter to stash (15¢)"
