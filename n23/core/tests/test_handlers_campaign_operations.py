"""
Tests for campaign operation handlers.

These tests drive handle_campaign_start in n23.core.handlers.campaign_operations.

Campaign start is now two-phase (issue #1222): handle_campaign_start synchronously
creates stub lists (status CLONING_IN_PROGRESS) and enqueues one
complete_campaign_list_clone task per stub on commit; those tasks do the actual cloning
and budget distribution and flip each stub to CAMPAIGN_MODE. In dev/test the ImmediateBackend
runs the tasks inline, but only once the on_commit callbacks fire — so tests that want the
finished result wrap the call in ``django_capture_on_commit_callbacks(execute=True)`` via the
``_start`` helper below. These are end-to-end equivalence tests: the final state must match
the old synchronous behaviour.
"""

import pytest
from django.core.exceptions import ValidationError

from n23.core.handlers.campaign_operations import handle_campaign_start
from n23.core.models.action import ListAction, ListActionType
from n23.core.models.campaign import Campaign, CampaignAction
from n23.core.models.list import List


def _start(user, campaign, capture):
    """Start the campaign AND run its deferred Phase-2 clone tasks.

    The clone tasks are enqueued via ``transaction.on_commit``; ``capture(execute=True)``
    fires those callbacks (running the tasks inline under the ImmediateBackend), so on
    return the campaign is fully started just like the old synchronous path.
    """
    with capture(execute=True):
        result = handle_campaign_start(user=user, campaign=campaign)
    return result


