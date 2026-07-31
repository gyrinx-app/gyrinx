import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAction,
    CampaignAsset,
    CampaignAssetType,
    CampaignSubAsset,
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
def test_campaign_assets_view_sanitizes_descriptions():
    """Script tags in asset/asset-type descriptions must be stripped on render."""
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
        description='<script>alert("type")</script><p>Safe type text</p>',
        owner=user,
    )

    CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        description='<img src=x onerror="alert(1)"><p>Safe asset text</p>',
        owner=user,
    )

    response = client.get(reverse("core:campaign-assets", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()
    # Sanitised rich text drops the <script> wrapper and the onerror handler so
    # nothing executes; benign markup/text survives. (bleach keeps inert text
    # content, and the page has its own legitimate <script> tags, so assert
    # against the executable constructs rather than substrings like "alert".)
    assert "<script>alert" not in content
    assert "onerror" not in content
    assert "Safe type text" in content
    assert "Safe asset text" in content


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


@pytest.mark.django_db
def test_campaign_asset_detail_view():
    """The asset detail page shows description, properties, sub-assets and type text."""
    client = Client()
    user = User.objects.create_user(username="owner", password="pw")
    client.login(username="owner", password="pw")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        description="<p>Territory type blurb</p>",
        property_schema=[{"key": "boon", "label": "Boon"}],
        sub_asset_schema={
            "structure": {
                "label": "Structure",
                "label_plural": "Structures",
                "property_schema": [{"key": "benefit", "label": "Benefit"}],
            }
        },
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        description="<p>A toxic wasteland at the base of the hive.</p>",
        properties={"boon": "+D6 income"},
        owner=user,
    )
    CampaignSubAsset.objects.create(
        parent_asset=asset,
        sub_asset_type="structure",
        name="Generator Hall",
        properties={"benefit": "Free power"},
        owner=user,
    )

    response = client.get(
        reverse("core:campaign-asset-detail", args=[campaign.id, asset.id])
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "The Sump" in content
    assert "A toxic wasteland at the base of the hive." in content
    assert "Boon" in content
    assert "+D6 income" in content
    assert "Structures" in content
    assert "Generator Hall" in content
    assert "Free power" in content
    assert "Territory type blurb" in content
    # Owner sees the edit control on their own campaign's asset.
    assert reverse("core:campaign-asset-edit", args=[campaign.id, asset.id]) in content


@pytest.mark.django_db
def test_campaign_asset_detail_accessible_to_non_owner():
    """Any authenticated user can view the read-only page; edit controls are hidden."""
    owner = User.objects.create_user(username="owner", password="pw")
    User.objects.create_user(username="member", password="pw")

    campaign = Campaign.objects.create(name="Test Campaign", owner=owner, public=True)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=owner,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type, name="The Sump", owner=owner
    )

    client = Client()
    client.login(username="member", password="pw")
    response = client.get(
        reverse("core:campaign-asset-detail", args=[campaign.id, asset.id])
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "The Sump" in content
    # No owner-only edit control for a non-owner.
    assert (
        reverse("core:campaign-asset-edit", args=[campaign.id, asset.id]) not in content
    )


@pytest.mark.django_db
def test_campaign_asset_detail_404_for_other_campaign():
    """An asset belonging to a different campaign 404s under this campaign's URL."""
    user = User.objects.create_user(username="owner", password="pw")
    campaign_a = Campaign.objects.create(name="A", owner=user, public=True)
    campaign_b = Campaign.objects.create(name="B", owner=user, public=True)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign_b,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type, name="The Sump", owner=user
    )

    client = Client()
    client.login(username="owner", password="pw")
    response = client.get(
        reverse("core:campaign-asset-detail", args=[campaign_a.id, asset.id])
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_campaign_asset_detail_requires_login():
    """Anonymous users are redirected to login."""
    user = User.objects.create_user(username="owner", password="pw")
    campaign = Campaign.objects.create(name="Test", owner=user, public=True)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type, name="The Sump", owner=user
    )

    response = Client().get(
        reverse("core:campaign-asset-detail", args=[campaign.id, asset.id])
    )
    assert response.status_code == 302
    assert "login" in response.url


@pytest.mark.django_db
def test_campaign_dashboard_links_asset_name_and_previews_text():
    """The dashboard links each asset name to its detail page and previews text."""
    client = Client()
    user = User.objects.create_user(username="owner", password="pw")
    client.login(username="owner", password="pw")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        description="<p>A toxic wasteland.</p>",
        owner=user,
    )

    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "A toxic wasteland." in content
    assert (
        reverse("core:campaign-asset-detail", args=[campaign.id, asset.id]) in content
    )


