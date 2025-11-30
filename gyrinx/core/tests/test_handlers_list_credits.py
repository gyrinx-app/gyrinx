"""
Tests for list credits handlers.

These tests directly test the handle_credits_modification function in
gyrinx.core.handlers.list.credits, ensuring that business logic works
correctly without involving HTTP machinery.
"""

import pytest

from gyrinx.core.handlers.list import handle_credits_modification
from gyrinx.core.models.action import ListActionType
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List


@pytest.fixture
def campaign_list(user, make_list):
    """Create a list in campaign mode with initial credits."""
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    lst = make_list(
        "Test Gang",
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )
    lst.credits_current = 500
    lst.credits_earned = 1000
    lst.save()
    campaign.lists.add(lst)

    return lst


# ===== Add Credits Tests =====


@pytest.mark.parametrize("feature_flag_enabled", [True, False])
@pytest.mark.django_db
def test_handle_credits_add(campaign_list, user, settings, feature_flag_enabled):
    """Test adding credits increases both current and earned."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    lst = campaign_list

    initial_current = lst.credits_current
    initial_earned = lst.credits_earned
    amount = 100

    result = handle_credits_modification(
        user=user,
        lst=lst,
        operation="add",
        amount=amount,
        description="Test income",
    )

    # Verify result
    assert result.operation == "add"
    assert result.amount == amount
    assert result.credits_before == initial_current
    assert result.credits_after == initial_current + amount
    assert result.credits_earned_before == initial_earned
    assert result.credits_earned_after == initial_earned + amount

    # Verify list updated
    lst.refresh_from_db()
    assert lst.credits_current == initial_current + amount
    assert lst.credits_earned == initial_earned + amount

    # Verify ListAction
    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.action_type == ListActionType.UPDATE_CREDITS
        assert result.list_action.credits_delta == amount
        assert result.list_action.rating_delta == 0
        assert result.list_action.stash_delta == 0
        assert "Added 100¢" in result.list_action.description
    else:
        assert result.list_action is None

    # Verify CampaignAction
    assert result.campaign_action is not None
    assert "Added 100¢" in result.campaign_action.description
    assert "+100¢" in result.campaign_action.outcome


@pytest.mark.django_db
def test_handle_credits_add_with_description(campaign_list, user, settings):
    """Test adding credits with a description includes it in the action."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = campaign_list

    result = handle_credits_modification(
        user=user,
        lst=lst,
        operation="add",
        amount=50,
        description="Reward for winning battle",
    )

    assert "Reward for winning battle" in result.description
    assert "Reward for winning battle" in result.list_action.description


# ===== Spend Credits Tests =====


@pytest.mark.parametrize("feature_flag_enabled", [True, False])
@pytest.mark.django_db
def test_handle_credits_spend(campaign_list, user, settings, feature_flag_enabled):
    """Test spending credits decreases current but not earned."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    lst = campaign_list

    initial_current = lst.credits_current
    initial_earned = lst.credits_earned
    amount = 100

    result = handle_credits_modification(
        user=user,
        lst=lst,
        operation="spend",
        amount=amount,
    )

    # Verify result
    assert result.operation == "spend"
    assert result.amount == amount
    assert result.credits_before == initial_current
    assert result.credits_after == initial_current - amount
    assert result.credits_earned_before == initial_earned
    assert result.credits_earned_after == initial_earned  # Unchanged

    # Verify list updated
    lst.refresh_from_db()
    assert lst.credits_current == initial_current - amount
    assert lst.credits_earned == initial_earned  # Unchanged

    # Verify ListAction
    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.credits_delta == -amount
        assert "Spent 100¢" in result.list_action.description
    else:
        assert result.list_action is None


@pytest.mark.django_db
def test_handle_credits_spend_insufficient(campaign_list, user):
    """Test spending more credits than available raises error."""
    lst = campaign_list
    lst.credits_current = 50
    lst.save()

    with pytest.raises(ValueError) as exc_info:
        handle_credits_modification(
            user=user,
            lst=lst,
            operation="spend",
            amount=100,
        )

    assert "Cannot spend more credits than available" in str(exc_info.value)

    # Verify credits unchanged
    lst.refresh_from_db()
    assert lst.credits_current == 50


# ===== Reduce Credits Tests =====


@pytest.mark.parametrize("feature_flag_enabled", [True, False])
@pytest.mark.django_db
def test_handle_credits_reduce(campaign_list, user, settings, feature_flag_enabled):
    """Test reducing credits decreases both current and earned."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled
    lst = campaign_list

    initial_current = lst.credits_current
    initial_earned = lst.credits_earned
    amount = 100

    result = handle_credits_modification(
        user=user,
        lst=lst,
        operation="reduce",
        amount=amount,
    )

    # Verify result
    assert result.operation == "reduce"
    assert result.amount == amount
    assert result.credits_before == initial_current
    assert result.credits_after == initial_current - amount
    assert result.credits_earned_before == initial_earned
    assert result.credits_earned_after == initial_earned - amount

    # Verify list updated
    lst.refresh_from_db()
    assert lst.credits_current == initial_current - amount
    assert lst.credits_earned == initial_earned - amount

    # Verify ListAction
    if feature_flag_enabled:
        assert result.list_action is not None
        assert result.list_action.credits_delta == -amount
        assert "Reduced 100¢" in result.list_action.description
    else:
        assert result.list_action is None

    # Verify CampaignAction shows all time credits
    assert result.campaign_action is not None
    assert "all time:" in result.campaign_action.outcome


