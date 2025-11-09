"""
Tests for fighter operation handlers.

These tests directly test the handle_fighter_hire function in
gyrinx.core.handlers.fighter_operations, ensuring that business logic works
correctly without involving HTTP machinery.
"""

import pytest
from django.core.exceptions import ValidationError

from gyrinx.core.handlers.fighter_operations import handle_fighter_hire
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import ListFighter
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_handle_fighter_hire_campaign_mode(user, list_with_campaign, content_fighter):
    """Test hiring a fighter in campaign mode creates actions and spends credits."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.save()

    fighter_cost = content_fighter.cost_for_house(lst.content_house)

    # Create fighter instance (not saved yet)
    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    # Call the handler
    result = handle_fighter_hire(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify result
    assert result.fighter_cost == fighter_cost
    assert result.fighter == fighter
    assert f"Hired Test Fighter ({fighter_cost}¢)" in result.description

    # Verify fighter was saved
    assert result.fighter.id is not None
    assert ListFighter.objects.filter(id=result.fighter.id).exists()

    # Verify ListAction created
    assert result.list_action is not None
    assert result.list_action.action_type == ListActionType.ADD_FIGHTER
    assert result.list_action.rating_delta == fighter_cost
    assert result.list_action.stash_delta == 0
    assert result.list_action.credits_delta == -fighter_cost
    assert result.list_action.rating_before == 500
    assert result.list_action.credits_before == 1000

    # Verify CampaignAction created
    assert result.campaign_action is not None
    assert f"Hired Test Fighter ({fighter_cost}¢)" in result.campaign_action.description

    # Verify credits spent (no refresh needed - handler modifies the same object)
    assert lst.credits_current == 1000 - fighter_cost


@pytest.mark.django_db
def test_handle_fighter_hire_list_building_mode(
    user, make_list, content_fighter, content_house
):
    """Test hiring a fighter in list building mode (no credits)."""
    lst = make_list("Test List")
    lst.rating_current = 500
    lst.save()

    fighter_cost = content_fighter.cost_for_house(content_house)

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    result = handle_fighter_hire(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify result
    assert result.fighter_cost == fighter_cost
    assert result.campaign_action is None  # No campaign mode

    # Verify ListAction created with no credit delta
    assert result.list_action.credits_delta == 0
    assert result.list_action.rating_delta == fighter_cost

    # Verify credits unchanged (no refresh needed - handler modifies the same object)
    assert lst.credits_current == 0


@pytest.mark.django_db
def test_handle_fighter_hire_stash_fighter(
    user, list_with_campaign, content_house, make_content_fighter
):
    """Test hiring a stash fighter affects stash, not rating."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.stash_current = 100
    lst.rating_current = 500
    lst.save()

    # Create a stash fighter type
    stash_fighter_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=stash_fighter_type,
        name="Stash",
    )

    result = handle_fighter_hire(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify stash delta, not rating delta
    assert result.list_action.stash_delta == result.fighter_cost
    assert result.list_action.rating_delta == 0
    assert result.list_action.credits_delta == -result.fighter_cost


@pytest.mark.django_db
def test_handle_fighter_hire_insufficient_credits(
    user, list_with_campaign, content_fighter
):
    """Test fighter hire fails with insufficient credits."""
    lst = list_with_campaign
    lst.credits_current = 25  # Not enough for 100 credit fighter
    lst.save()

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    # Should raise ValidationError due to insufficient credits
    with pytest.raises(ValidationError, match="Insufficient credits"):
        handle_fighter_hire(
            user=user,
            lst=lst,
            fighter=fighter,
        )

    # Verify no new actions created (only the initial CREATE action exists)
    assert ListAction.objects.count() == 1  # Only the initial CREATE action
    assert ListAction.objects.first().action_type == ListActionType.CREATE
    assert CampaignAction.objects.count() == 0

    # Verify fighter was not saved
    assert not ListFighter.objects.filter(name="Test Fighter").exists()


@pytest.mark.django_db
def test_handle_fighter_hire_correct_before_values(
    user, list_with_campaign, content_fighter
):
    """Test that before values are captured correctly in ListAction."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.stash_current = 200
    lst.save()

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    result = handle_fighter_hire(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify before values match original list state
    assert result.list_action.rating_before == 500
    assert result.list_action.stash_before == 200
    assert result.list_action.credits_before == 1000


@pytest.mark.django_db
def test_handle_fighter_hire_transaction_rollback(
    user, list_with_campaign, content_fighter, monkeypatch
):
    """Test that transaction rolls back on error."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    # Count initial objects
    initial_fighter_count = ListFighter.objects.count()
    initial_action_count = ListAction.objects.count()
    initial_campaign_action_count = CampaignAction.objects.count()

    # Monkeypatch create_action to raise an error
    def failing_create_action(*args, **kwargs):
        raise RuntimeError("Simulated error")

    monkeypatch.setattr(lst, "create_action", failing_create_action)

    # Call the handler - should raise error and rollback
    with pytest.raises(RuntimeError):
        handle_fighter_hire(
            user=user,
            lst=lst,
            fighter=fighter,
        )

    # Verify transaction rolled back - no new objects created
    assert ListFighter.objects.count() == initial_fighter_count
    assert ListAction.objects.count() == initial_action_count
    assert CampaignAction.objects.count() == initial_campaign_action_count

    # Verify credits unchanged
    # Refresh needed here because: handler modified the object (spend_credits), then transaction
    # failed and rolled back. DB is correct, but Python object still has modified value.
    # In the running app, this is fine - the modified object is discarded after the view returns.
    lst.refresh_from_db()
    assert lst.credits_current == 1000


@pytest.mark.django_db
def test_handle_fighter_hire_campaign_action_created(
    user, list_with_campaign, content_fighter
):
    """Test that CampaignAction is created in campaign mode."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    fighter_cost = content_fighter.cost_for_house(lst.content_house)

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
    )

    result = handle_fighter_hire(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify CampaignAction details
    assert result.campaign_action is not None
    assert result.campaign_action.campaign == lst.campaign
    assert result.campaign_action.list == lst
    assert f"Hired Test Fighter ({fighter_cost}¢)" in result.campaign_action.description
    assert (
        f"Credits remaining: {lst.credits_current}¢" in result.campaign_action.outcome
    )


@pytest.mark.django_db
def test_handle_fighter_hire_description_format(
    user, list_with_campaign, content_fighter
):
    """Test that description is formatted correctly."""
    lst = list_with_campaign
    lst.credits_current = 1000
    lst.save()

    fighter_cost = content_fighter.cost_for_house(lst.content_house)

    fighter = ListFighter(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Specialized Fighter Name",
    )

    result = handle_fighter_hire(
        user=user,
        lst=lst,
        fighter=fighter,
    )

    # Verify description format includes name and cost
    expected_desc = f"Hired Specialized Fighter Name ({fighter_cost}¢)"
    assert result.description == expected_desc
    assert result.list_action.description == expected_desc
    assert expected_desc in result.campaign_action.description
