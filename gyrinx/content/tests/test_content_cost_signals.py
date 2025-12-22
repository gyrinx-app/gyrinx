"""
Tests for content model cost change signals.

When a Content model's cost field changes, affected core objects
(assignments, fighters, lists) should be marked as dirty.
"""

import pytest

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentFighterHouseOverride,
    ContentHouse,
    ContentWeaponAccessory,
    ContentWeaponProfile,
)
from gyrinx.core.models.list import (
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.models import FighterCategoryChoices


@pytest.fixture
def content_house():
    """Create a test house."""
    return ContentHouse.objects.create(name="Test House")


@pytest.fixture
def content_fighter(content_house):
    """Create a test content fighter."""
    return ContentFighter.objects.create(
        type="Test Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )


@pytest.fixture
def equipment_category():
    """Create a test equipment category."""
    return ContentEquipmentCategory.objects.create(name="Test Category", group="Gear")


@pytest.fixture
def content_equipment(equipment_category):
    """Create a test equipment with cost."""
    return ContentEquipment.objects.create(
        name="Test Equipment", category=equipment_category, cost="100"
    )


@pytest.fixture
def content_weapon_equipment(equipment_category):
    """Create a test weapon equipment."""
    return ContentEquipment.objects.create(
        name="Test Weapon", category=equipment_category, cost="75"
    )


@pytest.fixture
def content_weapon_profile(content_weapon_equipment):
    """Create a test weapon profile."""
    return ContentWeaponProfile.objects.create(
        equipment=content_weapon_equipment, name="Long Range", cost=25
    )


@pytest.fixture
def content_accessory():
    """Create a test weapon accessory."""
    return ContentWeaponAccessory.objects.create(name="Test Scope", cost=15)


@pytest.fixture
def content_upgrade(content_equipment):
    """Create a test equipment upgrade."""
    return ContentEquipmentUpgrade.objects.create(
        equipment=content_equipment, name="Basic Upgrade", position=1, cost=20
    )


# ============================================================================
# ContentEquipment.cost change tests
# ============================================================================


@pytest.mark.django_db
def test_equipment_cost_change_marks_assignment_dirty(
    user, make_list, content_fighter, content_equipment
):
    """When ContentEquipment.cost changes, affected assignments should be marked dirty."""
    # Create list and fighter (without initial action to test dirty propagation in isolation)
    lst = make_list("Test List", create_initial_action=False)
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=150,
        dirty=False,
    )

    # Create assignment using the equipment
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        rating_current=100,
        dirty=False,
    )

    # Verify initial state
    assert assignment.dirty is False
    assert fighter.dirty is False
    assert lst.dirty is False

    # Change equipment cost - this should trigger the signal
    content_equipment.cost = "150"
    content_equipment.save()

    # Refresh from database
    assignment.refresh_from_db()
    fighter.refresh_from_db()
    lst.refresh_from_db()

    # All should now be dirty
    assert assignment.dirty is True
    assert fighter.dirty is True
    assert lst.dirty is True


@pytest.mark.django_db
def test_equipment_cost_no_change_does_not_mark_dirty(
    user, make_list, content_fighter, content_equipment
):
    """When ContentEquipment.cost stays the same, no dirty flags should be set."""
    # Create list and fighter
    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=150,
        dirty=False,
    )

    # Create assignment using the equipment
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        rating_current=100,
        dirty=False,
    )

    # Save without changing cost
    content_equipment.save()

    # Refresh from database
    assignment.refresh_from_db()
    fighter.refresh_from_db()
    lst.refresh_from_db()

    # Should still be clean
    assert assignment.dirty is False
    assert fighter.dirty is False
    assert lst.dirty is False


@pytest.mark.django_db
def test_new_equipment_does_not_trigger_dirty(equipment_category):
    """Creating new equipment should not trigger dirty flag signals."""
    # This is a new instance - no assignments exist yet
    equipment = ContentEquipment.objects.create(
        name="New Equipment", category=equipment_category, cost="100"
    )
    # If this doesn't raise, we're good - no assignments to mark dirty
    assert equipment.pk is not None


# ============================================================================
# ContentFighter.base_cost change tests
# ============================================================================


