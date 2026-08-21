"""The nameless gang type, and the repair that retires it.

An ingest planned a gang type from a blank Gang cell, so a ``GangType``
with no name stood in the pack — foundable by default, drawn as an empty
card sorting before every real type, and foundable into a gang of
nothing. Nothing may author such a row and the create page does not
offer one that already stands; what is left is what to do with the gangs
already founded on it, and they are not alike. One nobody played is
deleted. One somebody played is repointed to the list its models were
really hired from, which is what it has been all along. One nobody can
read is left exactly as it stands.
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
    """The row as production holds it: no name, no badge, foundable."""
    return GangType.objects.create(name="")


@pytest.fixture
def escher(db, default_pack):
    """A real gang list, with something to hire off it."""
    return create_gang_type("Escher", starting_credits=1000)


@pytest.fixture
def escher_ganger(escher, person_type):
    return create_profile("Ganger", person_type, escher, price=50)


@pytest.fixture
def founded_on_it(nameless, owner):
    """A gang of nothing — founded on the empty card and untouched since."""
    return found_gang("A Gang Of Nothing", nameless, owner=owner)


@pytest.fixture
def played_on_it(nameless, owner, escher_ganger):
    """The same founding, then played: models hired off a real list.

    Nothing stops a gang hiring from a list its own type does not name,
    so a gang founded on nothing gets filled from somewhere real — which
    is what tells the repair what it has been all along.
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
    """A name of nothing but spaces draws the identical empty card, so
    every guard treats it as the blank it looks like."""

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
    """A played gang is what its models say it is. Saying so must take
    nothing away and must leave the gang's books straight."""

    def test_it_keeps_everything_the_gang_owns(self, played_on_it, escher):
        was_rating = played_on_it.rating
        models = {m.pk for m in Miniature.objects.filter(membership__gang=played_on_it)}

        apply(find())

        played_on_it.refresh_from_db()
        assert played_on_it.gang_type_id == escher.pk
        assert {
            m.pk for m in Miniature.objects.filter(membership__gang=played_on_it)
        } == models
        assert played_on_it.rating >= was_rating
        assert_reconciled(played_on_it)

    def test_the_new_type_brings_its_built_ins(self, played_on_it, escher):
        """A gang type hands its gang things through the founding
        assignment, so a repoint that did not found again would leave the
        gang without what its type gives."""
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
        """Founding is something the owner did, and the history says so.

        A repoint that deleted the founding assignment would take that
        act with it — entry and event cascade — and write a new one,
        dated today, in the name of whoever ran the repair. The owner
        would open their history and find their hires first and a
        stranger creating their gang last.
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

        # And it now says what the gang really is, because the history
        # reads the assignment as it stands rather than any stored wording.
        acts = build(played_on_it, viewer=owner)
        opening_act = acts[0]
        told = "".join(span.text for span in opening_act.spans)
        assert "created the gang" in told
        assert "Escher" in told
        assert opening_act.actor

    def test_a_gang_with_no_founding_counts_nothing_of_anybody_elses(
        self, played_on_it, escher
    ):
        """Asked what a founding caused when there is no founding, the
        question becomes "caused by nothing" — which every assignment
        anybody was ever given answers."""
        played_on_it.founding = None
        played_on_it.save(update_fields=["founding", "modified"])

        found = find()

        assert found.replaced == 0
        assert found.repoint == ((played_on_it.pk, escher.pk),)

    def test_the_nameless_type_goes_once_nothing_stands_on_it(
        self, played_on_it, founded_on_it, escher
    ):
        """One gang of each kind on the same type: the untouched one is
        deleted, the played one repointed, and only then may the type go."""
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
        """Models from two lists, and nobody can say which the gang is.
        It keeps what it has, and so does the type it names."""
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
        """Hired guns and pets carry profiles off lists nobody plays as.
        A gang moved onto one of those would be a gang no player could
        have made, so it is left standing instead."""
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
        """Per gang, not all or nothing: the unreadable one holding up
        the type must not hold up the empty one's deletion."""
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
        # The record must still name the gang it destroyed, even though
        # the type it stood on outlived it.
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
        """``Assignment.gang_type`` is PROTECT, so the delete would fail
        anyway — refusing in words beats a crash, and says how many."""
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
        """A repointed gang keeps its own assignments, so one of those
        naming the nameless type would still name it when the delete
        came — and PROTECT would fail the whole run."""
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
        """Taking back what a type gave means unwinding purchases that
        hang off it and saying in the ledger that they went, which is a
        refund's work. This repair repoints a founding that granted
        nothing, and says so rather than deleting quietly."""
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
        """Names are unique per pack, and another pack's rows are
        somebody's content rather than this accident."""
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
        # The founding assignment rode the gang down; the real gang beside
        # it is untouched.
        assert not Assignment.objects.filter(gang_root=founded_on_it).exists()
        assert Gang.objects.filter(pk=kept.pk).exists()
        assert GangType.objects.filter(pk=named.pk).exists()
        assert "retired; every gang type in the pack has a name" in report

    def test_a_plan_read_before_the_world_moved_is_refused(
        self, founded_on_it, escher_ganger
    ):
        """A gang's assignments cascade rather than protect, so a gang
        hired into between reading the plan and deleting would ride the
        delete down. The plan is read again inside the transaction, and
        anything that has moved refuses."""
        stale = find()
        assert stale.ok
        hire(founded_on_it, escher_ganger, "Somebody At All", paid=50)

        with pytest.raises(Refused, match="changed since the plan was read"):
            apply(stale)

        assert Gang.objects.filter(pk=founded_on_it.pk).exists()
        assert GangType.objects.filter(name="").exists()
        assert_reconciled(founded_on_it)

    def test_a_layout_saved_since_the_plan_was_read_refuses_too(self, founded_on_it):
        """The preview promises everything that dies by count, and a
        print layout cascades with its gang."""
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
    """``operation.refound`` is a verb of its own, and a second caller
    would not have this repair's proof that the old type gave nothing."""

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
