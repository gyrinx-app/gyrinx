"""Tests for copying campaign assets and resources between campaigns."""

import pytest
from django.urls import reverse

from gyrinx.core.handlers.campaign_copy import (
    apply_campaign_template,
    check_copy_conflicts,
    copy_campaign_content,
    describe_campaign_contents,
)
from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAsset,
    CampaignAssetType,
    CampaignAttributeType,
    CampaignAttributeValue,
    CampaignResourceType,
    CampaignSubAsset,
)
from gyrinx.core.models.pack import CustomContentPack


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
    assert b"Copy to another Campaign" in response.content


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
    assert b"Copy from another Campaign" in response.content


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


# --- Template Campaign Tests ---


@pytest.mark.django_db
def test_campaign_copy_from_template_preview(client, user, make_campaign, make_user):
    """Test that copy-from allows selecting a template campaign as the source."""
    target = make_campaign("Target Campaign")

    # Create a template campaign owned by a different user
    admin_user = make_user("admin", "password")
    template = Campaign.objects.create(
        name="Dominion Template",
        owner=admin_user,
        template=True,
    )
    asset_type = CampaignAssetType.objects.create(
        campaign=template,
        owner=admin_user,
        name_singular="Territory",
        name_plural="Territories",
    )

    client.force_login(user)

    # POST to select the template as the source campaign (preview step)
    response = client.post(
        reverse("core:campaign-copy-in", args=[target.id]),
        {
            "action": "preview",
            "source_campaign": str(template.id),
            "asset_types": [str(asset_type.id)],
        },
    )

    # Should show the confirmation page (200), not a 404
    assert response.status_code == 200


@pytest.mark.django_db
def test_campaign_copy_from_template_confirm(client, user, make_campaign, make_user):
    """Test that copy-from confirm works with a template campaign as the source."""
    target = make_campaign("Target Campaign")

    # Create a template campaign owned by a different user
    admin_user = make_user("admin", "password")
    template = Campaign.objects.create(
        name="Dominion Template",
        owner=admin_user,
        template=True,
    )
    asset_type = CampaignAssetType.objects.create(
        campaign=template,
        owner=admin_user,
        name_singular="Territory",
        name_plural="Territories",
    )
    CampaignAsset.objects.create(
        asset_type=asset_type,
        owner=admin_user,
        name="The Sump",
        description="A murky place",
    )

    client.force_login(user)

    # POST to confirm copying from the template
    response = client.post(
        reverse("core:campaign-copy-in", args=[target.id]),
        {
            "action": "confirm",
            "source_campaign_id": str(template.id),
            "selected_asset_types": [str(asset_type.id)],
        },
    )

    # Should redirect to the target campaign after successful copy
    assert response.status_code == 302
    assert f"/campaign/{target.id}" in response.url

    # Verify the content was actually copied
    assert target.asset_types.count() == 1
    copied_type = target.asset_types.get()
    assert copied_type.name_singular == "Territory"
    assert copied_type.assets.count() == 1
    assert copied_type.assets.get().name == "The Sump"


@pytest.mark.django_db
def test_campaign_copy_from_accessible_with_only_templates(
    client, user, make_campaign, make_user
):
    """Test that copy-from page is accessible when user has no other campaigns but templates exist."""
    target = make_campaign("Target Campaign")

    # Create a template campaign (owned by someone else)
    admin_user = make_user("admin", "password")
    Campaign.objects.create(
        name="Dominion Template",
        owner=admin_user,
        template=True,
    )

    client.force_login(user)

    # GET the copy-from page - should show the form (200), not redirect (302)
    response = client.get(reverse("core:campaign-copy-in", args=[target.id]))

    assert response.status_code == 200


# --- Attribute Type Copy Tests ---


