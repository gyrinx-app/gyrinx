"""Golden-equivalence test for the list-fighter clone page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_clone_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.core.forms.list import CloneListFighterForm

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    # Build the form exactly as the view's GET branch does.
    form = CloneListFighterForm(
        fighter=fighter,
        initial={
            "name": f"{fighter.name} (Clone)",
            "content_fighter": fighter.content_fighter,
            "list": fighter.list,
        },
        user=user,
    )

    request = _request(user)
    context = {
        "form": form,
        "list": lst,
        "fighter": fighter,
        "error_message": None,
    }
    assert_equivalent("core/list_fighter_clone.html", context, request)
