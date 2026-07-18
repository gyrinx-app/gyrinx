"""Golden-equivalence test for the campaign pack remove confirmation page."""

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
def test_campaign_pack_remove_matches_legacy(user, make_campaign):
    campaign = make_campaign("Underhive Wars")
    pack = CustomContentPack.objects.create(name="House Rules Pack", owner=user)
    request = _request(user)
    context = {"campaign": campaign, "pack": pack}
    assert_equivalent("core/campaign/campaign_pack_remove.html", context, request)