@pytest.mark.django_db
def test_copy_attribute_types_with_values(user, make_campaign):
    """Test that attribute types and their values are copied correctly."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    attr_type = CampaignAttributeType.objects.create(
        campaign=source,
        owner=user,
        name="Faction",
        description="Choose your faction",
        is_single_select=True,
    )
    CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        owner=user,
        name="Order",
        description="Forces of Order",
        colour="#0000FF",
    )
    CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        owner=user,
        name="Chaos",
        description="Forces of Chaos",
        colour="#FF0000",
    )

    result = copy_campaign_content(
        source_campaign=source,
        target_campaign=target,
        user=user,
        attribute_type_ids=[str(attr_type.id)],
    )

    assert result.attribute_types_copied == 1
    assert result.attribute_values_copied == 2

    # Verify the copied attribute type
    copied_type = target.attribute_types.get()
    assert copied_type.name == "Faction"
    assert copied_type.description == "Choose your faction"
    assert copied_type.is_single_select is True

    # Verify values
    values = copied_type.values.order_by("name")
    assert values.count() == 2
    assert values[0].name == "Chaos"
    assert values[0].colour == "#FF0000"
    assert values[1].name == "Order"
    assert values[1].colour == "#0000FF"


@pytest.mark.django_db
def test_copy_attribute_type_conflict_detection(user, make_campaign):
    """Test that attribute type name conflicts are detected."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    source_type = CampaignAttributeType.objects.create(
        campaign=source,
        owner=user,
        name="Faction",
    )
    CampaignAttributeType.objects.create(
        campaign=target,
        owner=user,
        name="Faction",
    )

    conflicts = check_copy_conflicts(
        source_campaign=source,
        target_campaign=target,
        attribute_type_ids=[str(source_type.id)],
    )

    assert conflicts.has_conflicts
    assert conflicts.attribute_type_conflicts == ["Faction"]


@pytest.mark.django_db
def test_copy_attribute_type_conflict_skipped(user, make_campaign):
    """Test that conflicting attribute types are skipped during copy."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    # Create non-conflicting type
    source_type1 = CampaignAttributeType.objects.create(
        campaign=source,
        owner=user,
        name="Alliance",
    )

    # Create conflicting type
    source_type2 = CampaignAttributeType.objects.create(
        campaign=source,
        owner=user,
        name="Faction",
    )
    CampaignAttributeType.objects.create(
        campaign=target,
        owner=user,
        name="Faction",
    )

    result = copy_campaign_content(
        source_campaign=source,
        target_campaign=target,
        user=user,
        attribute_type_ids=[str(source_type1.id), str(source_type2.id)],
    )

    # Alliance copied, Faction skipped
    assert result.attribute_types_copied == 1
    assert target.attribute_types.count() == 2  # Original Faction + copied Alliance


@pytest.mark.django_db
def test_copy_attribute_type_without_values(user, make_campaign):
    """Test that attribute types with no values copy correctly."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    attr_type = CampaignAttributeType.objects.create(
        campaign=source,
        owner=user,
        name="Team",
        description="Assign teams later",
        is_single_select=False,
    )

    result = copy_campaign_content(
        source_campaign=source,
        target_campaign=target,
        user=user,
        attribute_type_ids=[str(attr_type.id)],
    )

    assert result.attribute_types_copied == 1
    assert result.attribute_values_copied == 0

    copied_type = target.attribute_types.get()
    assert copied_type.name == "Team"
    assert copied_type.is_single_select is False
    assert copied_type.values.count() == 0


@pytest.mark.django_db
def test_copy_from_view_with_attribute_types(client, user, make_campaign):
    """Integration test for copy-from view with attribute types."""
    target = make_campaign("Target Campaign")
    source = make_campaign("Source Campaign")

    attr_type = CampaignAttributeType.objects.create(
        campaign=source,
        owner=user,
        name="Faction",
    )
    CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        owner=user,
        name="Order",
    )

    client.force_login(user)

    # Preview step
    response = client.post(
        reverse("core:campaign-copy-in", args=[target.id]),
        {
            "action": "preview",
            "source_campaign": str(source.id),
            "attribute_types": [str(attr_type.id)],
        },
    )
    assert response.status_code == 200

    # Confirm step
    response = client.post(
        reverse("core:campaign-copy-in", args=[target.id]),
        {
            "action": "confirm",
            "source_campaign_id": str(source.id),
            "selected_attribute_types": [str(attr_type.id)],
        },
    )
    assert response.status_code == 302
    assert target.attribute_types.count() == 1
    assert target.attribute_types.get().values.count() == 1


