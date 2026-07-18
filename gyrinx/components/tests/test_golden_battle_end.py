"""Golden-equivalence test for the battle end confirmation page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_battle_end_matches_legacy(user, campaign):
    from gyrinx.core.models.battle import Battle

    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    request = _request(user)
    context = {"battle": battle}
    assert_equivalent("core/battle/battle_end.html", context, request)
