"""Golden-equivalence test for the campaign asset transfer page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_asset_transfer_matches_legacy(user, make_campaign, make_list):
    from gyrinx.core.forms.campaign import AssetTransferForm
    from gyrinx.core.models.campaign import CampaignAsset, CampaignAssetType

    campaign = make_campaign("Underhive Wars")
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )
    holder = make_list("Iron Skulls", owner=user)
    asset = CampaignAsset.objects.create(
        asset_type=asset_type,
        name="The Sump",
        holder=holder,
        owner=user,
    )
    form = AssetTransferForm(asset=asset)
    return_url = reverse("core:campaign-assets", args=[campaign.id])
    request = _request(user)
    context = {
        "form": form,
        "campaign": campaign,
        "asset": asset,
        "return_url": return_url,
    }
    assert_equivalent("core/campaign/campaign_asset_transfer.html", context, request)