@pytest.mark.django_db
def test_list_page_shows_asset_metadata(client, list_with_campaign, user):
    """The list page asset panel shows properties, sub-asset counts, text and a link."""
    campaign = list_with_campaign.campaign
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        property_schema=[{"key": "boon", "label": "Boon"}],
        sub_asset_schema={
            "structure": {"label": "Structure", "label_plural": "Structures"}
        },
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        description="<p>A toxic wasteland.</p>",
        properties={"boon": "+D6 income"},
        holder=list_with_campaign,
        owner=user,
    )
    CampaignSubAsset.objects.create(
        parent_asset=asset,
        sub_asset_type="structure",
        name="Generator Hall",
        owner=user,
    )

    client.force_login(user)
    response = client.get(reverse("core:list", args=[list_with_campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "The Sump" in content
    assert "Boon" in content
    assert "+D6 income" in content
    assert "1 Structures" in content
    assert "A toxic wasteland." in content
    assert (
        reverse("core:campaign-asset-detail", args=[campaign.id, asset.id]) in content
    )


@pytest.mark.django_db
def test_campaign_dashboard_details_link_hidden_for_anonymous():
    """The Details link (login-only page) is not shown to anonymous viewers."""
    user = User.objects.create_user(username="owner", password="pw")
    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        description="<p>A toxic wasteland.</p>",
        owner=user,
    )

    # Anonymous client viewing the public campaign dashboard.
    response = Client().get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()
    # Description preview is still visible...
    assert "A toxic wasteland." in content
    # ...but the login-only Details link is not offered.
    assert (
        reverse("core:campaign-asset-detail", args=[campaign.id, asset.id])
        not in content
    )


@pytest.mark.django_db
def test_campaign_asset_detail_shows_campaign_header():
    """The detail page carries the shared campaign header (name + link back)."""
    client = Client()
    user = User.objects.create_user(username="owner", password="pw")
    client.login(username="owner", password="pw")

    campaign = Campaign.objects.create(name="Ashmoot Campaign", owner=user, public=True)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type, name="The Sump", owner=user
    )

    response = client.get(
        reverse("core:campaign-asset-detail", args=[campaign.id, asset.id])
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Ashmoot Campaign" in content
    assert reverse("core:campaign", args=[campaign.id]) in content


@pytest.mark.django_db
def test_campaign_asset_detail_shows_sub_assets_missing_from_schema():
    """Sub-assets whose type left the schema still render (canonical page)."""
    client = Client()
    user = User.objects.create_user(username="owner", password="pw")
    client.login(username="owner", password="pw")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        sub_asset_schema={
            "structure": {"label": "Structure", "label_plural": "Structures"}
        },
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type, name="The Sump", owner=user
    )
    # In-schema and orphaned (schema no longer lists "outpost") sub-assets.
    CampaignSubAsset.objects.create(
        parent_asset=asset,
        sub_asset_type="structure",
        name="Generator Hall",
        owner=user,
    )
    CampaignSubAsset.objects.create(
        parent_asset=asset, sub_asset_type="outpost", name="Lost Bunker", owner=user
    )

    response = client.get(
        reverse("core:campaign-asset-detail", args=[campaign.id, asset.id])
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Generator Hall" in content
    # The orphaned sub-asset is not silently dropped.
    assert "Lost Bunker" in content


@pytest.mark.django_db
def test_campaign_dashboard_shows_held_by(content_house):
    """The dashboard shows the holder using the 'Held by X' pattern."""
    client = Client()
    user = User.objects.create_user(username="owner", password="pw")
    client.login(username="owner", password="pw")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)
    gang = List.objects.create(
        name="Iron Skulls", owner=user, content_house=content_house
    )
    campaign.lists.add(gang)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )
    CampaignAsset.objects.create(
        asset_type=asset_type, name="The Sump", holder=gang, owner=user
    )

    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Held by" in content
    assert "Iron Skulls" in content


