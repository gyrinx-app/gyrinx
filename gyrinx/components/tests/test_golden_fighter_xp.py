"""Golden-equivalence test for the fighter XP edit page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_xp_edit_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.core.forms.list import EditFighterXPForm

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    form = EditFighterXPForm(fighter=fighter)
    request = _request(user)
    context = {
        "form": form,
        "list": lst,
        "fighter": fighter,
    }
    assert_equivalent("core/list_fighter_xp_edit.html", context, request)
