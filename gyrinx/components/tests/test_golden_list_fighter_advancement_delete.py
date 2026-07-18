"""Golden-equivalence test: list_fighter_advancement_delete page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.list import ListFighterAdvancement


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_advancement_delete_matches_legacy(
    user, make_list, make_list_fighter
):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    advancement = ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_OTHER,
        advancement_choice="other",
        description="Extra training",
        xp_cost=6,
        cost_increase=5,
    )
    request = _request(user)
    context = {"list": lst, "fighter": fighter, "advancement": advancement}
    assert_equivalent("core/list_fighter_advancement_delete.html", context, request)


@pytest.mark.django_db
def test_list_fighter_advancement_delete_equipment_matches_legacy(
    user, make_list, make_list_fighter
):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    advancement = ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
        description="Chosen Gunsmith: Autopistol",
        xp_cost=3,
        cost_increase=10,
    )
    request = _request(user)
    context = {"list": lst, "fighter": fighter, "advancement": advancement}
    assert_equivalent("core/list_fighter_advancement_delete.html", context, request)