@pytest.mark.django_db
def test_fighter_base_cost_change_marks_list_fighter_dirty(
    user, make_list, content_fighter
):
    """When ContentFighter.base_cost changes, affected ListFighters should be marked dirty."""
    # Create list and fighter (without initial action to test dirty propagation in isolation)
    lst = make_list("Test List", create_initial_action=False)
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=50,
        dirty=False,
    )

    # Verify initial state
    assert fighter.dirty is False
    assert lst.dirty is False

    # Change base cost - this should trigger the signal
    content_fighter.base_cost = 75
    content_fighter.save()

    # Refresh from database
    fighter.refresh_from_db()
    lst.refresh_from_db()

    # Both should now be dirty
    assert fighter.dirty is True
    assert lst.dirty is True


# ============================================================================
# ContentFighterHouseOverride.cost change tests
# ============================================================================


@pytest.mark.django_db
def test_fighter_house_override_cost_change_marks_matching_fighter_dirty(
    user, make_list, content_fighter, content_house
):
    """
    When ContentFighterHouseOverride.cost changes, only ListFighters using
    that fighter type in that specific house should be marked dirty.

    This test verifies the bug fix for using the correct field name
    (instance.fighter, not instance.content_fighter).
    """
    # Create a house override for this fighter in this house
    override = ContentFighterHouseOverride.objects.create(
        fighter=content_fighter,
        house=content_house,
        cost=75,  # Different from base_cost (50)
    )

    # Create list in the same house (without initial action to test dirty propagation)
    lst = make_list("Test List", create_initial_action=False)
    # Ensure the list uses the correct house
    lst.content_house = content_house
    lst.save()

    # Create a fighter that matches the override (same fighter type, same house)
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=75,
        dirty=False,
    )

    # Verify initial state
    assert fighter.dirty is False
    assert lst.dirty is False

    # Change the house override cost - this should trigger the signal
    override.cost = 100
    override.save()

    # Refresh from database
    fighter.refresh_from_db()
    lst.refresh_from_db()

    # Both should now be dirty
    assert fighter.dirty is True
    assert lst.dirty is True


@pytest.mark.django_db
def test_fighter_house_override_cost_change_does_not_mark_other_house_dirty(
    user, make_list, content_fighter, content_house
):
    """
    When ContentFighterHouseOverride.cost changes, ListFighters in
    different houses should NOT be marked dirty.
    """
    # Create a second house
    other_house = ContentHouse.objects.create(name="Other House")

    # Create a house override for the fighter in the FIRST house
    override = ContentFighterHouseOverride.objects.create(
        fighter=content_fighter,
        house=content_house,
        cost=75,
    )

    # Create list in the OTHER house
    lst = make_list("Test List", create_initial_action=False)
    lst.content_house = other_house
    lst.save()

    # Create a fighter using the same fighter type but in the other house
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=50,  # Using base cost since no override for this house
        dirty=False,
    )

    # Verify initial state
    assert fighter.dirty is False
    assert lst.dirty is False

    # Change the house override cost
    override.cost = 100
    override.save()

    # Refresh from database
    fighter.refresh_from_db()
    lst.refresh_from_db()

    # Should NOT be dirty since this list is in a different house
    assert fighter.dirty is False
    assert lst.dirty is False


# ============================================================================
# ContentWeaponProfile.cost change tests
# ============================================================================


@pytest.mark.django_db
def test_weapon_profile_cost_change_marks_assignment_dirty(
    user, make_list, content_fighter, content_weapon_equipment, content_weapon_profile
):
    """When ContentWeaponProfile.cost changes, affected assignments should be marked dirty."""
    # Create list and fighter (without initial action to test dirty propagation in isolation)
    lst = make_list("Test List", create_initial_action=False)
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
        dirty=False,
    )

    # Create assignment with the weapon profile
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_weapon_equipment,
        rating_current=100,
        dirty=False,
    )
    assignment.weapon_profiles_field.add(content_weapon_profile)

    # Verify initial state
    assert assignment.dirty is False

    # Change profile cost
    content_weapon_profile.cost = 50
    content_weapon_profile.save()

    # Refresh from database
    assignment.refresh_from_db()
    fighter.refresh_from_db()
    lst.refresh_from_db()

    # All should now be dirty
    assert assignment.dirty is True
    assert fighter.dirty is True
    assert lst.dirty is True


# ============================================================================
# ContentWeaponAccessory.cost change tests
# ============================================================================


