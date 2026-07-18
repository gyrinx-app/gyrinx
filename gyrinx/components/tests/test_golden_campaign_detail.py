"""Golden-equivalence test for the campaign detail page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.views.campaign.views import CampaignDetailView


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_detail_matches_legacy(user, make_campaign, make_list):
    campaign = make_campaign("Underhive Wars", status=Campaign.IN_PROGRESS)
    lst = make_list("Iron Skulls")
    campaign.lists.add(lst)

    request = _request(user, path=f"/campaign/{campaign.id}")

    # Build the exact context CampaignDetailView produces on GET.
    view = CampaignDetailView()
    view.request = request
    view.kwargs = {"id": campaign.id}
    view.object = view.get_object()
    context = view.get_context_data()

    assert_equivalent("core/campaign/campaign.html", context, request)
