"""Golden-equivalence test for the add-a-Fighter form page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_new_matches_legacy(user, make_list):
    from gyrinx.core.forms.list import ListFighterForm
    from gyrinx.core.models.list import ListFighter

    lst = make_list("Iron Skulls", owner=user)
    # Mirror the view GET branch: an unsaved ListFighter seeded with the list,
    # bound to a fresh ListFighterForm.
    fighter = ListFighter(list=lst, owner=lst.owner)
    form = ListFighterForm(instance=fighter)
    request = _request(user)
    context = {"form": form, "list": lst, "error_message": None}
    assert_equivalent("core/list_fighter_new.html", context, request)
