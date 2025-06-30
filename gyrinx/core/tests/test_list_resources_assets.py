"""Test list view displays campaign resources and assets correctly."""

import pytest
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAsset,
    CampaignAssetType,
    CampaignListResource,
    CampaignResourceType,
)
from gyrinx.core.models.list import List


@pytest.mark.django_db
def test_list_view_displays_campaign_resources_and_assets(django_user_model):
    """Test that list detail view includes campaign resources and assets in context."""
    # Create test user
    user = django_user_model.objects.create_user(
        username="testuser", password="testpass"
    )
    client = Client()
    client.login(username="testuser", password="testpass")

    # Create test data
    house = ContentHouse.objects.create(name="Test House")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    # Create a list in campaign mode
    test_list = List.objects.create(
        name="Test Gang",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    # Create resource type and resource
    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Credits",
        owner=user,
    )

    CampaignListResource.objects.create(
        campaign=campaign,
        resource_type=resource_type,
        list=test_list,
        amount=100,
        owner=user,
    )

    # Create asset type and asset
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )

    CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        description="A valuable territory",
        holder=test_list,
        owner=user,
    )

    # Test the view
    response = client.get(reverse("core:list", kwargs={"id": test_list.id}))
    assert response.status_code == 200

    # Check context contains resources and assets
    assert "campaign_resources" in response.context
    assert "held_assets" in response.context

    # Verify the resources are included
    resources = list(response.context["campaign_resources"])
    assert len(resources) == 1
    assert resources[0].amount == 100
    assert resources[0].resource_type.name == "Credits"

    # Verify the assets are included
    assets = list(response.context["held_assets"])
    assert len(assets) == 1
    assert assets[0].name == "The Sump"
    assert assets[0].asset_type.name_singular == "Territory"

    # Check that the content is rendered in the HTML
    # HTML entities are encoded in the response
    assert (
        "Assets &amp; Resources" in response.content.decode()
        or "Assets & Resources" in response.content.decode()
    )
    assert "Credits" in response.content.decode()
    assert "100" in response.content.decode()
    assert "The Sump" in response.content.decode()
    assert "Territory" in response.content.decode()


@pytest.mark.django_db
def test_list_view_no_resources_or_assets_shows_message(django_user_model):
    """Test that list detail view shows 'No assets or resources held' when empty."""
    # Create test user
    user = django_user_model.objects.create_user(
        username="testuser2", password="testpass"
    )
    client = Client()
    client.login(username="testuser2", password="testpass")

    # Create test data
    house = ContentHouse.objects.create(name="Test House 2")
    campaign = Campaign.objects.create(
        name="Test Campaign 2",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    # Create a list in campaign mode with no resources or assets
    test_list = List.objects.create(
        name="Empty Gang",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    # Test the view
    response = client.get(reverse("core:list", kwargs={"id": test_list.id}))
    assert response.status_code == 200

    # Check that the empty message is shown
    assert (
        "No assets, resources, or captured fighters held." in response.content.decode()
    )


@pytest.mark.django_db
def test_list_building_mode_does_not_show_resources_assets(django_user_model):
    """Test that lists in list building mode don't show resources/assets card."""
    # Create test user
    user = django_user_model.objects.create_user(
        username="testuser3", password="testpass"
    )
    client = Client()
    client.login(username="testuser3", password="testpass")

    # Create test data
    house = ContentHouse.objects.create(name="Test House 3")

    # Create a list in list building mode
    test_list = List.objects.create(
        name="List Building Gang",
        content_house=house,
        owner=user,
        status=List.LIST_BUILDING,  # Not in campaign mode
    )

    # Test the view
    response = client.get(reverse("core:list", kwargs={"id": test_list.id}))
    assert response.status_code == 200

    # Check that resources/assets are not in context or are empty
    # The template may pass empty strings for these variables
    if "campaign_resources" in response.context:
        assert response.context["campaign_resources"] == ""
    if "held_assets" in response.context:
        assert response.context["held_assets"] == ""

    # Check that the card is not rendered
    assert "Assets &amp; Resources" not in response.content.decode()
