"""Golden-equivalence test for the campaign sub-asset create page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.forms.campaign import CampaignSubAssetForm
from gyrinx.core.models.campaign import CampaignAsset, CampaignAssetType


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_sub_asset_new_matches_legacy(user, make_campaign):
    campaign = make_campaign("Underhive Wars")
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Settlement",
        name_plural="Settlements",
        sub_asset_schema={
            "structure": {
                "label": "Structure",
                "description": "A building within the settlement.",
                "property_schema": [
                    {
                        "key": "benefit",
                        "label": "Benefit",
                        "description": "What this structure provides",
                    }
                ],
            }
        },
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        owner=user,
    )
    sub_asset_type = "structure"
    sub_asset_type_def = asset_type.sub_asset_schema[sub_asset_type]
    form = CampaignSubAssetForm(parent_asset=asset, sub_asset_type=sub_asset_type)

    request = _request(user)
    context = {
        "campaign": campaign,
        "asset": asset,
        "sub_asset_type_key": sub_asset_type,
        "sub_asset_type_def": sub_asset_type_def,
        "form": form,
    }
    assert_equivalent("core/campaign/campaign_sub_asset_new.html", context, request)