@pytest.mark.django_db
def test_copy_to_view_with_attribute_types(client, user, make_campaign):
    """Integration test for copy-to view with attribute types."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    attr_type = CampaignAttributeType.objects.create(
        campaign=source,
        owner=user,
        name="Faction",
    )
    CampaignAttributeValue.objects.create(
        attribute_type=attr_type,
        owner=user,
        name="Chaos",
    )

    client.force_login(user)

    # Preview step
    response = client.post(
        reverse("core:campaign-copy-out", args=[source.id]),
        {
            "action": "preview",
            "target_campaign": str(target.id),
            "attribute_types": [str(attr_type.id)],
        },
    )
    assert response.status_code == 200

    # Confirm step
    response = client.post(
        reverse("core:campaign-copy-out", args=[source.id]),
        {
            "action": "confirm",
            "target_campaign_id": str(target.id),
            "selected_attribute_types": [str(attr_type.id)],
        },
    )
    assert response.status_code == 302
    assert target.attribute_types.count() == 1
    assert target.attribute_types.get().values.count() == 1


# --- Pack Copy Tests ---


@pytest.mark.django_db
def test_copy_packs_between_campaigns(user, make_campaign):
    """Test that packs are copied by reference (M2M add) between campaigns."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    pack1 = CustomContentPack.objects.create(name="Pack Alpha", owner=user, listed=True)
    pack2 = CustomContentPack.objects.create(name="Pack Beta", owner=user, listed=True)
    source.packs.add(pack1, pack2)

    result = copy_campaign_content(
        source_campaign=source,
        target_campaign=target,
        user=user,
        pack_ids=[str(pack1.id), str(pack2.id)],
    )

    assert result.packs_copied == 2
    assert set(target.packs.values_list("id", flat=True)) == {pack1.id, pack2.id}


@pytest.mark.django_db
def test_copy_packs_skips_already_existing(user, make_campaign):
    """Test that packs already in the target campaign are not duplicated."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    pack = CustomContentPack.objects.create(name="Pack Alpha", owner=user, listed=True)
    source.packs.add(pack)
    target.packs.add(pack)  # Already exists in target

    result = copy_campaign_content(
        source_campaign=source,
        target_campaign=target,
        user=user,
        pack_ids=[str(pack.id)],
    )

    assert result.packs_copied == 0
    assert target.packs.count() == 1


@pytest.mark.django_db
def test_copy_packs_no_conflict_check_needed(user, make_campaign):
    """Test that check_copy_conflicts ignores packs (no conflict detection needed)."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    pack = CustomContentPack.objects.create(name="Pack Alpha", owner=user, listed=True)
    source.packs.add(pack)
    target.packs.add(pack)

    conflicts = check_copy_conflicts(
        source_campaign=source,
        target_campaign=target,
        pack_ids=[str(pack.id)],
    )

    # Packs don't generate conflicts
    assert not conflicts.has_conflicts


