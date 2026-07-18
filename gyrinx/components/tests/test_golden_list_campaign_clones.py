"""Golden-equivalence test for the campaign-clones list page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_campaign_clones_matches_legacy(user, make_list, campaign):
    source = make_list("Iron Skulls", owner=user)

    # A clone tied to a campaign (exercises the campaign/owner/status branches)
    clone_with_campaign = make_list("Iron Skulls (Campaign)", owner=user)
    clone_with_campaign.original_list = source
    clone_with_campaign.campaign = campaign
    clone_with_campaign.save()

    # A clone with no campaign (exercises the "-" / "No campaign" branches)
    clone_without_campaign = make_list("Iron Skulls (Orphan)", owner=user)
    clone_without_campaign.original_list = source
    clone_without_campaign.save()

    request = _request(user)
    campaign_clones = source.campaign_clones.all().select_related(
        "campaign", "campaign__owner"
    )
    context = {"list": source, "campaign_clones": campaign_clones}
    assert_equivalent("core/list_campaign_clones.html", context, request)


@pytest.mark.django_db
def test_list_campaign_clones_empty_matches_legacy(user, make_list):
    source = make_list("Iron Skulls", owner=user)
    request = _request(user)
    campaign_clones = source.campaign_clones.all().select_related(
        "campaign", "campaign__owner"
    )
    context = {"list": source, "campaign_clones": campaign_clones}
    assert_equivalent("core/list_campaign_clones.html", context, request)