@pytest.mark.django_db
def test_weapon_accessory_cost_change_marks_assignment_dirty(
    user,
    make_list,
    content_fighter,
    content_weapon_equipment,
    content_accessory,
):
    """When ContentWeaponAccessory.cost changes, affected assignments should be marked dirty."""
    # Create list and fighter (without initial action to test dirty propagation in isolation)
    lst = make_list("Test List", create_initial_action=False)
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
        dirty=False,
    )

    # Create assignment with the accessory
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_weapon_equipment,
        rating_current=100,
        dirty=False,
    )
    assignment.weapon_accessories_field.add(content_accessory)

    # Verify initial state
    assert assignment.dirty is False

    # Change accessory cost
    content_accessory.cost = 30
    content_accessory.save()

    # Refresh from database
    assignment.refresh_from_db()
    fighter.refresh_from_db()
    lst.refresh_from_db()

    # All should now be dirty
    assert assignment.dirty is True
    assert fighter.dirty is True
    assert lst.dirty is True


# ============================================================================
# ContentEquipmentUpgrade.cost change tests
# ============================================================================


@pytest.mark.django_db
def test_equipment_upgrade_cost_change_marks_assignment_dirty(
    user,
    make_list,
    content_fighter,
    content_equipment,
    content_upgrade,
):
    """When ContentEquipmentUpgrade.cost changes, affected assignments should be marked dirty."""
    # Create list and fighter (without initial action to test dirty propagation in isolation)
    lst = make_list("Test List", create_initial_action=False)
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
        dirty=False,
    )

    # Create assignment with the upgrade
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        rating_current=100,
        dirty=False,
    )
    assignment.upgrades_field.add(content_upgrade)

    # Verify initial state
    assert assignment.dirty is False

    # Change upgrade cost
    content_upgrade.cost = 40
    content_upgrade.save()

    # Refresh from database
    assignment.refresh_from_db()
    fighter.refresh_from_db()
    lst.refresh_from_db()

    # All should now be dirty
    assert assignment.dirty is True
    assert fighter.dirty is True
    assert lst.dirty is True


# ============================================================================
# ContentFighterEquipmentListItem.cost change tests
# ============================================================================


@pytest.mark.django_db
def test_equipment_list_item_cost_change_marks_assignment_dirty(
    user, make_list, content_fighter, content_equipment
):
    """When ContentFighterEquipmentListItem.cost changes, affected assignments should be marked dirty."""
    from gyrinx.content.models import ContentFighterEquipmentListItem

    # Create an equipment list item for this fighter/equipment combo
    list_item = ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter,
        equipment=content_equipment,
        cost=50,  # Override cost
    )

    # Create list and fighter (without initial action to test dirty propagation in isolation)
    lst = make_list("Test List", create_initial_action=False)
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=100,
        dirty=False,
    )

    # Create assignment with the equipment
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        rating_current=50,
        dirty=False,
    )

    # Verify initial state
    assert assignment.dirty is False
    assert fighter.dirty is False
    assert lst.dirty is False

    # Change the equipment list item cost
    list_item.cost = 75
    list_item.save()

    # Refresh from database
    assignment.refresh_from_db()
    fighter.refresh_from_db()
    lst.refresh_from_db()

    # All should now be dirty
    assert assignment.dirty is True
    assert fighter.dirty is True
    assert lst.dirty is True


# ============================================================================
# Multiple lists affected tests
# ============================================================================


@pytest.mark.django_db
def test_equipment_cost_change_marks_multiple_lists_dirty(
    user, make_list, content_fighter, content_equipment
):
    """When ContentEquipment.cost changes, ALL affected lists should be marked dirty."""
    # Create two lists (without initial action to test dirty propagation in isolation)
    lst1 = make_list("Test List 1", create_initial_action=False)
    lst2 = make_list("Test List 2", create_initial_action=False)

    fighter1 = ListFighter.objects.create(
        name="Fighter 1",
        content_fighter=content_fighter,
        list=lst1,
        owner=user,
        dirty=False,
    )
    fighter2 = ListFighter.objects.create(
        name="Fighter 2",
        content_fighter=content_fighter,
        list=lst2,
        owner=user,
        dirty=False,
    )

    assignment1 = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter1,
        content_equipment=content_equipment,
        dirty=False,
    )
    assignment2 = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter2,
        content_equipment=content_equipment,
        dirty=False,
    )

    # Change equipment cost
    content_equipment.cost = "200"
    content_equipment.save()

    # Refresh all from database
    assignment1.refresh_from_db()
    assignment2.refresh_from_db()
    fighter1.refresh_from_db()
    fighter2.refresh_from_db()
    lst1.refresh_from_db()
    lst2.refresh_from_db()

    # All should now be dirty
    assert assignment1.dirty is True
    assert assignment2.dirty is True
    assert fighter1.dirty is True
    assert fighter2.dirty is True
    assert lst1.dirty is True
    assert lst2.dirty is True


