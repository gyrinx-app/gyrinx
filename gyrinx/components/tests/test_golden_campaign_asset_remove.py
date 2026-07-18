"""Golden-equivalence test for the campaign asset remove page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_asset_remove_matches_legacy(user, make_campaign, make_list):
    from gyrinx.core.models.campaign import CampaignAsset, CampaignAssetType

    campaign = make_campaign("Underhive Wars")
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        description="Areas of the underhive",
        owner=user,
    )
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        description="A grim watering hole",
        owner=user,
    )
    request = _request(user)

    # Unheld asset (no holder branch).
    context = {"campaign": campaign, "asset": asset}
    assert_equivalent("core/campaign/campaign_asset_remove.html", context, request)

    # Held asset (renders the holder paragraph).
    asset.holder = make_list("Cawdor Redemptionists")
    asset.save()
    context = {"campaign": campaign, "asset": asset}
    assert_equivalent("core/campaign/campaign_asset_remove.html", context, request)
