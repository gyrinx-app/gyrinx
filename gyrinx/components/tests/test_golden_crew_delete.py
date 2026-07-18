"""Golden-equivalence test for the crew delete confirmation page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_crew_delete_matches_legacy(user, list_with_campaign, campaign):
    from gyrinx.core.models import Battle
    from gyrinx.core.models.crew import Crew

    gang = list_with_campaign
    battle = Battle.objects.create(campaign=campaign, mission="Ambush", owner=user)
    crew = Crew.objects.create(battle=battle, list=gang, owner=user)

    request = _request(user)
    context = {"crew": crew, "battle": battle}
    assert_equivalent("core/crew/crew_delete.html", context, request)