@pytest.mark.django_db
def test_copy_packs_included_in_total(user, make_campaign):
    """Test that packs_copied is included in total_copied."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    pack = CustomContentPack.objects.create(name="Pack Alpha", owner=user, listed=True)
    source.packs.add(pack)

    result = copy_campaign_content(
        source_campaign=source,
        target_campaign=target,
        user=user,
        pack_ids=[str(pack.id)],
    )

    assert result.packs_copied == 1
    assert result.total_copied == 1


@pytest.mark.django_db
def test_copy_from_view_with_packs(client, user, make_campaign):
    """Integration test for copy-from view with packs."""
    target = make_campaign("Target Campaign")
    source = make_campaign("Source Campaign")

    pack = CustomContentPack.objects.create(name="Pack Alpha", owner=user, listed=True)
    source.packs.add(pack)

    client.force_login(user)

    # Preview step
    response = client.post(
        reverse("core:campaign-copy-in", args=[target.id]),
        {
            "action": "preview",
            "source_campaign": str(source.id),
            "packs": [str(pack.id)],
        },
    )
    assert response.status_code == 200

    # Confirm step
    response = client.post(
        reverse("core:campaign-copy-in", args=[target.id]),
        {
            "action": "confirm",
            "source_campaign_id": str(source.id),
            "selected_packs": [str(pack.id)],
        },
    )
    assert response.status_code == 302
    assert target.packs.count() == 1
    assert target.packs.get().name == "Pack Alpha"


@pytest.mark.django_db
def test_copy_to_view_with_packs(client, user, make_campaign):
    """Integration test for copy-to view with packs."""
    source = make_campaign("Source Campaign")
    target = make_campaign("Target Campaign")

    pack = CustomContentPack.objects.create(name="Pack Beta", owner=user, listed=True)
    source.packs.add(pack)

    client.force_login(user)

    # Preview step
    response = client.post(
        reverse("core:campaign-copy-out", args=[source.id]),
        {
            "action": "preview",
            "target_campaign": str(target.id),
            "packs": [str(pack.id)],
        },
    )
    assert response.status_code == 200

    # Confirm step
    response = client.post(
        reverse("core:campaign-copy-out", args=[source.id]),
        {
            "action": "confirm",
            "target_campaign_id": str(target.id),
            "selected_packs": [str(pack.id)],
        },
    )
    assert response.status_code == 302
    assert target.packs.count() == 1
    assert target.packs.get().name == "Pack Beta"


# --- Starting a new Campaign from a template ---


@pytest.fixture
def template_campaign(user, make_campaign):
    """A template campaign with one of everything worth copying."""
    template = make_campaign(
        "Ash Wastes Starter",
        template=True,
        budget=1000,
        default_included_crew_categories=["CREW"],
    )
    asset_type = CampaignAssetType.objects.create(
        campaign=template,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        owner=user,
        name="Slag Furnace",
    )
    CampaignSubAsset.objects.create(
        parent_asset=asset,
        owner=user,
        sub_asset_type="crew",
        name="Furnace Crew",
    )
    CampaignResourceType.objects.create(
        campaign=template,
        owner=user,
        name="Meat",
        default_amount=4,
    )
    attribute_type = CampaignAttributeType.objects.create(
        campaign=template,
        owner=user,
        name="Alliance",
    )
    CampaignAttributeValue.objects.create(
        attribute_type=attribute_type,
        owner=user,
        name="Guild",
    )
    template.packs.add(
        CustomContentPack.objects.create(name="Pack Alpha", owner=user, listed=True)
    )
    return template


@pytest.mark.django_db
def test_new_campaign_from_template_copies_everything(client, user, template_campaign):
    """Creating from a template copies assets, resources, attributes and packs."""
    client.force_login(user)

    response = client.post(
        reverse("core:campaigns-new") + f"?template={template_campaign.id}",
        {"name": "My Ash Wastes", "summary": "", "narrative": "", "budget": 1000},
    )
    assert response.status_code == 302

    campaign = Campaign.objects.get(name="My Ash Wastes")
    assert response.url == reverse("core:campaign", args=(campaign.id,))

    asset_type = campaign.asset_types.get()
    assert asset_type.name_plural == "Territories"
    asset = asset_type.assets.get()
    assert asset.name == "Slag Furnace"
    assert asset.sub_assets.get().name == "Furnace Crew"

    assert campaign.resource_types.get(name="Meat").default_amount == 4
    attribute_type = campaign.attribute_types.get()
    assert attribute_type.name == "Alliance"
    assert attribute_type.values.get().name == "Guild"
    assert campaign.packs.get().name == "Pack Alpha"

    # The template is untouched — this is a copy, not a move.
    assert template_campaign.asset_types.count() == 1


@pytest.mark.django_db
def test_new_campaign_from_template_copies_crew_categories(
    client, user, template_campaign
):
    """Crew category defaults come across; they have no field on the form."""
    client.force_login(user)

    client.post(
        reverse("core:campaigns-new") + f"?template={template_campaign.id}",
        {"name": "Crewed Up", "summary": "", "narrative": "", "budget": 1000},
    )

    campaign = Campaign.objects.get(name="Crewed Up")
    assert campaign.default_included_crew_categories == ["CREW"]


@pytest.mark.django_db
def test_new_campaign_form_prefills_budget_from_template(
    client, user, template_campaign
):
    """The template's budget is a starting point the user can still override."""
    client.force_login(user)

    response = client.get(
        reverse("core:campaigns-new") + f"?template={template_campaign.id}"
    )
    assert response.status_code == 200
    assert response.context["form"].initial["budget"] == 1000
    assert response.context["template_campaign"] == template_campaign
    assert "Ash Wastes Starter" in response.content.decode()

    # Whatever the user submits wins over the template.
    client.post(
        reverse("core:campaigns-new") + f"?template={template_campaign.id}",
        {"name": "Richer Gangs", "summary": "", "narrative": "", "budget": 2000},
    )
    assert Campaign.objects.get(name="Richer Gangs").budget == 2000


