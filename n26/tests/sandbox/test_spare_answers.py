"""Clearing the answers a doubled click left behind.

A question answered twice in one moment left two rows where one belongs.
The second settles nothing — its sibling already did — but it still
draws a line on the model's gear list, named after the question rather
than after anything a player owns. This is what takes that line away,
and it holds itself to taking away exactly that.
"""

import pytest

from n26.core.capture import gang_state
from n26.core.models import Assignment, LedgerEntry
from n26.core.reconcile import assert_reconciled
from n26.library.conversion import apply as apply_conversion
from n26.library.conversion import plan_specialisation
from n26.library.models import Specialisation
from n26.library.spare_answers import Refused, apply, find
from n26.tests.sandbox.actions import (
    buy,
    choose,
    create_default_set,
    create_gang_type,
    create_profile,
    create_skill,
    create_specialisation,
    create_subtype,
    create_wargear,
    ef_adds,
    found_gang,
    hire,
    modifier,
    offers_choice,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def settled(default_pack, person_type, owner):
    """A specialisation system, converted, with one question settled."""
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
    choose(anchor, specs["Medic"])
    apply_conversion(plan_specialisation())
    return gang, fighter, anchor, specs


@pytest.fixture
def doubled(settled):
    """The same, with the second row a doubled click leaves.

    Made directly: the picker refuses to make one, which is the whole
    reason these are a handful of rows rather than an ongoing supply.
    """
    gang, fighter, anchor, specs = settled
    spare = Assignment.objects.create(
        specialisation=specs["Sniper"],
        miniature=fighter,
        caused_by=anchor,
        gang_root=gang,
    )
    return gang, fighter, anchor, specs, spare


class TestFindingThem:
    def test_a_clean_world_has_nothing_to_clear(self, settled):
        assert find().nothing_here

    def test_it_names_the_line_it_would_take_away(self, doubled):
        gang, fighter, _, _, spare = doubled

        found = find()

        assert found.ok and not found.nothing_here
        assert len(found.found) == 1
        only = found.found[0]
        assert only.assignment_id == spare.pk
        assert only.line_name == "Sniper"
        assert only.model_id == str(fighter.pk)
        assert f"clear the spare “Sniper” from {fighter}" in "\n".join(found.preview())

    def test_the_line_it_names_is_really_on_the_page(self, doubled):
        gang, fighter, _, _, _ = doubled

        drawn = gang_state(gang)["models"][str(fighter.pk)]["equipment"]

        assert ("Sniper", find().found[0].line_rating) in drawn


class TestClearingThem:
    def test_the_row_goes(self, doubled):
        _, _, _, _, spare = doubled

        apply(find())

        assert not Assignment.objects.filter(pk=spare.pk).exists()

    def test_the_line_goes_and_nothing_else_moves(self, doubled):
        gang, fighter, _, _, _ = doubled
        before = gang_state(gang)

        apply(find())

        after = gang_state(gang)
        gone = [
            line
            for line in before["models"][str(fighter.pk)]["equipment"]
            if line not in after["models"][str(fighter.pk)]["equipment"]
        ]
        assert [name for name, _ in gone] == ["Sniper"]
        before["models"][str(fighter.pk)]["equipment"].remove(gone[0])
        assert before == after

    def test_the_settled_answer_is_untouched(self, doubled):
        _, fighter, _, _, _ = doubled
        settled_row = Assignment.objects.get(
            miniature=fighter, pickable__isnull=False, archived=False
        )

        apply(find())

        settled_row.refresh_from_db()
        assert settled_row.pickable.name == "Medic"

    def test_what_the_sibling_grants_still_arrives(self, doubled):
        """The skill was never doubled and must not now be halved."""
        gang, fighter, _, _, _ = doubled

        apply(find())

        assert "Medicate" in gang_state(gang)["models"][str(fighter.pk)]["skills"]

    def test_the_gang_still_reconciles(self, doubled):
        gang, _, _, _, _ = doubled

        apply(find())

        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_second_run_finds_nothing(self, doubled):
        apply(find())

        assert find().nothing_here


class TestAClickThatLandedMoreThanTwice:
    """Two spares of one name on one model draw two identical lines.
    Which line belongs to which row is not a question worth asking —
    both go, and the page is held to losing exactly two."""

    @pytest.fixture
    def twice_over(self, doubled):
        gang, fighter, anchor, specs, spare = doubled
        second = Assignment.objects.create(
            specialisation=specs["Sniper"],
            miniature=fighter,
            caused_by=anchor,
            gang_root=gang,
        )
        return gang, fighter, specs, [spare, second]

    def test_both_are_found(self, twice_over):
        _, _, _, spares = twice_over

        found = find()

        assert found.ok
        assert {spare.assignment_id for spare in found.found} == {
            row.pk for row in spares
        }

    def test_both_lines_go_and_nothing_else_moves(self, twice_over):
        gang, fighter, _, _ = twice_over
        before = gang_state(gang)
        drawn = before["models"][str(fighter.pk)]["equipment"]
        assert len([line for line in drawn if line[0] == "Sniper"]) == 2

        apply(find())

        after = gang_state(gang)
        assert not [
            line
            for line in after["models"][str(fighter.pk)]["equipment"]
            if line[0] == "Sniper"
        ]
        for line in [line for line in drawn if line[0] == "Sniper"]:
            drawn.remove(line)
        assert before == after


class TestWhatItRefuses:
    def test_a_thing_owned_under_the_same_name_is_not_touched(self, doubled):
        """One spare and two lines of its name means something a player
        owns shares it, and which line would go is not settled."""
        gang, fighter, _, _, _ = doubled
        drawn = gang_state(gang)["models"][str(fighter.pk)]["equipment"]
        assert len([line for line in drawn if line[0] == "Sniper"]) == 1
        # A real piece of kit that happens to wear the same name.
        buy(fighter, thing=create_wargear("Sniper", price=10), paid=10)

        found = find()

        assert not found.ok
        assert any("is not settled" in p for p in found.problems)

    def test_the_only_answer_is_not_a_spare(self, settled):
        """Without a sibling standing, the row *is* the answer, and
        clearing it would take a player's choice away."""
        gang, fighter, anchor, specs = settled
        Assignment.objects.filter(
            miniature=fighter, pickable__isnull=False, archived=False
        ).delete()
        Assignment.objects.create(
            specialisation=specs["Sniper"],
            miniature=fighter,
            caused_by=anchor,
            gang_root=gang,
        )

        found = find()

        assert not found.ok
        assert any("is the answer rather than a spare" in p for p in found.problems)
        with pytest.raises(Refused):
            apply(found)

    def test_a_row_with_something_hanging_off_it_is_refused(self, doubled):
        gang, fighter, _, specs, spare = doubled
        Assignment.objects.create(
            specialisation=specs["Medic"],
            miniature=fighter,
            caused_by=spare,
            gang_root=gang,
        )

        found = find()

        assert not found.ok
        assert any("hangs off the spare" in p for p in found.problems)

    def test_a_row_that_was_paid_for_is_refused(self, doubled):
        gang, _, _, _, spare = doubled
        LedgerEntry.objects.create(assignment=spare, list_price=25, paid=25)

        found = find()

        assert not found.ok
        assert any("25 credits paid" in p for p in found.problems)

    def test_a_row_counting_towards_what_the_gang_is_worth_is_refused(self, doubled):
        _, _, _, _, spare = doubled
        LedgerEntry.objects.create(assignment=spare, rating_contribution=25)

        found = find()

        assert not found.ok
        assert any("of the gang's worth" in p for p in found.problems)

    def test_a_page_that_moves_further_than_promised_ends_the_run(self, doubled):
        """The proof is the page minus the named lines. A spare is only
        safe to delete because the conversion left the kind it names
        carrying nothing; one that has been given something back takes
        that away with it, and the run unwinds rather than commit it."""
        gang, fighter, _, specs, spare = doubled
        modifier(
            "Sniper: its skill again",
            targets_model(),
            ef_adds(create_skill("Overwatch")),
            carried_by=specs["Sniper"],
        )
        found = find()
        assert "Overwatch" in gang_state(gang)["models"][str(fighter.pk)]["skills"]

        with pytest.raises(Refused) as refused:
            apply(found)

        assert "Overwatch" in str(refused.value)
        assert Assignment.objects.filter(pk=spare.pk).exists()
