"""Golden-equivalence test for the upgrade delete confirmation page."""

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
def test_list_fighter_assign_upgrade_delete_confirm_matches_legacy(
    user, make_list, make_list_fighter, make_equipment_with_upgrades
):
    from gyrinx.core.models.list import ListFighterEquipmentAssignment

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    equipment, upgrade = make_equipment_with_upgrades()
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    return_url = reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])
    context = {
        "list": lst,
        "fighter": fighter,
        "assign": assignment,
        "upgrade": upgrade,
        "upgrade_cost": assignment._upgrade_cost_with_override(upgrade),
        "action_url": "core:list-fighter-gear-upgrade-delete",
        "return_url": return_url,
    }
    request = _request(user)
    assert_equivalent(
        "core/list_fighter_assign_upgrade_delete_confirm.html", context, request
    )
