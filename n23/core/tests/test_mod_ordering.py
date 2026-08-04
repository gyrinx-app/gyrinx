"""Ordering of the modifications that build a fighter's statline.

Order is only observable when a "set" modification is involved, because
improve/worsen are additive. A set discards whatever it is applied to, so
whether it wins depends entirely on what comes after it.
"""

import pytest

from n23.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentModFighterStat,
)
from n23.core.models import ListFighter, ListFighterAdvancement
from n23.core.models.list import ListFighterEquipmentAssignment


def shown(fighter, stat):
    fresh = ListFighter.objects.get(pk=fighter.pk)
    for entry in fresh.statline:
        if entry.field_name == stat:
            return entry.value
    raise AssertionError(f"{stat} missing from statline")


@pytest.fixture
def wheels():
    """Equipment that fixes a fighter's movement, rather than adjusting it."""
    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Set Gear", defaults={"group": "Vehicle & Mount"}
    )
    gear = ContentEquipment.objects.create(
        name="Ash Wheels", category=category, cost="0"
    )
    mod, _ = ContentModFighterStat.objects.get_or_create(
        stat="movement", mode="set", value='8"'
    )
    gear.modifiers.add(mod)
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
    assert shown(fighter, "movement") == '5"'

    advance(fighter, user, "movement")

    assert shown(fighter, "movement") == '6"'


@pytest.mark.django_db
def test_an_injury_still_worsens_a_stat_the_gear_set(
    user, make_list, make_list_fighter, wheels
):
    """Injuries apply after equipment, so a set is not the last word."""
    from n23.content.models import ContentInjury, ContentInjuryDefaultOutcome
    from n23.core.models.list import ListFighterInjury

    injury = ContentInjury.objects.create(
        name="Buckled Wheel",
        phase=ContentInjuryDefaultOutcome.NO_CHANGE,
    )
    injury.modifiers.add(
        ContentModFighterStat.objects.get_or_create(
            stat="movement", mode="worsen", value="1"
        )[0]
    )

    lst = make_list("Gang", status="campaign_mode")
    fighter = make_list_fighter(lst, "Injured Rider")
    give(fighter, wheels)
    ListFighterInjury.objects.create(fighter=fighter, injury=injury, owner=user)

    # The gear sets 8"; the injury still takes one off it
    assert shown(fighter, "movement") == '7"'


@pytest.mark.django_db
def test_advancement_set_and_injury_together(
    user, make_list, make_list_fighter, wheels
):
    """All three at once: the advancement is swallowed, the injury is not."""
    from n23.content.models import ContentInjury, ContentInjuryDefaultOutcome
    from n23.core.models.list import ListFighterInjury

    injury = ContentInjury.objects.create(
        name="Cracked Axle",
        phase=ContentInjuryDefaultOutcome.NO_CHANGE,
    )
    injury.modifiers.add(
        ContentModFighterStat.objects.get_or_create(
            stat="movement", mode="worsen", value="1"
        )[0]
    )

    lst = make_list("Gang", status="campaign_mode")
    fighter = make_list_fighter(lst, "Injured Ashwheel")
    give(fighter, wheels)
    advance(fighter, user, "movement")
    ListFighterInjury.objects.create(fighter=fighter, injury=injury, owner=user)

    assert shown(fighter, "movement") == '7"'


@pytest.mark.django_db
def test_a_roll_result_does_not_stack_on_a_set_either(
    user, make_list, make_list_fighter, wheels
):
    """Power Boosts are permanent improvements, same as advancements.

    Both roll-result stat mods in content improve movement or initiative, and
    every set-mode mod targets movement — so this is the same collision.
    """
    from n23.content.models.roll_table import ContentRollTable, ContentRollTableRow
    from n23.core.models.list import ListFighterRollResult

    table = ContentRollTable.objects.create(name="Power Boost")
    row = ContentRollTableRow.objects.create(
        table=table, roll_value="1", name="Speed Boost"
    )
    row.modifiers.add(
        ContentModFighterStat.objects.get_or_create(
            stat="movement", mode="improve", value="1"
        )[0]
    )

    lst = make_list("Gang")
    fighter = make_list_fighter(lst, "Boosted Rider")
    give(fighter, wheels)
    ListFighterRollResult.objects.create(fighter=fighter, row=row, owner=user)

    assert shown(fighter, "movement") == '8"'
