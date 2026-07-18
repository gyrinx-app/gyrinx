"""Golden-equivalence test for the campaign asset detail page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.campaign import (
    CampaignAsset,
    CampaignAssetType,
    CampaignSubAsset,
)


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _sub_assets_by_type(asset):
    """Replicate the view's grouping of sub-assets in schema order."""
    sub_asset_schema = asset.asset_type.sub_asset_schema or {}
    grouped = {}
    for sub_asset in asset.sub_assets.all():
        sub_asset.parent_asset = asset
        grouped.setdefault(sub_asset.sub_asset_type, []).append(sub_asset)

    sub_assets_by_type = []
    for type_key, type_def in sub_asset_schema.items():
        items = grouped.pop(type_key, None)
        if items:
            label = type_def.get("label_plural", type_def.get("label", type_key))
            sub_assets_by_type.append((label, items))

    for type_key, items in sorted(grouped.items()):
        sub_assets_by_type.append((type_key, items))

    return sub_assets_by_type


@pytest.mark.django_db
def test_campaign_asset_detail_matches_legacy(user, make_campaign, make_list):
    campaign = make_campaign("Underhive Wars")
    holder = make_list("Iron Skulls", owner=user)

    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
        description="<p>Territories are places worth fighting for.</p>",
        property_schema=[
            {"key": "boon", "label": "Boon"},
            {"key": "income", "label": "Income"},
        ],
        sub_asset_schema={
            "structure": {
                "label": "Structure",
                "label_plural": "Structures",
                "property_schema": [
                    {"key": "benefit", "label": "Benefit"},
                    {"key": "upkeep", "label": "Upkeep"},
                ],
            }
        },
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        owner=user,
        name="The Sump",
        description="<p>A deep and murky place.</p>",
        holder=holder,
        properties={"boon": "+1 Rep", "income": "20"},
    )
    CampaignSubAsset.objects.create(
        parent_asset=asset,
        owner=user,
        sub_asset_type="structure",
        name="Generator Hall",
        properties={"benefit": "+1", "upkeep": "5"},
    )

    request = _request(user)
    context = {
        "campaign": campaign,
        "asset": asset,
        "sub_assets_by_type": _sub_assets_by_type(asset),
        "is_admin": True,
    }
    assert_equivalent("core/campaign/campaign_asset_detail.html", context, request)
