import pytest
from django.contrib.auth import get_user_model
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

User = get_user_model()


@pytest.mark.django_db
def test_list_view_shows_resources_and_assets_in_campaign_mode():
    """Test that the list view shows resources and assets when list is in campaign mode."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")
    
    # Create campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )
    
    # Create a list in campaign mode
    list_obj = List.objects.create(
        name="Test Gang",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )
    
    # Create resource types and resources
    resource_type1 = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Credits",
        description="Gang credits",
        default_amount=100,
        owner=user,
    )
    resource_type2 = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Reputation",
        description="Gang reputation",
        default_amount=5,
        owner=user,
    )
    
    # Create resources for the list
    CampaignListResource.objects.create(
        campaign=campaign,
        list=list_obj,
        resource_type=resource_type1,
        amount=150,
        owner=user,
    )
    CampaignListResource.objects.create(
        campaign=campaign,
        list=list_obj,
        resource_type=resource_type2,
        amount=10,
        owner=user,
    )
    
    # Create asset types and assets
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        description="Gang territories",
        owner=user,
    )
    
    asset1 = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        description="A toxic wasteland",
        holder=list_obj,
        owner=user,
    )
    asset2 = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="Trading Post",
        description="A bustling marketplace",
        holder=list_obj,
        owner=user,
    )
    
    # Login and access the list view
    client = Client()
    client.login(username="testuser", password="testpass")
    
    response = client.get(reverse("core:list", args=[list_obj.id]))
    assert response.status_code == 200
    
    # Check that resources are displayed
    assert b"Assets &amp; Resources" in response.content
    assert b"Credits" in response.content
    assert b"150" in response.content  # Credits amount
    assert b"Reputation" in response.content
    assert b"10" in response.content  # Reputation amount
    
    # Check that assets are displayed
    assert b"The Sump" in response.content
    assert b"Trading Post" in response.content
    assert b"Territory" in response.content
    
    # Check that links are present
    assert b"Modify" in response.content
    assert b"Transfer" in response.content


@pytest.mark.django_db
def test_list_view_does_not_show_resources_assets_for_non_campaign_lists():
    """Test that resources/assets panel is not shown for lists not in campaign mode."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")
    
    # Create a regular list (not in campaign mode)
    list_obj = List.objects.create(
        name="Test Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    
    # Login and access the list view
    client = Client()
    client.login(username="testuser", password="testpass")
    
    response = client.get(reverse("core:list", args=[list_obj.id]))
    assert response.status_code == 200
    
    # Check that resources/assets panel is not displayed
    assert b"Assets &amp; Resources" not in response.content


@pytest.mark.django_db
def test_list_view_shows_empty_state_when_no_resources_or_assets():
    """Test that empty state is shown when gang has no resources or assets."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")
    
    # Create campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )
    
    # Create a list in campaign mode but with no resources/assets
    list_obj = List.objects.create(
        name="Test Gang",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )
    
    # Login and access the list view
    client = Client()
    client.login(username="testuser", password="testpass")
    
    response = client.get(reverse("core:list", args=[list_obj.id]))
    assert response.status_code == 200
    
    # Check that the panel is displayed with empty state
    assert b"Assets &amp; Resources" in response.content
    assert b"No assets or resources held." in response.content