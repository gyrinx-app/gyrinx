"""Golden-equivalence test: enable-default-assignment page matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_assign_convert_matches_legacy(
    user, make_list, make_list_fighter, make_equipment
):
    from gyrinx.content.models import ContentFighterDefaultAssignment

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    equipment = make_equipment("Autogun", category="Basic Weapons")
    assign = ContentFighterDefaultAssignment.objects.create(
        fighter=fighter.content_fighter,
        equipment=equipment,
    )
    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "assign": assign,
        "action_url": "core:list-fighter-gear-default-convert",
        "back_url": "core:list-fighter-gear-edit",
    }
    assert_equivalent("core/list_fighter_assign_convert.html", context, request)
