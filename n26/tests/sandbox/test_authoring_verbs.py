"""The authoring grammar — the verbs the admin's forms compile to.

Step 0 of design/authoring-build-plan.md:
conditions *nest* inside scope verbs instead of exploding into keyword
arguments, effect verbs carry a prefix saying when they happen (``ef_``
at read, ``op_`` at purchase), and modifiers attach via ``attach_to`` /
``attach_modifiers_to``. The example suites still speak the old sandbox
names — thin aliases in ``tests.sandbox.actions`` — so this file covers
what only the new grammar says.

Conditions are **rows** (``HasSubtypes``, ``CounterAtLeast``): a new way
of narrowing is a new small model FK'ing the scope, never a new column
on it. A boot check (n26.E003/E004) keeps the scope's fold honest.
"""

import pytest

from n26.library.authoring import (
    attach_modifiers_to,
    counter_at_least,
    create_counter,
    create_rule,
    create_subtype,
    create_trait,
    ef_adds,
    has_subtypes,
    has_traits,
    is_profile_type,
    modifier,
    targets_model,
    targets_weapons,
)
from n26.library.models import CounterAtLeast, HasSubtypes, IsProfileType

pytestmark = pytest.mark.django_db


class TestConditionsNest:
    def test_conditions_become_rows_on_the_scope(self, default_pack):
        leader = create_subtype("Leader")
        champion = create_subtype("Champion")
        xp = create_counter("XP")

        scope = targets_model(
            has_subtypes(leader, champion),
            counter_at_least(xp, 75),
        )

        (subtype_row,) = HasSubtypes.objects.filter(scope=scope)
        assert set(subtype_row.subtypes.all()) == {leader, champion}
        (threshold_row,) = CounterAtLeast.objects.filter(scope=scope)
        assert threshold_row.counter == xp
        assert threshold_row.at_least == 75
        # The folded sentence — what plan traces and auto-names compose.
        # Subtypes read in their own Meta order (by name), as before.
        assert str(scope) == "Champion or Leader models, at XP 75+"

    def test_an_unconditioned_scope_reads_as_the_model(self, default_pack):
        assert str(targets_model()) == "the model"

    def test_the_type_condition_names_fighters_or_vehicles(
        self, default_pack, fighter_type, vehicle_type
    ):
        scope = targets_model(is_profile_type(fighter_type))
        (row,) = IsProfileType.objects.filter(scope=scope)
        assert list(row.profile_types.all()) == [fighter_type]
        assert str(scope) == "Fighter models"
        assert (
            str(targets_model(is_profile_type(vehicle_type, negate=True)))
            == "every model except Vehicle"
        )

    def test_an_empty_type_condition_narrows_nothing(self, default_pack):
        assert (
            targets_model(is_profile_type()).as_selector()
            == targets_model().as_selector()
        )

    def test_the_weapon_condition(self, default_pack):
        melee = create_trait("Melee")
        assert str(targets_weapons(has_traits(melee))) == "weapons with Melee"
        assert str(targets_weapons()) == "all weapons"

    def test_conditions_refuse_the_wrong_scope(self, default_pack):
        melee = create_trait("Melee")
        with pytest.raises(ValueError, match="use targets_weapons"):
            targets_model(has_traits(melee))
        leader = create_subtype("Leader")
        with pytest.raises(ValueError, match="cannot take"):
            targets_weapons(has_subtypes(leader))


class TestGlue:
    def test_attach_modifiers_to_shares_one_rule_between_carriers(self, default_pack):
        """Written once, attachable to many carriers — the reusable
        modifier the composer's ``make_reusable`` flag names."""
        mounted = create_subtype("Mounted")
        reusable = modifier("Grants Mounted", targets_model(), ef_adds(mounted))
        cutter = create_rule("Cutter Rig")
        helamite = create_rule("Helamite Saddle")

        attach_modifiers_to(cutter, [reusable])
        attach_modifiers_to(helamite, [reusable])

        assert list(cutter.modifiers.all()) == [reusable]
        assert list(helamite.modifiers.all()) == [reusable]

    def test_attach_to_hangs_the_modifier_at_creation(self, default_pack):
        mounted = create_subtype("Mounted")
        carrier = create_rule("Saddle")
        row = modifier(
            "Saddle grants Mounted",
            targets_model(),
            ef_adds(mounted),
            attach_to=carrier,
        )
        assert list(carrier.modifiers.all()) == [row]


class TestAWeaponsOwnLineNamesItself:
    """A profile's annotation defaults to its weapon's name, so the
    column must take any name the name column took."""

    def test_a_long_weapon_name_fits_its_profiles_annotation(self):
        from n26.library.authoring import add_weapon_profile, create_weapon

        weapon = create_weapon("W" * 200, price=15)
        profile = add_weapon_profile(weapon)
        assert profile.annotation == weapon.name
