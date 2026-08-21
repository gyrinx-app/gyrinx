"""Sweeping up the answers already taken back.

The conversions moved what a gang still holds and left what it had
dropped. Those archived answers are the last things naming the retired
kinds, and this is what moves them — read from the anchor, because they
name no slot themselves, and proven by the story rather than the page.
"""

import pytest

from n26.core import history
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.conversion import apply, plan_specialisation
from n26.library.conversion.archived import apply_archived, plan_archived
from n26.library.models import Pickable, Slot, Specialisation
from n26.tests.sandbox.actions import (
    choose,
    create_default_set,
    create_gang_type,
    create_profile,
    create_skill,
    create_specialisation,
    create_subtype,
    ef_adds,
    found_gang,
    hire,
    modifier,
    offers_choice,
    remove,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(default_pack, person_type, owner):
    """A specialisation system, converted, with answers taken back both
    before and after the conversion ran."""
    specs = {}
    for name, skill in [("Sniper", "Precision Shot"), ("Medic", "Medicate")]:
        specs[name] = create_specialisation(name)
        modifier(
            f"{name}: its skill",
            targets_model(),
            ef_adds(create_skill(skill)),
            carried_by=specs[name],
        )
    specialist = create_subtype("Specialist")
    modifier(
        "Specialist: offers a choice of specialisation",
        targets_model(),
        offers_choice(Specialisation),
        carried_by=specialist,
    )
    gang_type = create_gang_type("Enforcers", starting_credits=2000)
    profile = create_profile("Patrol Officer", person_type, gang_type, price=50)
    profile.built_ins = create_default_set("Officer kit", members=[specialist])
    profile.save()

    gang = found_gang("The Watch", gang_type, owner=owner, budget=2000)
    fighter = hire(gang, profile, "Vex", paid=50)
    anchor = Assignment.objects.get(subtype=specialist, miniature=fighter)

    # Answered, taken back, answered again — the archived answer this
    # sweep is for, made while the system was still offers.
    choose(anchor, specs["Sniper"])
    remove(Assignment.objects.get(specialisation=specs["Sniper"], miniature=fighter))
    choose(anchor, specs["Medic"])

    apply(plan_specialisation())
    return gang, fighter, specialist, specs


class TestThePlan:
    def test_it_finds_the_answer_left_behind(self, world):
        plan = plan_archived()

        assert plan.ok and not plan.nothing_here
        said = "\n".join(plan.preview())
        assert "rewrite the archived specialisation" in said
        assert "“Sniper”" in said
        assert "for “Specialisation”" in said

    def test_a_second_run_finds_nothing(self, world):
        apply_archived(plan_archived())

        assert plan_archived().nothing_here


class TestTheSweep:
    def test_the_archived_answer_becomes_a_pick(self, world):
        gang, fighter, _, _ = world

        apply_archived(plan_archived())

        moved = Assignment.objects.get(archived=True, pickable__isnull=False)
        assert moved.pickable.name == "Sniper"
        assert moved.specialisation_id is None
        assert moved.chosen_for_slot == Slot.objects.get(name="Specialisation")
        assert moved.chosen_for_id == moved.caused_by_id
        assert moved.archived is True

    def test_nothing_names_the_old_kind_afterwards(self, world):
        apply_archived(plan_archived())

        assert not Assignment.objects.filter(specialisation__isnull=False).exists()

    def test_the_story_reads_the_same(self, world):
        gang, _, _, _ = world
        said = _story(history.build(gang))
        assert any("Sniper" in line for line in said)

        apply_archived(plan_archived())

        assert _story(history.build(gang)) == said

    def test_the_gang_still_reconciles(self, world):
        gang, _, _, _ = world

        apply_archived(plan_archived())

        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_the_live_answer_is_left_alone(self, world):
        """The conversions moved those. This is only for what they left."""
        _, fighter, _, _ = world
        live = Assignment.objects.get(
            miniature=fighter, pickable__isnull=False, archived=False
        )
        was = live.pickable_id

        apply_archived(plan_archived())

        live.refresh_from_db()
        assert live.pickable_id == was


class TestTheRefusals:
    def test_an_anchor_granting_nothing_is_refused(self, world):
        """Where the anchor no longer grants a slot, the answer cannot
        be placed and the sweep says so rather than guessing."""
        _, _, specialist, _ = world
        for held in list(specialist.modifiers.all()):
            specialist.modifiers.remove(held)

        plan = plan_archived()

        assert not plan.ok
        assert any("grants 0 slots" in problem for problem in plan.problems)

    def test_a_name_with_no_pickable_is_refused(self, world):
        # Renamed rather than deleted: the live pick protects it, which
        # is itself the reason a sweep must never assume a name resolves.
        Pickable.objects.filter(name="Sniper").update(name="Something Else")

        plan = plan_archived()

        assert not plan.ok
        assert any("is called “Sniper”" in problem for problem in plan.problems)

    def test_a_name_shared_across_slot_types_goes_to_its_own(self, world):
        """Two slot types may wear one name — the sweep places an answer
        by the slot its anchor grants, not by the name alone."""
        from n26.tests.sandbox.actions import create_pickable, create_slot_type

        elsewhere = create_slot_type("Something Else")
        # A qualifier is what lets one name sit on two slot types: the
        # uniqueness is per pack and qualifier, not per slot type.
        stray = create_pickable("Sniper", elsewhere, qualifier="Elsewhere")

        apply_archived(plan_archived())

        moved = Assignment.objects.get(archived=True, pickable__isnull=False)
        assert moved.pickable_id != stray.pk
        assert moved.pickable.slot_type.name == "Specialisation"


def _story(acts):
    told = []
    for act in acts:
        told.append("".join(span.text for span in act.spans))
        told.extend(f"{sub.name}|{sub.kind}|{sub.note}" for sub in act.subs)
    return told
