"""Golden-equivalence test: fighter injury-removal page matches its template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models import ContentInjury, ContentInjuryDefaultOutcome
from gyrinx.core.models.list import ListFighterInjury


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_remove_injury_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    injury, _ = ContentInjury.objects.get_or_create(
        name="Spinal Injury",
        defaults={
            "description": "Recovery, -1 Strength",
            "phase": ContentInjuryDefaultOutcome.RECOVERY,
        },
    )
    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        notes="Injured in battle against Goliaths",
        owner=user,
    )

    request = _request(user)
    context = {
        "injury": fighter_injury,
        "fighter": fighter,
        "list": lst,
    }
    assert_equivalent("core/list_fighter_remove_injury.html", context, request)
