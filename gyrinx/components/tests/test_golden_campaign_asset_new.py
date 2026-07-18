"""Golden-equivalence test for the campaign asset new page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_asset_new_matches_legacy(user, make_campaign):
    from gyrinx.core.forms.campaign import CampaignAssetForm
    from gyrinx.core.models.campaign import Campaign, CampaignAssetType

    campaign = make_campaign("Underhive Wars", status=Campaign.IN_PROGRESS)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        description="A patch of the underhive",
        property_schema=[
            {"key": "boon", "label": "Boon", "description": "Its benefit"}
        ],
        owner=user,
    )
    form = CampaignAssetForm(asset_type=asset_type, campaign=campaign)
    request = _request(user)
    context = {
        "form": form,
        "campaign": campaign,
        "asset_type": asset_type,
    }
    assert_equivalent("core/campaign/campaign_asset_new.html", context, request)
