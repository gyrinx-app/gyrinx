"""
Tests for fighter capture, release, return, and sell handlers.

These tests directly test the handler functions in gyrinx.core.handlers.fighter.capture,
ensuring that business logic works correctly without involving HTTP machinery.
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from gyrinx.core.handlers.fighter.capture import (
    handle_fighter_capture,
    handle_fighter_release,
    handle_fighter_return_to_owner,
    handle_fighter_sell_to_guilders,
)
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import (
    CapturedFighter,
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.models import FighterCategoryChoices

User = get_user_model()


@pytest.fixture
def two_gang_campaign(user, content_house, make_content_fighter, make_list):
    """Create a campaign with two gangs owned by different users."""
    owner2 = User.objects.create_user(username="owner2", email="owner2@test.com")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    # Gang 1 - owned by user fixture
    gang1 = make_list(
        "Gang 1",
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )
    gang1.credits_current = 500
    gang1.rating_current = 300
    gang1.save()
    campaign.lists.add(gang1)

    # Gang 2 - owned by owner2
    gang2 = List.objects.create(
        name="Gang 2",
        owner=owner2,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
        credits_current=200,
        rating_current=250,
    )
    # Create initial action so gang2 can create ListActions
    ListAction.objects.create(
        list=gang2,
        action_type=ListActionType.CREATE,
        owner=owner2,
        applied=True,
    )
    campaign.lists.add(gang2)

    # Create a fighter for gang1
    fighter_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    fighter = ListFighter.objects.create(
        name="Test Ganger",
        content_fighter=fighter_type,
        list=gang1,
        owner=user,
    )

    return {
        "campaign": campaign,
        "gang1": gang1,
        "gang2": gang2,
        "fighter": fighter,
        "owner1": user,
        "owner2": owner2,
        "fighter_type": fighter_type,
    }


# ===== Capture Handler Tests =====


@pytest.mark.parametrize("feature_flag_enabled", [True, False])
@pytest.mark.django_db
def test_handle_fighter_capture_basic(
    two_gang_campaign,
    settings,
    feature_flag_enabled,
):
    """Test capturing a regular fighter creates correct actions."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    data = two_gang_campaign
    fighter = data["fighter"]
    gang1 = data["gang1"]
    gang2 = data["gang2"]
    owner1 = data["owner1"]

    initial_rating = gang1.rating_current
    fighter_cost = fighter.cost_int()

    result = handle_fighter_capture(
        user=owner1,
        fighter=fighter,
        capturing_list=gang2,
    )

    # Verify result
    assert result.captured_fighter_record is not None
    assert result.fighter == fighter
    assert result.capturing_list == gang2
    assert result.original_list == gang1
    assert result.fighter_cost == fighter_cost
    assert result.equipment_removed == []

    # Verify CapturedFighter record created
    assert CapturedFighter.objects.filter(fighter=fighter).exists()
    captured = CapturedFighter.objects.get(fighter=fighter)
    assert captured.capturing_list == gang2
    assert captured.sold_to_guilders is False

    # Verify fighter is now captured
    fighter.refresh_from_db()
    assert fighter.is_captured is True
    assert fighter.cost_int() == 0

    # Verify ListAction
    if feature_flag_enabled:
        assert result.capture_list_action is not None
        assert result.capture_list_action.action_type == ListActionType.CAPTURE_FIGHTER
        assert result.capture_list_action.rating_delta == -fighter_cost
        assert result.capture_list_action.credits_delta == 0
        assert result.capture_list_action.rating_before == initial_rating
    else:
        assert result.capture_list_action is None

    # Verify CampaignAction (always created in campaign mode)
    assert result.campaign_action is not None
    assert "captured by Gang 2" in result.campaign_action.description


