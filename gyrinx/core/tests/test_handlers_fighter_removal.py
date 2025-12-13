"""
Tests for fighter removal operation handlers.

These tests directly test the removal handlers in
gyrinx.core.handlers.fighter.removal, ensuring that business logic works
correctly without involving HTTP machinery.
"""

import pytest

from gyrinx.core.handlers.equipment import (
    handle_equipment_component_removal,
    handle_equipment_removal,
)
from gyrinx.core.handlers.fighter import (
    handle_fighter_archive_toggle,
    handle_fighter_deletion,
)
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment


# ===== Equipment Removal Tests =====


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_equipment_removal_campaign_mode_with_refund(
    user,
    list_with_campaign,
    content_fighter,
    make_equipment,
    settings,
    feature_flag_enabled,
):
    """Test removing equipment in campaign mode with refund."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 500
    lst.rating_current = 1000
    lst.save()

    # Create fighter with equipment
    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    equipment = make_equipment(name="Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )
    equipment_cost = assignment.cost_int()

    # Initialize rating_current fields
    initial_assignment_rating = 50
    initial_fighter_rating = 150
    assignment.rating_current = initial_assignment_rating
    assignment.save(update_fields=["rating_current"])
    fighter.rating_current = initial_fighter_rating
    fighter.save(update_fields=["rating_current"])

    assignment_id = assignment.id  # Store before deletion

    # Call handler with refund requested
    result = handle_equipment_removal(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        request_refund=True,
    )

    # Verify result
    assert result.assignment_id == assignment_id
    assert result.equipment_name == "Test Weapon"
    assert result.equipment_cost == equipment_cost
    assert result.refund_applied is True
    assert "refund applied" in result.description

    # Verify assignment was deleted
    assert not ListFighterEquipmentAssignment.objects.filter(
        id=result.assignment_id
    ).exists()

    # Verify ListAction created
    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.action_type == ListActionType.REMOVE_EQUIPMENT
        assert result.list_action.rating_delta == -equipment_cost
        assert result.list_action.credits_delta == equipment_cost  # Refund
        assert result.list_action.rating_before == 1000
        assert result.list_action.credits_before == 500

        # Verify rating_current propagation (before deletion)
        if lst.latest_action:
            fighter.refresh_from_db()
            # Rating delta is -50, so fighter rating_current should decrease
            assert fighter.rating_current == initial_fighter_rating - equipment_cost
            # Assignment was deleted, so we can't check it
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_equipment_removal_campaign_mode_without_refund(
    user,
    list_with_campaign,
    content_fighter,
    make_equipment,
    settings,
    feature_flag_enabled,
):
    """Test removing equipment in campaign mode without refund."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 500
    lst.rating_current = 1000
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    equipment = make_equipment(name="Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )
    equipment_cost = assignment.cost_int()

    # Call handler WITHOUT refund
    result = handle_equipment_removal(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        request_refund=False,
    )

    # Verify no refund
    assert result.refund_applied is False
    assert "refund" not in result.description

    # Verify credits unchanged (no refund delta)
    if feature_flag_enabled:
        assert result.list_action.credits_delta == 0
        assert result.list_action.rating_delta == -equipment_cost
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_equipment_removal_list_building_mode(
    user, make_list, content_fighter, make_equipment, settings, feature_flag_enabled
):
    """Test removing equipment in list building mode ignores refund request."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = make_list("Test List")
    lst.rating_current = 1000
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    equipment = make_equipment(name="Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )
    equipment_cost = assignment.cost_int()

    # Request refund in list building mode - should be ignored
    result = handle_equipment_removal(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        request_refund=True,  # Will be ignored
    )

    # Verify refund was NOT applied (not campaign mode)
    assert result.refund_applied is False
    assert "refund" not in result.description

    # ListAction still has rating delta but no credits delta
    if feature_flag_enabled:
        assert result.list_action.rating_delta == -equipment_cost
        assert result.list_action.credits_delta == 0
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_equipment_removal_stash_fighter(
    user,
    list_with_campaign,
    content_house,
    make_content_fighter,
    make_equipment,
    settings,
    feature_flag_enabled,
):
    """Test removing equipment from stash fighter affects stash, not rating."""
    from gyrinx.models import FighterCategoryChoices

    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 500
    lst.stash_current = 200
    lst.rating_current = 1000
    lst.save()

    # Create stash fighter
    stash_fighter_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=stash_fighter_type,
        name="Stash",
    )

    equipment = make_equipment(name="Stash Item", cost="30")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )
    equipment_cost = assignment.cost_int()

    # Initialize rating_current fields
    initial_assignment_rating = 30
    initial_fighter_rating = 50
    assignment.rating_current = initial_assignment_rating
    assignment.save(update_fields=["rating_current"])
    fighter.rating_current = initial_fighter_rating
    fighter.save(update_fields=["rating_current"])

    result = handle_equipment_removal(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        request_refund=True,
    )

    # Verify stash delta, not rating delta
    if feature_flag_enabled:
        assert result.list_action.stash_delta == -equipment_cost
        assert result.list_action.rating_delta == 0
        assert (
            result.list_action.credits_delta == equipment_cost
        )  # Refund still applies

        # Verify rating_current propagation
        if lst.latest_action:
            fighter.refresh_from_db()
            # Stash delta is -30, so fighter rating_current should decrease
            assert fighter.rating_current == initial_fighter_rating - equipment_cost
    else:
        assert result.list_action is None


@pytest.mark.django_db
def test_handle_equipment_removal_transaction_rollback(
    user, list_with_campaign, content_fighter, make_equipment, monkeypatch
):
    """Test that transaction rolls back on error."""
    lst = list_with_campaign
    lst.credits_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    equipment = make_equipment(name="Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )
    assignment_id = assignment.id

    # Count initial objects
    initial_action_count = ListAction.objects.count()

    # Monkeypatch create_action to raise an error
    def failing_create_action(*args, **kwargs):
        raise RuntimeError("Simulated error")

    monkeypatch.setattr(lst, "create_action", failing_create_action)

    with pytest.raises(RuntimeError):
        handle_equipment_removal(
            user=user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
            request_refund=True,
        )

    # Verify transaction rolled back
    assert ListAction.objects.count() == initial_action_count

    # Assignment should still exist (rollback)
    assert ListFighterEquipmentAssignment.objects.filter(id=assignment_id).exists()


# ===== Equipment Component Removal Tests =====


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_equipment_component_removal_upgrade_with_refund(
    user,
    list_with_campaign,
    content_fighter,
    make_equipment_with_upgrades,
    settings,
    feature_flag_enabled,
):
    """Test removing an upgrade from equipment with refund."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 500
    lst.rating_current = 1000
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    equipment, upgrade = make_equipment_with_upgrades(cost=50, upgrade_cost=20)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )
    assignment.upgrades_field.add(upgrade)

    upgrade_cost = assignment._upgrade_cost_with_override(upgrade)

    # Initialize rating_current fields
    initial_assignment_rating = 70  # equipment (50) + upgrade (20)
    initial_fighter_rating = 150
    assignment.rating_current = initial_assignment_rating
    assignment.save(update_fields=["rating_current"])
    fighter.rating_current = initial_fighter_rating
    fighter.save(update_fields=["rating_current"])

    result = handle_equipment_component_removal(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        component_type="upgrade",
        component=upgrade,
        request_refund=True,
    )

    # Verify result
    assert result.component_type == "upgrade"
    assert result.component_name == upgrade.name
    assert result.component_cost == upgrade_cost
    assert result.refund_applied is True
    assert "refund applied" in result.description

    # Verify upgrade was removed from assignment
    assert upgrade not in assignment.upgrades_field.all()

    # Verify ListAction created
    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.action_type == ListActionType.UPDATE_EQUIPMENT
        assert result.list_action.rating_delta == -upgrade_cost
        assert result.list_action.credits_delta == upgrade_cost  # Refund

        # Verify rating_current propagation
        if lst.latest_action:
            assignment.refresh_from_db()
            fighter.refresh_from_db()
            # Rating delta is -20, so both should decrease
            assert assignment.rating_current == initial_assignment_rating - upgrade_cost
            assert fighter.rating_current == initial_fighter_rating - upgrade_cost
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_equipment_component_removal_profile_with_refund(
    user,
    list_with_campaign,
    content_fighter,
    make_weapon_with_profile,
    settings,
    feature_flag_enabled,
):
    """Test removing a weapon profile from equipment with refund."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 500
    lst.rating_current = 1000
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    weapon, profile = make_weapon_with_profile(cost=50, profile_cost=30)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )
    assignment.weapon_profiles_field.add(profile)

    from gyrinx.content.models import VirtualWeaponProfile

    virtual_profile = VirtualWeaponProfile(profile=profile)
    profile_cost = assignment.profile_cost_int(virtual_profile)

    # Initialize rating_current fields
    initial_assignment_rating = 80  # weapon (50) + profile (30)
    initial_fighter_rating = 150
    assignment.rating_current = initial_assignment_rating
    assignment.save(update_fields=["rating_current"])
    fighter.rating_current = initial_fighter_rating
    fighter.save(update_fields=["rating_current"])

    result = handle_equipment_component_removal(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        component_type="profile",
        component=profile,
        request_refund=True,
    )

    # Verify result
    assert result.component_type == "profile"
    assert result.component_name == profile.name
    assert result.component_cost == profile_cost
    assert result.refund_applied is True

    # Verify profile was removed
    assert profile not in assignment.weapon_profiles_field.all()

    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.action_type == ListActionType.UPDATE_EQUIPMENT

        # Verify rating_current propagation
        if lst.latest_action:
            assignment.refresh_from_db()
            fighter.refresh_from_db()
            # Rating delta is -30, so both should decrease
            assert assignment.rating_current == initial_assignment_rating - profile_cost
            assert fighter.rating_current == initial_fighter_rating - profile_cost
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_equipment_component_removal_accessory_with_refund(
    user,
    list_with_campaign,
    content_fighter,
    make_weapon_with_accessory,
    settings,
    feature_flag_enabled,
):
    """Test removing a weapon accessory from equipment with refund."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 500
    lst.rating_current = 1000
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    weapon, accessory = make_weapon_with_accessory(cost=50, accessory_cost=25)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )
    assignment.weapon_accessories_field.add(accessory)

    accessory_cost = assignment.accessory_cost_int(accessory)

    # Initialize rating_current fields
    initial_assignment_rating = 75  # weapon (50) + accessory (25)
    initial_fighter_rating = 150
    assignment.rating_current = initial_assignment_rating
    assignment.save(update_fields=["rating_current"])
    fighter.rating_current = initial_fighter_rating
    fighter.save(update_fields=["rating_current"])

    result = handle_equipment_component_removal(
        user=user,
        lst=lst,
        fighter=fighter,
        assignment=assignment,
        component_type="accessory",
        component=accessory,
        request_refund=True,
    )

    # Verify result
    assert result.component_type == "accessory"
    assert result.component_name == accessory.name
    assert result.component_cost == accessory_cost
    assert result.refund_applied is True

    # Verify accessory was removed
    assert accessory not in assignment.weapon_accessories_field.all()

    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.action_type == ListActionType.UPDATE_EQUIPMENT

        # Verify rating_current propagation
        if lst.latest_action:
            assignment.refresh_from_db()
            fighter.refresh_from_db()
            # Rating delta is -25, so both should decrease
            assert (
                assignment.rating_current == initial_assignment_rating - accessory_cost
            )
            assert fighter.rating_current == initial_fighter_rating - accessory_cost
    else:
        assert result.list_action is None


