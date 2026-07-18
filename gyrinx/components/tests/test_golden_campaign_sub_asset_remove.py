"""Golden-equivalence test for the campaign sub-asset remove page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_sub_asset_remove_matches_legacy(user, make_campaign):
    from gyrinx.core.models.campaign import (
        CampaignAsset,
        CampaignAssetType,
        CampaignSubAsset,
    )

    campaign = make_campaign("Underhive Wars")
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Settlement",
        name_plural="Settlements",
        sub_asset_schema={
            "structure": {"label": "Structure", "label_plural": "Structures"}
        },
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        owner=user,
    )
    sub_asset = CampaignSubAsset.objects.create(
        parent_asset=asset,
        sub_asset_type="structure",
        name="Generator Hall",
        owner=user,
    )
    sub_asset_type_def = (asset_type.sub_asset_schema or {}).get(
        sub_asset.sub_asset_type, {}
    )

    request = _request(user)
    context = {
        "campaign": campaign,
        "asset": asset,
        "sub_asset": sub_asset,
        "sub_asset_type_def": sub_asset_type_def,
    }
    assert_equivalent("core/campaign/campaign_sub_asset_remove.html", context, request)
