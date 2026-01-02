"""Tests for copying campaign assets and resources between campaigns."""

import pytest
from django.urls import reverse

from gyrinx.core.handlers.campaign_copy import (
    check_copy_conflicts,
    copy_campaign_content,
)
from gyrinx.core.models.campaign import (
    CampaignAsset,
    CampaignAssetType,
    CampaignResourceType,
    CampaignSubAsset,
)


# --- Handler Tests ---


@pytest.mark.django_db
def test_check_copy_conflicts_no_conflicts(user, make_campaign):
    """Test conflict detection when there are no conflicts."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    # Add asset type to source
    asset_type = CampaignAssetType.objects.create(
        campaign=source,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )

    # Add resource type to source
    CampaignResourceType.objects.create(
        campaign=source,
        owner=user,
        name="Meat",
        default_amount=10,
    )

    conflicts = check_copy_conflicts(
        source_campaign=source,
        target_campaign=target,
        asset_type_ids=[str(asset_type.id)],
        resource_type_ids=None,
    )

    assert not conflicts.has_conflicts
    assert conflicts.asset_type_conflicts == []
    assert conflicts.resource_type_conflicts == []


@pytest.mark.django_db
def test_check_copy_conflicts_with_asset_type_conflict(user, make_campaign):
    """Test conflict detection when asset type names match."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    # Add same asset type name to both campaigns
    source_type = CampaignAssetType.objects.create(
        campaign=source,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )
    CampaignAssetType.objects.create(
        campaign=target,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )

    conflicts = check_copy_conflicts(
        source_campaign=source,
        target_campaign=target,
        asset_type_ids=[str(source_type.id)],
        resource_type_ids=None,
    )

    assert conflicts.has_conflicts
    assert conflicts.asset_type_conflicts == ["Territory"]


@pytest.mark.django_db
def test_check_copy_conflicts_with_resource_type_conflict(user, make_campaign):
    """Test conflict detection when resource type names match."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    # Add same resource type name to both campaigns
    source_type = CampaignResourceType.objects.create(
        campaign=source,
        owner=user,
        name="Meat",
        default_amount=10,
    )
    CampaignResourceType.objects.create(
        campaign=target,
        owner=user,
        name="Meat",
        default_amount=5,
    )

    conflicts = check_copy_conflicts(
        source_campaign=source,
        target_campaign=target,
        asset_type_ids=None,
        resource_type_ids=[str(source_type.id)],
    )

    assert conflicts.has_conflicts
    assert conflicts.resource_type_conflicts == ["Meat"]


@pytest.mark.django_db
def test_copy_campaign_content_copies_asset_types(user, make_campaign):
    """Test that asset types are copied correctly."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    # Create asset type with schema
    asset_type = CampaignAssetType.objects.create(
        campaign=source,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
        description="A piece of land to control",
        property_schema=[{"key": "boon", "label": "Boon"}],
        sub_asset_schema={
            "structure": {
                "label": "Structure",
                "label_plural": "Structures",
                "property_schema": [{"key": "benefit", "label": "Benefit"}],
            }
        },
    )

    result = copy_campaign_content(
        source_campaign=source,
        target_campaign=target,
        user=user,
        asset_type_ids=[str(asset_type.id)],
        resource_type_ids=None,
    )

    assert result.asset_types_copied == 1
    assert result.assets_copied == 0

    # Verify the copied asset type
    copied_type = target.asset_types.get()
    assert copied_type.name_singular == "Territory"
    assert copied_type.name_plural == "Territories"
    assert copied_type.description == "A piece of land to control"
    assert copied_type.property_schema == [{"key": "boon", "label": "Boon"}]
    assert "structure" in copied_type.sub_asset_schema


