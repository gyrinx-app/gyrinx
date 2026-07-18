"""Golden-equivalence test for the battle archive/unarchive confirmation page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models import Battle


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_battle_archive_matches_legacy(user, campaign):
    battle = Battle.objects.create(
        campaign=campaign,
        mission="Ambush",
        owner=user,
    )
    request = _request(user)
    assert_equivalent("core/battle/battle_archive.html", {"battle": battle}, request)
