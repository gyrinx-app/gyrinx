"""Golden-equivalence test for the fighter gear edit page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_gear_edit_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    request = _request(user, f"/list/{lst.id}/fighter/{fighter.id}/gear")

    # Mirrors the view's GET-branch context. An empty ``assigns`` list exercises
    # the ``{% empty %}`` "No gear found" branch; the fighter-card and filter
    # includes render from the same context in both engines.
    context = {
        "fighter": fighter,
        "equipment": [],
        "categories": [],
        "assigns": [],
        "list": lst,
        "error_message": None,
        "is_weapon": False,
        "is_equipment_list": True,
        "render_preset_al": True,
        "render_preset_mal": True,
        "preset_al": ["C", "R", "I"],
        "preset_mal": None,
        "pack_content_map": {},
    }
    assert_equivalent("core/list_fighter_gear_edit.html", context, request)
