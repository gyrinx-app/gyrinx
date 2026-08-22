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
from n26.library.conversion.archived import _unexpected as _unexpected
from n26.library.conversion.archived import (
    apply_archived,
    plan_archived,
)
from n26.library.conversion.base import ConversionRefused
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
        assert any("are called “Sniper”" in problem for problem in plan.problems)

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


class TestTheOtherColumns:
    """The sweep reads the slot off the anchor, so a system's shape is
    the anchor's shape. These are the other two it will meet: a skill
    tree, answered on a gang-held carrier, and an archetype, answered
    from a profile onto the gang."""

    def test_a_skill_trees_answer_taken_back_moves(
        self, default_pack, person_type, owner
    ):
        from n26.library.conversion import plan_skill_tree
        from n26.tests.sandbox.test_conversion_skill_tree import (
            build_prod_shape,
            build_world,
        )

        shape = build_prod_shape()
        build_world(shape, person_type, owner)
        apply(plan_skill_tree())
        assert Assignment.objects.filter(
            archived=True, skill_tree__isnull=False
        ).exists()

        apply_archived(plan_archived())

        # What was taken back has moved. A live spare from a doubled
        # click stays, being nobody's history and this sweep's business.
        assert not Assignment.objects.filter(
            archived=True, skill_tree__isnull=False
        ).exists()
        moved = Assignment.objects.filter(archived=True, pickable__isnull=False)
        assert moved.exists()
        assert all(row.chosen_for_slot_id is not None for row in moved)

    def test_an_archetypes_answer_taken_back_moves(
        self, default_pack, person_type, owner
    ):
        from n26.library.conversion import plan_archetype
        from n26.tests.sandbox.test_conversion_archetype import (
            build_prod_shape,
            build_world,
        )

        shape = build_prod_shape(person_type)
        build_world(shape, owner)
        apply(plan_archetype())
        assert Assignment.objects.filter(
            archived=True, archetype__isnull=False
        ).exists()

        apply_archived(plan_archived())

        assert not Assignment.objects.filter(
            archived=True, archetype__isnull=False
        ).exists()
        moved = Assignment.objects.filter(archived=True, pickable__isnull=False)
        assert all(row.chosen_for_slot_id is not None for row in moved)


class TestTheOneRewording:
    """A dropped gang legacy sat in the archetype column, so its history
    calls the house an archetype. Said as the pick it is, the history
    says "gang legacy" — the word the gang's kept legacies use. The
    sweep counts that on the page before it is agreed to, and refuses
    every other word that moves."""

    @pytest.fixture
    def legacies(self, default_pack, person_type, owner):
        from n26.library.conversion import plan_gang_legacy
        from n26.tests.sandbox.test_conversion_gang_legacy import (
            build_prod_shape,
            build_world,
        )

        shape = build_prod_shape(person_type)
        gangs, _ = build_world(shape, owner)
        apply(plan_gang_legacy())
        return gangs

    @pytest.fixture
    def sworn_at_hiring(self, default_pack, person_type, owner):
        """A legacy answered in the same breath as the hire that asked
        for it, then taken back.

        The word only reaches the page this way: an answer given in its
        own right is told as its own line, which names no sort of thing,
        while one folded under the hire is listed beneath it — and a
        listed thing says what sort it is.
        """
        from n26.core.operations import operation
        from n26.library.conversion import plan_gang_legacy
        from n26.tests.sandbox.actions import found_gang, remove
        from n26.tests.sandbox.test_conversion_gang_legacy import build_prod_shape

        gang_type, houses, profiles, _ = build_prod_shape(person_type)
        hunt_leader = profiles[0]
        gang = found_gang("The Long Watch", gang_type, owner=owner, budget=2000)
        with operation(gang, actor=owner) as op:
            fighter = op.hire(hunt_leader, "Vex", paid=50)
            anchor = Assignment.objects.get(profile=hunt_leader, miniature_root=fighter)
            op.choose(anchor, houses["Cawdor"])
        remove(
            Assignment.objects.get(
                archetype=houses["Cawdor"], miniature_root=fighter, archived=False
            )
        )
        apply(plan_gang_legacy())
        return gang

    def test_the_plan_says_the_word_will_move_and_how_often(self, legacies):
        plan = plan_archived()

        assert plan.rewords == (("archetype", "gang legacy", 1),)
        assert any(
            "will have their history say “gang legacy” where it says "
            "“archetype” today" in line
            for line in plan.preview()
        )

    def test_the_gang_whose_word_moves_is_the_only_one_allowed_to(self, legacies):
        plan = plan_archived()

        assert plan.reworded_gang_ids == (legacies["answered"].pk,)

    def test_the_story_says_the_new_word_afterwards(self, sworn_at_hiring):
        gang = sworn_at_hiring
        before = _story(history.build(gang))
        assert any("|archetype|" in line for line in before)

        apply_archived(plan_archived())

        after = _story(history.build(gang))
        assert not any("|archetype|" in line for line in after)
        assert any("|gang legacy|" in line for line in after)
        # Only the sort-of-thing word moved: what arrived is untouched.
        assert [line.split("|")[0] for line in before] == [
            line.split("|")[0] for line in after
        ]

    def test_a_rewording_nobody_declared_is_refused(self, legacies, monkeypatch):
        monkeypatch.setattr("n26.library.conversion.archived.ALLOWED_REWORDS", ())

        plan = plan_archived()

        assert not plan.ok
        assert any(
            "which is not a rewording this may make" in problem
            for problem in plan.problems
        )
        with pytest.raises(ConversionRefused):
            apply_archived(plan)