# ============================================================================
# set_dirty() method tests
# ============================================================================


@pytest.mark.django_db
def test_list_set_dirty_only_sets_own_flag(user, make_list):
    """List.set_dirty() should only set its own dirty flag."""
    lst = make_list("Test List")
    lst.dirty = False
    lst.save(update_fields=["dirty"])

    # Call set_dirty
    lst.set_dirty()

    lst.refresh_from_db()
    assert lst.dirty is True


@pytest.mark.django_db
def test_fighter_set_dirty_propagates_to_list(user, make_list, content_fighter):
    """ListFighter.set_dirty() should propagate to parent list."""
    lst = make_list("Test List")
    lst.dirty = False
    lst.save(update_fields=["dirty"])

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        dirty=False,
    )

    # Call set_dirty on fighter
    fighter.set_dirty()

    fighter.refresh_from_db()
    lst.refresh_from_db()

    assert fighter.dirty is True
    assert lst.dirty is True


@pytest.mark.django_db
def test_assignment_set_dirty_propagates_to_fighter_and_list(
    user, make_list, content_fighter, content_equipment
):
    """ListFighterEquipmentAssignment.set_dirty() should propagate to fighter and list."""
    lst = make_list("Test List")
    lst.dirty = False
    lst.save(update_fields=["dirty"])

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        dirty=False,
    )

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        dirty=False,
    )

    # Call set_dirty on assignment
    assignment.set_dirty()

    assignment.refresh_from_db()
    fighter.refresh_from_db()
    lst.refresh_from_db()

    assert assignment.dirty is True
    assert fighter.dirty is True
    assert lst.dirty is True


@pytest.mark.django_db
def test_set_dirty_idempotent_when_already_dirty(
    user, make_list, content_fighter, content_equipment
):
    """set_dirty() should be idempotent when object is already dirty."""
    lst = make_list("Test List")
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        dirty=True,  # Already dirty
    )
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        dirty=True,  # Already dirty
    )

    # Call set_dirty - should not raise or cause issues
    assignment.set_dirty()
    fighter.set_dirty()
    lst.set_dirty()

    # All should still be dirty
    assignment.refresh_from_db()
    fighter.refresh_from_db()
    lst.refresh_from_db()

    assert assignment.dirty is True
    assert fighter.dirty is True
    assert lst.dirty is True


# ============================================================================
# get_clean_list_or_404 tests
# ============================================================================


@pytest.mark.django_db
def test_get_clean_list_or_404_refreshes_dirty_list(user, make_list, content_fighter):
    """get_clean_list_or_404 should refresh a dirty list's cached facts."""
    from gyrinx.core.models.list import List
    from gyrinx.core.views.list import get_clean_list_or_404

    # Create a list with a fighter
    lst = make_list("Test List")
    ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        rating_current=50,
        dirty=False,
    )

    # Mark the list as dirty with stale rating
    lst.dirty = True
    lst.rating_current = 999  # Wrong value
    lst.save(update_fields=["dirty", "rating_current"])

    # get_clean_list_or_404 should refresh the list
    clean_list = get_clean_list_or_404(List, id=lst.id)

    # After refresh, the list should be clean with correct rating
    assert clean_list.dirty is False
    assert clean_list.rating_current == 50  # Fighter's base cost


@pytest.mark.django_db
def test_get_clean_list_or_404_skips_clean_list(user, make_list):
    """get_clean_list_or_404 should not call facts_from_db for clean lists."""
    from gyrinx.core.models.list import List
    from gyrinx.core.views.list import get_clean_list_or_404

    lst = make_list("Test List")
    lst.dirty = False
    lst.rating_current = 100
    lst.save(update_fields=["dirty", "rating_current"])

    # get_clean_list_or_404 should return the list without refreshing
    clean_list = get_clean_list_or_404(List, id=lst.id)

    # The list should still have its original rating (not recalculated)
    assert clean_list.dirty is False
    assert clean_list.rating_current == 100


# ============================================================================
# ContentEquipmentListExpansionItem.cost change tests
# ============================================================================


