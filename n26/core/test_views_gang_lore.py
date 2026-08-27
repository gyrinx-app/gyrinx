"""The lore page: the gang's story and every model's, readable by anyone."""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang
from n26.core.operations import operation

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
    return User.objects.create_user("player")


@pytest.fixture
def gang(gang_type, tester):
    return Gang.objects.create(
        name="The Ashen Choir", owner=tester, gang_type=gang_type
    )


@pytest.fixture
def roster(gang, make_profile, make_statline, tester):
    """Two models; only Vex has anything written."""
    profile = make_profile("Ganger", price=0)
    make_statline(profile)
    with operation(gang, actor=tester) as op:
        vex = op.hire(profile, "Vex")
        sull = op.hire(profile, "Sull")
        op.edit_lore(vex, "<p>Nobody knows where Vex came from.</p>")
        op.edit_gang_lore("<p>Founded on a debt.</p>")
    return vex, sull


def lore_url(gang):
    return reverse("n26-gang-lore", args=[gang.pk])


class TestReadingTheLore:
    def test_anyone_reads_it_signed_in_or_not(self, client, gang, roster):
        body = client.get(lore_url(gang)).content.decode()
        assert "Founded on a debt" in body
        assert "Nobody knows where Vex came from" in body

    def test_a_model_with_nothing_written_is_left_off(self, client, gang, roster):
        # The roster tally in the header names every model; what a bare
        # model must not get is a section of its own.
        body = client.get(lore_url(gang)).content.decode()
        assert 'data-lore-entry="Vex"' in body
        assert 'data-lore-entry="Sull"' not in body

    def test_hostile_lore_never_reaches_the_page_alive(
        self, client, tester, gang, roster
    ):
        vex, _ = roster
        with operation(gang, actor=tester) as op:
            op.edit_lore(vex, "<script>alert(1)</script><p>a story</p>")
        body = client.get(lore_url(gang)).content.decode()
        assert "<script>alert(1)</script>" not in body
        assert "a story" in body


class TestTheEditAffordance:
    def test_the_owner_gets_edit_links(self, client, tester, gang, roster):
        vex, _ = roster
        client.force_login(tester)
        body = client.get(lore_url(gang)).content.decode()
        # To the tab the lore is written on, not the edit page's front.
        assert reverse("n26-edit-gang", args=[gang.pk]) + "?tab=notes" in body
        assert reverse("n26-edit-fighter", args=[vex.pk]) in body

    def test_empty_gang_lore_names_the_gap_as_gang_wide(
        self, client, tester, gang, make_profile, make_statline
    ):
        """A gang with no lore of its own can still show a model's
        story. The empty line must name that gap, not read as if
        nothing is written at all."""
        profile = make_profile("Ganger", price=0)
        make_statline(profile)
        with operation(gang, actor=tester) as op:
            vex = op.hire(profile, "Vex")
            op.edit_lore(vex, "<p>Nobody knows where Vex came from.</p>")
        client.force_login(tester)
        body = client.get(lore_url(gang)).content.decode()
        assert "No gang-wide Lore yet" in body
        assert "Nobody knows where Vex came from" in body
        assert reverse("n26-edit-gang", args=[gang.pk]) + "?tab=notes" in body
        assert "Nothing written yet" not in body

    def test_a_reader_gets_none(self, client, gang, roster):
        vex, _ = roster
        body = client.get(lore_url(gang)).content.decode()
        assert reverse("n26-edit-fighter", args=[vex.pk]) not in body


class TestTheWayIn:
    def test_the_sheet_offers_the_owner_the_lore_item(
        self, client, tester, gang, roster
    ):
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert lore_url(gang) in body

    def test_a_signed_in_reader_gets_the_button_too(self, client, gang, roster):
        client.force_login(User.objects.create_user("someone-else"))
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert lore_url(gang) in body

    def test_a_signed_out_reader_gets_it_too(self, client, gang, roster):
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert lore_url(gang) in body
