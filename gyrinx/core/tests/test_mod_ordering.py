"""Ordering of the modifications that build a fighter's statline.

Order is only observable when a "set" modification is involved, because
improve/worsen are additive. A set discards whatever it is applied to, so
whether it wins depends entirely on what comes after it.
"""

import pytest

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentModFighterStat,
)
from gyrinx.core.models import ListFighter, ListFighterAdvancement
from gyrinx.core.models.list import ListFighterEquipmentAssignment


def shown(fighter, stat):
    fresh = ListFighter.objects.get(pk=fighter.pk)
    for entry in fresh.statline:
        if entry.field_name == stat:
            return entry.value
    raise AssertionError(f"{stat} missing from statline")


@pytest.fixture
def wheels():
    """Equipment that fixes a fighter's movement, rather than adjusting it."""
    category, _ = ContentEquipmentCategory.objects.get_or_create(name="Set Gear")
    gear = ContentEquipment.objects.create(
        name="Ash Wheels", category=category, cost="0"
    )
    gear.modifiers.add(
        ContentModFighterStat.objects.create(stat="movement", mode="set", value='8"')
    )
    return gear


def give(fighter, gear):
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=gear
    )


def advance(fighter, user, stat):
    return ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased=stat,
        uses_mod_system=True,
        xp_cost=5,
        cost_increase=5,
        owner=user,
    )


@pytest.mark.django_db
def test_gear_that_sets_a_stat_wins_over_an_advancement(
    user, make_list, make_list_fighter, wheels
):
    """An advancement must not stack on top of a stat the gear fixes.

    Advancements used to live in the fighter's override field, which a set
    discarded. Moving them onto the mod system and applying them after the
    set made them add to it instead, inflating movement on real fighters.
    """
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Ashwheel Drax")
    give(fighter, wheels)
    advance(fighter, user, "movement")

    assert shown(fighter, "movement") == '8"'


@pytest.mark.django_db
def test_several_advancements_still_do_not_stack_on_a_set(
    user, make_list, make_list_fighter, wheels
):
    """The worst real case ran to four advancements over a set value."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Four Advancements")
    give(fighter, wheels)
    for _ in range(4):
        advance(fighter, user, "movement")

    assert shown(fighter, "movement") == '8"'


@pytest.mark.django_db
def test_an_advancement_still_applies_without_a_set(user, make_list, make_list_fighter):
    """The reordering must not stop ordinary advancements working."""
    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Plain Fighter")
    base = shown(fighter, "movement")
    advance(fighter, user, "movement")

    assert shown(fighter, "movement") != base