@pytest.mark.django_db
def test_handle_campaign_start_all_lists_receive_credits(
    user,
    make_campaign,
    make_list,
    content_house,
    make_content_fighter,
    make_list_fighter,
    django_capture_on_commit_callbacks,
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

    # Start campaign (runs Phase 2 clone tasks inline)
    result = _start(user, campaign, django_capture_on_commit_callbacks)

    # Verify all 3 stubs were created
    assert len(result.stub_lists) == 3

    # Get the cloned lists and verify credits (all should have finished cloning)
    cloned_lists = List.objects.filter(
        campaign=campaign, status=List.CAMPAIGN_MODE
    ).order_by("name")
    assert cloned_lists.count() == 3

    # Gang 1: Cost 1000, gets 500 credits (1500 budget - 1000 cost)
    gang1_clone = cloned_lists.get(name="Gang 1")
    assert gang1_clone.credits_current == 500
    assert gang1_clone.credits_earned == 500

    # Gang 2: Cost 1200, gets 300 credits (1500 budget - 1200 cost)
    gang2_clone = cloned_lists.get(name="Gang 2")
    assert gang2_clone.credits_current == 300
    assert gang2_clone.credits_earned == 300

    # Gang 3: Cost 500, gets 1000 credits (1500 budget - 500 cost)
    gang3_clone = cloned_lists.get(name="Gang 3")
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
    django_capture_on_commit_callbacks,
):
    """Test that CAMPAIGN_START ListActions are created for each list.

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
    result = _start(user, campaign, django_capture_on_commit_callbacks)
    assert len(result.stub_lists) == 2

    # Verify CAMPAIGN_START ListActions created for both lists, with correct shape.
    list_actions = ListAction.objects.filter(action_type=ListActionType.CAMPAIGN_START)
    assert list_actions.count() == 2
    for list_action in list_actions:
        assert list_action.rating_delta == 0
        assert list_action.stash_delta == 0
        assert list_action.credits_delta > 0
        assert list_action.subject_app == "core"
        assert list_action.subject_type == "Campaign"
        assert list_action.subject_id == campaign.id
        assert "Campaign starting budget" in list_action.description

    # Gang 1 (cost 1000) -> +500, Gang 2 (cost 1200) -> +300
    assert {a.credits_delta for a in list_actions} == {500, 300}


@pytest.mark.django_db
def test_handle_campaign_start_credits_match_budget_configuration(
    user,
    make_campaign,
    make_list,
    content_house,
    make_content_fighter,
    make_list_fighter,
    django_capture_on_commit_callbacks,
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
    result = _start(user, campaign, django_capture_on_commit_callbacks)
    assert len(result.stub_lists) == 1

    # Cost 800, budget 2000, should get 1200 credits (2000 - 800)
    cloned_list = List.objects.get(campaign=campaign, status=List.CAMPAIGN_MODE)
    assert cloned_list.credits_current == 1200


@pytest.mark.django_db
def test_handle_campaign_start_zero_budget(
    user, make_campaign, make_list, content_house, django_capture_on_commit_callbacks
):
    """Test that no credits are distributed when budget is zero."""
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=0)

    lst = make_list("Gang 1", content_house=content_house)
    lst.rating_current = 1000
    lst.save()

    campaign.lists.add(lst)

    # Start campaign
    result = _start(user, campaign, django_capture_on_commit_callbacks)
    assert len(result.stub_lists) == 1

    # Verify no credits added and no CAMPAIGN_START action
    cloned_list = List.objects.get(campaign=campaign, status=List.CAMPAIGN_MODE)
    assert cloned_list.credits_current == 0
    assert not ListAction.objects.filter(
        list=cloned_list, action_type=ListActionType.CAMPAIGN_START
    ).exists()


@pytest.mark.django_db
def test_handle_campaign_start_expensive_list(
    user,
    make_campaign,
    make_list,
    content_house,
    make_content_fighter,
    make_list_fighter,
    django_capture_on_commit_callbacks,
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
    result = _start(user, campaign, django_capture_on_commit_callbacks)
    assert len(result.stub_lists) == 1

    # Cost 1500 > budget 1000, should get 0 credits (max(1000 - 1500, 0) = 0)
    cloned_list = List.objects.get(campaign=campaign, status=List.CAMPAIGN_MODE)
    assert cloned_list.credits_current == 0
    assert not ListAction.objects.filter(
        list=cloned_list, action_type=ListActionType.CAMPAIGN_START
    ).exists()


@pytest.mark.django_db
def test_handle_campaign_start_only_once(
    user, make_campaign, make_list, content_house, django_capture_on_commit_callbacks
):
    """Test that campaign start can only happen once."""
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    lst = make_list("Gang 1", content_house=content_house)
    campaign.lists.add(lst)

    # Start campaign first time
    result1 = _start(user, campaign, django_capture_on_commit_callbacks)
    assert result1.campaign.status == Campaign.IN_PROGRESS

    # Try to start again - should raise ValidationError (campaign no longer PRE_CAMPAIGN)
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
    django_capture_on_commit_callbacks,
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
    result = _start(user, campaign, django_capture_on_commit_callbacks)
    assert len(result.stub_lists) == 2

    # Verify overall CampaignAction created
    assert result.overall_campaign_action is not None
    assert "Campaign Started:" in result.overall_campaign_action.description
    assert "is now in progress" in result.overall_campaign_action.description
    assert "2 gang(s) joined" in result.overall_campaign_action.outcome

    # Verify per-list CampaignActions created (one budget action per cloned list)
    per_list_actions = CampaignAction.objects.filter(
        campaign=campaign, list__isnull=False
    )
    assert per_list_actions.count() == 2
    for action in per_list_actions:
        assert "Campaign starting budget" in action.description

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
    django_capture_on_commit_callbacks,
):
    """Test budget distribution when list already has credits.

    Note: Existing credits are copied to the clone, and the budget calculation
    is based on rating + stash + existing credits (cost_int includes credits).
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
    _start(user, campaign, django_capture_on_commit_callbacks)

    # List cost is 1200 (1000 fighter cost + 200 existing credits), budget is 1500
    # Credits to add: 1500 - 1200 = 300. Clone inherits 200, then +300 = 500 total.
    cloned_list = List.objects.get(campaign=campaign, status=List.CAMPAIGN_MODE)
    assert cloned_list.credits_current == 500


@pytest.mark.django_db
def test_handle_campaign_start_updates_campaign_status(
    user, make_campaign, make_list, content_house, django_capture_on_commit_callbacks
):
    """Test that campaign status is updated to IN_PROGRESS."""
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    lst = make_list("Gang 1", content_house=content_house)
    campaign.lists.add(lst)

    # Verify initial status
    assert campaign.status == Campaign.PRE_CAMPAIGN
    assert campaign.is_pre_campaign

    # Start campaign
    result = _start(user, campaign, django_capture_on_commit_callbacks)

    # Verify status updated (Phase 1 flips this synchronously)
    campaign.refresh_from_db()
    assert campaign.status == Campaign.IN_PROGRESS
    assert campaign.is_in_progress
    assert result.campaign.status == Campaign.IN_PROGRESS


