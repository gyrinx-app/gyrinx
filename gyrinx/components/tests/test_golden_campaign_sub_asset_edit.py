"""Golden-equivalence test: campaign_sub_asset_edit page matches legacy."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_sub_asset_edit_matches_legacy(user, make_campaign):
    from gyrinx.core.forms.campaign import CampaignSubAssetForm
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
        owner=user,
        sub_asset_schema={
            "structure": {
                "label": "Structure",
                "label_plural": "Structures",
                "property_schema": [
                    {
                        "key": "benefit",
                        "label": "Benefit",
                        "description": "What this structure provides",
                    },
                ],
            },
        },
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
        properties={"benefit": "Extra income"},
        owner=user,
    )

    sub_asset_schemas = asset.asset_type.sub_asset_schema or {}
    sub_asset_type_def = sub_asset_schemas.get(sub_asset.sub_asset_type, {})

    form = CampaignSubAssetForm(
        instance=sub_asset,
        parent_asset=asset,
        sub_asset_type=sub_asset.sub_asset_type,
    )

    request = _request(user)
    context = {
        "campaign": campaign,
        "asset": asset,
        "sub_asset": sub_asset,
        "sub_asset_type_def": sub_asset_type_def,
        "form": form,
    }
    assert_equivalent("core/campaign/campaign_sub_asset_edit.html", context, request)
