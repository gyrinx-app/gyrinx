"""Golden-equivalence test for the weapon-profile delete page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_weapon_profile_delete_matches_legacy(
    user, make_list, make_list_fighter, make_weapon_with_profile
):
    from gyrinx.content.models import VirtualWeaponProfile
    from gyrinx.core.models.list import (
        ListFighterEquipmentAssignment,
        VirtualListFighterEquipmentAssignment,
    )

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    weapon, profile = make_weapon_with_profile()

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )
    assignment.weapon_profiles_field.add(profile)
    # Refresh to clear cached cost state, as the view fetches it fresh.
    assignment = ListFighterEquipmentAssignment.objects.get(id=assignment.id)

    virtual_profile = VirtualWeaponProfile(profile=profile)
    profile_cost = assignment.profile_cost_int(virtual_profile)

    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "assign": VirtualListFighterEquipmentAssignment.from_assignment(assignment),
        "profile": profile,
        "profile_cost": profile_cost,
    }
    assert_equivalent("core/list_fighter_weapon_profile_delete.html", context, request)
