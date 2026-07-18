"""Golden-equivalence test for the weapon-accessories edit page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_weapons_accessories_edit_matches_legacy(
    user,
    make_list,
    make_list_fighter,
    make_equipment,
    make_weapon_profile,
):
    from gyrinx.core.models.list import (
        ListFighterEquipmentAssignment,
        VirtualListFighterEquipmentAssignment,
    )

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    weapon = make_equipment("Boltgun", category="Basic Weapons", cost="55")
    # Standard (free, unnamed) profile — renders the base weapon stats row.
    make_weapon_profile(
        weapon,
        name="",
        cost=0,
        range_long="24",
        strength="4",
        armour_piercing="1",
        damage="1",
        ammo="6+",
    )

    created = fighter.assign(weapon, weapon_profiles=[], weapon_accessories=[])
    assignment = ListFighterEquipmentAssignment.objects.with_related_data().get(
        pk=created.pk
    )
    assign = VirtualListFighterEquipmentAssignment.from_assignment(assignment)

    # Available accessories — mirrors the dict shape the view builds.
    accessories = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "name": "Telescopic Sight",
            "cost_int": 25,
            "cost_display": "25¢",
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "Gunfighter Grip",
            "cost_int": 0,
            "cost_display": "",
        },
    ]

    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "assign": assign,
        "accessories": accessories,
        "filter": "equipment-list",
        "search_query": "",
        "error_message": None,
        "mode": "edit",
    }
    assert_equivalent(
        "core/list_fighter_weapons_accessories_edit.html", context, request
    )
