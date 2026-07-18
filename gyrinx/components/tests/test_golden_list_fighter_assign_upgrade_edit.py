"""Golden-equivalence test for list_fighter_assign_upgrade_edit."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
)
from gyrinx.core.forms.list import ListFighterEquipmentAssignmentUpgradeForm
from gyrinx.core.models.list import ListFighterEquipmentAssignment


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_assign_upgrade_edit_matches_legacy(
    user, make_list, make_list_fighter
):
    category = ContentEquipmentCategory.objects.get_or_create(
        name="Personal Equipment",
        defaults={"group": "Gear"},
    )[0]
    equipment = ContentEquipment.objects.create(
        name="Cyberteknika Implant",
        category=category,
        rarity="C",
        cost="50",
        upgrade_mode=ContentEquipment.UpgradeMode.SINGLE,
        upgrade_stack_name="Augmentation",
    )
    for i, name in enumerate(["Basic", "Advanced", "Superior"]):
        ContentEquipmentUpgrade.objects.create(
            name=name,
            equipment=equipment,
            cost=str((i + 1) * 10),
            position=i,
        )

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment,
    )

    form = ListFighterEquipmentAssignmentUpgradeForm(instance=assignment)
    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "assign": assignment,
        "action_url": "core:list-fighter-gear-upgrade-edit",
        "back_url": "core:list-fighter-gear-edit",
        "form": form,
        "error_message": None,
    }
    assert_equivalent("core/list_fighter_assign_upgrade_edit.html", context, request)
