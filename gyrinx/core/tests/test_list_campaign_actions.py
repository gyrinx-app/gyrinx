import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models import Campaign, CampaignAction, List


@pytest.mark.django_db
def test_list_campaign_actions_filter_by_gang(client):
    """Test that campaign actions are filtered by specific gang, not by gang owner."""
    # Create test users
    user1 = User.objects.create_user(username="testuser1", password="password")
    user2 = User.objects.create_user(username="testuser2", password="password")
    
    # Create test data
    house = ContentHouse.objects.create(name="Test House")
    campaign = Campaign.objects.create(
        name="Test Campaign", 
        owner=user1, 
        status="in_progress"
    )
    
    # Create two gangs owned by the same user
    gang1 = List.objects.create(
        name="Gang 1",
        owner=user1,
        content_house=house,
        campaign=campaign,
        is_campaign_mode=True,
    )
    gang2 = List.objects.create(
        name="Gang 2",
        owner=user1,
        content_house=house,
        campaign=campaign,
        is_campaign_mode=True,
    )
    
    # Create a gang owned by a different user
    gang3 = List.objects.create(
        name="Gang 3",
        owner=user2,
        content_house=house,
        campaign=campaign,
        is_campaign_mode=True,
    )
    
    # Create actions for each gang
    action1 = CampaignAction.objects.create(
        campaign=campaign,
        user=user1,
        list=gang1,
        description="Action for Gang 1",
    )
    action2 = CampaignAction.objects.create(
        campaign=campaign,
        user=user1,
        list=gang2,
        description="Action for Gang 2",
    )
    action3 = CampaignAction.objects.create(
        campaign=campaign,
        user=user2,
        list=gang3,
        description="Action for Gang 3",
    )
    
    # Log in as user1
    client.login(username="testuser1", password="password")
    
    # Test that gang1 only sees its own action
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]),
        {"gang": gang1.id}
    )
    assert response.status_code == 200
    
    # Check that only gang1's action is shown
    action_list = response.context["actions"]
    assert len(action_list) == 1
    assert action_list[0].id == action1.id
    assert action_list[0].description == "Action for Gang 1"
    
    # Test that gang2 only sees its own action
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]),
        {"gang": gang2.id}
    )
    assert response.status_code == 200
    
    # Check that only gang2's action is shown
    action_list = response.context["actions"]
    assert len(action_list) == 1
    assert action_list[0].id == action2.id
    assert action_list[0].description == "Action for Gang 2"


@pytest.mark.django_db
def test_list_view_shows_only_gang_actions(client):
    """Test that the list detail view only shows actions for the specific gang."""
    # Create test user
    user = User.objects.create_user(username="testuser", password="password")
    
    # Create test data
    house = ContentHouse.objects.create(name="Test House")
    campaign = Campaign.objects.create(
        name="Test Campaign", 
        owner=user, 
        status="in_progress"
    )
    
    # Create two gangs owned by the same user
    gang1 = List.objects.create(
        name="Gang 1",
        owner=user,
        content_house=house,
        campaign=campaign,
        is_campaign_mode=True,
    )
    gang2 = List.objects.create(
        name="Gang 2",
        owner=user,
        content_house=house,
        campaign=campaign,
        is_campaign_mode=True,
    )
    
    # Create actions for each gang
    action1 = CampaignAction.objects.create(
        campaign=campaign,
        user=user,
        list=gang1,
        description="Action for Gang 1",
    )
    action2 = CampaignAction.objects.create(
        campaign=campaign,
        user=user,
        list=gang2,
        description="Action for Gang 2",
    )
    
    # Log in
    client.login(username="testuser", password="password")
    
    # Test gang1's list view
    response = client.get(reverse("core:list", args=[gang1.id]))
    assert response.status_code == 200
    
    # Check that only gang1's action is shown
    recent_actions = response.context.get("recent_actions", [])
    assert len(recent_actions) == 1
    assert recent_actions[0].id == action1.id
    assert recent_actions[0].description == "Action for Gang 1"
    
    # Test gang2's list view
    response = client.get(reverse("core:list", args=[gang2.id]))
    assert response.status_code == 200
    
    # Check that only gang2's action is shown
    recent_actions = response.context.get("recent_actions", [])
    assert len(recent_actions) == 1
    assert recent_actions[0].id == action2.id
    assert recent_actions[0].description == "Action for Gang 2"


@pytest.mark.django_db
def test_gang_with_no_actions_shows_no_actions(client):
    """Test that a gang with no actions shows no actions."""
    # Create test user
    user = User.objects.create_user(username="testuser", password="password")
    
    # Create test data
    house = ContentHouse.objects.create(name="Test House")
    campaign = Campaign.objects.create(
        name="Test Campaign", 
        owner=user, 
        status="in_progress"
    )
    
    # Create a gang with no actions
    gang = List.objects.create(
        name="Gang with No Actions",
        owner=user,
        content_house=house,
        campaign=campaign,
        is_campaign_mode=True,
    )
    
    # Create another gang with actions (to ensure filtering works)
    other_gang = List.objects.create(
        name="Other Gang",
        owner=user,
        content_house=house,
        campaign=campaign,
        is_campaign_mode=True,
    )
    CampaignAction.objects.create(
        campaign=campaign,
        user=user,
        list=other_gang,
        description="Action for Other Gang",
    )
    
    # Log in
    client.login(username="testuser", password="password")
    
    # Test gang's list view
    response = client.get(reverse("core:list", args=[gang.id]))
    assert response.status_code == 200
    
    # Check that no actions are shown
    recent_actions = response.context.get("recent_actions", [])
    assert len(recent_actions) == 0