@pytest.mark.django_db
def test_handle_campaign_start_creates_stubs_before_cloning(
    user, make_campaign, make_list, content_house
):
    """Phase 1 creates CLONING_IN_PROGRESS stubs and flips the campaign, without cloning.

    Without firing the on_commit callbacks, the clone tasks never run, so the stubs
    should still be in CLONING_IN_PROGRESS and no budget actions should exist yet.
    """
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    list1 = make_list("Gang 1", content_house=content_house)
    list2 = make_list("Gang 2", content_house=content_house)
    campaign.lists.add(list1, list2)

    # Start campaign but DON'T fire on_commit -> Phase 2 does not run.
    result = handle_campaign_start(user=user, campaign=campaign)

    assert len(result.stub_lists) == 2
    campaign.refresh_from_db()
    assert campaign.status == Campaign.IN_PROGRESS

    # Two stubs on the campaign, both still cloning
    stubs = List.objects.filter(campaign=campaign, status=List.CLONING_IN_PROGRESS)
    assert stubs.count() == 2
    assert set(campaign.lists.values_list("id", flat=True)) == set(
        stubs.values_list("id", flat=True)
    )
    for stub in stubs:
        assert stub.is_cloning
        assert stub.original_list_id in {list1.id, list2.id}

    # No cloned (CAMPAIGN_MODE) lists and no budget actions yet
    assert not List.objects.filter(
        campaign=campaign, status=List.CAMPAIGN_MODE
    ).exists()
    assert not ListAction.objects.filter(
        action_type=ListActionType.CAMPAIGN_START
    ).exists()


@pytest.mark.django_db
def test_handle_campaign_start_clones_lists_to_campaign_mode(
    user, make_campaign, make_list, content_house, django_capture_on_commit_callbacks
):
    """Test that lists are cloned with CAMPAIGN_MODE status (after Phase 2 runs)."""
    campaign = make_campaign("Test Campaign", status=Campaign.PRE_CAMPAIGN, budget=1500)

    list1 = make_list("Gang 1", content_house=content_house)
    list2 = make_list("Gang 2", content_house=content_house)

    # Verify lists are in LIST_BUILDING mode
    assert list1.status == List.LIST_BUILDING
    assert list2.status == List.LIST_BUILDING

    campaign.lists.add(list1, list2)

    # Start campaign (runs clone tasks inline)
    _start(user, campaign, django_capture_on_commit_callbacks)

    # Verify original lists still in LIST_BUILDING
    list1.refresh_from_db()
    list2.refresh_from_db()
    assert list1.status == List.LIST_BUILDING
    assert list2.status == List.LIST_BUILDING

    # Verify cloned lists are now in CAMPAIGN_MODE (Phase 2 flipped them)
    cloned_lists = List.objects.filter(campaign=campaign, status=List.CAMPAIGN_MODE)
    assert cloned_lists.count() == 2

    for cloned_list in cloned_lists:
        assert cloned_list.status == List.CAMPAIGN_MODE
        assert cloned_list.campaign == campaign
        assert cloned_list.original_list in [list1, list2]

    # No stubs left behind
    assert not List.objects.filter(
        campaign=campaign, status=List.CLONING_IN_PROGRESS
    ).exists()


@pytest.mark.django_db
def test_handle_campaign_start_create_action_has_correct_deltas(
    user,
    make_campaign,
    make_list,
    content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
    django_capture_on_commit_callbacks,
):
    """Test that the initial CREATE action for cloned lists has correct deltas.

    The CREATE action should represent creating the list from nothing, so before
    values should be 0 and deltas should equal the cloned values. This is the key
    equivalence check that the async split books the same audit chain as before.
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
    from n23.core.models.list import ListFighter

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

    # Start campaign (runs clone task inline)
    _start(user, campaign, django_capture_on_commit_callbacks)

    # Get the cloned list
    cloned_list = List.objects.get(campaign=campaign, status=List.CAMPAIGN_MODE)

    # Find the CREATE action
    create_action = ListAction.objects.filter(
        list=cloned_list, action_type=ListActionType.CREATE
    ).first()

    # A CREATE action should exist for the cloned list
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