@pytest.mark.django_db
def test_copy_campaign_content_copies_assets_with_properties(user, make_campaign):
    """Test that assets and their properties are copied."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    # Create asset type with asset
    asset_type = CampaignAssetType.objects.create(
        campaign=source,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
        property_schema=[{"key": "income", "label": "Income"}],
    )
    CampaignAsset.objects.create(
        asset_type=asset_type,
        owner=user,
        name="The Sump",
        description="A murky place",
        properties={"income": "D6x10"},
    )

    result = copy_campaign_content(
        source_campaign=source,
        target_campaign=target,
        user=user,
        asset_type_ids=[str(asset_type.id)],
        resource_type_ids=None,
    )

    assert result.asset_types_copied == 1
    assert result.assets_copied == 1

    # Verify the copied asset
    copied_type = target.asset_types.get()
    copied_asset = copied_type.assets.get()
    assert copied_asset.name == "The Sump"
    assert copied_asset.description == "A murky place"
    assert copied_asset.properties == {"income": "D6x10"}
    assert copied_asset.holder is None  # Holder should not be copied


@pytest.mark.django_db
def test_copy_campaign_content_copies_sub_assets(user, make_campaign):
    """Test that sub-assets are copied along with assets."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    # Create asset type with sub-asset schema
    asset_type = CampaignAssetType.objects.create(
        campaign=source,
        owner=user,
        name_singular="Settlement",
        name_plural="Settlements",
        sub_asset_schema={
            "structure": {
                "label": "Structure",
                "label_plural": "Structures",
                "property_schema": [{"key": "benefit", "label": "Benefit"}],
            }
        },
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        owner=user,
        name="Dust Falls",
    )
    CampaignSubAsset.objects.create(
        parent_asset=asset,
        owner=user,
        sub_asset_type="structure",
        name="Generator Hall",
        properties={"benefit": "+D6 power"},
    )

    result = copy_campaign_content(
        source_campaign=source,
        target_campaign=target,
        user=user,
        asset_type_ids=[str(asset_type.id)],
        resource_type_ids=None,
    )

    assert result.asset_types_copied == 1
    assert result.assets_copied == 1
    assert result.sub_assets_copied == 1

    # Verify the copied sub-asset
    copied_asset = target.asset_types.get().assets.get()
    copied_sub_asset = copied_asset.sub_assets.get()
    assert copied_sub_asset.name == "Generator Hall"
    assert copied_sub_asset.sub_asset_type == "structure"
    assert copied_sub_asset.properties == {"benefit": "+D6 power"}


@pytest.mark.django_db
def test_copy_campaign_content_copies_resource_types(user, make_campaign):
    """Test that resource types are copied correctly."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    resource_type = CampaignResourceType.objects.create(
        campaign=source,
        owner=user,
        name="Meat",
        description="Food for the gang",
        default_amount=10,
    )

    result = copy_campaign_content(
        source_campaign=source,
        target_campaign=target,
        user=user,
        asset_type_ids=None,
        resource_type_ids=[str(resource_type.id)],
    )

    assert result.resource_types_copied == 1

    # Verify the copied resource type
    copied_type = target.resource_types.get()
    assert copied_type.name == "Meat"
    assert copied_type.description == "Food for the gang"
    assert copied_type.default_amount == 10


@pytest.mark.django_db
def test_copy_campaign_content_skips_conflicts(user, make_campaign):
    """Test that conflicting items are skipped during copy."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    # Create non-conflicting asset type in source
    source_type1 = CampaignAssetType.objects.create(
        campaign=source,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )

    # Create conflicting asset type in both
    source_type2 = CampaignAssetType.objects.create(
        campaign=source,
        owner=user,
        name_singular="Relic",
        name_plural="Relics",
    )
    CampaignAssetType.objects.create(
        campaign=target,
        owner=user,
        name_singular="Relic",
        name_plural="Relics",
    )

    # Copy both explicitly - Relic should be skipped
    result = copy_campaign_content(
        source_campaign=source,
        target_campaign=target,
        user=user,
        asset_type_ids=[str(source_type1.id), str(source_type2.id)],
        resource_type_ids=None,
    )

    # Territory copied, Relic skipped
    assert result.asset_types_copied == 1
    assert target.asset_types.count() == 2  # Original Relic + copied Territory