@pytest.mark.django_db
def test_campaign_asset_detail_orders_description_after_structured_data():
    """On the detail page, properties/sub-assets come before the long description."""
    client = Client()
    user = User.objects.create_user(username="owner", password="pw")
    client.login(username="owner", password="pw")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        property_schema=[{"key": "boon", "label": "Boon"}],
        sub_asset_schema={
            "structure": {"label": "Structure", "label_plural": "Structures"}
        },
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        description="<p>A toxic wasteland.</p>",
        properties={"boon": "+D6 income"},
        owner=user,
    )
    CampaignSubAsset.objects.create(
        parent_asset=asset,
        sub_asset_type="structure",
        name="Generator Hall",
        owner=user,
    )

    response = client.get(
        reverse("core:campaign-asset-detail", args=[campaign.id, asset.id])
    )
    content = response.content.decode()
    assert content.index("Boon") < content.index("A toxic wasteland.")
    assert content.index("Generator Hall") < content.index("A toxic wasteland.")


@pytest.mark.django_db
def test_campaign_dashboard_orders_description_after_properties():
    """On the dashboard, an asset's properties come before its description."""
    client = Client()
    user = User.objects.create_user(username="owner", password="pw")
    client.login(username="owner", password="pw")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        property_schema=[{"key": "boon", "label": "Boon"}],
        owner=user,
    )
    CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        description="<p>A toxic wasteland.</p>",
        properties={"boon": "+D6 income"},
        owner=user,
    )

    response = client.get(reverse("core:campaign", args=[campaign.id]))
    content = response.content.decode()
    assert content.index("Boon") < content.index("A toxic wasteland.")


@pytest.mark.django_db
def test_campaign_asset_detail_breadcrumb_includes_type():
    """The breadcrumb shows the asset type (singular) as an intermediate crumb."""
    client = Client()
    user = User.objects.create_user(username="owner", password="pw")
    client.login(username="owner", password="pw")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)
    # Distinct singular/plural so counting the singular is unambiguous.
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Zone",
        name_plural="Districts",
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type, name="The Pit", owner=user
    )

    response = client.get(
        reverse("core:campaign-asset-detail", args=[campaign.id, asset.id])
    )
    content = response.content.decode()
    # Appears in the caps-label heading and, now, the breadcrumb crumb.
    assert content.count("Zone") >= 2


@pytest.fixture
def cloneable_asset(user, campaign):
    """An asset with a description, properties and two sub-assets."""
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        property_schema=[{"key": "boon", "label": "Boon"}],
        sub_asset_schema={
            "structure": {
                "label": "Structure",
                "label_plural": "Structures",
                "property_schema": [{"key": "benefit", "label": "Benefit"}],
            }
        },
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="Settlement",
        description="<p>A shanty town.</p>",
        properties={"boon": "+D6 income"},
        owner=user,
    )
    CampaignSubAsset.objects.create(
        parent_asset=asset,
        sub_asset_type="structure",
        name="Generator Hall",
        properties={"benefit": "Free power"},
        owner=user,
    )
    CampaignSubAsset.objects.create(
        parent_asset=asset,
        sub_asset_type="structure",
        name="Water Still",
        properties={"benefit": "Clean water"},
        owner=user,
    )
    return asset


@pytest.mark.django_db
def test_campaign_asset_clone_copies_content_and_sub_assets(
    client, user, campaign, cloneable_asset
):
    """Cloning under the same name leaves two identical assets side by side."""
    client.force_login(user)

    response = client.post(
        reverse("core:campaign-asset-clone", args=[campaign.id, cloneable_asset.id]),
        {"name": "Settlement"},
    )
    assert response.status_code == 302

    assets = CampaignAsset.objects.filter(
        asset_type=cloneable_asset.asset_type, name="Settlement"
    )
    assert assets.count() == 2

    clone = assets.exclude(pk=cloneable_asset.pk).get()
    assert clone.description == cloneable_asset.description
    assert clone.properties == {"boon": "+D6 income"}
    assert clone.owner == user

    # Sub-assets are copied onto the clone, not shared with the original.
    assert cloneable_asset.sub_assets.count() == 2
    clone_subs = clone.sub_assets.order_by("name")
    assert [s.name for s in clone_subs] == ["Generator Hall", "Water Still"]
    assert [s.sub_asset_type for s in clone_subs] == ["structure", "structure"]
    assert clone_subs[0].properties == {"benefit": "Free power"}
    assert set(clone_subs.values_list("pk", flat=True)).isdisjoint(
        cloneable_asset.sub_assets.values_list("pk", flat=True)
    )


