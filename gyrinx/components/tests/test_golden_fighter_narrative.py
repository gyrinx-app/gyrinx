"""Golden-equivalence test: fighter narrative (Lore) edit page."""

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
def test_list_fighter_narrative_edit_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.core.forms.list import EditListFighterNarrativeForm

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    form = EditListFighterNarrativeForm(instance=fighter)
    request = _request(user)
    context = {
        "form": form,
        "list": lst,
        "fighter": fighter,
        "error_message": None,
        "return_url": reverse("core:list-about", args=(lst.id,))
        + f"#about-{fighter.id}",
    }
    assert_equivalent("core/list_fighter_narrative_edit.html", context, request)
