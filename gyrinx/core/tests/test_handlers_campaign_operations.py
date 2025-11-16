"""
Tests for campaign operation handlers.

These tests directly test the handle_campaign_start function in
gyrinx.core.handlers.campaign_operations, ensuring that business logic works
correctly without involving HTTP machinery.
"""

import pytest
from django.core.exceptions import ValidationError

from gyrinx.core.handlers.campaign_operations import handle_campaign_start
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List


@pytest.mark.django_db
def test_handle_campaign_start_all_lists_receive_credits(
    user,
    make_campaign,
    make_list,
    content_house,
    make_content_fighter,
    make_list_fighter,
):
    """Test that all lists in campaign receive correct credits when starting."""
    # Create campaign in PRE_CAMPAIGN status with budget
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    # Create fighters with different costs
    fighter1 = make_content_fighter(
        type="Fighter 1", category="GANGER", house=content_house, base_cost=1000
    )
    fighter2 = make_content_fighter(
        type="Fighter 2", category="GANGER", house=content_house, base_cost=1200
    )
    fighter3 = make_content_fighter(
        type="Fighter 3", category="GANGER", house=content_house, base_cost=500
    )

    # Create 3 lists with different costs and add to campaign
    list1 = make_list("Gang 1", content_house=content_house)
    make_list_fighter(list1, "Fighter 1", content_fighter=fighter1)
    list1.rating_current = 1000  # Cost: 1000, should get 500 credits (1500 - 1000)
    list1.save()

    list2 = make_list("Gang 2", content_house=content_house)
    make_list_fighter(list2, "Fighter 2", content_fighter=fighter2)
    list2.rating_current = 1200  # Cost: 1200, should get 300 credits (1500 - 1200)
    list2.save()

    list3 = make_list("Gang 3", content_house=content_house)
    make_list_fighter(list3, "Fighter 3", content_fighter=fighter3)
    list3.rating_current = 500  # Cost: 500, should get 1000 credits (1500 - 500)
    list3.save()

    campaign.lists.add(list1, list2, list3)

    # Start campaign
    result = handle_campaign_start(user=user, campaign=campaign)

    # Verify all 3 lists received credits
    assert len(result.list_results) == 3

    # Get the cloned lists and verify credits
    cloned_lists = List.objects.filter(
        campaign=campaign, status=List.CAMPAIGN_MODE
    ).order_by("name")

    # Gang 1: Cost 1000, gets 500 credits (1500 budget - 1000 cost)
    gang1_clone = cloned_lists.get(name="Gang 1")
    gang1_result = next(
        r for r in result.list_results if r.campaign_list == gang1_clone
    )
    assert gang1_result.credits_added == 500
    gang1_clone.refresh_from_db()
    assert gang1_clone.credits_current == 500
    assert gang1_clone.credits_earned == 500

    # Gang 2: Cost 1200, gets 300 credits (1500 budget - 1200 cost)
    gang2_clone = cloned_lists.get(name="Gang 2")
    gang2_result = next(
        r for r in result.list_results if r.campaign_list == gang2_clone
    )
    assert gang2_result.credits_added == 300
    gang2_clone.refresh_from_db()
    assert gang2_clone.credits_current == 300
    assert gang2_clone.credits_earned == 300

    # Gang 3: Cost 500, gets 1000 credits (1500 budget - 500 cost)
    gang3_clone = cloned_lists.get(name="Gang 3")
    gang3_result = next(
        r for r in result.list_results if r.campaign_list == gang3_clone
    )
    assert gang3_result.credits_added == 1000
    gang3_clone.refresh_from_db()
    assert gang3_clone.credits_current == 1000
    assert gang3_clone.credits_earned == 1000


