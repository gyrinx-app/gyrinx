"""Golden-equivalence test for the campaign asset-type edit page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_asset_type_edit_matches_legacy(user, make_campaign):
    from gyrinx.core.forms.campaign import CampaignAssetTypeForm
    from gyrinx.core.models.campaign import CampaignAssetType

    campaign = make_campaign("Underhive Wars")
    asset_type = CampaignAssetType.objects.create(
        campaign=campaign,
        name_singular="Territory",
        name_plural="Territories",
        owner=user,
    )
    form = CampaignAssetTypeForm(instance=asset_type)
    request = _request(user)
    context = {"form": form, "campaign": campaign, "asset_type": asset_type}
    assert_equivalent("core/campaign/campaign_asset_type_edit.html", context, request)
