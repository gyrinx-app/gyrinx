"""Golden-equivalence test for the campaign log-action form page."""

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
def test_campaign_log_action_matches_legacy(user, make_campaign):
    from gyrinx.core.forms.campaign import CampaignActionForm

    campaign = make_campaign("Underhive Wars")
    request = _request(user)
    form = CampaignActionForm(campaign=campaign, user=user, initial={})
    return_url = reverse("core:campaign", args=[campaign.id])
    context = {
        "form": form,
        "campaign": campaign,
        "error_message": None,
        "return_url": return_url,
    }
    assert_equivalent("core/campaign/campaign_log_action.html", context, request)