@pytest.mark.django_db
def test_handle_campaign_start_creates_list_actions(
    user,
    make_campaign,
    make_list,
    content_house,
    make_content_fighter,
    make_list_fighter,
):
    """Test that ListActions are created for each list with CAMPAIGN_START type.

    Campaign-cloned lists get an initial CREATE ListAction, which allows
    subsequent CAMPAIGN_START actions to be created properly.
    """
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    # Create fighters
    fighter1 = make_content_fighter(
        type="Fighter 1", category="GANGER", house=content_house, base_cost=1000
    )
    fighter2 = make_content_fighter(
        type="Fighter 2", category="GANGER", house=content_house, base_cost=1200
    )

    list1 = make_list("Gang 1", content_house=content_house)
    make_list_fighter(list1, "Fighter 1", content_fighter=fighter1)
    list1.rating_current = 1000
    list1.save()

    list2 = make_list("Gang 2", content_house=content_house)
    make_list_fighter(list2, "Fighter 2", content_fighter=fighter2)
    list2.rating_current = 1200
    list2.save()

    campaign.lists.add(list1, list2)

    # Start campaign
    result = handle_campaign_start(user=user, campaign=campaign)

    # Verify ListActions created for both lists
    assert len(result.list_results) == 2
    for list_result in result.list_results:
        assert list_result.list_action is not None
        assert list_result.list_action.action_type == ListActionType.CAMPAIGN_START
        assert list_result.list_action.rating_delta == 0
        assert list_result.list_action.stash_delta == 0
        assert list_result.list_action.credits_delta == list_result.credits_added
        assert list_result.list_action.subject_app == "core"
        assert list_result.list_action.subject_type == "Campaign"
        assert list_result.list_action.subject_id == campaign.id
        assert "Campaign starting budget" in list_result.list_action.description

    # Verify ListActions are in database
    list_actions = ListAction.objects.filter(action_type=ListActionType.CAMPAIGN_START)
    assert list_actions.count() == 2


@pytest.mark.django_db
def test_handle_campaign_start_credits_match_budget_configuration(
    user,
    make_campaign,
    make_list,
    content_house,
    make_content_fighter,
    make_list_fighter,
):
    """Test that credits distributed match budget configuration."""
    # Create campaign with custom budget
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=2000)

    # Create fighter with cost 800
    fighter = make_content_fighter(
        type="Fighter", category="GANGER", house=content_house, base_cost=800
    )

    lst = make_list("Gang 1", content_house=content_house)
    make_list_fighter(lst, "Fighter", content_fighter=fighter)
    lst.rating_current = 800
    lst.save()

    campaign.lists.add(lst)

    # Start campaign
    result = handle_campaign_start(user=user, campaign=campaign)

    # Cost 800, budget 2000, should get 1200 credits (2000 - 800)
    assert len(result.list_results) == 1
    assert result.list_results[0].credits_added == 1200

    cloned_list = List.objects.get(campaign=campaign, status=List.CAMPAIGN_MODE)
    cloned_list.refresh_from_db()
    assert cloned_list.credits_current == 1200


@pytest.mark.django_db
def test_handle_campaign_start_zero_budget(
    user, make_campaign, make_list, content_house
):
    """Test that no credits are distributed when budget is zero."""
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=0)

    lst = make_list("Gang 1", content_house=content_house)
    lst.rating_current = 1000
    lst.save()

    campaign.lists.add(lst)

    # Start campaign
    result = handle_campaign_start(user=user, campaign=campaign)

    # Verify no credits added
    assert len(result.list_results) == 1
    assert result.list_results[0].credits_added == 0
    assert result.list_results[0].list_action is None
    assert result.list_results[0].campaign_action is None

    cloned_list = List.objects.get(campaign=campaign, status=List.CAMPAIGN_MODE)
    cloned_list.refresh_from_db()
    assert cloned_list.credits_current == 0


@pytest.mark.django_db
def test_handle_campaign_start_expensive_list(
    user,
    make_campaign,
    make_list,
    content_house,
    make_content_fighter,
    make_list_fighter,
):
    """Test that lists more expensive than budget get zero credits."""
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1000)

    # Create expensive fighter (costs more than budget)
    fighter = make_content_fighter(
        type="Expensive Fighter", category="LEADER", house=content_house, base_cost=1500
    )

    lst = make_list("Expensive Gang", content_house=content_house)
    make_list_fighter(lst, "Expensive Fighter", content_fighter=fighter)
    lst.rating_current = 1500  # More than budget
    lst.save()

    campaign.lists.add(lst)

    # Start campaign
    result = handle_campaign_start(user=user, campaign=campaign)

    # Cost 1500 > budget 1000, should get 0 credits (max(1000 - 1500, 0) = 0)
    assert len(result.list_results) == 1
    assert result.list_results[0].credits_added == 0

    cloned_list = List.objects.get(campaign=campaign, status=List.CAMPAIGN_MODE)
    cloned_list.refresh_from_db()
    assert cloned_list.credits_current == 0


