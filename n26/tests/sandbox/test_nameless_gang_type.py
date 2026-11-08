"""Reject blank gang-type names and repair existing unnamed types. Delete untouched gangs,
repoint gangs whose profiles identify one foundable list, and preserve gangs with
ambiguous sources.
"""

import pytest
from django.core.exceptions import ValidationError

from n26.core.forms import CreateGangForm
from n26.core.models import Assignment, Gang, Miniature
from n26.core.reconcile import assert_reconciled
from n26.library import authoring
from n26.library.models import GangType
from n26.library.nameless_gang_type import Refused, apply, find
from n26.tests.sandbox.actions import (
    create_gang_type,
    create_profile,
    create_rule,
    ef_adds,
    found_gang,
    hire,
    modifier,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def nameless(db, default_pack):
    """Create the invalid legacy row directly, bypassing authoring validation."""
    return GangType.objects.create(name="")


@pytest.fixture
def escher(db, default_pack):
    """A named, foundable gang type."""
    return create_gang_type("Escher", starting_credits=1000)


@pytest.fixture
def escher_ganger(escher, person_type):
    return create_profile("Ganger", person_type, escher, price=50)


@pytest.fixture
def founded_on_it(nameless, owner):
    """A gang with no activity after founding on the unnamed type."""
    return found_gang("A Gang Of Nothing", nameless, owner=owner)


@pytest.fixture
def played_on_it(nameless, owner, escher_ganger):
    """Hire profiles from a named list into a gang founded on the unnamed type, providing
    an unambiguous repair target.
    """
    gang = found_gang("Played As Escher", nameless, owner=owner)
    hire(gang, escher_ganger, "One", paid=50)
    hire(gang, escher_ganger, "Two", paid=50)
    return gang


class TestNothingMayAuthorOne:
    def test_the_verb_refuses_a_blank_name(self, db, default_pack):
        with pytest.raises(ValidationError, match="needs a name"):
            authoring.create_gang_type("")
        with pytest.raises(ValidationError, match="needs a name"):
            authoring.create_gang_type("   ")
        assert not GangType.objects.exists()


class TestTheCreatePageDoesNotOfferOne:
    def test_a_nameless_type_is_not_a_card(self, nameless, escher):
        offered = CreateGangForm().gang_type_choices()

        assert [card["value"] for card in offered] == [str(escher.pk)]

    def test_it_is_not_an_answer_either(self, nameless, escher):
        form = CreateGangForm(data={"name": "The Nothings", "gang_type": nameless.pk})

        assert not form.is_valid()
        assert "gang_type" in form.errors


class TestWhitespaceIsNoNameEither:
    """Whitespace-only names receive the same validation and repair as empty names."""

    @pytest.fixture
    def padded(self, db, default_pack):
        return GangType.objects.create(name="   ")

    def test_the_verb_refuses_it_and_strips_what_it_stores(self, db, default_pack):
        with pytest.raises(ValidationError, match="needs a name"):
            authoring.create_gang_type("   ")

        assert authoring.create_gang_type("  Escher  ").name == "Escher"

    def test_the_create_page_does_not_offer_it(self, padded, escher):
        offered = CreateGangForm().gang_type_choices()

        assert [card["value"] for card in offered] == [str(escher.pk)]

    def test_the_repair_finds_it(self, padded):
        found = find()

        assert found.ok and not found.nothing_here
        assert found.gang_type_ids == (padded.pk,)

        apply(found)

        assert not GangType.objects.filter(pk=padded.pk).exists()


class TestReadingWhatStandsOnIt:
    def test_an_untouched_gang_is_named_for_deleting(self, founded_on_it):
        found = find()

        assert found.ok and not found.nothing_here
        assert found.doomed_gang_ids == (founded_on_it.pk,)
        assert found.repoint == ()
        assert found.assignment_ids == (founded_on_it.founding_id,)
        said = "\n".join(found.preview())
        assert "delete 1 untouched gang founded on a nameless type" in said
        assert "delete 1 gang type with no name" in said

    def test_a_played_gang_is_named_for_repointing(self, played_on_it, escher):
        found = find()

        assert found.ok
        assert found.doomed_gang_ids == ()
        assert found.repoint == ((played_on_it.pk, escher.pk),)
        said = "\n".join(found.preview())
        assert "repoint a played gang onto Escher" in said
        assert "its history still opens with its owner creating it" in said
        assert "Its models, its gear and its budget are untouched" in said
        assert_reconciled(played_on_it)

    def test_a_type_with_no_gang_on_it_still_goes(self, nameless):
        found = find()

        assert found.ok and found.doomed_gang_ids == () and found.repoint == ()
        assert "delete 1 gang type with no name" in "\n".join(found.preview())

    def test_a_pack_of_named_types_has_nothing_to_retire(self, db, escher):
        found = find()

        assert found.nothing_here
        assert apply(found) == found.preview()


class TestRepointing:
    """Repointing preserves owned models, rating and reconciliation."""

    def test_it_keeps_everything_the_gang_owns(self, played_on_it, escher):
        was_rating = played_on_it.rating
        models = {m.pk for m in Miniature.objects.filter(membership__gang=played_on_it)}

        apply(find())

        played_on_it.refresh_from_db()
        assert played_on_it.gang_type_id == escher.pk
        assert {
            m.pk for m in Miniature.objects.filter(membership__gang=played_on_it)
        } == models
        # New built-ins must not change the existing rating.
        assert played_on_it.rating == was_rating
        assert_reconciled(played_on_it)

    def test_the_new_type_brings_its_built_ins(self, played_on_it, escher):
        """Repointing updates the founding assignment and grants the new type’s built-ins."""
        escher.built_ins = authoring.create_default_set(
            "Escher built-ins", members=[create_rule("Wise")]
        )
        escher.save()

        apply(find())

        played_on_it.refresh_from_db()
        assert played_on_it.founding is not None
        assert played_on_it.founding.assignable == escher
        arrived = Assignment.objects.filter(
            gang_root=played_on_it, caused_by=played_on_it.founding
        )
        assert [str(row.assignable) for row in arrived] == ["Wise"]
        assert_reconciled(played_on_it)

    def test_the_gang_keeps_its_own_founding_act(self, played_on_it, escher, owner):
        """Preserve the original founding assignment, event, date and actor instead of
        replacing them with a repair event.
        """
        from n26.core.history import build

        founding_id = played_on_it.founding_id
        opening = played_on_it.ledger_events.order_by("created", "id").first()
        was = (opening.pk, opening.created, opening.actor_id)

        apply(find())

        played_on_it.refresh_from_db()
        assert played_on_it.founding_id == founding_id
        still = played_on_it.ledger_events.order_by("created", "id").first()
        assert (still.pk, still.created, still.actor_id) == was
        assert still.actor_id == owner.pk

        # History reads the updated founding assignment.
        acts = build(played_on_it, viewer=owner)
        opening_act = acts[0]
        told = "".join(span.text for span in opening_act.spans)
        assert "created the gang" in told
        assert "Escher" in told
        assert opening_act.actor

    def test_a_gang_with_no_founding_counts_nothing_of_anybody_elses(
        self, played_on_it, escher
    ):
        """A missing founding must not match unrelated assignments whose caused_by is also
        NULL.
        """
        played_on_it.founding = None
        played_on_it.save(update_fields=["founding", "modified"])

        found = find()

        assert found.replaced == 0
        assert found.repoint == ((played_on_it.pk, escher.pk),)

    def test_the_nameless_type_goes_once_nothing_stands_on_it(
        self, played_on_it, founded_on_it, escher
    ):
        """Delete the untouched gang and repoint the played gang before removing their
        unnamed type.
        """
        report = apply(find())

        assert not Gang.objects.filter(pk=founded_on_it.pk).exists()
        assert Gang.objects.filter(pk=played_on_it.pk).exists()
        assert not GangType.objects.filter(name="").exists()
        assert any("repointed gangs" in line for line in report)
        assert any("deleted gangs" in line for line in report)
        assert_reconciled(Gang.objects.get(pk=played_on_it.pk))

    def test_a_gang_read_from_no_one_list_is_left_standing(
        self, played_on_it, nameless, person_type
    ):
        """Profiles from multiple lists provide no unambiguous repair target."""
        other = create_gang_type("Goliath", starting_credits=1000)
        hire(
            played_on_it,
            create_profile("Bruiser", person_type, other, price=50),
            "Three",
            paid=50,
        )

        found = find()

        assert found.ok
        assert found.repoint == ()
        assert found.gang_type_ids == ()
        assert found.kept_type_ids == (nameless.pk,)
        assert any("2 different gang lists" in reason for reason in found.stranded)

        apply(found)

        played_on_it.refresh_from_db()
        assert played_on_it.gang_type_id == nameless.pk
        assert GangType.objects.filter(pk=nameless.pk).exists()
        assert_reconciled(played_on_it)

    def test_a_list_nobody_can_found_is_not_a_target(
        self, nameless, owner, person_type
    ):
        """Non-foundable profile lists cannot become replacement gang types."""
        hangers_on = create_gang_type("Dramatis Personae", foundable=False)
        gang = found_gang("Odd One", nameless, owner=owner)
        hire(
            gang,
            create_profile("Hired Gun", person_type, hangers_on, price=50),
            "For Hire",
            paid=50,
        )

        found = find()

        assert found.repoint == ()
        assert found.kept_type_ids == (nameless.pk,)
        assert_reconciled(gang)

    def test_an_untouched_gang_still_goes_beside_one_left_standing(
        self, played_on_it, founded_on_it, nameless, person_type
    ):
        """An ambiguous gang protects its type without preventing deletion of another
        untouched gang.
        """
        other = create_gang_type("Goliath", starting_credits=1000)
        hire(
            played_on_it,
            create_profile("Bruiser", person_type, other, price=50),
            "Three",
            paid=50,
        )

        report = apply(find())

        assert not Gang.objects.filter(pk=founded_on_it.pk).exists()
        assert Gang.objects.filter(pk=played_on_it.pk).exists()
        assert GangType.objects.filter(pk=nameless.pk).exists()
        # The report names deleted gangs even when their type remains.
        assert any("deleted gangs" in line for line in report)
        assert_reconciled(played_on_it)


class TestRefusing:
    def test_a_type_something_is_hired_off_wants_a_name_instead(
        self, nameless, person_type
    ):
        create_profile("Somebody", person_type, nameless, price=50)

        found = find()

        assert not found.ok
        assert any(
            "hired off the nameless type" in problem for problem in found.problems
        )

    def test_a_type_carrying_built_ins_is_not_the_empty_row(self, nameless):
        nameless.built_ins = authoring.create_default_set("Something")
        nameless.save()

        found = find()

        assert not found.ok
        assert any("authored onto it" in problem for problem in found.problems)

    def test_a_type_carrying_modifiers_is_not_the_empty_row(self, nameless):
        nameless.modifiers.add(
            modifier("Something", targets_model(), ef_adds(create_rule("Tough")))
        )

        found = find()

        assert not found.ok
        assert any("authored onto it" in problem for problem in found.problems)

    def test_an_assignment_naming_it_on_no_such_gang_is_refused(
        self, nameless, escher, owner
    ):
        """Report protected gang_type references before attempting deletion."""
        elsewhere = found_gang("Somewhere Else", escher, owner=owner)
        Assignment.objects.create(gang_type=nameless, gang=elsewhere)

        found = find()

        assert not found.ok
        assert any(
            "not a founding this takes away" in problem for problem in found.problems
        )
        with pytest.raises(Refused, match="not retired"):
            apply(found)

    def test_a_row_naming_the_type_on_a_repointed_gang_is_refused(
        self, played_on_it, nameless
    ):
        """Preserved assignments must not retain references to the type being deleted."""
        Assignment.objects.create(gang_type=nameless, gang=played_on_it)

        found = find()

        assert not found.ok
        assert any(
            "not a founding this takes away" in problem for problem in found.problems
        )
        with pytest.raises(Refused, match="not retired"):
            apply(found)
        assert GangType.objects.filter(pk=nameless.pk).exists()

    def test_a_founding_that_granted_something_is_left_alone(
        self, played_on_it, escher
    ):
        """Existing caused assignments require a separate refund operation and prevent this
        repair.
        """
        Assignment.objects.create(
            rule=create_rule("A Gift"),
            gang=played_on_it,
            caused_by=played_on_it.founding,
        )

        found = find()

        assert not found.ok
        assert found.replaced == 1
        assert any("refund's work" in problem for problem in found.problems)
        with pytest.raises(Refused, match="not retired"):
            apply(found)
        played_on_it.refresh_from_db()
        assert played_on_it.gang_type_id != escher.pk

    def test_a_nameless_type_in_another_pack_is_left_alone(self, db, default_pack):
        """The repair is limited to the default pack."""
        theirs = authoring.create_pack("Someone Else's")
        GangType.objects.create(name="", pack=theirs)

        found = find()

        assert found.nothing_here
        assert GangType.objects.filter(pack=theirs, name="").exists()


class TestApplying:
    def test_it_deletes_the_untouched_gang_and_then_the_type(self, founded_on_it):
        named = create_gang_type("Cawdor", starting_credits=1000)
        kept = found_gang("The Real Thing", named, owner=founded_on_it.owner)

        report = apply(find())

        assert not GangType.objects.filter(name="").exists()
        assert not Gang.objects.filter(pk=founded_on_it.pk).exists()
        # Dependent founding rows are deleted; unrelated gangs and types remain.
        assert not Assignment.objects.filter(gang_root=founded_on_it).exists()
        assert Gang.objects.filter(pk=kept.pk).exists()
        assert GangType.objects.filter(pk=named.pk).exists()
        assert "retired; every gang type in the pack has a name" in report

    def test_a_plan_read_before_the_world_moved_is_refused(
        self, founded_on_it, escher_ganger
    ):
        """Recheck the plan inside the transaction before cascading deletion can remove
        newly added assignments.
        """
        stale = find()
        assert stale.ok
        hire(founded_on_it, escher_ganger, "Somebody At All", paid=50)

        with pytest.raises(Refused, match="changed since the plan was read"):
            apply(stale)

        assert Gang.objects.filter(pk=founded_on_it.pk).exists()
        assert GangType.objects.filter(name="").exists()
        assert_reconciled(founded_on_it)

    def test_a_layout_saved_since_the_plan_was_read_refuses_too(self, founded_on_it):
        """New print layouts change the planned cascade and require a fresh plan."""
        from n26.core.models import PrintConfig

        stale = find()
        PrintConfig.objects.create(gang=founded_on_it, name="For the table")

        with pytest.raises(Refused, match="changed since the plan was read"):
            apply(stale)

        assert Gang.objects.filter(pk=founded_on_it.pk).exists()

    def test_running_it_twice_finds_nothing_the_second_time(
        self, played_on_it, founded_on_it
    ):
        apply(find())

        again = find()

        assert again.nothing_here
        assert apply(again) == again.preview()
        assert_reconciled(Gang.objects.get(pk=played_on_it.pk))


class TestRefoundTheVerb:
    """refound independently refuses existing grants, even when called outside the repair."""

    def test_it_refuses_a_founding_that_granted_something(
        self, played_on_it, escher, owner
    ):
        from n26.core.operations import Refusal, operation

        Assignment.objects.create(
            rule=create_rule("A Gift"),
            gang=played_on_it,
            caused_by=played_on_it.founding,
        )

        with pytest.raises(Refusal, match="given back"):
            with operation(played_on_it, actor=owner) as op:
                op.refound(escher)

        # Refusal must preserve the in-memory instance as well as the database row.
        assert played_on_it.gang_type_id != escher.pk
        played_on_it.refresh_from_db()
        assert played_on_it.gang_type_id != escher.pk

    def test_a_gang_with_no_founding_is_simply_founded(
        self, played_on_it, escher, owner
    ):
        from n26.core.operations import operation

        played_on_it.founding = None
        played_on_it.save(update_fields=["founding", "modified"])

        with operation(played_on_it, actor=owner) as op:
            op.refound(escher)

        played_on_it.refresh_from_db()
        assert played_on_it.founding is not None
        assert played_on_it.founding.assignable == escher
        assert_reconciled(played_on_it)
