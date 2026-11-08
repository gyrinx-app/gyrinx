"""Assignments reference exactly one assignable through a per-kind foreign key.

The abstract assignable mixin has no shared table. Database constraints reject
ambiguous assignments, and startup checks detect missing kind declarations.
"""

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from n26.core.checks import every_assignable_has_a_column
from n26.core.models import Assignment, Gang
from n26.core.models.assignment import ASSIGNABLE_FIELDS
from n26.library.models import (
    AddsAssignable,
    Modifier,
    Subtype,
    TargetsMiniature,
    Wargear,
    Weapon,
    WeaponProfile,
)
from n26.library.models.assignable import Assignable

pytestmark = [pytest.mark.django_db, pytest.mark.core]


def make_modifier(name):
    """Create a valid modifier with one scope and one effect."""
    return Modifier.objects.create(
        name=name,
        targets_miniature=TargetsMiniature.objects.create(),
        adds_assignable=AddsAssignable.objects.create(
            subtype=Subtype.objects.create(name=f"{name} subtype")
        ),
    )


@pytest.fixture
def gang(gang_type):
    return Gang.objects.create(name="The Long Hunt", gang_type=gang_type)


@pytest.fixture
def mesh(db):
    return Wargear.objects.create(name="Mesh Armour")


class TestTheMixin:
    def test_assignable_is_abstract(self):
        assert Assignable._meta.abstract
        assert not any(
            model._meta.model_name == "assignable" for model in apps.get_models()
        )

    def test_display_uses_the_annotation(self, db):
        assert str(Wargear.objects.create(name="Mesh Armour")) == "Mesh Armour"
        ammo = WeaponProfile.objects.create(
            name="Salvo ammo",
            annotation="Combat Shotgun",
            weapon=Weapon.objects.create(name="Combat Shotgun"),
        )
        assert str(ammo) == "Salvo ammo (Combat Shotgun)"

    def test_each_kind_gets_its_own_modifier_table(self, db):
        """Fields on the abstract mixin create separate modifier join tables for each
        concrete kind.
        """
        mounted = make_modifier("Grants Mounted")
        weapon = Weapon.objects.create(name="Cutter")
        gear = Wargear.objects.create(name="Mesh Armour")
        weapon.modifiers.add(mounted)
        gear.modifiers.add(mounted)

        assert list(weapon.modifiers.all()) == [mounted]
        assert list(gear.modifiers.all()) == [mounted]
        assert list(mounted.library_weapon_set.all()) == [weapon]
        assert list(mounted.library_wargear_set.all()) == [gear]

    def test_join_tables_really_are_separate(self):
        weapon_table = Weapon.modifiers.through._meta.db_table
        wargear_table = Wargear.modifiers.through._meta.db_table
        assert weapon_table != wargear_table


class TestExactlyOneAssignable:
    def test_naming_none_is_rejected(self, gang):
        with pytest.raises(IntegrityError), transaction.atomic():
            Assignment.objects.create(gang=gang)

    def test_naming_two_is_rejected(self, gang, mesh):
        weapon = Weapon.objects.create(name="Combat Shotgun")
        with pytest.raises(IntegrityError), transaction.atomic():
            Assignment.objects.create(gang=gang, wargear=mesh, weapon=weapon)

    def test_clean_says_so_readably(self, gang):
        with pytest.raises(ValidationError, match="exactly one assignable"):
            Assignment(gang=gang).clean()


