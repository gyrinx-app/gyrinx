"""Tests for the 0196 migration that moves stat advancements onto the mod system."""

import pytest
from django.apps import apps

from gyrinx.core.models import ListFighter, ListFighterAdvancement

migration = __import__(
    "gyrinx.core.migrations.0196_convert_legacy_stat_advancements",
    fromlist=["convert", "improved"],
)


def stat_value(fighter, field_name):
    """The value shown for a stat on the fighter's statline."""
    fresh = ListFighter.objects.get(pk=fighter.pk)
    for stat in fresh.statline:
        if stat.field_name == field_name:
            return stat.value
    raise AssertionError(f"{field_name} not in statline")


def make_advancement(fighter, user, stat, *, uses_mod_system):
    return ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased=stat,
        uses_mod_system=uses_mod_system,
        xp_cost=5,
        cost_increase=5,
        owner=user,
    )


def test_improved_replicates_legacy_arithmetic():
    # Target rolls improve downwards
    assert migration.improved("4+", 1) == "3+"
    assert migration.improved("4+", 2) == "2+"
    # Distances keep their quote mark
    assert migration.improved('4"', 1) == '5"'
    # Plain values just count up
    assert migration.improved("3", 2) == "5"
    # Anything unparseable cannot be attributed
    assert migration.improved("-", 1) is None
    assert migration.improved("", 1) is None
    assert migration.improved("4+", 0) is None


@pytest.mark.django_db
def test_convert_leaves_the_displayed_statline_untouched(
    user, make_list, make_list_fighter
):
    """Converting legacy advancements must not move the fighter's stats."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Legacy Fighter")

    # Base weapon skill is 5+; two legacy advancements wrote 3+ into the override.
    make_advancement(fighter, user, "weapon_skill", uses_mod_system=False)
    make_advancement(fighter, user, "weapon_skill", uses_mod_system=False)
    fighter.weapon_skill_override = "3+"
    fighter.save()

    assert stat_value(fighter, "weapon_skill") == "3+"

    migration.convert(apps, None)

    fighter.refresh_from_db()
    assert fighter.weapon_skill_override is None
    assert not ListFighterAdvancement.objects.filter(
        fighter=fighter, uses_mod_system=False
    ).exists()
    # Same value, now computed from the advancements rather than stored
    assert stat_value(fighter, "weapon_skill") == "3+"


@pytest.mark.django_db
def test_repair_drops_a_double_counted_improvement(user, make_list, make_list_fighter):
    """An override duplicating a mod-system advancement is applied twice."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Copied Fighter")

    # What copy_attributes_to used to produce: the override a legacy
    # advancement wrote, alongside an advancement on the mod system.
    make_advancement(fighter, user, "ballistic_skill", uses_mod_system=True)
    fighter.ballistic_skill_override = "4+"
    fighter.save()

    # Base is 5+ and one advancement was taken, so 4+ is correct — but the
    # override and the mod both apply, so the fighter shows 3+.
    assert stat_value(fighter, "ballistic_skill") == "3+"

    migration.convert(apps, None)

    fighter.refresh_from_db()
    assert fighter.ballistic_skill_override is None
    assert stat_value(fighter, "ballistic_skill") == "4+"


@pytest.mark.django_db
def test_manual_stat_edits_are_left_alone(user, make_list, make_list_fighter):
    """An override that no advancement could have written is a manual edit."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Hand Edited Fighter")

    # One legacy advancement on a 5+ base would have written 4+, not 2+.
    make_advancement(fighter, user, "weapon_skill", uses_mod_system=False)
    fighter.weapon_skill_override = "2+"
    fighter.save()

    migration.convert(apps, None)

    fighter.refresh_from_db()
    assert fighter.weapon_skill_override == "2+"
    # The advancement stays legacy, so the value is not applied twice
    assert ListFighterAdvancement.objects.filter(
        fighter=fighter, uses_mod_system=False
    ).exists()
    assert stat_value(fighter, "weapon_skill") == "2+"


@pytest.mark.django_db
def test_repair_ignores_an_unrelated_override(user, make_list, make_list_fighter):
    """A manual edit alongside a mod-system advancement is legitimate."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Mixed Fighter")

    make_advancement(fighter, user, "toughness", uses_mod_system=True)
    # Base toughness is 3, one advancement would give 4 — 6 is a manual edit.
    fighter.toughness_override = "6"
    fighter.save()

    migration.convert(apps, None)

    fighter.refresh_from_db()
    assert fighter.toughness_override == "6"


@pytest.mark.django_db
def test_advancements_shadowed_by_a_stat_override_are_left_alone(
    user, make_list, make_list_fighter, content_fighter
):
    """A fighter reading its stats from the newer override store is skipped.

    Its legacy override — and so the advancement that wrote it — is inert.
    Converting would start applying an improvement that currently does
    nothing, moving the displayed stat.
    """
    from gyrinx.content.models.statline import (
        ContentStat,
        ContentStatline,
        ContentStatlineType,
        ContentStatlineTypeStat,
    )
    from gyrinx.core.models.list import ListFighterStatOverride

    statline_type = ContentStatlineType.objects.create(name="Custom Type")
    stat = ContentStat.objects.get(field_name="weapon_skill")
    type_stat = ContentStatlineTypeStat.objects.create(
        statline_type=statline_type, stat=stat, position=1
    )
    statline = ContentStatline.objects.create(
        content_fighter=content_fighter, statline_type=statline_type
    )
    statline.stats.create(statline_type_stat=type_stat, value="5+")

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Custom Statline Fighter")

    make_advancement(fighter, user, "weapon_skill", uses_mod_system=False)
    fighter.weapon_skill_override = "4+"
    fighter.save()
    ListFighterStatOverride.objects.create(
        list_fighter=fighter, content_stat=type_stat, value="3+", owner=user
    )

    before = stat_value(fighter, "weapon_skill")

    migration.convert(apps, None)

    fighter.refresh_from_db()
    assert ListFighterAdvancement.objects.filter(
        fighter=fighter, uses_mod_system=False
    ).exists()
    assert stat_value(fighter, "weapon_skill") == before


@pytest.mark.django_db
def test_copy_attributes_to_keeps_advancements_on_the_same_system(
    user, make_list, make_list_fighter
):
    """Copying must not flip a legacy advancement onto the mod system.

    The copy carries the override across, so a flipped advancement would apply
    the same improvement twice on the copy.
    """
    lst = make_list("Test List")
    source = make_list_fighter(lst, "Source Fighter")
    make_advancement(source, user, "weapon_skill", uses_mod_system=False)
    source.weapon_skill_override = "4+"
    source.save()

    target = make_list_fighter(lst, "Target Fighter")
    source.copy_attributes_to(target)

    copied = ListFighterAdvancement.objects.get(fighter=target)
    assert copied.uses_mod_system is False
    assert stat_value(target, "weapon_skill") == stat_value(source, "weapon_skill")
