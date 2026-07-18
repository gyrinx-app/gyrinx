"""Golden-equivalence test for the single-weapon profile edit page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_weapon_edit_matches_legacy(
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

    # Standard (free, unnamed) profile — renders in section 1 (uses the shared
    # assign-name partial because it has no name).
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
    # Paid, named profile — assigned to the weapon, renders in section 2.
    paid = make_weapon_profile(
        weapon,
        name="Krak",
        cost=25,
        range_long="24",
        strength="6",
        armour_piercing="2",
        damage="2",
        ammo="6+",
    )

    created = fighter.assign(weapon, weapon_profiles=[paid], weapon_accessories=[])
    assignment = ListFighterEquipmentAssignment.objects.with_related_data().get(
        pk=created.pk
    )
    assign = VirtualListFighterEquipmentAssignment.from_assignment(assignment)

    # Available (not-yet-added) profile — section 3. Mirrors the dict shape the
    # view builds for ``profiles``.
    profiles = [
        {
            "id": paid.id,
            "name": "Rad-phage",
            "cost_int": 15,
            "cost_display": "15¢",
            "range_short": "",
            "range_long": "18",
            "accuracy_short": "",
            "accuracy_long": "-1",
            "strength": "5",
            "armour_piercing": "1",
            "damage": "1",
            "ammo": "5+",
            "traits": "Rapid Fire (1)",
        }
    ]

    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "assign": assign,
        "profiles": profiles,
        "error_message": None,
    }
    assert_equivalent("core/list_fighter_weapon_edit.html", context, request)
