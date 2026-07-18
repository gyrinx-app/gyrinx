"""Golden-equivalence tests for ``core/list_fighter_equipment_sell.html``.

The one template drives three steps (selection / confirm / summary) selected by
the ``step`` context key. Each test below reproduces the exact context the view's
GET branch builds for that step and asserts byte-equivalence with the legacy
template. Where the view passes a real ``ListFighterEquipmentAssignment`` but the
template only reads a single attribute off it (``assign.is_weapon`` in selection,
``assign.id`` in confirm), a lightweight stand-in is used — the golden harness
renders both the legacy template and the component with the *same* object, so the
comparison stays exact.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.forms.list import EquipmentSellSelectionForm

TEMPLATE = "core/list_fighter_equipment_sell.html"


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_sell_equipment_selection_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Stash", owner=user)

    items = [
        {
            "name": "Lasgun",
            "total_cost": 15,
            "upgrades": [SimpleNamespace(name="Gold Plating")],
        },
        {"name": "Frag Grenade", "total_cost": 30},
    ]
    forms = [
        (item, EquipmentSellSelectionForm(prefix=str(i)))
        for i, item in enumerate(items)
    ]
    context = {
        "list": lst,
        "fighter": fighter,
        # Selection template only reads assign.is_weapon.
        "assign": SimpleNamespace(is_weapon=False),
        "forms": forms,
        "step": "selection",
    }
    assert_equivalent(TEMPLATE, context, _request(user))


@pytest.mark.django_db
def test_sell_equipment_confirm_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Stash", owner=user)

    sell_data = [
        {
            "name": "Lasgun",
            "type": "equipment",
            "base_cost": 15,
            "total_cost": 15,
            "price_method": "roll_auto",
            "roll_manual_d6": None,
            "price_manual_value": None,
            "upgrades": [{"name": "Gold Plating"}],
        },
        {
            "name": "Frag Grenade",
            "type": "equipment",
            "base_cost": 30,
            "total_cost": 30,
            "price_method": "roll_manual",
            "roll_manual_d6": 4,
            "price_manual_value": None,
            "upgrades": [],
        },
        {
            "name": "Autopistol",
            "type": "equipment",
            "base_cost": 10,
            "total_cost": 10,
            "price_method": "price_manual",
            "roll_manual_d6": None,
            "price_manual_value": 8,
            "upgrades": [],
        },
    ]
    context = {
        "list": lst,
        "fighter": fighter,
        # Confirm template only reads assign.id (for the back-link URL).
        "assign": SimpleNamespace(id=uuid.uuid4()),
        "sell_data": sell_data,
        "step": "confirm",
    }
    assert_equivalent(TEMPLATE, context, _request(user))


@pytest.mark.django_db
def test_sell_equipment_summary_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Stash", owner=user)

    sale_results = {
        "total_credits": 42,
        "dice_rolls": [3, 5],
        "sale_details": [
            {"name": "Lasgun", "total_cost": 15, "sale_price": 5, "dice_roll": 3},
            {
                "name": "Autopistol",
                "total_cost": 10,
                "sale_price": 8,
                "dice_roll": None,
            },
        ],
    }
    context = {
        "list": lst,
        "fighter": fighter,
        "sale_results": sale_results,
        "step": "summary",
    }
    assert_equivalent(TEMPLATE, context, _request(user))