@pytest.mark.django_db
def test_new_campaign_from_template_keeps_template_reputation(
    client, user, template_campaign
):
    """A template's own Reputation survives instead of being replaced by the default."""
    CampaignResourceType.objects.create(
        campaign=template_campaign,
        owner=user,
        name="Reputation",
        description="Standing among the wastelanders",
        default_amount=5,
    )
    client.force_login(user)

    client.post(
        reverse("core:campaigns-new") + f"?template={template_campaign.id}",
        {"name": "Reputable", "summary": "", "narrative": "", "budget": 1000},
    )

    campaign = Campaign.objects.get(name="Reputable")
    reputation = campaign.resource_types.get(name="Reputation")
    assert reputation.default_amount == 5
    assert reputation.description == "Standing among the wastelanders"
    assert campaign.resource_types.filter(name__iexact="Reputation").count() == 1


@pytest.mark.django_db
def test_new_campaign_from_template_without_reputation_gets_the_default(
    client, user, template_campaign
):
    """Templates that don't define Reputation still get the standard one."""
    client.force_login(user)

    client.post(
        reverse("core:campaigns-new") + f"?template={template_campaign.id}",
        {"name": "Standard Rep", "summary": "", "narrative": "", "budget": 1000},
    )

    campaign = Campaign.objects.get(name="Standard Rep")
    assert campaign.resource_types.get(name="Reputation").default_amount == 1


@pytest.mark.django_db
def test_new_campaign_without_template_is_unchanged(client, user):
    """The plain create flow still produces exactly one Reputation and nothing else."""
    client.force_login(user)

    client.post(
        reverse("core:campaigns-new"),
        {"name": "From Scratch", "summary": "", "narrative": "", "budget": 1500},
    )

    campaign = Campaign.objects.get(name="From Scratch")
    assert campaign.resource_types.get().name == "Reputation"
    assert not campaign.asset_types.exists()
    assert campaign.budget == 1500


