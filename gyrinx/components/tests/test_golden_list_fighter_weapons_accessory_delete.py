"""Golden-equivalence test for the weapon-accessory delete page."""

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
def test_list_fighter_weapons_accessory_delete_matches_legacy(
    user, make_list, make_list_fighter, make_weapon_with_accessory
):
    from gyrinx.core.models.list import ListFighterEquipmentAssignment

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    weapon, accessory = make_weapon_with_accessory()

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )
    assignment.weapon_accessories_field.add(accessory)
    # Refresh to clear cached cost state, as the view fetches it fresh.
    assignment = ListFighterEquipmentAssignment.objects.get(id=assignment.id)

    default_url = (
        reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
        + f"?flash={assignment.id}#{fighter.id}"
    )

    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "assign": assignment,
        "accessory": accessory,
        "accessory_cost": assignment.accessory_cost_int(accessory),
        "return_url": default_url,
    }
    assert_equivalent(
        "core/list_fighter_weapons_accessory_delete.html", context, request
    )
