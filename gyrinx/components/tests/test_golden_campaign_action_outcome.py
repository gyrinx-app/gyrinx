"""Golden-equivalence test for the campaign action-outcome form page."""

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
def test_campaign_action_outcome_matches_legacy(user, make_campaign, make_list):
    from gyrinx.core.forms.campaign import CampaignActionOutcomeForm
    from gyrinx.core.models.campaign import CampaignAction

    campaign = make_campaign("Underhive Wars")
    gang = make_list("The Skulls")
    action = CampaignAction.objects.create(
        campaign=campaign,
        user=user,
        list=gang,
        description="Scavenged the ruins",
        dice_count=2,
    )
    request = _request(user)
    form = CampaignActionOutcomeForm(instance=action)
    return_url = reverse("core:campaign", args=[campaign.id])
    context = {
        "form": form,
        "campaign": campaign,
        "action": action,
        "error_message": None,
        "return_url": return_url,
    }
    assert_equivalent("core/campaign/campaign_action_outcome.html", context, request)
