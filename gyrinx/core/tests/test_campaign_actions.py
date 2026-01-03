import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List


@pytest.mark.django_db
def test_campaign_action_list_filtering():
    """Test that campaign action list view supports filtering."""
    client = Client()

    # Create test users
    user1 = User.objects.create_user(username="player1", password="testpass")
    user2 = User.objects.create_user(username="player2", password="testpass")
    owner = User.objects.create_user(username="owner", password="testpass")

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=owner,
        public=True,
        summary="A test campaign",
        status=Campaign.IN_PROGRESS,
    )

    # Create houses and lists for the campaign
    house1 = ContentHouse.objects.create(name="House Goliath")
    house2 = ContentHouse.objects.create(name="House Escher")

    list1 = List.objects.create(
        name="Gang Alpha",
        owner=user1,
        content_house=house1,
        campaign=campaign,
    )
    list2 = List.objects.create(
        name="Gang Beta",
        owner=user2,
        content_house=house2,
        campaign=campaign,
    )

    campaign.lists.add(list1, list2)

    # Create some campaign actions
    action1 = CampaignAction.objects.create(
        campaign=campaign,
        user=user1,
        owner=user1,  # Add owner field
        list=list1,  # Associate with Gang Alpha
        description="Gang Alpha attacks the water still",
        outcome="Victory! Water still captured",
        dice_count=3,
    )
    action1.roll_dice()
    action1.save()

    action2 = CampaignAction.objects.create(
        campaign=campaign,
        user=user2,
        owner=user2,  # Add owner field
        list=list2,  # Associate with Gang Beta
        description="Gang Beta scouts the underhive",
        outcome="Found a hidden cache",
        dice_count=2,
    )
    action2.roll_dice()
    action2.save()

    CampaignAction.objects.create(
        campaign=campaign,
        user=user1,
        owner=user1,  # Add owner field
        list=list1,  # Associate with Gang Alpha
        description="Gang Alpha trades at the market",
        outcome="",
        dice_count=0,
    )

    # Log in as owner
    client.login(username="owner", password="testpass")

    # Test unfiltered view
    response = client.get(reverse("core:campaign-actions", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gang Alpha attacks the water still" in content
    assert "Gang Beta scouts the underhive" in content
    assert "Gang Alpha trades at the market" in content

    # Test text search filtering
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]), {"q": "water still"}
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gang Alpha attacks the water still" in content
    assert "Gang Beta scouts the underhive" not in content
    assert "Gang Alpha trades at the market" not in content

    # Test gang filtering
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]), {"gang": str(list1.id)}
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gang Alpha attacks the water still" in content
    assert "Gang Beta scouts the underhive" not in content
    assert "Gang Alpha trades at the market" in content

    # Test author filtering
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]), {"author": str(user2.id)}
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gang Alpha attacks the water still" not in content
    assert "Gang Beta scouts the underhive" in content
    assert "Gang Alpha trades at the market" not in content

    # Test combined filters
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]),
        {"q": "market", "author": str(user1.id)},
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gang Alpha attacks the water still" not in content
    assert "Gang Beta scouts the underhive" not in content
    assert "Gang Alpha trades at the market" in content

    # Test that filter form elements are present
    response = client.get(reverse("core:campaign-actions", args=[campaign.id]))
    content = response.content.decode()
    assert 'name="q"' in content  # Search input
    assert 'name="gang"' in content  # Gang select
    assert 'name="author"' in content  # Author select
    assert "Update Filters" in content  # Filter button

    # Test that pagination preserves filters
    # Create more actions to trigger pagination
    # We need more than 50 results matching the filter to see pagination
    for i in range(55):
        CampaignAction.objects.create(
            campaign=campaign,
            user=user1,
            description=f"Gang Alpha trades water supplies - batch {i}",
        )

    # Now we have 56 water-related actions (1 original + 55 new), which triggers pagination
    response = client.get(
        reverse("core:campaign-actions", args=[campaign.id]), {"q": "water"}
    )
    assert response.status_code == 200
    content = response.content.decode()
    # Check that filter parameters are preserved in pagination links
    assert "page=2" in content  # Next page link should exist
    assert "q=water" in content  # Filter should be preserved