@pytest.mark.django_db
def test_handle_campaign_start_only_once(user, make_campaign, make_list, content_house):
    """Test that campaign start can only happen once."""
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    lst = make_list("Gang 1", content_house=content_house)
    campaign.lists.add(lst)

    # Start campaign first time
    result1 = handle_campaign_start(user=user, campaign=campaign)
    assert result1.campaign.status == Campaign.IN_PROGRESS

    # Try to start again - should raise ValidationError
    with pytest.raises(ValidationError) as exc_info:
        handle_campaign_start(user=user, campaign=campaign)

    assert "cannot be started" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_handle_campaign_start_no_lists(user, make_campaign):
    """Test that campaign cannot be started without lists."""
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    # Try to start campaign with no lists
    with pytest.raises(ValidationError) as exc_info:
        handle_campaign_start(user=user, campaign=campaign)

    assert "cannot be started without lists" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_handle_campaign_start_creates_campaign_actions(
    user,
    make_campaign,
    make_list,
    content_house,
    make_content_fighter,
    make_list_fighter,
):
    """Test that both per-list and overall CampaignActions are created."""
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    # Create fighters
    fighter1 = make_content_fighter(
        type="Fighter 1", category="GANGER", house=content_house, base_cost=1000
    )
    fighter2 = make_content_fighter(
        type="Fighter 2", category="GANGER", house=content_house, base_cost=1200
    )

    list1 = make_list("Gang 1", content_house=content_house)
    make_list_fighter(list1, "Fighter 1", content_fighter=fighter1)
    list1.rating_current = 1000
    list1.save()

    list2 = make_list("Gang 2", content_house=content_house)
    make_list_fighter(list2, "Fighter 2", content_fighter=fighter2)
    list2.rating_current = 1200
    list2.save()

    campaign.lists.add(list1, list2)

    # Count CampaignActions before
    actions_before = CampaignAction.objects.filter(campaign=campaign).count()

    # Start campaign
    result = handle_campaign_start(user=user, campaign=campaign)

    # Verify overall CampaignAction created
    assert result.overall_campaign_action is not None
    assert "Campaign Started:" in result.overall_campaign_action.description
    assert "is now in progress" in result.overall_campaign_action.description
    assert "2 gang(s) joined" in result.overall_campaign_action.outcome

    # Verify per-list CampaignActions created
    assert len(result.list_results) == 2
    for list_result in result.list_results:
        assert list_result.campaign_action is not None
        assert "Campaign starting budget" in list_result.campaign_action.description
        assert list_result.campaign_action.list == list_result.campaign_list

    # Verify total CampaignActions: 2 per-list + 1 overall = 3 new actions
    actions_after = CampaignAction.objects.filter(campaign=campaign).count()
    assert actions_after == actions_before + 3


@pytest.mark.django_db
def test_handle_campaign_start_list_with_existing_credits(
    user,
    make_campaign,
    make_list,
    content_house,
    make_content_fighter,
    make_list_fighter,
):
    """Test budget distribution when list already has credits.

    Note: Existing credits are copied to the clone, and the budget calculation
    is based on rating + stash (not reduced by existing credits).
    """
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    # Create a fighter with cost 1000
    fighter_type = make_content_fighter(
        type="Expensive Fighter",
        category="LEADER",
        house=content_house,
        base_cost=1000,
    )

    lst = make_list("Gang 1", content_house=content_house)
    lst.credits_current = 200  # List already has 200 credits
    lst.save()

    # Add the fighter to the list (this sets rating_current to 1000)
    make_list_fighter(lst, "Leader", content_fighter=fighter_type)

    campaign.lists.add(lst)

    # Start campaign
    result = handle_campaign_start(user=user, campaign=campaign)

    # List cost is 1200 (1000 fighter cost + 200 existing credits), budget is 1500
    # Credits to add: 1500 - 1200 = 300
    assert result.list_results[0].credits_added == 300

    cloned_list = List.objects.get(campaign=campaign, status=List.CAMPAIGN_MODE)
    cloned_list.refresh_from_db()
    # Clone inherits 200 credits, then receives 300 more = 500 total
    assert cloned_list.credits_current == 500


@pytest.mark.django_db
def test_handle_campaign_start_updates_campaign_status(
    user, make_campaign, make_list, content_house
):
    """Test that campaign status is updated to IN_PROGRESS."""
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    lst = make_list("Gang 1", content_house=content_house)
    campaign.lists.add(lst)

    # Verify initial status
    assert campaign.status == Campaign.PRE_CAMPAIGN
    assert campaign.is_pre_campaign

    # Start campaign
    result = handle_campaign_start(user=user, campaign=campaign)

    # Verify status updated
    campaign.refresh_from_db()
    assert campaign.status == Campaign.IN_PROGRESS
    assert campaign.is_in_progress
    assert result.campaign.status == Campaign.IN_PROGRESS


