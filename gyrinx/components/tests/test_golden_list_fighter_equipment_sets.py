"""Golden-equivalence test for the fighter equipment-sets management page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _fighter_with_tools(user, make_list, make_list_fighter):
    """A list + fighter that has the "Tools of the Trade" rule.

    Mirrors the view: the manage page is only surfaced (with the sets UI) for a
    fighter carrying that rule. Refetch so ``has_tools_of_the_trade`` recomputes
    with the rule present.
    """
    from gyrinx.content.models import ContentRule
    from gyrinx.core.models.list import ListFighter

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    rule, _ = ContentRule.objects.get_or_create(name="Tools of the Trade")
    fighter.custom_rules.add(rule)
    fighter = ListFighter.objects.with_related_data().get(id=fighter.id)
    return lst, fighter


@pytest.mark.django_db
def test_equipment_sets_no_rule_matches_legacy(user, make_list, make_list_fighter):
    # A plain fighter lacks the rule, so the view renders the explanatory alert
    # with the minimal context.
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    request = _request(user)
    context = {"list": lst, "fighter": fighter}
    assert_equivalent("core/list_fighter_equipment_sets.html", context, request)


@pytest.mark.django_db
def test_equipment_sets_with_sets_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.core.models.list import ListFighterEquipmentSet

    lst, fighter = _fighter_with_tools(user, make_list, make_list_fighter)
    set_a = ListFighterEquipmentSet.objects.create_with_user(
        user=user, list_fighter=fighter, name="Raid Kit", owner=lst.owner
    )
    set_b = ListFighterEquipmentSet.objects.create_with_user(
        user=user, list_fighter=fighter, name="Backup", owner=lst.owner
    )
    # Reproduce the view's `equipment_sets` shape: an active set with a
    # comma-separated item summary, and an inactive set with nothing selected.
    equipment_sets = [
        {"set": set_a, "is_active": True, "item_names": ["Autopistol", "Mesh Armour"]},
        {"set": set_b, "is_active": False, "item_names": []},
    ]
    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "equipment_sets": equipment_sets,
        "has_active_set": True,
    }
    assert_equivalent("core/list_fighter_equipment_sets.html", context, request)


@pytest.mark.django_db
def test_equipment_sets_empty_matches_legacy(user, make_list, make_list_fighter):
    lst, fighter = _fighter_with_tools(user, make_list, make_list_fighter)
    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "equipment_sets": [],
        "has_active_set": False,
    }
    assert_equivalent("core/list_fighter_equipment_sets.html", context, request)
