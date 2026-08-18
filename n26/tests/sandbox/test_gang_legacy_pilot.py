"""Retiring the Gang Legacy slot pilot — the one operation that deletes.

The pilot is a hand-built slot type whose pickables carry nothing,
answered on one test gang. Retiring it must delete exactly what it
names, refuse the moment anything outside the pilot depends on it, and
leave the gang reconciling — a slot and its picks are free, so the
rating must not move by a credit.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.models import Assignment, LedgerEvent
from n26.core.reconcile import assert_reconciled
from n26.library.gang_legacy_pilot import Refused, apply, find
from n26.library.models import Pickable, Picklist, Slot, SlotType
from n26.tests.sandbox.actions import (
    choose,
    create_gang_type,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    found_gang,
    hire,
    modifier,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def pilot_world(db, default_pack, person_type, owner):
    """The pilot as production holds it: hollow machinery, and one test
    gang holding the slot by hand with answers behind it."""
    slot_type = create_slot_type("Gang Legacy")
    hollow = [create_pickable(name, slot_type) for name in ["Cawdor", "Ironhead Squat"]]
    picklist = create_picklist("All Gang Legacies", slot_type, members=hollow)
    slot = create_slot("Gang Legacy", slot_type, picklist, min_picks=0)

    gang_type = create_gang_type("Venators", starting_credits=2000)
    profile = create_profile("Squat Hunt Leader", person_type, gang_type, price=50)
    gang = found_gang("The Pilot Yard", gang_type, owner=owner, budget=2000)
    fighter = hire(gang, profile, "Grombrindal", paid=50)
    line = Assignment.objects.get(profile=profile, miniature_root=fighter)
    # The hand-placed experiment: the slot assigned directly under the
    # fighter's own line, then answered.
    held = Assignment.objects.create(
        slot=slot, miniature=fighter, caused_by=line, gang_root=gang
    )
    choose(held, hollow[0], slot=slot, miniature=fighter)
    return gang, fighter, slot_type, hollow, slot


class TestFindingThePilot:
    def test_it_names_everything_it_would_delete(self, pilot_world):
        pilot = find()

        assert pilot.ok and not pilot.nothing_here
        assert len(pilot.pickable_ids) == 2
        assert len(pilot.assignment_ids) == 2  # the held slot and its answer
        said = "\n".join(pilot.preview())
        assert "delete 2 assignments on The Pilot Yard" in said
        assert "2 hollow pickables" in said
        assert "prove the gang still reconciles" in said

    def test_no_pilot_means_nothing_to_retire(self, db, default_pack):
        pilot = find()

        assert pilot.nothing_here
        assert apply(pilot) == pilot.preview()

    def test_a_pickable_grown_a_purpose_is_refused(self, pilot_world):
        _, _, _, hollow, _ = pilot_world
        modifier(
            "Cawdor: does something now",
            targets_model(),
            _any_effect(),
            carried_by=hollow[0],
        )

        pilot = find()

        assert not pilot.ok
        assert any("grown a purpose" in problem for problem in pilot.problems)
        with pytest.raises(Refused):
            apply(pilot)

    def test_a_second_gang_answering_is_refused(self, pilot_world, person_type, owner):
        _, _, _, hollow, slot = pilot_world
        gang_type = create_gang_type("More Venators", starting_credits=2000)
        profile = create_profile("Another Hunter", person_type, gang_type, price=50)
        other = found_gang("Somebody Else", gang_type, owner=owner, budget=2000)
        fighter = hire(other, profile, "Stranger", paid=50)
        line = Assignment.objects.get(profile=profile, miniature_root=fighter)
        Assignment.objects.create(
            slot=slot, miniature=fighter, caused_by=line, gang_root=other
        )

        pilot = find()

        assert not pilot.ok
        assert any("2 gangs" in problem for problem in pilot.problems)


class TestRetiring:
    def test_it_deletes_exactly_the_pilot_and_the_gang_survives(self, pilot_world):
        gang, fighter, slot_type, hollow, slot = pilot_world
        events_before = LedgerEvent.objects.filter(gang=gang).count()

        report = apply(find())

        assert report[-1] == "retired; the field is clean"
        assert not SlotType.objects.filter(name="Gang Legacy").exists()
        assert not Slot.objects.filter(pk=slot.pk).exists()
        assert not Picklist.objects.filter(name="All Gang Legacies").exists()
        assert not Pickable.objects.filter(pk__in=[p.pk for p in hollow]).exists()
        assert not Assignment.objects.filter(slot=slot.pk).exists()
        # The fighter, the hire, and every unrelated event survive.
        assert Assignment.objects.filter(miniature_root=fighter).exists()
        assert LedgerEvent.objects.filter(gang=gang).count() < events_before
        assert LedgerEvent.objects.filter(gang=gang, kind="purchased").exists()
        assert_reconciled(gang)

    def test_the_field_is_clean_for_the_conversion(self, pilot_world):
        """The retirement exists so the Gang Legacy conversion can
        build; afterwards the name it needed is free."""
        apply(find())

        assert find().nothing_here
        assert not SlotType.objects.filter(name="Gang Legacy").exists()


def _any_effect():
    from n26.library.authoring import ef_adds
    from n26.tests.sandbox.actions import create_rule

    return ef_adds(create_rule("Suddenly Real"))