@pytest.mark.parametrize("feature_flag_enabled", [True, False])
@pytest.mark.django_db
def test_handle_fighter_capture_with_child_equipment(
    two_gang_campaign,
    make_content_fighter,
    make_equipment,
    settings,
    feature_flag_enabled,
):
    """Test capturing a child fighter removes parent equipment."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    data = two_gang_campaign
    gang1 = data["gang1"]
    gang2 = data["gang2"]
    owner1 = data["owner1"]
    handler = data["fighter"]  # Use existing fighter as handler

    # Create exotic beast content type
    beast_type = make_content_fighter(
        type="Exotic Beast",
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=data["fighter_type"].house,
        base_cost=0,  # Child fighters typically have 0 base cost
    )

    # Create exotic beast as child fighter
    beast = ListFighter.objects.create(
        name="Test Beast",
        content_fighter=beast_type,
        list=gang1,
        owner=owner1,
    )

    # Create equipment linking handler to beast
    beast_equipment = make_equipment("Beast Handler Equipment", cost="75")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=handler,
        content_equipment=beast_equipment,
        child_fighter=beast,
    )
    equipment_cost = assignment.cost_int()

    result = handle_fighter_capture(
        user=owner1,
        fighter=beast,
        capturing_list=gang2,
    )

    # Verify child equipment was removed
    assert len(result.equipment_removed) == 1
    assert result.equipment_removed[0][1] == equipment_cost

    # Verify assignment was deleted
    assert not ListFighterEquipmentAssignment.objects.filter(id=assignment.id).exists()

    # Verify equipment removal ListAction
    if feature_flag_enabled:
        assert len(result.equipment_removal_actions) == 1
        removal_action = result.equipment_removal_actions[0]
        assert removal_action.action_type == ListActionType.REMOVE_EQUIPMENT
        assert removal_action.rating_delta == -equipment_cost
    else:
        # Actions may be None when feature flag is disabled
        assert all(a is None for a in result.equipment_removal_actions)

    # Verify CampaignAction mentions equipment removal
    assert "linked equipment removed" in result.campaign_action.description


@pytest.mark.django_db
def test_handle_fighter_capture_child_fighter_zero_cost(
    two_gang_campaign,
    make_content_fighter,
    make_equipment,
):
    """Test that child fighters have 0 cost contribution to capture delta."""
    data = two_gang_campaign
    gang1 = data["gang1"]
    gang2 = data["gang2"]
    owner1 = data["owner1"]
    handler = data["fighter"]

    # Create exotic beast as child fighter
    beast_type = make_content_fighter(
        type="Exotic Beast",
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=data["fighter_type"].house,
        base_cost=100,  # Even with base cost, child fighters return 0
    )
    beast = ListFighter.objects.create(
        name="Test Beast",
        content_fighter=beast_type,
        list=gang1,
        owner=owner1,
    )

    # Create equipment linking handler to beast (this makes beast a child)
    beast_equipment = make_equipment("Beast Handler Equipment", cost="75")
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=handler,
        content_equipment=beast_equipment,
        child_fighter=beast,
    )

    # Beast is now a child fighter and should have 0 cost
    assert beast.is_child_fighter is True
    assert beast.cost_int() == 0

    result = handle_fighter_capture(
        user=owner1,
        fighter=beast,
        capturing_list=gang2,
    )

    # Fighter cost should be 0 (child fighter)
    assert result.fighter_cost == 0


# ===== Sell to Guilders Handler Tests =====


@pytest.mark.parametrize("feature_flag_enabled", [True, False])
@pytest.mark.django_db
def test_handle_fighter_sell_to_guilders(
    two_gang_campaign,
    settings,
    feature_flag_enabled,
):
    """Test selling a captured fighter to guilders adds credits."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    data = two_gang_campaign
    fighter = data["fighter"]
    gang2 = data["gang2"]
    owner2 = data["owner2"]

    # First capture the fighter
    captured = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=gang2,
        owner=data["owner1"],
    )

    initial_credits = gang2.credits_current
    sale_price = 75

    result = handle_fighter_sell_to_guilders(
        user=owner2,
        captured_fighter=captured,
        sale_price=sale_price,
    )

    # Verify result
    assert result.sale_price == sale_price
    assert result.fighter == fighter
    assert result.capturing_list == gang2

    # Verify CapturedFighter updated
    captured.refresh_from_db()
    assert captured.sold_to_guilders is True
    assert captured.ransom_amount == sale_price
    assert captured.sold_at is not None

    # Verify fighter is sold to guilders
    fighter.refresh_from_db()
    assert fighter.is_sold_to_guilders is True
    assert fighter.is_captured is False

    # Verify credits added
    gang2.refresh_from_db()
    assert gang2.credits_current == initial_credits + sale_price

    # Verify ListAction
    if feature_flag_enabled:
        assert result.sell_list_action is not None
        assert result.sell_list_action.action_type == ListActionType.SELL_FIGHTER
        assert result.sell_list_action.credits_delta == sale_price
        assert result.sell_list_action.rating_delta == 0
    else:
        assert result.sell_list_action is None

    # Verify CampaignAction
    assert result.campaign_action is not None
    assert f"for {sale_price}¢" in result.campaign_action.description


