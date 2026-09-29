"""Deleting a thing that models already have as a built-in.

A built-in set hands its things to every model hired from the carrier:
nobody chose them and nobody paid. When an author deletes a thing a set
handed out by mistake — a skill named after an empty cell, say — the
copies are a grant being reversed, not history being taken away. Once
the author has taken the thing out of every set, the delete page names
the models, removes the copy from each, gang by gang, and deletes the
thing with the archived memberships (``n26/library/deletion.py``).
"""

import pytest
from django.contrib.auth.models import User

from gyrinx.maintenance.models import Backfill
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import add_built_in, create_skill, remove_default_member
from n26.library.deletion import plan_deletion
from n26.library.models import DefaultAssignment, Skill
from n26.tests.sandbox.actions import (
    create_gang_type,
    create_profile,
    found_gang,
    hire,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(client):
    user = User.objects.create_user("author", is_staff=True)
    client.force_login(user)
    return user


@pytest.fixture
def player(db):
    return User.objects.create_user("player")


@pytest.fixture
def escher(default_pack):
    return create_gang_type("Escher", starting_credits=1000)


@pytest.fixture
def ganger(escher, person_type):
    return create_profile("Ganger", person_type, escher, price=50)


@pytest.fixture
def stray(ganger):
    skill = create_skill("None")
    add_built_in(ganger, skill)
    return skill


def hired(owner, name, escher, ganger, models=1):
    gang = found_gang(name, escher, owner=owner)
    for n in range(models):
        hire(gang, ganger, f"Model {n + 1}", paid=50)
    return gang


def take_out_of_its_set(skill):
    for member in DefaultAssignment.objects.filter(skill=skill):
        remove_default_member(member)


def delete_page(skill):
    return f"/n26/authoring/skill/{skill.pk}/delete/"


class TestWhileASetStillBringsIt:
    def test_it_refuses_and_names_the_set(self, player, escher, ganger, stray):
        hired(player, "Theirs", escher, ganger)

        plan = plan_deletion([stray], remove_built_in_copies=True)

        assert not plan.ok
        assert any("built-in set" in words for words in plan.refusals)


class TestOnceTakenOutOfEverySet:
    def test_the_models_are_named_rather_than_refusing(
        self, player, escher, ganger, stray
    ):
        hired(player, "Theirs", escher, ganger, models=2)
        take_out_of_its_set(stray)

        plan = plan_deletion([stray], remove_built_in_copies=True)

        assert plan.ok, plan.refusals
        assert [line.name for line in plan.lines] == ["Theirs"]
        assert plan.fighters_with_lines == 2
        assert plan.lines_are_built_ins
        assert any(
            "remove it from 2 models on 1 gang first" in w for w in plan.preview()
        )

    def test_without_asking_the_copies_still_refuse(
        self, player, escher, ganger, stray
    ):
        hired(player, "Theirs", escher, ganger)
        take_out_of_its_set(stray)

        assert not plan_deletion([stray]).ok

    def test_a_copy_a_player_selected_still_refuses(
        self, player, escher, ganger, stray
    ):
        from n26.tests.sandbox.actions import assign

        theirs = hired(player, "Theirs", escher, ganger)
        take_out_of_its_set(stray)
        model = Assignment.objects.get(gang_root=theirs, profile=ganger)
        assign(stray, miniature=model.miniature_root)

        plan = plan_deletion([stray], remove_built_in_copies=True)

        assert not plan.ok
        assert any("not staff" in words for words in plan.refusals)

    def test_the_page_names_the_models_and_deleting_removes_every_copy(
        self, author, client, player, escher, ganger, stray
    ):
        theirs = hired(player, "Theirs", escher, ganger, models=2)
        take_out_of_its_set(stray)

        body = client.get(delete_page(stray)).content.decode()
        assert "Models that have it" in body
        assert "Model 1, Model 2" in body
        assert "Delete None and remove it from 2 models" in body

        client.post(delete_page(stray))

        record = Backfill.objects.get()
        assert record.status == Backfill.Status.DONE, record.error
        assert not Skill.objects.filter(pk=stray.pk).exists()
        assert not DefaultAssignment.objects.filter(skill_id=stray.pk).exists()
        assert not Assignment.objects.filter(skill_id=stray.pk).exists()
        assert Assignment.objects.filter(gang_root=theirs, profile=ganger).count() == 2
        theirs.refresh_from_db()
        assert_reconciled(theirs)

    def test_a_removed_models_copy_goes_too(
        self, author, client, player, escher, ganger, stray
    ):
        from n26.tests.sandbox.actions import remove

        theirs = hired(player, "Theirs", escher, ganger, models=2)
        remove(Assignment.objects.filter(gang_root=theirs, profile=ganger).first())
        take_out_of_its_set(stray)

        client.post(delete_page(stray))

        record = Backfill.objects.get()
        assert record.status == Backfill.Status.DONE, record.error
        assert not Skill.objects.filter(pk=stray.pk).exists()
        assert not Assignment.objects.filter(skill_id=stray.pk).exists()
        theirs.refresh_from_db()
        assert_reconciled(theirs)
