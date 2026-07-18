"""Golden-equivalence test for the fighter stats-edit page."""

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
def test_list_fighter_stats_edit_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.core.forms.list import EditListFighterStatsForm
    from gyrinx.core.utils import get_return_url

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    request = _request(user)

    # Replicate the view's GET branch exactly.
    default_url = reverse("core:list-fighter-edit", args=(lst.id, fighter.id))
    return_url = get_return_url(request, default_url)
    form = EditListFighterStatsForm(fighter=fighter)

    context = {
        "form": form,
        "list": lst,
        "fighter": fighter,
        "error_message": None,
        "return_url": return_url,
    }
    assert_equivalent("core/list_fighter_stats_edit.html", context, request)
