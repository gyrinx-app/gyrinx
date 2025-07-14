import pytest
from django.contrib.auth.models import User

from gyrinx.core.forms.campaign import CampaignAssetForm
from gyrinx.core.models.campaign import Campaign, CampaignAssetType


@pytest.mark.django_db
def test_asset_form_hides_holder_field_when_campaign_not_in_progress():
    """Test that the holder field is hidden when campaign is not in progress."""
    user = User.objects.create_user(username="testuser", password="testpass")
    
    # Create a pre-campaign campaign (default status)
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        status=Campaign.PRE_CAMPAIGN,
    )
    
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )
    
    # Test form with pre-campaign status
    form = CampaignAssetForm(asset_type=asset_type, campaign=campaign)
    assert "holder" not in form.fields
    
    # Start the campaign
    campaign.status = Campaign.IN_PROGRESS
    campaign.save()
    
    # Test form with in-progress campaign
    form = CampaignAssetForm(asset_type=asset_type, campaign=campaign)
    assert "holder" in form.fields
    
    # End the campaign
    campaign.status = Campaign.POST_CAMPAIGN
    campaign.save()
    
    # Test form with post-campaign status
    form = CampaignAssetForm(asset_type=asset_type, campaign=campaign)
    assert "holder" not in form.fields


@pytest.mark.django_db
def test_asset_form_gets_campaign_from_asset_type():
    """Test that the form can infer the campaign from the asset_type."""
    user = User.objects.create_user(username="testuser", password="testpass")
    
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True,
        status=Campaign.PRE_CAMPAIGN,
    )
    
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )
    
    # Test form without explicitly passing campaign
    form = CampaignAssetForm(asset_type=asset_type)
    assert "holder" not in form.fields
    
    # Start campaign and test again
    campaign.status = Campaign.IN_PROGRESS
    campaign.save()
    
    form = CampaignAssetForm(asset_type=asset_type)
    assert "holder" in form.fields