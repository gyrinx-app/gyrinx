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
def test_campaign_log_action_list_owner_can_view():
    """Test that only owners of lists in a campaign can view the campaign action log."""
    client = Client()

    # Create test users
    list_owner = User.objects.create_user(username="list_owner", password="testpass")
    campaign_owner = User.objects.create_user(
        username="campaign_owner", password="testpass"
    )
    User.objects.create_user(username="other_user", password="testpass")

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Owner View Campaign",
        owner=campaign_owner,
        public=True,
        summary="A campaign to test owner view",
        status=Campaign.IN_PROGRESS,
    )

    # Create a house and a list for the campaign
    house = ContentHouse.objects.create(name="House Van Saar")
    gang = List.objects.create(
        name="Gang Gamma",
        owner=list_owner,
        content_house=house,
        campaign=campaign,
    )
    campaign.lists.add(gang)

    # Create a campaign action
    CampaignAction.objects.create(
        campaign=campaign,
        user=list_owner,
        owner=list_owner,  # Add owner field
        list=gang,
        description="Gang Gamma secures a new territory",
        outcome="Success",
        dice_count=4,
    )

    # Test that the list owner can view the campaign action log
    client.login(username="list_owner", password="testpass")
    response = client.get(reverse("core:campaign-actions", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gang Gamma secures a new territory" in content
    client.logout()

    # Test that the campaign owner can view the campaign action log
    client.login(username="campaign_owner", password="testpass")
    response = client.get(reverse("core:campaign-actions", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Gang Gamma secures a new territory" in content
    client.logout()

    # Test that another user cannot view the campaign action log
    client.login(username="other_user", password="testpass")
    response = client.get(reverse("core:campaign-actions", args=[campaign.id]))
    assert response.status_code == 303  # Redirect to login or no permission
    client.logout()


@pytest.mark.django_db
def test_campaign_log_action_permissions():
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
