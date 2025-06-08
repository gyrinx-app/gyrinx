import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List

User = get_user_model()


@pytest.mark.django_db
def test_homepage_campaign_modules():
    """Test that the homepage shows campaign gangs and campaigns correctly."""
    # Create test user
    user = User.objects.create_user(username="testuser", password="password")

    # Create test house
    house = ContentHouse.objects.create(name="Test House")

    # Create regular lists (in list building mode)
    regular_list1 = List.objects.create(
        name="Regular Gang 1",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    regular_list2 = List.objects.create(
        name="Regular Gang 2",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Create a campaign
    active_campaign = Campaign.objects.create(
        name="Active Campaign", owner=user, status=Campaign.IN_PROGRESS
    )

    # Create campaign gangs (in campaign mode)
    campaign_gang1 = List.objects.create(
        name="Campaign Gang 1",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=active_campaign,
        theme_color="#FF0000",
    )
    campaign_gang2 = List.objects.create(
        name="Campaign Gang 2",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=active_campaign,
        theme_color="#00FF00",
    )

    # Create a pre-campaign that user owns
    pre_campaign = Campaign.objects.create(
        name="Pre Campaign", owner=user, status=Campaign.PRE_CAMPAIGN
    )

    # Create another user and their campaign where our user participates
    other_user = User.objects.create_user(username="otheruser", password="password")
    other_campaign = Campaign.objects.create(
        name="Other's Campaign", owner=other_user, status=Campaign.IN_PROGRESS
    )

    # Create a gang in the other campaign
    other_campaign_gang = List.objects.create(
        name="Gang in Other Campaign",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=other_campaign,
    )

    # Test authenticated user view
    client = Client()
    client.login(username="testuser", password="password")
    response = client.get(reverse("core:index"))

    assert response.status_code == 200

    # Check context variables
    assert "lists" in response.context
    assert "campaign_gangs" in response.context
    assert "campaigns" in response.context

    # Check regular lists
    lists = response.context["lists"]
    assert regular_list1 in lists
    assert regular_list2 in lists
    assert campaign_gang1 not in lists  # Campaign gangs should not be in regular lists
    assert campaign_gang2 not in lists

    # Check campaign gangs
    campaign_gangs = response.context["campaign_gangs"]
    assert campaign_gang1 in campaign_gangs
    assert campaign_gang2 in campaign_gangs
    assert other_campaign_gang in campaign_gangs
    assert regular_list1 not in campaign_gangs

    # Check campaigns
    campaigns = response.context["campaigns"]
    assert active_campaign in campaigns
    assert pre_campaign in campaigns
    assert other_campaign in campaigns  # User has a gang in this campaign

    # Check content rendering
    content = response.content.decode()

    # Check headings
    assert "Campaign gangs" in content
    assert "Campaigns" in content
    assert "Lists" in content
    assert "Your Lists" not in content  # Should be changed to just "Lists"

    # Check campaign gangs section
    assert "Campaign Gang 1" in content
    assert "Campaign Gang 2" in content
    assert "Gang in Other Campaign" in content
    assert active_campaign.name in content
    # HTML encodes apostrophes, check for both possibilities
    assert "Other's Campaign" in content or "Other&#x27;s Campaign" in content

    # Check campaigns section
    assert "Active Campaign" in content
    assert "Pre Campaign" in content
    assert "Other's Campaign" in content or "Other&#x27;s Campaign" in content
    assert "In Progress" in content
    assert "Pre-Campaign" in content

    # Check regular lists section
    assert "Regular Gang 1" in content
    assert "Regular Gang 2" in content


@pytest.mark.django_db
def test_homepage_no_campaigns():
    """Test homepage when user has no campaigns or campaign gangs."""
    # Create test user
    user = User.objects.create_user(username="testuser", password="password")

    # Create test house
    house = ContentHouse.objects.create(name="Test House")

    # Create only regular lists
    List.objects.create(
        name="Only Regular Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    client = Client()
    client.login(username="testuser", password="password")
    response = client.get(reverse("core:index"))

    assert response.status_code == 200

    content = response.content.decode()

    # Check empty state messages
    assert "You have no campaign gangs." in content
    assert (
        'You are not part of any campaigns. <a href="/campaigns/">Click here to create a new campaign</a>.'
        in content
    )


@pytest.mark.django_db
def test_homepage_anonymous_user():
    """Test that anonymous users don't see campaign modules."""
    client = Client()
    response = client.get(reverse("core:index"))

    assert response.status_code == 200

    # Anonymous users should get empty lists
    assert response.context["lists"] == []
    assert response.context["campaign_gangs"] == []
    assert response.context["campaigns"] == []

    content = response.content.decode()

    # Should see marketing content
    assert "Build and manage your gangs" in content