@pytest.mark.django_db
def test_expansion_item_cost_change_marks_assignment_dirty(
    user, make_list, content_fighter, content_equipment
):
    """When ContentEquipmentListExpansionItem.cost changes, affected assignments should be marked dirty."""
    from gyrinx.content.models_.expansion import (
        ContentEquipmentListExpansion,
        ContentEquipmentListExpansionItem,
    )

    # Create expansion with item
    expansion = ContentEquipmentListExpansion.objects.create(name="Test Expansion")
    expansion_item = ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=content_equipment,
        cost=50,
    )

    # Create list and fighter (without initial action to test dirty propagation in isolation)
    lst = make_list("Test List", create_initial_action=False)
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        dirty=False,
    )
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        dirty=False,
    )

    # Verify initial state
    assert assignment.dirty is False
    assert fighter.dirty is False
    assert lst.dirty is False

    # Change the expansion item cost
    expansion_item.cost = 75
    expansion_item.save()

    # Refresh from database
    assignment.refresh_from_db()
    fighter.refresh_from_db()
    lst.refresh_from_db()

    # All should now be dirty
    assert assignment.dirty is True
    assert fighter.dirty is True
    assert lst.dirty is True


# ============================================================================
# CONTENT_COST_CHANGE action creation tests
# ============================================================================


@pytest.mark.django_db
def test_equipment_cost_change_creates_action(
    user, make_list, content_fighter, content_equipment, settings
):
    """When ContentEquipment.cost changes, a CONTENT_COST_CHANGE action should be created."""
    from gyrinx.core.models.action import ListAction, ListActionType

    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    # Create list with initial action (required for create_action to work)
    lst = make_list("Test List", create_initial_action=True)
    # Create fighter and assignment with dirty=True so facts_from_db will recalculate
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        dirty=True,
    )
    _assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        dirty=True,
    )
    # Also mark list dirty
    lst.dirty = True
    lst.save()

    # Recalculate to get correct initial rating (150 = 50 fighter + 100 equipment)
    lst.facts_from_db(update=True)
    lst.refresh_from_db()
    initial_rating = lst.rating_current
    assert initial_rating == 150  # Sanity check

    initial_action_count = ListAction.objects.filter(list=lst).count()

    # Change equipment cost from 100 to 150 (increase of 50)
    content_equipment.cost = "150"
    content_equipment.save()

    # Check action was created
    lst.refresh_from_db()
    new_action_count = ListAction.objects.filter(list=lst).count()
    assert new_action_count == initial_action_count + 1

    # Verify action properties
    action = ListAction.objects.filter(list=lst).order_by("-created").first()
    assert action.action_type == ListActionType.CONTENT_COST_CHANGE
    assert "changed cost" in action.description
    assert "(+50¢)" in action.description  # Shows the cost increase
    assert action.rating_delta == 50  # Cost increased by 50
    assert action.credits_delta == 0  # Not campaign mode


@pytest.mark.django_db
def test_equipment_cost_change_campaign_mode_credits_increase(
    user, make_list, content_fighter, content_equipment, settings
):
    """In campaign mode, cost increase should charge credits."""
    from gyrinx.core.models.action import ListAction, ListActionType
    from gyrinx.core.models.list import List

    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    # Create campaign mode list with initial action
    lst = make_list("Campaign List", create_initial_action=True)
    lst.status = List.CAMPAIGN_MODE
    lst.credits_current = 500
    lst.dirty = True
    lst.save()

    # Create fighter and assignment with dirty=True so facts_from_db will recalculate
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        dirty=True,
    )
    _assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        dirty=True,
    )

    # Recalculate to get correct initial state
    lst.facts_from_db(update=True)
    lst.refresh_from_db()
    initial_credits = lst.credits_current

    # Change equipment cost from 100 to 150 (increase of 50)
    content_equipment.cost = "150"
    content_equipment.save()

    # Check credits were charged
    lst.refresh_from_db()
    action = ListAction.objects.filter(list=lst).order_by("-created").first()

    assert action.action_type == ListActionType.CONTENT_COST_CHANGE
    assert action.rating_delta == 50  # Cost increased by 50
    assert action.credits_delta == -50  # Charged 50 credits
    assert lst.credits_current == initial_credits - 50


