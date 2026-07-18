"""Golden-equivalence test for the post-battle updates page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.forms.post_battle import PostBattleUpdatesForm
from gyrinx.core.views.list.post_battle import (
    _build_rows,
    _post_battle_fighters,
    _selectable_battles,
)


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _context(lst):
    """Rebuild the exact context the view's GET branch produces."""
    fighters = _post_battle_fighters(lst)
    battles = _selectable_battles(lst)
    form = PostBattleUpdatesForm(fighters=fighters, battles=battles, initial={})
    rows = _build_rows(fighters, form)
    return {
        "list": lst,
        "form": form,
        "rows": rows,
        "has_battles": battles.exists(),
    }


@pytest.mark.django_db
def test_list_post_battle_updates_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    make_list_fighter(lst, "Boss", owner=user)
    make_list_fighter(lst, "Ganger", owner=user)
    request = _request(user)
    assert_equivalent("core/list_post_battle_updates.html", _context(lst), request)


@pytest.mark.django_db
def test_list_post_battle_updates_no_fighters_matches_legacy(user, make_list):
    lst = make_list("Empty Skulls", owner=user)
    request = _request(user)
    assert_equivalent("core/list_post_battle_updates.html", _context(lst), request)