@pytest.mark.django_db
def test_handle_credits_reduce_insufficient_current(campaign_list, user):
    """Test reducing more credits than current raises error."""
    lst = campaign_list
    lst.credits_current = 50
    lst.credits_earned = 1000
    lst.save()

    with pytest.raises(ValueError) as exc_info:
        handle_credits_modification(
            user=user,
            lst=lst,
            operation="reduce",
            amount=100,
        )

    assert "Cannot reduce credits below zero (current:" in str(exc_info.value)


@pytest.mark.django_db
def test_handle_credits_reduce_insufficient_earned(campaign_list, user):
    """Test reducing more credits than earned raises error."""
    lst = campaign_list
    lst.credits_current = 500
    lst.credits_earned = 50  # Less than amount
    lst.save()

    with pytest.raises(ValueError) as exc_info:
        handle_credits_modification(
            user=user,
            lst=lst,
            operation="reduce",
            amount=100,
        )

    assert "Cannot reduce all time credits below zero" in str(exc_info.value)


# ===== Validation Tests =====


@pytest.mark.django_db
def test_handle_credits_negative_amount(campaign_list, user):
    """Test negative amount raises error."""
    with pytest.raises(ValueError) as exc_info:
        handle_credits_modification(
            user=user,
            lst=campaign_list,
            operation="add",
            amount=-50,
        )

    assert "Amount must be non-negative" in str(exc_info.value)


@pytest.mark.django_db
def test_handle_credits_invalid_operation(campaign_list, user):
    """Test invalid operation raises error."""
    with pytest.raises(ValueError) as exc_info:
        handle_credits_modification(
            user=user,
            lst=campaign_list,
            operation="invalid",
            amount=50,
        )

    assert "Invalid operation" in str(exc_info.value)


@pytest.mark.django_db
def test_handle_credits_zero_amount(campaign_list, user, settings):
    """Test zero amount is valid but has no effect."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = campaign_list
    initial_current = lst.credits_current

    result = handle_credits_modification(
        user=user,
        lst=lst,
        operation="add",
        amount=0,
    )

    # Credits unchanged
    assert result.credits_after == initial_current

    # But action is still created
    assert result.list_action is not None
    assert result.list_action.credits_delta == 0


# ===== Non-Campaign Mode Tests =====


@pytest.mark.django_db
def test_handle_credits_non_campaign_no_campaign_action(user, make_list, settings):
    """Test no CampaignAction created when not in campaign mode."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    # Create a list NOT in campaign mode but still test handler directly
    lst = make_list("Non-Campaign Gang", status=List.LIST_BUILDING)
    lst.credits_current = 500
    lst.credits_earned = 1000
    lst.save()

    result = handle_credits_modification(
        user=user,
        lst=lst,
        operation="add",
        amount=100,
    )

    # Credits updated
    lst.refresh_from_db()
    assert lst.credits_current == 600
    assert lst.credits_earned == 1100

    # No CampaignAction
    assert result.campaign_action is None
