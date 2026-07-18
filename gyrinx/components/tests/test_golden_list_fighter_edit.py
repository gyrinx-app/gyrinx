"""Golden-equivalence test for the list-fighter edit page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_edit_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.core.forms.list import ListFighterForm

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    form = ListFighterForm(instance=fighter)
    request = _request(user)
    context = {
        "form": form,
        "list": lst,
        "error_message": None,
    }
    assert_equivalent("core/list_fighter_edit.html", context, request)
