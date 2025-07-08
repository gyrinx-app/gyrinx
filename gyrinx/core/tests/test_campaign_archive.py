"""Tests for campaign archive functionality."""

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from gyrinx.core.models import Campaign, CampaignAssetType, CampaignResourceType

pytestmark = pytest.mark.django_db


@pytest.fixture
def pre_campaign(user):
    """Create a pre-campaign for testing."""
    return Campaign.objects.create(
        name="Test Pre-Campaign",
        owner=user,
        status=Campaign.PRE_CAMPAIGN,
    )


@pytest.fixture
def in_progress_campaign(user):
    """Create an in-progress campaign for testing."""
    return Campaign.objects.create(
        name="Test In Progress Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )


@pytest.fixture
def archived_campaign(user):
    """Create an archived campaign for testing."""
    campaign = Campaign.objects.create(
        name="Test Archived Campaign",
        owner=user,
        status=Campaign.PRE_CAMPAIGN,
    )
    campaign.archive()
    return campaign


def test_cannot_archive_in_progress_campaign(client, in_progress_campaign):
    """Test that in-progress campaigns cannot be archived."""
    client.force_login(in_progress_campaign.owner)

    url = reverse("core:campaign-archive", args=[in_progress_campaign.id])
    response = client.post(url, {"archive": "1"})

    # Should redirect back to campaign detail page
    assert response.status_code == 302
    assert response.url == reverse("core:campaign", args=[in_progress_campaign.id])

    # Campaign should not be archived
    in_progress_campaign.refresh_from_db()
    assert not in_progress_campaign.archived

    # Should have error message
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) == 1
    assert "cannot archive" in messages[0].message.lower()
    assert "in progress" in messages[0].message.lower()


def test_can_archive_pre_campaign(client, pre_campaign):
    """Test that pre-campaigns can be archived."""
    client.force_login(pre_campaign.owner)

    url = reverse("core:campaign-archive", args=[pre_campaign.id])
    response = client.post(url, {"archive": "1"})

    # Should redirect back to campaign detail page
    assert response.status_code == 302
    assert response.url == reverse("core:campaign", args=[pre_campaign.id])

    # Campaign should be archived
    pre_campaign.refresh_from_db()
    assert pre_campaign.archived

    # Should have success message
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) == 1
    assert "has been archived" in messages[0].message


def test_campaign_detail_shows_archived_message(client, archived_campaign):
    """Test that archived campaigns show an archived message."""
    client.force_login(archived_campaign.owner)

    url = reverse("core:campaign", args=[archived_campaign.id])
    response = client.get(url)

    assert response.status_code == 200
    assert b"This campaign has been archived by its owner" in response.content
    assert b"Unarchive" in response.content


def test_archived_campaign_hides_action_buttons(client, archived_campaign):
    """Test that archived campaigns don't show action buttons."""
    client.force_login(archived_campaign.owner)

    url = reverse("core:campaign", args=[archived_campaign.id])
    response = client.get(url)

    assert response.status_code == 200
    # These buttons should not appear for archived campaigns
    assert b"Add Gangs" not in response.content
    assert b"New Battle" not in response.content
    assert b"Log Action" not in response.content


def test_cannot_create_asset_type_for_archived_campaign(client, archived_campaign):
    """Test that asset types cannot be created for archived campaigns."""
    client.force_login(archived_campaign.owner)

    url = reverse("core:campaign-asset-type-new", args=[archived_campaign.id])
    response = client.post(
        url,
        {
            "name_singular": "Test Asset",
            "name_plural": "Test Assets",
            "is_transferable": True,
        },
    )

    # Should redirect to campaign assets page
    assert response.status_code == 302
    assert response.url == reverse("core:campaign-assets", args=[archived_campaign.id])

    # No asset type should be created
    assert not CampaignAssetType.objects.filter(campaign=archived_campaign).exists()

    # Should have error message
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) == 1
    assert (
        "cannot create new asset types for archived campaigns"
        in messages[0].message.lower()
    )


def test_cannot_create_resource_type_for_archived_campaign(client, archived_campaign):
    """Test that resource types cannot be created for archived campaigns."""
    client.force_login(archived_campaign.owner)

    url = reverse("core:campaign-resource-type-new", args=[archived_campaign.id])
    response = client.post(
        url,
        {
            "name": "Test Resource",
            "default_amount": 10,
        },
    )

    # Should redirect to campaign resources page
    assert response.status_code == 302
    assert response.url == reverse(
        "core:campaign-resources", args=[archived_campaign.id]
    )

    # No resource type should be created
    assert not CampaignResourceType.objects.filter(campaign=archived_campaign).exists()

    # Should have error message
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) == 1
    assert (
        "cannot create new resource types for archived campaigns"
        in messages[0].message.lower()
    )


def test_cannot_create_asset_for_archived_campaign(client, archived_campaign):
    """Test that assets cannot be created for archived campaigns."""
    # First create an asset type
    asset_type = CampaignAssetType.objects.create(
        campaign=archived_campaign,
        owner=archived_campaign.owner,
        name_singular="Test Asset",
        name_plural="Test Assets",
    )

    client.force_login(archived_campaign.owner)

    url = reverse("core:campaign-asset-new", args=[archived_campaign.id, asset_type.id])
    response = client.post(
        url,
        {
            "name": "Specific Asset",
        },
    )

    # Should redirect to campaign assets page
    assert response.status_code == 302
    assert response.url == reverse("core:campaign-assets", args=[archived_campaign.id])

    # No asset should be created
    assert not asset_type.assets.exists()

    # Should have error message
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) == 1
    assert (
        "cannot create new assets for archived campaigns" in messages[0].message.lower()
    )
