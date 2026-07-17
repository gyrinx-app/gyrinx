"""Golden-equivalence test: fighter resurrect page matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.list import ListFighter


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_resurrect_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    target_state = ListFighter.ACTIVE
    request = _request(user)
    context = {
        "fighter": fighter,
        "list": lst,
        "target_state": target_state,
        "target_state_display": dict(ListFighter.INJURY_STATE_CHOICES).get(
            target_state, ""
        ),
        "reason": "",
    }
    assert_equivalent("core/list_fighter_resurrect.html", context, request)