@pytest.mark.django_db
def test_handle_equipment_component_removal_invalid_type(
    user, list_with_campaign, content_fighter, make_equipment
):
    """Test that invalid component_type raises ValueError."""
    lst = list_with_campaign

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    equipment = make_equipment(name="Test", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    with pytest.raises(ValueError, match="Unknown component_type"):
        handle_equipment_component_removal(
            user=user,
            lst=lst,
            fighter=fighter,
            assignment=assignment,
            component_type="invalid",
            component=equipment,  # Doesn't matter, will fail before use
            request_refund=False,
        )


# ===== Fighter Archive Toggle Tests =====


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_archive_toggle_archive_with_refund(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test archiving a fighter with refund in campaign mode."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 500
    lst.rating_current = 1000
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    fighter_cost = fighter.cost_int()

    result = handle_fighter_archive_toggle(
        user=user,
        lst=lst,
        fighter=fighter,
        archive=True,
        request_refund=True,
    )

    # Verify result
    assert result.archived is True
    assert result.fighter_cost == fighter_cost
    assert result.refund_applied is True
    assert "refund applied" in result.description

    # Verify fighter was archived
    fighter.refresh_from_db()
    assert fighter.archived is True

    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.action_type == ListActionType.UPDATE_FIGHTER
        assert result.list_action.rating_delta == -fighter_cost
        assert result.list_action.credits_delta == fighter_cost  # Refund
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_archive_toggle_archive_without_refund(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test archiving a fighter without refund."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 500
    lst.rating_current = 1000
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    fighter_cost = fighter.cost_int()

    result = handle_fighter_archive_toggle(
        user=user,
        lst=lst,
        fighter=fighter,
        archive=True,
        request_refund=False,
    )

    assert result.refund_applied is False
    assert "refund" not in result.description

    if feature_flag_enabled:
        assert result.list_action.credits_delta == 0
        assert result.list_action.rating_delta == -fighter_cost
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_archive_toggle_unarchive(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test unarchiving a fighter."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 500
    lst.rating_current = 1000
    lst.save()

    # Create an already-archived fighter
    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    fighter.archive()
    fighter_cost = fighter.cost_int()

    result = handle_fighter_archive_toggle(
        user=user,
        lst=lst,
        fighter=fighter,
        archive=False,  # Unarchive
        request_refund=True,  # Should be ignored for unarchive
    )

    # Verify result
    assert result.archived is False
    assert result.refund_applied is False  # No refund on unarchive
    assert "Restored" in result.description

    # Verify fighter was unarchived
    fighter.refresh_from_db()
    assert fighter.archived is False

    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.rating_delta == fighter_cost  # Added back
        assert result.list_action.credits_delta == 0  # No refund on restore
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_archive_toggle_archive_list_building_mode(
    user, make_list, content_fighter, settings, feature_flag_enabled
):
    """Test archiving a fighter in list building mode ignores refund."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = make_list("Test List")
    lst.rating_current = 1000
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    fighter_cost = fighter.cost_int()

    result = handle_fighter_archive_toggle(
        user=user,
        lst=lst,
        fighter=fighter,
        archive=True,
        request_refund=True,  # Will be ignored
    )

    # Refund not applied in list building mode
    assert result.refund_applied is False

    if feature_flag_enabled:
        assert result.list_action.credits_delta == 0
        assert result.list_action.rating_delta == -fighter_cost
    else:
        assert result.list_action is None


# ===== Fighter Deletion Tests =====


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_deletion_campaign_mode_with_refund(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test deleting a fighter in campaign mode with refund."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 500
    lst.rating_current = 1000
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    fighter_id = fighter.id
    fighter_cost = fighter.cost_int()

    result = handle_fighter_deletion(
        user=user,
        lst=lst,
        fighter=fighter,
        request_refund=True,
    )

    # Verify result
    assert result.fighter_id == fighter_id
    assert result.fighter_name == "Test Fighter"
    assert result.fighter_cost == fighter_cost
    assert result.refund_applied is True
    assert "refund applied" in result.description

    # Verify fighter was deleted
    assert not ListFighter.objects.filter(id=fighter_id).exists()

    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.action_type == ListActionType.REMOVE_FIGHTER
        assert result.list_action.rating_delta == -fighter_cost
        assert result.list_action.credits_delta == fighter_cost  # Refund
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_deletion_campaign_mode_without_refund(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test deleting a fighter without refund."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 500
    lst.rating_current = 1000
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    fighter_cost = fighter.cost_int()

    result = handle_fighter_deletion(
        user=user,
        lst=lst,
        fighter=fighter,
        request_refund=False,
    )

    assert result.refund_applied is False
    assert "refund" not in result.description

    if feature_flag_enabled:
        assert result.list_action.credits_delta == 0
        assert result.list_action.rating_delta == -fighter_cost
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_deletion_list_building_mode(
    user, make_list, content_fighter, settings, feature_flag_enabled
):
    """Test deleting a fighter in list building mode ignores refund."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = make_list("Test List")
    lst.rating_current = 1000
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    fighter_id = fighter.id
    fighter_cost = fighter.cost_int()

    result = handle_fighter_deletion(
        user=user,
        lst=lst,
        fighter=fighter,
        request_refund=True,  # Will be ignored
    )

    # Refund not applied in list building mode
    assert result.refund_applied is False

    # Fighter was still deleted
    assert not ListFighter.objects.filter(id=fighter_id).exists()

    if feature_flag_enabled:
        assert result.list_action.credits_delta == 0
        assert result.list_action.rating_delta == -fighter_cost
    else:
        assert result.list_action is None


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_deletion_stash_fighter(
    user,
    list_with_campaign,
    content_house,
    make_content_fighter,
    settings,
    feature_flag_enabled,
):
    """Test deleting a stash fighter affects stash, not rating."""
    from gyrinx.models import FighterCategoryChoices

    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 500
    lst.stash_current = 200
    lst.rating_current = 1000
    lst.save()

    stash_fighter_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )
    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=stash_fighter_type,
        name="Stash",
    )
    fighter_cost = fighter.cost_int()

    result = handle_fighter_deletion(
        user=user,
        lst=lst,
        fighter=fighter,
        request_refund=True,
    )

    if feature_flag_enabled:
        assert result.list_action.stash_delta == -fighter_cost
        assert result.list_action.rating_delta == 0
        assert result.list_action.credits_delta == fighter_cost  # Refund still applies
    else:
        assert result.list_action is None


@pytest.mark.django_db
def test_handle_fighter_deletion_transaction_rollback(
    user, list_with_campaign, content_fighter, monkeypatch
):
    """Test that transaction rolls back on error."""
    lst = list_with_campaign
    lst.credits_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )
    fighter_id = fighter.id

    # Count initial objects
    initial_fighter_count = ListFighter.objects.count()
    initial_action_count = ListAction.objects.count()

    # Monkeypatch create_action to raise an error
    def failing_create_action(*args, **kwargs):
        raise RuntimeError("Simulated error")

    monkeypatch.setattr(lst, "create_action", failing_create_action)

    with pytest.raises(RuntimeError):
        handle_fighter_deletion(
            user=user,
            lst=lst,
            fighter=fighter,
            request_refund=True,
        )

    # Verify transaction rolled back
    assert ListFighter.objects.count() == initial_fighter_count
    assert ListAction.objects.count() == initial_action_count

    # Fighter should still exist (rollback)
    assert ListFighter.objects.filter(id=fighter_id).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_deletion_correct_before_values(
    user, list_with_campaign, content_fighter, settings, feature_flag_enabled
):
    """Test that before values are captured correctly in ListAction."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.stash_current = 200
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    result = handle_fighter_deletion(
        user=user,
        lst=lst,
        fighter=fighter,
        request_refund=False,
    )

    if feature_flag_enabled:
        assert result.list_action.rating_before == 500
        assert result.list_action.stash_before == 200
        assert result.list_action.credits_before == 1000
    else:
        assert result.list_action is None
