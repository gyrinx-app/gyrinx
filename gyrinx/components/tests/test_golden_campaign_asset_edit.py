"""Golden-equivalence test for the campaign asset edit page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_asset_edit_matches_legacy(user, make_campaign):
    from gyrinx.core.forms.campaign import CampaignAssetForm
    from gyrinx.core.models.campaign import (
        Campaign,
        CampaignAsset,
        CampaignAssetType,
        CampaignSubAsset,
    )

    campaign = make_campaign("Underhive Wars", status=Campaign.IN_PROGRESS)
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        property_schema=[{"key": "income", "label": "Income"}],
        sub_asset_schema={
            "structure": {
                "label": "Structure",
                "label_plural": "Structures",
                "description": "Buildings within the territory",
                "property_schema": [{"key": "benefit", "label": "Benefit"}],
            }
        },
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        description="A deep, dark place",
        properties={"income": "5"},
        owner=user,
    )
    CampaignSubAsset.objects.create(
        parent_asset=asset,
        sub_asset_type="structure",
        name="Generator Hall",
        properties={"benefit": "Extra power"},
        owner=user,
    )

    # Mirror the view's GET branch: CampaignAssetForm(instance=asset, campaign=campaign)
    form = CampaignAssetForm(instance=asset, campaign=campaign)
    request = _request(user)
    context = {"form": form, "campaign": campaign, "asset": asset}
    assert_equivalent("core/campaign/campaign_asset_edit.html", context, request)
