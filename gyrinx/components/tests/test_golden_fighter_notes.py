"""Golden-equivalence test: fighter notes edit page matches legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_notes_edit_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.core.forms.list import EditListFighterNotesForm

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    form = EditListFighterNotesForm(instance=fighter)
    request = _request(user)
    return_url = reverse("core:list-notes", args=[lst.id]) + f"#notes-{fighter.id}"
    context = {
        "form": form,
        "list": lst,
        "error_message": None,
        "return_url": return_url,
    }
    assert_equivalent("core/list_fighter_notes_edit.html", context, request)
