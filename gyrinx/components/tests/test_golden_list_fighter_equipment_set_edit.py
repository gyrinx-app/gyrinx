"""Golden-equivalence test for the fighter equipment-set edit page component."""

from __future__ import annotations

import uuid

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_equipment_set_edit_matches_legacy(
    user, make_list, make_list_fighter
):
    from gyrinx.core.models.list import ListFighterEquipmentSet

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    equipment_set = ListFighterEquipmentSet.objects.create_with_user(
        user=user,
        list_fighter=fighter,
        name="Raid Kit",
        owner=lst.owner,
    )
    # The view builds `items` as plain dicts (id/name/is_weapon/included) from the
    # fighter's direct assignment wrappers; reproduce that shape directly so both
    # icon branches and both checked states are exercised.
    items = [
        {
            "id": uuid.uuid4(),
            "name": "Autopistol",
            "is_weapon": True,
            "included": True,
        },
        {
            "id": uuid.uuid4(),
            "name": "Mesh Armour",
            "is_weapon": False,
            "included": False,
        },
    ]
    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "equipment_set": equipment_set,
        "items": items,
    }
    assert_equivalent("core/list_fighter_equipment_set_edit.html", context, request)


@pytest.mark.django_db
def test_list_fighter_equipment_set_edit_empty_matches_legacy(
    user, make_list, make_list_fighter
):
    from gyrinx.core.models.list import ListFighterEquipmentSet

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    equipment_set = ListFighterEquipmentSet.objects.create_with_user(
        user=user,
        list_fighter=fighter,
        name="Raid Kit",
        owner=lst.owner,
    )
    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "equipment_set": equipment_set,
        "items": [],
    }
    assert_equivalent("core/list_fighter_equipment_set_edit.html", context, request)
