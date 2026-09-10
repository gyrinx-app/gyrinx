"""Deleting a firing line that fighters already have.

A weapon's free lines ride along with it onto every fighter that has
the weapon: nobody chose them and nobody paid. When an author deletes
such a line — one added by mistake, say, to support a bundle the
modifier already brings — the fighters that have it are not history
being taken away; they are a grant being reversed. The delete page
names them, and the line is removed from each, gang by gang, before the
row goes (``n26/library/deletion.py``). A line somebody paid for
refuses, as any held row does.
"""

import pytest
from django.contrib.auth.models import User

from gyrinx.maintenance.models import Backfill
from n26.core.models import Assignment, Gang
from n26.core.reconcile import assert_reconciled
from n26.library.deletion import DeletionPlan, Line, plan_deletion
from n26.library.models import WeaponProfile
from n26.tests.sandbox.actions import (
    buy_weapon_profile,
    create_gang_type,
    create_profile,
    create_weapon,
    found_gang,
    give_weapon,
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
def claw(default_pack):
    """A weapon with its own line and a second free line that was never
    needed: the bundle it comes with brings the thing itself."""
    return create_weapon(
        "Malcadon slashing claw",
        price=30,
        profiles=[("", 0), ("Web incisor", 0)],
    )


@pytest.fixture
def incisor(claw):
    return WeaponProfile.objects.get(weapon=claw, name="Web incisor")


@pytest.fixture
def escher(default_pack):
    return create_gang_type("Escher", starting_credits=1000)


@pytest.fixture
def ganger(escher, person_type):
    return create_profile("Ganger", person_type, escher, price=50)


def armed(owner, name, escher, ganger, claw, fighters=1):
    gang = found_gang(name, escher, owner=owner)
    for n in range(fighters):
        model = hire(gang, ganger, f"Fighter {n + 1}", paid=50)
        give_weapon(model, claw, paid=30)
    return gang


def delete_page(line):
    return f"/n26/authoring/weapon-profiles/{line.pk}/delete/"


class TestNamingTheFighters:
    def test_a_free_line_names_the_fighters_rather_than_refusing(
        self, author, player, escher, ganger, claw, incisor
    ):
        mine = armed(author, "Mine", escher, ganger, claw)
        theirs = armed(player, "Theirs", escher, ganger, claw, fighters=2)

        plan = plan_deletion([incisor], remove_free_lines=True)

        assert plan.ok
        assert not plan.gangs
        assert [line.name for line in plan.lines] == [mine.name, theirs.name]
        assert plan.fighters_with_lines == 3
        assert plan.touches_players
        assert any(
            "remove the firing line from 3 fighters" in w for w in plan.preview()
        )

    def test_without_asking_the_fighters_are_holders(
        self, author, player, escher, ganger, claw, incisor
    ):
        armed(player, "Theirs", escher, ganger, claw)

        plan = plan_deletion([incisor])

        assert not plan.ok
        assert not plan.lines

    def test_a_paid_line_refuses(self, author, player, escher, ganger, claw):
        from n26.library.authoring import add_weapon_profile

        acid = add_weapon_profile(claw, name="Acid ammo", price=15)
        theirs = armed(player, "Theirs", escher, ganger, claw)
        weapon_line = Assignment.objects.get(gang_root=theirs, weapon=claw)
        buy_weapon_profile(weapon_line, acid)

        plan = plan_deletion([acid], remove_free_lines=True)

        assert not plan.ok
        assert any("paid for" in words for words in plan.refusals)
        assert not plan.lines

    def test_a_record_reads_back_with_its_lines(
        self, author, player, escher, ganger, claw, incisor
    ):
        from n26.library.deletion import DeletionPlan

        armed(player, "Theirs", escher, ganger, claw)
        plan = plan_deletion([incisor], remove_free_lines=True)

        again = DeletionPlan.from_record(plan.as_record())

        assert again.same_as(plan)
        assert again.fighters_with_lines == 1


class TestThePage:
    def test_it_names_the_fighters_and_counts_them_on_the_button(
        self, author, client, player, escher, ganger, claw, incisor
    ):
        armed(author, "Mine", escher, ganger, claw)
        armed(player, "Theirs", escher, ganger, claw, fighters=2)

        body = client.get(delete_page(incisor)).content.decode()

        assert "Fighters that have this line" in body
        assert "Theirs" in body
        assert "Fighter 1, Fighter 2" in body
        assert "Delete the firing line and remove it from 3 fighters" in body

    def test_deleting_removes_the_line_from_every_fighter_and_deletes_the_row(
        self, author, client, player, escher, ganger, claw, incisor
    ):
        mine = armed(author, "Mine", escher, ganger, claw)
        theirs = armed(player, "Theirs", escher, ganger, claw, fighters=2)

        response = client.post(delete_page(incisor))

        record = Backfill.objects.get()
        assert record.operation == "n26_delete_firing_line"
        assert response["Location"] == f"/n26/authoring/deletions/{record.pk}/"
        assert record.status == Backfill.Status.DONE, record.error
        assert not WeaponProfile.objects.filter(pk=incisor.pk).exists()
        assert not Assignment.objects.filter(weapon_profile=incisor).exists()
        # The weapon and its own line stay on every fighter.
        assert Assignment.objects.filter(gang_root=theirs, weapon=claw).count() == 2
        assert (
            Assignment.objects.filter(
                gang_root=theirs, weapon_profile__weapon=claw
            ).count()
            == 2
        )
        for gang in (Gang.objects.get(pk=mine.pk), Gang.objects.get(pk=theirs.pk)):
            assert_reconciled(gang)
        report = " ".join(record.summary["report"])
        assert "Theirs: removed the line from 2 fighters" in report
        assert "deleted" in report

        body = client.get(response["Location"]).content.decode()
        assert "Deleted" in body

    def test_a_fighter_who_paid_since_the_page_was_read_stops_the_run(
        self, author, client, player, escher, ganger, claw, incisor
    ):
        from n26.library.authoring import revise

        theirs = armed(player, "Theirs", escher, ganger, claw)
        body = client.get(delete_page(incisor)).content.decode()
        assert "remove it from 1 fighter" in body
        # A second fighter buys the line after the page was read.
        revise(incisor, price=10)
        second = hire(theirs, ganger, "Late", paid=50)
        weapon_line = give_weapon(second, claw, paid=30)
        buy_weapon_profile(weapon_line, incisor)

        response = client.post(delete_page(incisor), follow=True)

        assert "paid for" in response.content.decode()
        assert WeaponProfile.objects.filter(pk=incisor.pk).exists()
        assert not Backfill.objects.exists()

    def test_a_replayed_delivery_finds_nothing_left_to_remove(
        self, author, player, escher, ganger, claw, incisor
    ):
        from n26.library.deletion import remove_free_lines_from

        theirs = armed(player, "Theirs", escher, ganger, claw)
        plan = plan_deletion([incisor], remove_free_lines=True)
        first = remove_free_lines_from(theirs.pk, plan)
        assert "deleted" in first

        again = remove_free_lines_from(theirs.pk, plan)

        assert "already gone" in again

    def test_a_fighter_who_paid_mid_run_fails_the_gang_in_words(
        self, author, player, escher, ganger, claw, incisor
    ):
        from n26.library.authoring import revise
        from n26.library.deletion import Refused, remove_free_lines_from

        theirs = armed(player, "Theirs", escher, ganger, claw)
        plan = plan_deletion([incisor], remove_free_lines=True)
        # A second fighter buys the line, paid, after the plan was read.
        revise(incisor, price=10)
        second = hire(theirs, ganger, "Late", paid=50)
        weapon_line = give_weapon(second, claw, paid=30)
        buy_weapon_profile(weapon_line, incisor)
        plan_now = plan_deletion([incisor], remove_free_lines=True)
        assert not plan_now.ok

        # The gang's own stored lines are still free, so this gang is
        # settled; the paid one is on a fighter the plan never named,
        # and the row stays because something still names it.
        said = remove_free_lines_from(theirs.pk, plan)
        assert "removed the line from 1 fighter" in said
        assert "deleted" not in said
        assert WeaponProfile.objects.filter(pk=incisor.pk).exists()

        # A stored line that was paid for since fails the gang.
        paid_line = Assignment.objects.get(
            gang_root=theirs, weapon_profile=incisor, parent=weapon_line
        )
        stale = DeletionPlan(
            targets=plan.targets,
            lines=(
                Line(
                    pk=str(theirs.pk),
                    name=theirs.name,
                    owner="player",
                    archived=False,
                    fighters=("Late",),
                    assignment_ids=(str(paid_line.pk),),
                ),
            ),
        )
        with pytest.raises(Refused):
            remove_free_lines_from(theirs.pk, stale)

    def test_an_unused_line_is_deleted_in_the_request(self, author, client, incisor):
        body = client.get(delete_page(incisor)).content.decode()
        assert "Nothing else holds it" in body

        response = client.post(delete_page(incisor))

        assert response.status_code == 302
        assert not WeaponProfile.objects.filter(pk=incisor.pk).exists()
        assert not Backfill.objects.exists()
