"""Golden-equivalence test for the reassign-equipment page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.forms.list import EquipmentReassignForm
from gyrinx.core.models.list import ListFighterEquipmentAssignment


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_assign_reassign_matches_legacy(
    user, make_list, make_list_fighter, make_equipment
):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    # Another fighter to receive the reassignment (populates the select options).
    make_list_fighter(lst, "Grunt", owner=user)

    equipment = make_equipment("Test Weapon", cost="50")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    # Mirror the view's GET branch: form seeded with the available fighters.
    target_fighters = lst.listfighter_set.filter(archived=False).exclude(id=fighter.id)
    form = EquipmentReassignForm(fighters=target_fighters)

    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "assign": assignment,
        "form": form,
        "is_weapon": False,
        "back_url": "core:list-fighter-gear-edit",
    }
    assert_equivalent("core/list_fighter_assign_reassign.html", context, request)
