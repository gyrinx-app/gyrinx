"""Test that archived campaigns have disabled buttons."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from gyrinx.core.models import (
    Campaign,
    Battle,
    CampaignAssetType,
    CampaignAsset,
    CampaignResourceType,
    CampaignListResource,
    List,
)

User = get_user_model()


@pytest.mark.django_db
def test_archived_campaign_disables_log_action_button():
    """Test that archived campaigns don't show the log action button."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
        archived=True,
    )

    client = Client()
    client.login(username="testuser", password="testpass")

    # Test on campaign detail page
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200
    assert not response.context["can_log_actions"]

    # Test on campaign actions page
    response = client.get(reverse("core:campaign-actions", args=[campaign.id]))
    assert response.status_code == 200
    assert not response.context["can_log_actions"]


@pytest.mark.django_db
def test_archived_campaign_disables_battle_edit():
    """Test that battles in archived campaigns can't be edited."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
        archived=True,
    )
    battle = Battle.objects.create(
        campaign=campaign,
        owner=user,
        date="2025-01-01",
        mission="Test Mission",
    )

    # Test that can_edit returns False for archived campaigns
    assert not battle.can_edit(user)

    # Test that can_add_notes returns False for archived campaigns
    assert not battle.can_add_notes(user)


@pytest.mark.django_db
def test_archived_campaign_prevents_asset_transfer():
    """Test that assets in archived campaigns can't be transferred."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
        archived=True,
    )
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        owner=user,
        name="Old Factory",
    )

    client = Client()
    client.login(username="testuser", password="testpass")

    # Try to access transfer page
    response = client.get(
        reverse("core:campaign-asset-transfer", args=[campaign.id, asset.id])
    )
    assert response.status_code == 302  # Should redirect

    # Check that error message was added
    response = client.get(reverse("core:campaign-assets", args=[campaign.id]))
    messages = list(response.context["messages"])
    assert any(
        "Cannot transfer assets for archived campaigns" in str(m) for m in messages
    )


@pytest.mark.django_db
def test_archived_campaign_prevents_resource_modify():
    """Test that resources in archived campaigns can't be modified."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
        archived=True,
    )
    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        owner=user,
        name="Reputation",
        default_amount=0,
    )
    test_list = List.objects.create(
        name="Test Gang",
        owner=user,
        status=List.CAMPAIGN_MODE,
    )
    test_list.campaigns.add(campaign)

    resource = CampaignListResource.objects.create(
        campaign=campaign,
        resource_type=resource_type,
        list=test_list,
        amount=5,
        owner=user,
    )

    client = Client()
    client.login(username="testuser", password="testpass")

    # Try to access modify page
    response = client.get(
        reverse("core:campaign-resource-modify", args=[campaign.id, resource.id])
    )
    assert response.status_code == 302  # Should redirect

    # Check that error message was added
    response = client.get(reverse("core:campaign-resources", args=[campaign.id]))
    messages = list(response.context["messages"])
    assert any(
        "Cannot modify resources for archived campaigns" in str(m) for m in messages
    )


@pytest.mark.django_db
def test_archived_campaign_hides_buttons_in_templates():
    """Test that buttons are hidden in templates for archived campaigns."""
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
        archived=True,
    )

    # Create some test data
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        owner=user,
        name="Old Factory",
    )

    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        owner=user,
        name="Reputation",
        default_amount=0,
    )
    test_list = List.objects.create(
        name="Test Gang",
        owner=user,
        status=List.CAMPAIGN_MODE,
    )
    test_list.campaigns.add(campaign)

    resource = CampaignListResource.objects.create(
        campaign=campaign,
        resource_type=resource_type,
        list=test_list,
        amount=5,
        owner=user,
    )

    client = Client()
    client.login(username="testuser", password="testpass")

    # Check campaign detail page
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()

    # Should not have Transfer link for assets
    assert (
        'href="'
        + reverse("core:campaign-asset-transfer", args=[campaign.id, asset.id])
        + '"'
        not in content
    )

    # Should not have Modify link for resources
    assert (
        'href="'
        + reverse("core:campaign-resource-modify", args=[campaign.id, resource.id])
        + '"'
        not in content
    )

    # Check assets page
    response = client.get(reverse("core:campaign-assets", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()

    # Should not have Transfer button for assets
    assert (
        'href="'
        + reverse("core:campaign-asset-transfer", args=[campaign.id, asset.id])
        + '"'
        not in content
    )

    # Check resources page
    response = client.get(reverse("core:campaign-resources", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()

    # Should not have Modify button for resources
    assert (
        'href="'
        + reverse("core:campaign-resource-modify", args=[campaign.id, resource.id])
        + '"'
        not in content
    )
