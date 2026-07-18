"""Golden-equivalence test: battle start confirmation page."""

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
def test_battle_start_matches_legacy(user, campaign):
    battle = Battle.objects.create(campaign=campaign, mission="M", owner=user)
    request = _request(user)
    context = {"battle": battle}
    assert_equivalent("core/battle/battle_start.html", context, request)