@pytest.mark.django_db
def test_handle_fighter_sell_zero_credits(
    two_gang_campaign,
):
    """Test selling a fighter for 0 credits."""
    data = two_gang_campaign
    fighter = data["fighter"]
    gang2 = data["gang2"]
    owner2 = data["owner2"]

    captured = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=gang2,
        owner=data["owner1"],
    )

    initial_credits = gang2.credits_current

    handle_fighter_sell_to_guilders(
        user=owner2,
        captured_fighter=captured,
        sale_price=0,
    )

    # Credits unchanged
    gang2.refresh_from_db()
    assert gang2.credits_current == initial_credits

    # Fighter is still marked as sold
    fighter.refresh_from_db()
    assert fighter.is_sold_to_guilders is True


# ===== Return to Owner Handler Tests =====


@pytest.mark.parametrize("feature_flag_enabled", [True, False])
@pytest.mark.django_db
def test_handle_fighter_return_with_ransom(
    two_gang_campaign,
    settings,
    feature_flag_enabled,
):
    """Test returning a fighter with ransom transfers credits."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    data = two_gang_campaign
    fighter = data["fighter"]
    gang1 = data["gang1"]
    gang2 = data["gang2"]
    owner1 = data["owner1"]

    # Capture the fighter
    captured = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=gang2,
        owner=owner1,
    )

    # Record initial state (after capture)
    gang1.refresh_from_db()
    gang2.refresh_from_db()
    gang1_initial_credits = gang1.credits_current
    gang2_initial_credits = gang2.credits_current

    ransom = 100

    result = handle_fighter_return_to_owner(
        user=owner1,
        captured_fighter=captured,
        ransom_amount=ransom,
    )

    # Verify result
    assert result.ransom_amount == ransom
    assert result.fighter == fighter
    assert result.original_list == gang1
    assert result.capturing_list == gang2
    assert result.fighter_cost > 0  # Fighter cost is restored

    # Verify CapturedFighter deleted
    assert not CapturedFighter.objects.filter(fighter=fighter).exists()

    # Verify fighter is restored
    fighter.refresh_from_db()
    assert fighter.is_captured is False
    assert fighter.is_sold_to_guilders is False
    assert fighter.cost_int() > 0

    # Verify credits transferred
    gang1.refresh_from_db()
    gang2.refresh_from_db()
    assert gang1.credits_current == gang1_initial_credits - ransom
    assert gang2.credits_current == gang2_initial_credits + ransom

    # Verify ListActions on both lists
    if feature_flag_enabled:
        # Original gang action
        assert result.original_list_action is not None
        assert result.original_list_action.action_type == ListActionType.RETURN_FIGHTER
        assert result.original_list_action.rating_delta == result.fighter_cost
        assert result.original_list_action.credits_delta == -ransom

        # Capturing gang action (only when ransom > 0)
        assert result.capturing_list_action is not None
        assert result.capturing_list_action.credits_delta == ransom
    else:
        assert result.original_list_action is None
        assert result.capturing_list_action is None

    # Verify CampaignActions
    assert result.original_campaign_action is not None
    assert f"{ransom}¢ ransom" in result.original_campaign_action.description
    assert result.capturing_campaign_action is not None


@pytest.mark.parametrize("feature_flag_enabled", [True, False])
@pytest.mark.django_db
def test_handle_fighter_return_without_ransom(
    two_gang_campaign,
    settings,
    feature_flag_enabled,
):
    """Test returning a fighter without ransom."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    data = two_gang_campaign
    fighter = data["fighter"]
    gang1 = data["gang1"]
    gang2 = data["gang2"]
    owner1 = data["owner1"]

    captured = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=gang2,
        owner=owner1,
    )

    gang1_initial_credits = gang1.credits_current
    gang2_initial_credits = gang2.credits_current

    result = handle_fighter_return_to_owner(
        user=owner1,
        captured_fighter=captured,
        ransom_amount=0,
    )

    # Verify no credit transfer
    gang1.refresh_from_db()
    gang2.refresh_from_db()
    assert gang1.credits_current == gang1_initial_credits
    assert gang2.credits_current == gang2_initial_credits

    # Verify only original gang gets ListAction
    if feature_flag_enabled:
        assert result.original_list_action is not None
        assert result.original_list_action.credits_delta == 0
        assert result.capturing_list_action is None  # No ransom = no capturing action
    else:
        assert result.original_list_action is None

    # Verify only original gang gets CampaignAction
    assert result.original_campaign_action is not None
    assert result.capturing_campaign_action is None


