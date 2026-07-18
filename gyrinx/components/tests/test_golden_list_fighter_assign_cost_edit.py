"""Golden-equivalence test: the assignment cost-edit page matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_assign_cost_edit_matches_legacy(
    user, make_list, make_list_fighter, make_equipment
):
    from gyrinx.core.forms.list import ListFighterEquipmentAssignmentCostForm

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    equipment = make_equipment("Laspistol")
    assignment = fighter.assign(equipment)
    form = ListFighterEquipmentAssignmentCostForm(instance=assignment)

    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "assign": assignment,
        "form": form,
        "error_message": None,
        "action_url": "core:list-fighter-gear-cost-edit",
        "back_url": "core:list-fighter-gear-edit",
    }
    assert_equivalent("core/list_fighter_assign_cost_edit.html", context, request)
