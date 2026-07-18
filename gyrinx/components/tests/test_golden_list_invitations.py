"""Golden-equivalence test: list campaign-invitations display page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.invitation import CampaignInvitation


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_invitations_matches_legacy(user, make_user, make_list, make_campaign):
    lst = make_list("Iron Skulls", owner=user)
    campaign_owner = make_user("arbitrator", "password")
    campaign = make_campaign("Winter War", owner=campaign_owner)
    CampaignInvitation.objects.create(
        campaign=campaign,
        list=lst,
        owner=campaign_owner,
        message="Join us for glory in the underhive.",
    )

    # Replicate the view's GET-branch query exactly.
    invitations = CampaignInvitation.objects.filter(
        list=lst, status=CampaignInvitation.PENDING
    ).select_related("campaign", "campaign__owner")

    request = _request(user, reverse("core:list-invitations", args=[lst.id]))
    context = {"list": lst, "invitations": invitations}
    assert_equivalent("core/list/list_invitations.html", context, request)
