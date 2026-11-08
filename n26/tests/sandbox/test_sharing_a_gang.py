"""Share gang sheets with authenticated and anonymous readers while restricting edits to
the owner. Signed-in readers may print or clone the source gang without modifying it.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.library.authoring import (
    create_counter,
    create_skill,
    create_wargear,
    create_weapon,
    ef_offers_choice,
    modifier,
    targets_model,
)
from n26.tests.sandbox.actions import (
    assign,
    found_gang,
    give_weapon,
    hire,
    tally,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("the-owner")


@pytest.fixture
def stranger(db):
    return User.objects.create_user("a-stranger")


@pytest.fixture
def ganger(make_profile, make_statline):
    profile = make_profile("Ganger", price=55)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    return profile


@pytest.fixture
def gang(gang_type, owner, ganger):
    """A gang with one armed model, a gang counter and stash equipment."""
    gang = found_gang("The Ashen Choir", gang_type, owner=owner)
    vex = hire(gang, ganger, "Vex", paid=55, actor=owner)
    give_weapon(vex, create_weapon("Autogun", price=30), paid=30, actor=owner)
    tally(assign(create_counter("Meat"), gang=gang, actor=owner), +3)
    assign(create_wargear("Ammo crate", price=25), stash=gang.stash, actor=owner)
    return gang


@pytest.fixture
def at(gang):
    return reverse("n26-gang", args=[gang.pk])


def read(client, at):
    response = client.get(at)
    assert response.status_code == 200
    return response.content.decode()


class TestWhoMayRead:
    def test_the_owner_reads_it(self, client, owner, gang, at):
        client.force_login(owner)
        assert gang.name in read(client, at)

    def test_a_signed_in_stranger_reads_it(self, client, stranger, gang, at):
        client.force_login(stranger)
        assert gang.name in read(client, at)

    def test_a_visitor_who_has_not_signed_in_reads_it(self, client, gang, at):
        assert gang.name in read(client, at)

    def test_an_archived_gang_is_nobodys_to_read(self, client, gang, at):
        gang.archived = True
        gang.save()

        assert client.get(at).status_code == 404


class TestNothingIsWithheld:
    """Show the same roster, counters and stash data to all readers."""

    def test_a_stranger_sees_the_fighters_and_their_kit(self, client, gang, at):
        body = read(client, at)

        assert "Vex" in body
        assert "Autogun" in body

    def test_a_stranger_sees_what_the_gang_is_worth_and_holds(self, client, gang, at):
        body = read(client, at)

        assert "Meat" in body
        assert "Ammo crate" in body

    def test_a_stranger_reads_the_same_gang_the_owner_does(
        self, client, owner, gang, at
    ):
        theirs = read(client, at)
        client.force_login(owner)
        mine = read(client, at)

        for said in (gang.name, "Vex", "Autogun", "Meat", "Ammo crate"):
            assert said in theirs and said in mine


class TestNoSourceControls:
    """Restrict actions that modify the shared gang to its owner. Print and Clone are
    checked separately because they do not modify that gang.
    """

    def test_the_gang_level_controls_are_the_owners_alone(
        self, client, owner, gang, at
    ):
        theirs = read(client, at)
        client.force_login(owner)
        mine = read(client, at)

        for control in ("Hire Fighters", "Your other gangs", "More actions"):
            assert control in mine
            assert control not in theirs

    def test_the_per_fighter_controls_go_too(self, client, owner, gang, at):
        theirs = read(client, at)
        client.force_login(owner)
        mine = read(client, at)

        assert "/fighters/" in mine
        assert "/fighters/" not in theirs
        assert "/edit/" in mine
        assert "?delete=" not in theirs

    def test_no_way_through_to_a_screen_that_would_refuse_them(
        self, client, stranger, gang, at
    ):
        """Omit owner-only destinations for both anonymous and signed-in non-owners."""
        signed_out = read(client, at)
        client.force_login(stranger)
        signed_in = read(client, at)

        for body in (signed_out, signed_in):
            assert reverse("n26-hire-fighter", args=[gang.pk]) not in body
            assert reverse("n26-edit-gang", args=[gang.pk]) not in body
            assert reverse("n26-gang-history", args=[gang.pk]) not in body


class TestAReadersOwnActions:
    """Permit signed-in readers to print the roster or create their own clone. Anonymous
    readers can read but receive neither action.
    """

    def test_a_signed_in_stranger_is_offered_print(self, client, stranger, gang, at):
        client.force_login(stranger)

        assert reverse("n26-print-setup", args=[gang.pk]) in read(client, at)

    def test_a_signed_in_stranger_is_offered_clone(self, client, stranger, gang, at):
        client.force_login(stranger)
        url = reverse("n26-clone-gang", args=[gang.pk])

        assert url in read(client, at)
        assert client.get(url).status_code == 200

    def test_a_visitor_who_has_not_signed_in_gets_neither(self, client, gang, at):
        body = read(client, at)

        assert reverse("n26-print-setup", args=[gang.pk]) not in body
        assert reverse("n26-clone-gang", args=[gang.pk]) not in body

    def test_the_control_leads_somewhere_that_opens_for_them(
        self, client, stranger, gang
    ):
        client.force_login(stranger)

        setup = client.get(reverse("n26-print-setup", args=[gang.pk]))
        paper = client.get(reverse("n26-print", args=[gang.pk]))

        assert setup.status_code == 200
        assert paper.status_code == 200
        assert "Vex" in paper.content.decode()

    def test_signing_in_still_adds_no_source_editing_controls(
        self, client, stranger, gang, at
    ):
        client.force_login(stranger)
        body = read(client, at)

        assert "Print" in body
        assert "Clone gang" in body
        for control in ("Hire Fighters", "Buy Equipment", "History", "Delete gang"):
            assert control not in body


class TestAQuestionNobodyHasChosenFor:
    """Display unresolved choices to non-owners as text without editable links."""

    @pytest.fixture
    def asked(self, gang, ganger, owner):
        from n26.library.models import Skill

        create_skill("Catfall")
        modifier(
            "A Ganger starts with a skill",
            targets_model(),
            ef_offers_choice(Skill),
            attach_to=ganger,
        )
        return gang

    def test_the_owner_is_offered_the_choice(self, client, owner, asked, at):
        client.force_login(owner)
        body = read(client, at)

        assert "Choose" in body

    def test_a_stranger_reads_it_and_cannot_click_it(self, client, asked, at):
        import re

        body = read(client, at)

        assert "Choose" in body
        # Retain the choice label without an anchor.
        assert not re.search(r"<a[^>]*>\s*Choose", body)
