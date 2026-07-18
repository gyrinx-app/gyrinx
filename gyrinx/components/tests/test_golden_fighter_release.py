"""Golden-equivalence test: fighter_release page matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.list import CapturedFighter


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_fighter_release_matches_legacy(
    user, make_campaign, make_list, make_list_fighter
):
    campaign = make_campaign("Underhive Wars")
    original_list = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(original_list, "Boss", owner=user)
    capturing_list = make_list("Steel Talons", owner=user)
    captured_fighter = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=capturing_list,
    )

    request = _request(user)
    context = {
        "campaign": campaign,
        "captured_fighter": captured_fighter,
        "return_url": "/campaign/captured/",
    }
    assert_equivalent("core/campaign/fighter_release.html", context, request)
