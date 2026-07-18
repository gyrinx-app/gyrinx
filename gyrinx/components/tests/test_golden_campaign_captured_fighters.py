"""Golden-equivalence test: campaign captured-fighters page matches legacy."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.list import CapturedFighter

TEMPLATE = "core/campaign/campaign_captured_fighters.html"


def _request(user, path="/campaign/x/captured-fighters"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_captured_fighters_matches_legacy(
    user, make_user, make_campaign, make_list, make_list_fighter
):
    other = make_user("other", "password")
    campaign = make_campaign("Underhive Wars")

    list_user = make_list("User Gang", owner=user)
    list_other = make_list("Other Gang", owner=other)
    list_third = make_list("Third Gang", owner=other)

    # Capturing gang owned by the viewer -> full action button group.
    f1 = make_list_fighter(list_other, "Captive One", owner=other)
    c1 = CapturedFighter.objects.create(fighter=f1, capturing_list=list_user)

    # Original gang owned by the viewer -> return/release only.
    f2 = make_list_fighter(list_user, "Captive Two", owner=user)
    c2 = CapturedFighter.objects.create(fighter=f2, capturing_list=list_other)

    # Neither gang owned by the viewer -> "Not your captive".
    f3 = make_list_fighter(list_third, "Captive Three", owner=other)
    c3 = CapturedFighter.objects.create(fighter=f3, capturing_list=list_other)

    # Sold to guilders with a ransom amount.
    f4 = make_list_fighter(list_other, "Captive Four", owner=other)
    c4 = CapturedFighter.objects.create(
        fighter=f4,
        capturing_list=list_user,
        sold_to_guilders=True,
        ransom_amount=25,
    )

    # Sold to guilders with no ransom amount.
    f5 = make_list_fighter(list_other, "Captive Five", owner=other)
    c5 = CapturedFighter.objects.create(
        fighter=f5,
        capturing_list=list_user,
        sold_to_guilders=True,
    )

    request = _request(user)
    context = {
        "campaign": campaign,
        "captured_fighters": [c1, c2, c3, c4, c5],
        "is_admin": False,
    }
    assert_equivalent(TEMPLATE, context, request)


@pytest.mark.django_db
def test_campaign_captured_fighters_empty_matches_legacy(user, make_campaign):
    campaign = make_campaign("Underhive Wars")
    request = _request(user)
    context = {
        "campaign": campaign,
        "captured_fighters": [],
        "is_admin": False,
    }
    assert_equivalent(TEMPLATE, context, request)