@pytest.mark.django_db
def test_handle_fighter_return_insufficient_credits(
    two_gang_campaign,
):
    """Test returning with ransom fails if original gang can't afford it."""
    data = two_gang_campaign
    fighter = data["fighter"]
    gang1 = data["gang1"]
    gang2 = data["gang2"]
    owner1 = data["owner1"]

    captured = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=gang2,
        owner=owner1,
    )

    # Set gang1 credits lower than ransom
    gang1.credits_current = 50
    gang1.save()

    with pytest.raises(ValidationError) as exc_info:
        handle_fighter_return_to_owner(
            user=owner1,
            captured_fighter=captured,
            ransom_amount=100,
        )

    assert "doesn't have enough credits" in str(exc_info.value)

    # Verify fighter is still captured
    assert CapturedFighter.objects.filter(fighter=fighter).exists()


# ===== Release Handler Tests =====


@pytest.mark.parametrize("feature_flag_enabled", [True, False])
@pytest.mark.django_db
def test_handle_fighter_release(
    two_gang_campaign,
    settings,
    feature_flag_enabled,
):
    """Test releasing a fighter restores rating without credit transfer."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    data = two_gang_campaign
    fighter = data["fighter"]
    gang1 = data["gang1"]
    gang2 = data["gang2"]
    owner2 = data["owner2"]

    captured = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=gang2,
        owner=data["owner1"],
    )

    gang1_initial_credits = gang1.credits_current
    gang2_initial_credits = gang2.credits_current

    result = handle_fighter_release(
        user=owner2,
        captured_fighter=captured,
    )

    # Verify result
    assert result.fighter == fighter
    assert result.original_list == gang1
    assert result.fighter_cost > 0

    # Verify CapturedFighter deleted
    assert not CapturedFighter.objects.filter(fighter=fighter).exists()

    # Verify fighter is restored
    fighter.refresh_from_db()
    assert fighter.is_captured is False
    assert fighter.cost_int() > 0

    # Verify no credit transfer
    gang1.refresh_from_db()
    gang2.refresh_from_db()
    assert gang1.credits_current == gang1_initial_credits
    assert gang2.credits_current == gang2_initial_credits

    # Verify ListAction
    if feature_flag_enabled:
        assert result.release_list_action is not None
        assert result.release_list_action.action_type == ListActionType.RELEASE_FIGHTER
        assert result.release_list_action.rating_delta == result.fighter_cost
        assert result.release_list_action.credits_delta == 0
    else:
        assert result.release_list_action is None

    # Verify CampaignAction
    assert result.campaign_action is not None
    assert "Released" in result.campaign_action.description
    assert "without ransom" in result.campaign_action.description


# ===== Edge Case Tests =====


@pytest.mark.django_db
def test_capture_then_return_restores_rating(
    two_gang_campaign,
    settings,
):
    """Test that capture then return properly restores rating."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    data = two_gang_campaign
    fighter = data["fighter"]
    gang2 = data["gang2"]
    owner1 = data["owner1"]

    initial_fighter_cost = fighter.cost_int()

    # Capture
    capture_result = handle_fighter_capture(
        user=owner1,
        fighter=fighter,
        capturing_list=gang2,
    )

    assert capture_result.capture_list_action.rating_delta == -initial_fighter_cost

    # Return
    captured = CapturedFighter.objects.get(fighter=fighter)
    return_result = handle_fighter_return_to_owner(
        user=owner1,
        captured_fighter=captured,
        ransom_amount=0,
    )

    # Rating deltas should be opposite
    assert return_result.original_list_action.rating_delta == initial_fighter_cost
    assert return_result.fighter_cost == initial_fighter_cost