@pytest.mark.django_db
def test_handle_campaign_start_clones_lists_to_campaign_mode(
    user, make_campaign, make_list, content_house
):
    """Test that lists are cloned with CAMPAIGN_MODE status."""
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    list1 = make_list("Gang 1", content_house=content_house)
    list2 = make_list("Gang 2", content_house=content_house)

    # Verify lists are in LIST_BUILDING mode
    assert list1.status == List.LIST_BUILDING
    assert list2.status == List.LIST_BUILDING

    campaign.lists.add(list1, list2)

    # Start campaign
    handle_campaign_start(user=user, campaign=campaign)

    # Verify original lists still in LIST_BUILDING
    list1.refresh_from_db()
    list2.refresh_from_db()
    assert list1.status == List.LIST_BUILDING
    assert list2.status == List.LIST_BUILDING

    # Verify cloned lists are in CAMPAIGN_MODE
    cloned_lists = List.objects.filter(campaign=campaign, status=List.CAMPAIGN_MODE)
    assert cloned_lists.count() == 2

    for cloned_list in cloned_lists:
        assert cloned_list.status == List.CAMPAIGN_MODE
        assert cloned_list.campaign == campaign
        assert cloned_list.original_list in [list1, list2]


@pytest.mark.django_db
def test_handle_campaign_start_create_action_has_correct_deltas(
    user,
    make_campaign,
    make_list,
    content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    """Test that the initial CREATE action for cloned lists has correct deltas.

    The CREATE action should represent creating the list from nothing,
    so before values should be 0 and deltas should equal the cloned values.
    """
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    # Create fighters with specific costs
    fighter1 = make_content_fighter(
        type="Fighter 1", category="GANGER", house=content_house, base_cost=500
    )
    fighter2 = make_content_fighter(
        type="Fighter 2", category="GANGER", house=content_house, base_cost=500
    )

    # Create stash fighter
    stash_cf = make_content_fighter(
        type="Stash", category="STASH", house=content_house, base_cost=0
    )
    stash_cf.is_stash = True
    stash_cf.save()

    # Create list with specific values
    lst = make_list("Gang 1", content_house=content_house)
    lst.credits_current = 200
    lst.save()

    # Add fighters (total rating: 1000)
    make_list_fighter(lst, "Fighter 1", content_fighter=fighter1)
    make_list_fighter(lst, "Fighter 2", content_fighter=fighter2)

    # Add stash fighter with equipment (total stash: 50)
    from gyrinx.core.models.list import ListFighter

    stash_fighter = ListFighter.objects.create(
        name="Gang Stash", content_fighter=stash_cf, list=lst, owner=user
    )
    stash_equipment = make_equipment("Stash Item", cost="50")
    stash_fighter.assign(stash_equipment)

    # Explicitly set rating_current and stash_current to match costs
    lst.rating_current = 1000
    lst.stash_current = 50
    lst.save()

    campaign.lists.add(lst)

    # Start campaign
    handle_campaign_start(user=user, campaign=campaign)

    # Get the cloned list
    cloned_list = List.objects.get(campaign=campaign, status=List.CAMPAIGN_MODE)

    # Find the CREATE action
    create_action = ListAction.objects.filter(
        list=cloned_list, action_type=ListActionType.CREATE
    ).first()

    assert create_action is not None, "CREATE action should exist"

    # Verify before values are 0 (list created from nothing)
    assert create_action.rating_before == 0
    assert create_action.stash_before == 0
    assert create_action.credits_before == 0

    # Verify deltas match the cloned values
    assert create_action.rating_delta == 1000
    assert create_action.stash_delta == 50
    assert create_action.credits_delta == 200

    # Verify after values match current values
    assert create_action.rating_after == 1000
    assert create_action.stash_after == 50
    assert create_action.credits_after == 200

    # Verify the CAMPAIGN_START action exists and adds budget credits
    campaign_start_action = ListAction.objects.filter(
        list=cloned_list, action_type=ListActionType.CAMPAIGN_START
    ).first()

    assert campaign_start_action is not None
    # Credits before should be what CREATE action set (200)
    assert campaign_start_action.credits_before == 200
    # List cost is 1250 (1000 fighters + 50 stash + 200 credits), budget is 1500
    # Credits to add: 1500 - 1250 = 250
    assert campaign_start_action.credits_delta == 250
    # Final credits: 200 + 250 = 450
    assert campaign_start_action.credits_after == 450
