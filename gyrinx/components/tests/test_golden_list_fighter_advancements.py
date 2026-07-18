"""Golden-equivalence test: list_fighter_advancements page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.list import ListFighterAdvancement


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _advancements(fighter):
    return ListFighterAdvancement.objects.filter(
        fighter=fighter,
        archived=False,
    ).select_related("skill", "campaign_action")


@pytest.mark.django_db
def test_list_fighter_advancements_empty_matches_legacy(
    user, make_list, make_list_fighter
):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "advancements": _advancements(fighter),
    }
    assert_equivalent("core/list_fighter_advancements.html", context, request)


@pytest.mark.django_db
def test_list_fighter_advancements_with_rows_matches_legacy(
    user, make_list, make_list_fighter, make_content_skill
):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        advancement_choice="stat_movement",
        stat_increased="movement",
        xp_cost=6,
        cost_increase=5,
    )
    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        skill=make_content_skill("Nerves of Steel"),
        xp_cost=9,
        cost_increase=20,
    )
    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_OTHER,
        advancement_choice="other",
        description="Extra training",
        xp_cost=3,
        cost_increase=0,
    )
    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "advancements": _advancements(fighter),
    }
    assert_equivalent("core/list_fighter_advancements.html", context, request)


@pytest.mark.django_db
def test_list_fighter_advancements_non_owner_matches_legacy(
    user, make_user, make_list, make_list_fighter
):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_OTHER,
        advancement_choice="other",
        description="Extra training",
        xp_cost=3,
        cost_increase=0,
    )
    viewer = make_user("viewer", "password")
    request = _request(viewer)
    context = {
        "list": lst,
        "fighter": fighter,
        "advancements": _advancements(fighter),
    }
    assert_equivalent("core/list_fighter_advancements.html", context, request)
