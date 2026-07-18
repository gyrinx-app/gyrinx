"""Golden-equivalence test for the fighter psyker-powers edit page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_psyker_powers_edit_matches_legacy(
    user, make_list, make_list_fighter
):
    from gyrinx.core.utils import search_queryset
    from gyrinx.core.views.fighter.helpers import (
        FighterEditMixin,
        build_virtual_psyker_power_assignments,
        get_common_query_params,
        get_fighter_powers,
        group_available_assignments,
    )

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    request = _request(user)

    # Replicate the view GET branch exactly.
    helper = FighterEditMixin()
    lst, fighter = helper.get_fighter_and_list(request, lst.id, fighter.id)

    params = get_common_query_params(request)
    powers = get_fighter_powers(fighter, params["show_restricted"])
    all_assigns = build_virtual_psyker_power_assignments(powers, fighter)
    current_powers = [
        a
        for a in all_assigns
        if a.kind() in ["default", "assigned"] or getattr(a, "is_disabled", False)
    ]
    if params["search_query"]:
        filtered_powers = search_queryset(
            powers, params["search_query"], ["name", "discipline__name"]
        )
        assigns = build_virtual_psyker_power_assignments(filtered_powers, fighter)
    else:
        assigns = all_assigns
    available_disciplines = group_available_assignments(assigns, "disc")
    for disc_data in available_disciplines:
        disc_data["discipline"] = disc_data.pop("group")
        disc_data["powers"] = disc_data.pop("items")

    context = {
        "list": lst,
        "fighter": fighter,
        "powers": powers,
        "assigns": assigns,
        "current_powers": current_powers,
        "available_disciplines": available_disciplines,
        "error_message": None,
        **params,
    }
    assert_equivalent("core/list_fighter_psyker_powers_edit.html", context, request)