class TestRouting:
    def test_the_assignable_keyword_finds_the_right_column(self, gang, mesh):
        assignment = Assignment.objects.create(assignable=mesh, gang=gang)

        assert assignment.wargear == mesh
        assert assignment.weapon is None
        assert assignment.assignable == mesh

    def test_an_unknown_kind_is_refused_with_a_useful_message(self, gang, person_type):
        # ProfileType is content but cannot be assigned directly.
        with pytest.raises(ValueError, match="not something a"):
            Assignment(assignable=person_type, gang=gang)

    def test_reading_the_assignable_costs_no_queries_for_empty_columns(
        self, gang, mesh, django_assert_num_queries
    ):
        Assignment.objects.create(assignable=mesh, gang=gang)
        assignment = Assignment.objects.get()
        with django_assert_num_queries(1):
            assert assignment.assignable == mesh

    def test_a_whole_queryset_resolves_in_one_query(
        self, gang, mesh, django_assert_num_queries
    ):
        """Resolve mixed assignment kinds through joins rather than a query for each
        kind.
        """
        weapon = Weapon.objects.create(name="Combat Shotgun")
        Assignment.objects.create(assignable=mesh, gang=gang)
        Assignment.objects.create(assignable=weapon, gang=gang)

        with django_assert_num_queries(1):
            names = sorted(str(a.assignable) for a in Assignment.with_assignables())
        assert names == ["Combat Shotgun", "Mesh Armour"]


class TestSettlingAChoice:
    """chosen_for records the assignment whose choice a pick answers."""

    def test_a_pick_points_at_what_asked(self, gang, db):
        from n26.library.models import Pickable, Picklist, Slot, SlotType

        legacy = SlotType.objects.create(name="Gang Legacy")
        picklist = Picklist.objects.create(name="Gang Legacies", slot_type=legacy)
        slot = Assignment.objects.create(
            assignable=Slot.objects.create(
                name="Gang Legacy", slot_type=legacy, picklist=picklist
            ),
            gang=gang,
        )
        pick = Assignment.objects.create(
            assignable=Pickable.objects.create(name="Cawdor", slot_type=legacy),
            gang=gang,
            caused_by=slot,
            chosen_for=slot,
        )

        assert list(slot.picks.all()) == [pick]

    def test_it_is_the_same_link_the_cause_is(self):
        """Use matching deletion policies when chosen_for and caused_by reference the
        same assignment.
        """
        cause = Assignment._meta.get_field("caused_by")
        chosen_for = Assignment._meta.get_field("chosen_for")
        assert chosen_for.remote_field.on_delete is cause.remote_field.on_delete

    def test_the_slot_it_settles_cannot_be_deleted_under_it(self):
        """Protect slot content referenced by an existing player choice."""
        from django.db.models.deletion import PROTECT

        named = Assignment._meta.get_field("chosen_for_slot")
        assert named.remote_field.on_delete is PROTECT
        assert named.null is True

    def test_the_offer_it_settles_gives_way_instead(self):
        """Modifier offers are replaced when reauthored; clear the old reference
        while retaining the player's answer.
        """
        from django.db.models.deletion import SET_NULL

        named = Assignment._meta.get_field("chosen_for_offer")
        assert named.remote_field.on_delete is SET_NULL
        assert named.null is True


class TestTheStartupCheck:
    def test_it_passes_as_things_stand(self):
        assert every_assignable_has_a_column(None) == []

    def test_every_declared_field_exists_on_the_model(self):
        for field in ASSIGNABLE_FIELDS:
            assert Assignment._meta.get_field(field)

    def test_a_forgotten_kind_is_an_error(self, monkeypatch):
        trimmed = dict(ASSIGNABLE_FIELDS)
        trimmed.pop("wargear")
        monkeypatch.setattr(
            "n26.core.models.assignment.ASSIGNABLE_FIELDS", trimmed, raising=True
        )

        errors = every_assignable_has_a_column(None)
        assert [error.id for error in errors] == ["n26.E001"]
        assert "library.wargear" in errors[0].msg

    def test_a_stale_declaration_is_an_error(self, monkeypatch):
        extended = dict(ASSIGNABLE_FIELDS)
        extended["profile_type"] = "library.ProfileType"
        monkeypatch.setattr(
            "n26.core.models.assignment.ASSIGNABLE_FIELDS", extended, raising=True
        )

        errors = every_assignable_has_a_column(None)
        assert [error.id for error in errors] == ["n26.E002"]