@pytest.mark.django_db
def test_copy_campaign_content_empty_selection(user, make_campaign):
    """Test that nothing is copied when no IDs are provided."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    CampaignAssetType.objects.create(
        campaign=source,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )

    result = copy_campaign_content(
        source_campaign=source,
        target_campaign=target,
        user=user,
        asset_type_ids=None,
        resource_type_ids=None,
    )

    assert result.total_copied == 0
    assert target.asset_types.count() == 0


# --- View Tests ---


@pytest.mark.django_db
def test_campaign_copy_from_view_requires_owner(client, user, make_campaign):
    """Test that copy-from view requires campaign ownership."""
    other_user = type(user).objects.create_user(
        username="other", email="other@example.com", password="test123"
    )
    campaign = make_campaign("Test Campaign")
    campaign.owner = other_user
    campaign.save()

    client.force_login(user)
    response = client.get(reverse("core:campaign-copy-in", args=[campaign.id]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_campaign_copy_to_view_requires_ownership_or_public(
    client, user, make_campaign
):
    """Test that copy-to view requires ownership or public campaign."""
    from gyrinx.core.models.campaign import Campaign

    other_user = type(user).objects.create_user(
        username="other", email="other@example.com", password="test123"
    )
    # Create campaign directly owned by other_user (not using make_campaign)
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=other_user,
        public=False,
    )
    # User needs a campaign to copy TO
    make_campaign("User's Campaign")

    client.force_login(user)

    # Private campaign owned by someone else should 404
    response = client.get(reverse("core:campaign-copy-out", args=[campaign.id]))
    assert response.status_code == 404

    # Public campaign owned by someone else should be accessible
    campaign.public = True
    campaign.save()
    # Add content so it doesn't redirect
    CampaignAssetType.objects.create(
        campaign=campaign,
        owner=other_user,
        name_singular="Territory",
        name_plural="Territories",
    )
    response = client.get(reverse("core:campaign-copy-out", args=[campaign.id]))
    assert response.status_code == 200


@pytest.mark.django_db
def test_campaign_copy_from_view_redirects_if_archived(client, user, make_campaign):
    """Test that copy-from redirects if campaign is archived."""
    campaign = make_campaign("Test Campaign")
    campaign.archived = True
    campaign.save()

    client.force_login(user)
    response = client.get(reverse("core:campaign-copy-in", args=[campaign.id]))

    assert response.status_code == 302


@pytest.mark.django_db
def test_campaign_copy_from_view_redirects_if_no_other_campaigns(
    client, user, make_campaign
):
    """Test that copy-from redirects if user has no other campaigns."""
    campaign = make_campaign("Test Campaign")

    client.force_login(user)
    response = client.get(reverse("core:campaign-copy-in", args=[campaign.id]))

    assert response.status_code == 302


@pytest.mark.django_db
def test_campaign_copy_to_view_redirects_if_no_content(client, user, make_campaign):
    """Test that copy-to redirects if source campaign has no content."""
    campaign = make_campaign("Test Campaign")
    make_campaign("Other Campaign")  # Need another campaign

    client.force_login(user)
    response = client.get(reverse("core:campaign-copy-out", args=[campaign.id]))

    assert response.status_code == 302


@pytest.mark.django_db
def test_campaign_copy_to_view_shows_form_when_content_exists(
    client, user, make_campaign
):
    """Test that copy-to shows form when source has content."""
    source = make_campaign("Source Campaign")
    make_campaign("Target Campaign")

    # Add asset type to source
    CampaignAssetType.objects.create(
        campaign=source,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )

    client.force_login(user)
    response = client.get(reverse("core:campaign-copy-out", args=[source.id]))

    assert response.status_code == 200
    assert b"Copy To Another Campaign" in response.content


@pytest.mark.django_db
def test_campaign_copy_from_view_shows_form_when_other_campaigns_exist(
    client, user, make_campaign
):
    """Test that copy-from shows form when user has other campaigns."""
    target = make_campaign("Target Campaign")
    source = make_campaign("Source Campaign")

    # Add content to source so it's worth copying
    CampaignAssetType.objects.create(
        campaign=source,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )

    client.force_login(user)
    response = client.get(reverse("core:campaign-copy-in", args=[target.id]))

    assert response.status_code == 200
    assert b"Copy From Another Campaign" in response.content


# --- Model Tests ---


@pytest.mark.django_db
def test_campaign_is_admin_returns_true_for_owner(user, make_campaign):
    """Test that is_admin returns True for campaign owner."""
    campaign = make_campaign("Test Campaign")
    assert campaign.is_admin(user) is True


@pytest.mark.django_db
def test_campaign_is_admin_returns_false_for_non_owner(user, make_campaign):
    """Test that is_admin returns False for non-owner."""
    other_user = type(user).objects.create_user(
        username="other", email="other@example.com", password="test123"
    )
    campaign = make_campaign("Test Campaign")
    assert campaign.is_admin(other_user) is False


# --- Race Condition Tests ---


@pytest.mark.django_db
def test_campaign_copy_to_rejects_archived_target_on_confirm(
    client, user, make_campaign
):
    """Test that copy-to rejects if target campaign becomes archived before confirm."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    # Add asset type to source
    asset_type = CampaignAssetType.objects.create(
        campaign=source,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )

    client.force_login(user)

    # Simulate confirm action with a target that has been archived
    target.archived = True
    target.save()

    response = client.post(
        reverse("core:campaign-copy-out", args=[source.id]),
        {
            "action": "confirm",
            "target_campaign_id": str(target.id),
            "selected_asset_types": [str(asset_type.id)],
        },
    )

    # Should redirect back to source campaign with error
    assert response.status_code == 302
    assert f"/campaign/{source.id}" in response.url


@pytest.mark.django_db
def test_campaign_copy_from_rejects_archived_source_on_confirm(
    client, user, make_campaign
):
    """Test that copy-from rejects if source campaign becomes archived before confirm."""
    target = make_campaign("Target Campaign")
    source = make_campaign("Source Campaign")

    # Add asset type to source
    asset_type = CampaignAssetType.objects.create(
        campaign=source,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )

    client.force_login(user)

    # Simulate confirm action with a source that has been archived
    source.archived = True
    source.save()

    response = client.post(
        reverse("core:campaign-copy-in", args=[target.id]),
        {
            "action": "confirm",
            "source_campaign_id": str(source.id),
            "selected_asset_types": [str(asset_type.id)],
        },
    )

    # Should redirect back to target campaign with error
    assert response.status_code == 302
    assert f"/campaign/{target.id}" in response.url
