"""Golden-equivalence test: campaign_copy_to component matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_copy_to_matches_legacy(user, make_campaign):
    from gyrinx.core.forms.campaign import CampaignCopyToForm
    from gyrinx.core.models.campaign import (
        CampaignAssetType,
        CampaignResourceType,
    )

    campaign = make_campaign("Underhive Wars")
    # Give the source campaign content so the checkbox groups render.
    CampaignResourceType.objects.create(
        campaign=campaign, owner=user, name="Meat", default_amount=0
    )
    CampaignAssetType.objects.create(
        campaign=campaign,
        owner=user,
        name_singular="Territory",
        name_plural="Territories",
    )

    request = _request(user)
    form = CampaignCopyToForm(source_campaign=campaign, user=user)
    context = {
        "campaign": campaign,
        "form": form,
        "target_campaign": None,
        "conflicts": None,
        "show_confirmation": False,
    }
    assert_equivalent("core/campaign/campaign_copy_to.html", context, request)
