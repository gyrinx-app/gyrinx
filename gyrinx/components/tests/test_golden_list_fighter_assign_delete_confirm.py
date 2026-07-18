"""Golden-equivalence test for the equipment-assignment delete confirm page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_assign_delete_confirm_matches_legacy(
    user, make_list, make_list_fighter, make_equipment
):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    equipment = make_equipment("Spoon", category="Basic Weapons")
    assign = fighter.assign(equipment)
    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "assign": assign,
        "action_url": "core:list-fighter-gear-delete",
        "back_url": "core:list-fighter-gear-edit",
        "error_message": None,
    }
    assert_equivalent("core/list_fighter_assign_delete_confirm.html", context, request)