@pytest.mark.django_db
def test_equipment_cost_change_campaign_mode_credits_decrease(
    user, make_list, content_fighter, content_equipment, settings
):
    """In campaign mode, cost decrease should refund credits."""
    from gyrinx.core.models.action import ListAction, ListActionType
    from gyrinx.core.models.list import List

    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    # Create campaign mode list with initial action
    lst = make_list("Campaign List", create_initial_action=True)
    lst.status = List.CAMPAIGN_MODE
    lst.credits_current = 200
    lst.dirty = True
    lst.save()

    # Create fighter and assignment with dirty=True so facts_from_db will recalculate
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        dirty=True,
    )
    _assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        dirty=True,
    )

    # Recalculate to get correct initial state
    lst.facts_from_db(update=True)
    lst.refresh_from_db()
    initial_credits = lst.credits_current

    # Change equipment cost from 100 to 60 (decrease of 40)
    content_equipment.cost = "60"
    content_equipment.save()

    # Check credits were refunded
    lst.refresh_from_db()
    action = ListAction.objects.filter(list=lst).order_by("-created").first()

    assert action.action_type == ListActionType.CONTENT_COST_CHANGE
    assert action.rating_delta == -40  # Cost decreased by 40
    assert action.credits_delta == 40  # Refunded 40 credits
    assert lst.credits_current == initial_credits + 40


@pytest.mark.django_db
def test_equipment_cost_change_campaign_mode_credits_can_go_negative(
    user, make_list, content_fighter, content_equipment, settings
):
    """In campaign mode, credits can go negative when cost increases."""
    from gyrinx.core.models.action import ListAction, ListActionType
    from gyrinx.core.models.list import List

    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    # Create campaign mode list with low credits
    lst = make_list("Campaign List", create_initial_action=True)
    lst.status = List.CAMPAIGN_MODE
    lst.credits_current = 20  # Only 20 credits
    lst.dirty = True
    lst.save()

    # Create fighter and assignment with dirty=True so facts_from_db will recalculate
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        dirty=True,
    )
    _assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        dirty=True,
    )

    # Recalculate to get correct initial state
    lst.facts_from_db(update=True)
    lst.refresh_from_db()

    # Change equipment cost from 100 to 200 (increase of 100, more than credits)
    content_equipment.cost = "200"
    content_equipment.save()

    # Check credits went negative
    lst.refresh_from_db()
    action = ListAction.objects.filter(list=lst).order_by("-created").first()

    assert action.action_type == ListActionType.CONTENT_COST_CHANGE
    assert action.credits_delta == -100  # Charged 100 credits
    assert lst.credits_current == 20 - 100  # = -80 (negative!)


@pytest.mark.django_db
def test_no_action_created_for_list_without_initial_action(
    user, content_house, content_fighter, content_equipment
):
    """Lists without an initial action should not get CONTENT_COST_CHANGE actions."""
    from gyrinx.core.models.action import ListAction
    from gyrinx.core.models.list import List

    # Create list WITHOUT initial action
    lst = List.objects.create(
        name="No Action List",
        content_house=content_house,
        owner=user,
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        dirty=False,
    )
    _assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        dirty=False,
    )

    initial_action_count = ListAction.objects.filter(list=lst).count()
    assert initial_action_count == 0  # No initial action

    # Change equipment cost
    content_equipment.cost = "150"
    content_equipment.save()

    # No action should be created
    final_action_count = ListAction.objects.filter(list=lst).count()
    assert final_action_count == 0


@pytest.mark.django_db
def test_content_cost_change_clears_dirty_flags_on_children(
    user, make_list, content_fighter, content_equipment, settings
):
    """Content cost change should clear dirty flags on list, fighter, and assignment."""
    from gyrinx.core.models.action import ListAction, ListActionType

    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = make_list("Test List", create_initial_action=True)

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        dirty=False,
    )
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=content_equipment,
        dirty=False,
    )

    # Recalculate to get correct initial state
    lst.facts_from_db(update=True)
    lst.refresh_from_db()
    fighter.refresh_from_db()
    assignment.refresh_from_db()

    # Verify all clean initially
    assert lst.dirty is False
    assert fighter.dirty is False
    assert assignment.dirty is False

    # Change equipment cost (triggers set_dirty on assignment -> fighter -> list)
    content_equipment.cost = "200"
    content_equipment.save()

    # Verify action was created
    action = ListAction.objects.filter(list=lst).order_by("-created").first()
    assert action.action_type == ListActionType.CONTENT_COST_CHANGE

    # Verify ALL dirty flags are now False (not just the list)
    lst.refresh_from_db()
    fighter.refresh_from_db()
    assignment.refresh_from_db()

    assert lst.dirty is False, "List dirty flag should be cleared"
    assert fighter.dirty is False, "Fighter dirty flag should be cleared"
    assert assignment.dirty is False, "Assignment dirty flag should be cleared"