@pytest.mark.django_db
def test_new_campaign_rejects_a_campaign_that_is_not_a_template(
    client, user, make_campaign
):
    """?template= only accepts campaigns actually marked as templates."""
    not_a_template = make_campaign("Just a Campaign")
    client.force_login(user)

    response = client.get(
        reverse("core:campaigns-new") + f"?template={not_a_template.id}"
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_new_campaign_rejects_archived_and_malformed_templates(
    client, user, template_campaign
):
    template_campaign.archived = True
    template_campaign.save()
    client.force_login(user)

    assert (
        client.get(
            reverse("core:campaigns-new") + f"?template={template_campaign.id}"
        ).status_code
        == 404
    )
    assert (
        client.get(reverse("core:campaigns-new") + "?template=not-a-uuid").status_code
        == 404
    )


@pytest.mark.django_db
def test_template_owned_by_another_user_can_be_used(
    client, make_user, template_campaign
):
    """Templates are offered to everyone — that is what marking one is for."""
    other = make_user("otheruser", "password")
    client.force_login(other)

    response = client.post(
        reverse("core:campaigns-new") + f"?template={template_campaign.id}",
        {"name": "Borrowed", "summary": "", "narrative": "", "budget": 1000},
    )
    assert response.status_code == 302

    campaign = Campaign.objects.get(name="Borrowed")
    assert campaign.owner == other
    assert campaign.asset_types.get().name_plural == "Territories"


@pytest.mark.django_db
def test_campaign_page_offers_the_template_button(client, user, template_campaign):
    """The button appears on a template campaign and not on an ordinary one."""
    client.force_login(user)
    use_url = reverse("core:campaigns-new") + f"?template={template_campaign.id}"

    response = client.get(reverse("core:campaign", args=(template_campaign.id,)))
    assert use_url in response.content.decode()

    template_campaign.template = False
    template_campaign.save()
    response = client.get(reverse("core:campaign", args=(template_campaign.id,)))
    assert use_url not in response.content.decode()


@pytest.mark.django_db
def test_apply_campaign_template_leaves_id_bearing_settings_alone(
    user, make_campaign, template_campaign
):
    """group_attribute_type and default_gang_sort point at the template's own rows."""
    attribute_type = template_campaign.attribute_types.get()
    template_campaign.group_attribute_type = attribute_type
    template_campaign.default_gang_sort = "-wealth"
    template_campaign.save()

    campaign = make_campaign("Fresh")
    apply_campaign_template(
        template_campaign=template_campaign, campaign=campaign, user=user
    )

    campaign.refresh_from_db()
    assert campaign.group_attribute_type is None
    assert campaign.default_gang_sort == ""


@pytest.mark.django_db
def test_describe_campaign_contents_summarises_a_template(template_campaign):
    groups = {
        g["label"]: g["names"] for g in describe_campaign_contents(template_campaign)
    }

    assert groups["Assets"] == ["Territories (1)"]
    assert groups["Resources"] == ["Meat"]
    assert groups["Attributes"] == ["Alliance"]
    assert groups["Content Packs"] == ["Pack Alpha"]


@pytest.mark.django_db
def test_new_campaign_from_template_logs_an_action(client, user, template_campaign):
    """The action log records where the campaign came from, and links back to it."""
    client.force_login(user)

    client.post(
        reverse("core:campaigns-new") + f"?template={template_campaign.id}",
        {"name": "Logged", "summary": "", "narrative": "", "budget": 1000},
    )

    campaign = Campaign.objects.get(name="Logged")
    action = campaign.actions.get()
    assert action.description == "Campaign created from Ash Wastes Starter template"
    assert action.template_campaign == template_campaign
    assert action.user == user
    assert action.outcome == (
        "Copied 1 asset type, 1 asset, 1 sub-asset, 1 resource type, "
        "1 attribute type, 1 Content Pack"
    )

    # The campaign page renders the link back to the template.
    response = client.get(reverse("core:campaign", args=(campaign.id,)))
    content = response.content.decode()
    assert "Campaign created from Ash Wastes Starter template" in content
    assert reverse("core:campaign", args=(template_campaign.id,)) in content


@pytest.mark.django_db
def test_new_campaign_without_template_logs_no_action(client, user):
    """Campaigns created from scratch keep an empty action log."""
    client.force_login(user)

    client.post(
        reverse("core:campaigns-new"),
        {"name": "Unlogged", "summary": "", "narrative": "", "budget": 1500},
    )

    assert not Campaign.objects.get(name="Unlogged").actions.exists()


@pytest.mark.django_db
def test_new_campaign_from_an_empty_template(client, user, make_campaign):
    """A template with nothing in it still creates a campaign, and says as much."""
    empty = make_campaign("Empty Starter", template=True)
    client.force_login(user)

    response = client.post(
        reverse("core:campaigns-new") + f"?template={empty.id}",
        {"name": "Nothing Copied", "summary": "", "narrative": "", "budget": 1500},
    )
    assert response.status_code == 302

    campaign = Campaign.objects.get(name="Nothing Copied")
    action = campaign.actions.get()
    assert action.outcome == "Nothing was copied — the template was empty."
    assert campaign.resource_types.get().name == "Reputation"
