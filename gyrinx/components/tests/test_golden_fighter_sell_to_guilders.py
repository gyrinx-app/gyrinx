"""Golden-equivalence test: sell-fighter-to-guilders page matches legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.list import CapturedFighter

TEMPLATE = "core/campaign/fighter_sell_to_guilders.html"


def _request(user, path="/campaign/x/fighter/y/sell-to-guilders"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_fighter_sell_to_guilders_matches_legacy(
    user, make_user, make_campaign, make_list, make_list_fighter
):
    other = make_user("other", "password")
    campaign = make_campaign("Underhive Wars")

    # Capturing gang owned by the viewer -> "(Your Gang)" marker shows.
    capturing_list = make_list("User Gang", owner=user)
    original_list = make_list("Other Gang", owner=other)
    fighter = make_list_fighter(original_list, "Captive One", owner=other)
    captured_fighter = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=capturing_list,
    )

    request = _request(user)
    context = {
        "campaign": campaign,
        "captured_fighter": captured_fighter,
        "return_url": f"/campaign/{campaign.id}/captured-fighters/",
    }
    assert_equivalent(TEMPLATE, context, request)
