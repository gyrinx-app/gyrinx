"""The nameless gang type, and the repair that deletes it.

An ingest planned a gang type from a blank Gang cell, so a ``GangType``
with no name stood in the pack — foundable by default, drawn as an empty
card sorting before every real type, and founded on by one player. Three
things are proven here: nothing may author such a row any more, the
create page would not offer one that already stands, and the repair
deletes exactly the accident — refusing the moment a gang founded on it
turns out to have been played.
"""

import pytest
from django.core.exceptions import ValidationError

from n26.core.forms import CreateGangForm
from n26.core.models import Assignment, Gang
from n26.library import authoring
from n26.library.models import GangType
from n26.library.nameless_gang_type import Refused, apply, find
from n26.tests.sandbox.actions import (
    create_gang_type,
    create_profile,
    found_gang,
    hire,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def nameless(db, default_pack):
    """The row as production holds it: no name, no badge, foundable."""
    return GangType.objects.create(name="")


@pytest.fixture
def founded_on_it(nameless, owner):
    """A gang of nothing — founded on the empty card and untouched since."""
    return found_gang("A Gang Of Nothing", nameless, owner=owner)


class TestNothingMayAuthorOne:
    def test_the_verb_refuses_a_blank_name(self, db, default_pack):
        with pytest.raises(ValidationError, match="needs a name"):
            authoring.create_gang_type("")
        with pytest.raises(ValidationError, match="needs a name"):
            authoring.create_gang_type("   ")
        assert not GangType.objects.exists()


class TestTheCreatePageDoesNotOfferOne:
    def test_a_nameless_type_is_not_a_card(self, nameless):
        real = create_gang_type("Escher", starting_credits=1000)

        offered = CreateGangForm().gang_type_choices()

        assert [card["value"] for card in offered] == [str(real.pk)]

    def test_it_is_not_an_answer_either(self, nameless):
        create_gang_type("Escher", starting_credits=1000)

        form = CreateGangForm(data={"name": "The Nothings", "gang_type": nameless.pk})

        assert not form.is_valid()
        assert "gang_type" in form.errors


class TestFindingIt:
    def test_it_names_the_type_and_the_gang_founded_on_it(self, founded_on_it):
        found = find()

        assert found.ok and not found.nothing_here
        assert len(found.gang_type_ids) == 1
        assert found.gang_ids == (founded_on_it.pk,)
        assert found.assignment_ids == (founded_on_it.founding_id,)
        said = "\n".join(found.preview())
        assert "delete 1 gang founded on a nameless type" in said
        assert "delete 1 gang type with no name" in said

    def test_a_type_with_no_gang_on_it_still_goes(self, nameless):
        found = find()

        assert found.ok and found.gang_ids == ()
        assert "nothing of a player's dies" in "\n".join(found.preview())

    def test_a_pack_of_named_types_has_nothing_to_delete(self, db, default_pack):
        create_gang_type("Escher", starting_credits=1000)

        found = find()

        assert found.nothing_here
        assert apply(found) == found.preview()


class TestRefusing:
    def test_a_gang_that_has_been_hired_into_is_left_alone(
        self, founded_on_it, person_type
    ):
        profile = create_profile(
            "Somebody", person_type, founded_on_it.gang_type, price=50
        )
        hire(founded_on_it, profile, "Somebody At All")

        found = find()

        assert not found.ok
        assert any("has been played" in problem for problem in found.problems)
        with pytest.raises(Refused, match="not deleted"):
            apply(found)
        assert Gang.objects.filter(pk=founded_on_it.pk).exists()

    def test_a_type_something_is_hired_off_wants_a_name_instead(
        self, nameless, person_type
    ):
        create_profile("Somebody", person_type, nameless, price=50)

        found = find()

        assert not found.ok
        assert any(
            "hired off the nameless type" in problem for problem in found.problems
        )

    def test_a_type_authored_onto_is_not_the_empty_row(self, nameless, person_type):
        nameless.built_ins = authoring.create_default_set("Something")
        nameless.save()

        found = find()

        assert not found.ok
        assert any("authored onto it" in problem for problem in found.problems)


class TestApplying:
    def test_it_deletes_the_gang_and_then_the_type(self, founded_on_it):
        named = create_gang_type("Escher", starting_credits=1000)
        kept = found_gang("The Real Thing", named, owner=founded_on_it.owner)

        report = apply(find())

        assert not GangType.objects.filter(name="").exists()
        assert not Gang.objects.filter(pk=founded_on_it.pk).exists()
        # The founding assignment rode the gang down; the real gang beside
        # it is untouched.
        assert not Assignment.objects.filter(gang_root=founded_on_it).exists()
        assert Gang.objects.filter(pk=kept.pk).exists()
        assert GangType.objects.filter(pk=named.pk).exists()
        assert "deleted; every gang type in the pack has a name" in report

    def test_running_it_twice_finds_nothing_the_second_time(self, founded_on_it):
        apply(find())

        again = find()

        assert again.nothing_here
        assert apply(again) == again.preview()