@pytest.mark.django_db
def test_campaign_action_new_permissions():
    """Test that only campaign owner or list owners can access the log action form."""
    client = Client()

    # Create users
    campaign_owner = User.objects.create_user(
        username="campaign_owner", password="testpass"
    )
    list_owner = User.objects.create_user(username="list_owner", password="testpass")
    User.objects.create_user(username="outsider", password="testpass")

    # Create campaign and list
    campaign = Campaign.objects.create(
        name="Permission Test Campaign",
        owner=campaign_owner,
        public=True,
        status=Campaign.IN_PROGRESS,
    )
    house = ContentHouse.objects.create(name="House Orlock")
    gang = List.objects.create(
        name="Orlock Gang",
        owner=list_owner,
        content_house=house,
        campaign=campaign,
    )
    campaign.lists.add(gang)

    url = reverse("core:campaign-action-new", args=[campaign.id])

    # Campaign owner can access
    client.login(username="campaign_owner", password="testpass")
    response = client.get(url)
    assert response.status_code == 200
    client.logout()

    # List owner can access
    client.login(username="list_owner", password="testpass")
    response = client.get(url)
    assert response.status_code == 200
    client.logout()

    # Outsider is redirected
    client.login(username="outsider", password="testpass")
    response = client.get(url)
    assert response.status_code in (302, 303)
    # Optionally, check redirect location:
    assert reverse("core:campaign", args=[campaign.id]) in response["Location"]
    client.logout()


@pytest.mark.django_db
def test_campaign_action_new_form_initialization():
    """Test that the campaign action form initializes with gang selected if parameter is given."""
    client = Client()

    # Create users
    campaign_owner = User.objects.create_user(
        username="campaign_owner", password="testpass"
    )
    list_owner = User.objects.create_user(username="list_owner", password="testpass")

    # Create campaign and list
    campaign = Campaign.objects.create(
        name="Form Init Campaign",
        owner=campaign_owner,
        public=True,
        status=Campaign.IN_PROGRESS,
    )
    house = ContentHouse.objects.create(name="House Cawdor")
    gang = List.objects.create(
        name="Cawdor Gang",
        owner=list_owner,
        content_house=house,
        campaign=campaign,
    )
    campaign.lists.add(gang)

    url = reverse("core:campaign-action-new", args=[campaign.id])

    # Log in as list owner
    client.login(username="list_owner", password="testpass")
    response = client.get(url + f"?gang={gang.id}")
    assert response.status_code == 200
    content = response.content.decode()

    # Check that the gang is pre-selected in the form
    assert f'<option value="{gang.id}" selected>' in content
    client.logout()


@pytest.mark.django_db
def test_campaign_action_outcome_permissions():
    """Test that only the action creator can access the outcome form; others are redirected."""
    client = Client()

    # Create users
    campaign_owner = User.objects.create_user(
        username="campaign_owner", password="testpass"
    )
    action_creator = User.objects.create_user(
        username="action_creator", password="testpass"
    )
    User.objects.create_user(username="outsider", password="testpass")

    # Create campaign and list
    campaign = Campaign.objects.create(
        name="Outcome Permission Campaign",
        owner=campaign_owner,
        public=True,
        status=Campaign.IN_PROGRESS,
    )
    house = ContentHouse.objects.create(name="House Delaque")
    gang = List.objects.create(
        name="Delaque Gang",
        owner=action_creator,
        content_house=house,
        campaign=campaign,
    )
    campaign.lists.add(gang)

    # Create a campaign action
    action = CampaignAction.objects.create(
        campaign=campaign,
        user=action_creator,
        owner=action_creator,
        list=gang,
        description="Delaque Gang infiltrates",
        outcome="Stealth success",
        dice_count=2,
    )

    url = reverse("core:campaign-action-outcome", args=[campaign.id, action.id])

    # Action creator can access
    client.login(username="action_creator", password="testpass")
    response = client.get(url)
    assert response.status_code == 200
    client.logout()

    # Campaign owner (not action creator) is redirected
    client.login(username="campaign_owner", password="testpass")
    response = client.get(url)
    assert response.status_code in (302, 303)
    assert reverse("core:campaign", args=[campaign.id]) in response["Location"]
    client.logout()

    # Outsider is redirected
    client.login(username="outsider", password="testpass")
    response = client.get(url)
    assert response.status_code in (302, 303)
    assert reverse("core:campaign", args=[campaign.id]) in response["Location"]
    client.logout()