class TestReadingTwoStories:
    """What counts as a story having moved, given the one allowance."""

    def test_an_identical_story_has_not_moved(self):
        assert _unexpected(["a", "b"], ["a", "b"], ()) == []

    def test_a_declared_word_put_in_place_of_another_is_expected(self):
        assert (
            _unexpected(
                ["Cawdor|archetype|"],
                ["Cawdor|gang legacy|"],
                (("archetype", "gang legacy", 1),),
            )
            == []
        )

    def test_the_same_word_moving_where_it_was_not_declared_is_not(self):
        found = _unexpected(["Cawdor|archetype|"], ["Cawdor|gang legacy|"], ())

        assert found == ["“Cawdor|archetype|” -> “Cawdor|gang legacy|”"]

    def test_a_name_changing_is_never_expected(self):
        found = _unexpected(
            ["Cawdor|archetype|"],
            ["Escher|gang legacy|"],
            (("archetype", "gang legacy", 1),),
        )

        assert found == ["“Cawdor|archetype|” -> “Escher|gang legacy|”"]

    def test_a_story_that_gains_a_line_is_not_expected(self):
        found = _unexpected(["a"], ["a", "b"], (("archetype", "gang legacy", 1),))

        assert found == ["the story is 1 lines long and becomes 2"]


class TestWhatItLeaves:
    """A spare from a doubled click is live, not taken back, so it is
    not this sweep's to move — and while one stands its kind cannot be
    retired. The page that runs this says so; the plan counts them."""

    def test_a_live_spare_is_not_swept(self, world):
        gang, fighter, specialist, specs = world
        anchor = Assignment.objects.get(subtype=specialist, miniature=fighter)
        standing = Assignment.objects.get(
            miniature=fighter, pickable__isnull=False, archived=False
        )
        # A second answer beside the one that settled it, as a doubled
        # click leaves — made directly, the picker refusing to make one.
        Assignment.objects.create(
            specialisation=specs["Sniper"],
            miniature=fighter,
            caused_by=anchor,
            gang_root=gang,
        )

        apply_archived(plan_archived())

        spare = Assignment.objects.get(specialisation__isnull=False)
        assert spare.archived is False
        assert spare.pickable_id is None
        standing.refresh_from_db()
        assert standing.pickable_id is not None


def _story(acts):
    told = []
    for act in acts:
        told.append("".join(span.text for span in act.spans))
        told.extend(f"{sub.name}|{sub.kind}|{sub.note}" for sub in act.subs)
    return told
