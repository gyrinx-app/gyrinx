"""Golden-equivalence test for the campaign copy-from page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _get_context(campaign, request):
    """Replicate the GET branch of ``campaign_copy_from`` view."""
    from gyrinx.core.forms.campaign import CampaignCopyFromForm
    from gyrinx.core.models.campaign import Campaign

    form = CampaignCopyFromForm(target_campaign=campaign, user=request.user)
    template_campaigns = (
        Campaign.objects.filter(template=True).exclude(pk=campaign.pk).order_by("name")
    )
    return {
        "campaign": campaign,
        "form": form,
        "source_campaign": None,
        "conflicts": None,
        "show_confirmation": False,
        "template_campaigns": template_campaigns,
    }


@pytest.mark.django_db
def test_campaign_copy_from_matches_legacy(user, make_campaign):
    campaign = make_campaign("Underhive Wars")
    request = _request(user)
    context = _get_context(campaign, request)
    assert_equivalent("core/campaign/campaign_copy_from.html", context, request)


@pytest.mark.django_db
def test_campaign_copy_from_with_template_matches_legacy(user, make_campaign):
    campaign = make_campaign("Underhive Wars")
    make_campaign(
        "Starter Template", template=True, summary="<p>A ready-made setup</p>"
    )
    request = _request(user)
    context = _get_context(campaign, request)
    assert_equivalent("core/campaign/campaign_copy_from.html", context, request)
