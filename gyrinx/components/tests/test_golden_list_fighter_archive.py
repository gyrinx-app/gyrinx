"""Golden-equivalence test: list fighter archive confirmation page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_archive_matches_legacy(user, make_list, make_list_fighter):
    # Mirrors the archive_list_fighter GET branch: fighter + list + cost_int().
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    request = _request(user)
    context = {
        "fighter": fighter,
        "list": lst,
        "fighter_cost": fighter.cost_int(),
    }
    assert_equivalent("core/list_fighter_archive.html", context, request)
