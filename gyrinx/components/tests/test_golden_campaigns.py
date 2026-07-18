"""Golden-equivalence test for the campaigns index page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.campaign import Campaign


def _request(user, path="/campaigns/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaigns_matches_legacy(user, make_campaign):
    listed = make_campaign("Underhive Wars", status=Campaign.IN_PROGRESS)
    pinned = make_campaign("Dust Bowl Feud", status=Campaign.IN_PROGRESS)
    request = _request(user)
    context = {
        "campaigns": [listed],
        "status_choices": Campaign.STATUS_CHOICES,
        "current_sort": "recent",
        "pinned_campaigns": [pinned],
    }
    assert_equivalent("core/campaign/campaigns.html", context, request)
