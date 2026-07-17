"""Golden-equivalence tests: converted pages match their legacy templates."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_delete_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "fighter_cost": fighter.cost_int(),
    }
    assert_equivalent("core/list_fighter_delete.html", context, request)