@pytest.mark.django_db
def test_multiple_equipment_removal_on_capture(
    two_gang_campaign,
    make_content_fighter,
    make_equipment,
    settings,
):
    """Test capturing a fighter linked to multiple equipment assignments."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    data = two_gang_campaign
    gang1 = data["gang1"]
    gang2 = data["gang2"]
    owner1 = data["owner1"]

    # Create a beast that will be linked to multiple handlers
    beast_type = make_content_fighter(
        type="Exotic Beast",
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=data["fighter_type"].house,
        base_cost=0,
    )
    beast = ListFighter.objects.create(
        name="Test Beast",
        content_fighter=beast_type,
        list=gang1,
        owner=owner1,
    )

    # Create first handler with beast equipment
    handler1 = data["fighter"]
    equipment1 = make_equipment("Beast Handler 1", cost="50")
    assignment1 = ListFighterEquipmentAssignment.objects.create(
        list_fighter=handler1,
        content_equipment=equipment1,
        child_fighter=beast,
    )

    # Create second handler with different beast equipment
    handler2 = ListFighter.objects.create(
        name="Second Handler",
        content_fighter=data["fighter_type"],
        list=gang1,
        owner=owner1,
    )
    equipment2 = make_equipment("Beast Handler 2", cost="30")
    assignment2 = ListFighterEquipmentAssignment.objects.create(
        list_fighter=handler2,
        content_equipment=equipment2,
        child_fighter=beast,
    )

    result = handle_fighter_capture(
        user=owner1,
        fighter=beast,
        capturing_list=gang2,
    )

    # Verify both equipment assignments removed
    assert len(result.equipment_removed) == 2
    assert len(result.equipment_removal_actions) == 2

    # Verify both assignments deleted
    assert not ListFighterEquipmentAssignment.objects.filter(id=assignment1.id).exists()
    assert not ListFighterEquipmentAssignment.objects.filter(id=assignment2.id).exists()

    # Verify CampaignAction mentions total equipment cost
    total_equipment_cost = 50 + 30
    assert f"{total_equipment_cost}¢" in result.campaign_action.description


@pytest.mark.django_db
def test_list_building_mode_no_campaign_actions(
    user,
    make_list,
    content_house,
    make_content_fighter,
):
    """Test that no CampaignActions are created in list building mode."""
    # Create a list in LIST_BUILDING mode (no campaign)
    gang1 = make_list("Gang 1", status=List.LIST_BUILDING)
    gang2 = make_list("Gang 2", status=List.LIST_BUILDING)

    fighter_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=fighter_type,
        list=gang1,
        owner=user,
    )

    result = handle_fighter_capture(
        user=user,
        fighter=fighter,
        capturing_list=gang2,
    )

    # No CampaignAction in list building mode
    assert result.campaign_action is None