@pytest.mark.django_db
def test_campaign_asset_clone_can_be_renamed(client, user, campaign, cloneable_asset):
    """The name is editable at clone time."""
    client.force_login(user)

    client.post(
        reverse("core:campaign-asset-clone", args=[campaign.id, cloneable_asset.id]),
        {"name": "Settlement (North)"},
    )

    clone = CampaignAsset.objects.get(name="Settlement (North)")
    assert clone.asset_type == cloneable_asset.asset_type
    assert clone.sub_assets.count() == 2


@pytest.mark.django_db
def test_campaign_asset_clone_does_not_copy_holder(
    client, user, campaign, cloneable_asset, list_with_campaign
):
    """A clone starts unowned even when the original is held."""
    cloneable_asset.holder = list_with_campaign
    cloneable_asset.save()

    client.force_login(user)
    client.post(
        reverse("core:campaign-asset-clone", args=[campaign.id, cloneable_asset.id]),
        {"name": "Settlement"},
    )

    clone = CampaignAsset.objects.exclude(pk=cloneable_asset.pk).get()
    assert clone.holder is None
    cloneable_asset.refresh_from_db()
    assert cloneable_asset.holder == list_with_campaign


@pytest.mark.django_db
def test_campaign_asset_clone_get_prefills_name(
    client, user, campaign, cloneable_asset
):
    """The confirmation page pre-fills the source name and mentions the sub-assets."""
    client.force_login(user)

    response = client.get(
        reverse("core:campaign-asset-clone", args=[campaign.id, cloneable_asset.id])
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert 'value="Settlement"' in content
    assert "2 sub-assets" in content
    # Nothing is created by merely viewing the page.
    assert CampaignAsset.objects.count() == 1


@pytest.mark.django_db
def test_campaign_asset_clone_records_campaign_action(
    client, user, campaign, cloneable_asset
):
    """Cloning in an in-progress campaign is recorded in the action log."""
    client.force_login(user)

    client.post(
        reverse("core:campaign-asset-clone", args=[campaign.id, cloneable_asset.id]),
        {"name": "Settlement"},
    )

    action = CampaignAction.objects.get(campaign=campaign)
    assert "Settlement" in action.description
    assert action.user == user


@pytest.mark.django_db
def test_campaign_asset_clone_requires_admin(
    client, make_user, campaign, cloneable_asset
):
    """A user who does not administer the campaign cannot clone its assets."""
    other = make_user("intruder", "pw")
    client.force_login(other)

    response = client.post(
        reverse("core:campaign-asset-clone", args=[campaign.id, cloneable_asset.id]),
        {"name": "Settlement"},
    )
    assert response.status_code == 404
    assert CampaignAsset.objects.count() == 1


@pytest.mark.django_db
def test_campaign_asset_clone_refused_for_archived_campaign(
    client, user, campaign, cloneable_asset
):
    """Archived campaigns are read-only."""
    campaign.archive()
    client.force_login(user)

    response = client.post(
        reverse("core:campaign-asset-clone", args=[campaign.id, cloneable_asset.id]),
        {"name": "Settlement"},
        follow=True,
    )
    assert response.status_code == 200
    assert CampaignAsset.objects.count() == 1


@pytest.mark.django_db
def test_campaign_assets_page_offers_clone(client, user, campaign, cloneable_asset):
    """The assets page links to the clone action for admins."""
    client.force_login(user)

    response = client.get(reverse("core:campaign-assets", args=[campaign.id]))
    assert (
        reverse("core:campaign-asset-clone", args=[campaign.id, cloneable_asset.id])
        in response.content.decode()
    )
