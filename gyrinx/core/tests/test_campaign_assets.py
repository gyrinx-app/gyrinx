import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAction,
    CampaignAsset,
    CampaignAssetType,
)
from gyrinx.core.models.list import List


@pytest.mark.django_db
def test_create_asset_type():
    """Test creating a campaign asset type."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        description="<p>Areas controlled by gangs</p>",
        owner=user,
    )

    assert asset_type.name_singular == "Territory"
    assert asset_type.name_plural == "Territories"
    assert str(asset_type) == "Test Campaign - Territory"


@pytest.mark.django_db
def test_create_asset():
    """Test creating a campaign asset."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )

    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        description="<p>A toxic wasteland</p>",
        owner=user,
    )

    assert asset.name == "The Sump"
    assert asset.holder is None
    assert str(asset) == "The Sump (Territory)"


@pytest.mark.django_db
def test_asset_transfer(content_house):
    """Test transferring an asset to a list."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    # Create a list
    gang_list = List.objects.create(
        name="Test Gang",
        owner=user,
        content_house=content_house,
    )
    campaign.lists.add(gang_list)

    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )

    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        owner=user,
    )

    # Transfer the asset
    asset.transfer_to(gang_list, user=user)

    # Check the asset is now held by the list
    asset.refresh_from_db()
    assert asset.holder == gang_list

    # Check that an action was logged
    action = CampaignAction.objects.last()
    assert action.campaign == campaign
    assert action.user == user
    assert (
        action.description
        == "Territory Transfer: The Sump transferred from no one to Test Gang"
    )
    assert action.dice_count == 0


@pytest.mark.django_db
def test_asset_transfer_between_lists(content_house):
    """Test transferring an asset between two lists."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    # Create two lists
    gang1 = List.objects.create(
        name="Gang One", owner=user, content_house=content_house
    )
    gang2 = List.objects.create(
        name="Gang Two", owner=user, content_house=content_house
    )
    campaign.lists.add(gang1, gang2)

    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Relic",
        name_plural="Relics",
        owner=user,
    )

    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="Ancient Artifact",
        holder=gang1,
        owner=user,
    )

    # Transfer the asset
    asset.transfer_to(gang2, user=user)

    # Check the transfer
    asset.refresh_from_db()
    assert asset.holder == gang2

    # Check the action log
    action = CampaignAction.objects.last()
    assert (
        action.description
        == "Relic Transfer: Ancient Artifact transferred from Gang One to Gang Two"
    )


@pytest.mark.django_db
def test_asset_transfer_requires_user():
    """Test that asset transfer requires a user."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )

    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        owner=user,
    )

    # Try to transfer without a user
    with pytest.raises(ValueError, match="User is required for asset transfers"):
        asset.transfer_to(None, user=None)


@pytest.mark.django_db
def test_campaign_assets_view():
    """Test the campaign assets management view."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    # Create asset type
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )

    # Create asset
    CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        owner=user,
    )

    # Test the assets view
    response = client.get(reverse("core:campaign-assets", args=[campaign.id]))
    assert response.status_code == 200
    assert "Territories" in response.content.decode()
    assert "The Sump" in response.content.decode()
    assert "Unowned" in response.content.decode()


@pytest.mark.django_db
def test_create_asset_type_view():
    """Test creating an asset type through the view."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    # Test creating an asset type
    response = client.post(
        reverse("core:campaign-asset-type-new", args=[campaign.id]),
        {
            "name_singular": "Territory",
            "name_plural": "Territories",
            "description": "<p>Areas controlled by gangs</p>",
        },
    )
    assert response.status_code == 302  # Redirect after creation

    # Check the asset type was created
    asset_type = CampaignAssetType.objects.get(campaign=campaign)
    assert asset_type.name_singular == "Territory"
    assert asset_type.name_plural == "Territories"


@pytest.mark.django_db
def test_create_asset_with_add_another():
    """Test creating an asset with the 'Create and Add Another' button."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )

    # Test creating an asset with "save_and_add_another"
    response = client.post(
        reverse("core:campaign-asset-new", args=[campaign.id, asset_type.id]),
        {
            "name": "The Sump",
            "description": "<p>A toxic wasteland</p>",
            "holder": "",
            "save_and_add_another": "Create and Add Another",
        },
    )

    # Should redirect back to the same form
    assert response.status_code == 302
    assert response.url == reverse(
        "core:campaign-asset-new", args=[campaign.id, asset_type.id]
    )

    # Check the asset was created
    asset = CampaignAsset.objects.get(name="The Sump")
    assert asset.asset_type == asset_type


@pytest.mark.django_db
def test_campaign_detail_shows_assets(content_house):
    """Test that the campaign detail view shows assets summary."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
    )

    # Create asset type and assets
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )

    CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        owner=user,
    )

    gang_list = List.objects.create(
        name="Test Gang", owner=user, content_house=content_house
    )
    campaign.lists.add(gang_list)

    CampaignAsset.objects.create(
        asset_type=asset_type,
        name="Old Ruins",
        holder=gang_list,
        owner=user,
    )

    # Test the campaign detail view
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200

    # Check that assets are shown in the table
    content = response.content.decode()
    assert "Territories" in content
    assert "The Sump" in content
    assert "Old Ruins" in content
    assert "Test Gang" in content
    assert "Unowned" in content


@pytest.mark.django_db
def test_campaign_asset_transfer_to_none(content_house):
    """Test transferring an asset to no one (unowned) through the view."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    # Create a gang list
    gang_list = List.objects.create(
        name="Test Gang",
        owner=user,
        content_house=content_house,
    )
    campaign.lists.add(gang_list)

    # Create asset type
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )

    # Create asset owned by the gang
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        holder=gang_list,
        owner=user,
    )

    # Transfer the asset to no one (unowned)
    response = client.post(
        reverse("core:campaign-asset-transfer", args=[campaign.id, asset.id]),
        {
            "new_holder": "",  # Empty means transfer to no one
        },
    )

    # Should redirect back to the assets page
    assert response.status_code == 302
    assert response.url == reverse("core:campaign-assets", args=[campaign.id])

    # Check the asset is now unowned
    asset.refresh_from_db()
    assert asset.holder is None

    # Check that a campaign action was logged
    action = CampaignAction.objects.last()
    assert action.campaign == campaign
    assert (
        action.description
        == "Territory Transfer: The Sump transferred from Test Gang to no one"
    )
