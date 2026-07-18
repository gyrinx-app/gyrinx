"""Golden-equivalence test for the pack "Your Campaigns" page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.pack import CustomContentPack


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_campaigns_matches_legacy(user, make_campaign):
    pack = CustomContentPack.objects.create(name="My Content Pack", owner=user)
    subscribed = make_campaign("Underhive Wars")
    unsubscribed = make_campaign("Dust Bowl Skirmish")

    request = _request(user)
    context = {
        "pack": pack,
        "is_owner": True,
        "can_edit": True,
        "subscribed_campaigns": [subscribed],
        "unsubscribed_campaigns": [unsubscribed],
    }
    assert_equivalent("core/pack/pack_campaigns.html", context, request)


@pytest.mark.django_db
def test_pack_campaigns_empty_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="My Content Pack", owner=user)

    request = _request(user)
    context = {
        "pack": pack,
        "is_owner": True,
        "can_edit": True,
        "subscribed_campaigns": [],
        "unsubscribed_campaigns": [],
    }
    assert_equivalent("core/pack/pack_campaigns.html", context, request)
