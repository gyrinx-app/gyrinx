"""Golden-equivalence test: fighter injuries-edit page matches its template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models import ContentInjury, ContentInjuryDefaultOutcome
from gyrinx.core.models.list import ListFighter, ListFighterInjury


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_injuries_edit_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    fighter.injury_state = ListFighter.RECOVERY
    fighter.save()

    spinal, _ = ContentInjury.objects.get_or_create(
        name="Spinal Injury",
        defaults={
            "description": "Recovery, -1 Strength",
            "phase": ContentInjuryDefaultOutcome.RECOVERY,
        },
    )
    eye, _ = ContentInjury.objects.get_or_create(
        name="Eye Injury",
        defaults={"phase": ContentInjuryDefaultOutcome.RECOVERY},
    )
    ListFighterInjury.objects.create(
        fighter=fighter,
        injury=eye,
        owner=user,
    )
    ListFighterInjury.objects.create(
        fighter=fighter,
        injury=spinal,
        notes="Injured in battle against Goliaths",
        owner=user,
    )

    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
    }
    assert_equivalent("core/list_fighter_injuries_edit.html", context, request)


@pytest.mark.django_db
def test_list_fighter_injuries_edit_no_injuries_matches_legacy(
    user, make_list, make_list_fighter
):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
    }
    assert_equivalent("core/list_fighter_injuries_edit.html", context, request)
