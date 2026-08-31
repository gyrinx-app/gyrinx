"""The notes page: the gang's notes and every model's, readable by anyone."""

from io import BytesIO

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

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
        op.edit_notes(vex, "<p>Remember the toxin reroll.</p>")
        op.edit_gang_notes("<p>Meet at the sump gate.</p>")
    return vex, sull


def notes_url(gang):
    return reverse("n26-gang-notes", args=[gang.pk])


def png_upload(name="banner.png"):
    buffer = BytesIO()
    Image.new("RGB", (16, 9), "teal").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class TestReadingTheNotes:
    def test_anyone_reads_it_signed_in_or_not(self, client, gang, roster):
        body = client.get(notes_url(gang)).content.decode()
        assert "Meet at the sump gate" in body
        assert "Remember the toxin reroll" in body

    def test_lore_stays_off_this_page(self, client, tester, gang, roster):
        with operation(gang, actor=tester) as op:
            op.edit_gang_lore("<p>Founded on a debt.</p>")
        body = client.get(notes_url(gang)).content.decode()
        assert "Founded on a debt" not in body

    def test_a_model_with_nothing_written_is_left_off(self, client, gang, roster):
        # The roster tally in the header names every model; what a bare
        # model must not get is a section of its own.
        body = client.get(notes_url(gang)).content.decode()
        assert 'data-notes-entry="Vex"' in body
        assert 'data-notes-entry="Sull"' not in body

    def test_hostile_notes_never_reach_the_page_alive(
        self, client, tester, gang, roster
    ):
        vex, _ = roster
        with operation(gang, actor=tester) as op:
            op.edit_notes(vex, "<script>alert(1)</script><p>fine</p>")
        body = client.get(notes_url(gang)).content.decode()
        assert "<script>alert(1)</script>" not in body
        assert "fine" in body


class TestThePicture:
    def test_the_gang_picture_floats_beside_the_notes(
        self, client, tester, gang, roster, own_storage
    ):
        with operation(gang, actor=tester) as op:
            op.set_gang_image(png_upload())
        gang.refresh_from_db()
        body = client.get(notes_url(gang)).content.decode()
        assert gang.image.url in body
        assert f'alt="A picture of {gang.name}"' in body

    def test_a_pictured_model_with_no_notes_still_appears(
        self, client, tester, gang, roster, own_storage
    ):
        _, sull = roster
        with operation(gang, actor=tester) as op:
            op.set_image(sull, png_upload("sull.png"))
        sull.refresh_from_db()
        body = client.get(notes_url(gang)).content.decode()
        assert 'data-notes-entry="Sull"' in body
        assert sull.image.url in body


class TestTheEditAffordance:
    def test_the_owner_gets_edit_links(self, client, tester, gang, roster):
        vex, _ = roster
        client.force_login(tester)
        body = client.get(notes_url(gang)).content.decode()
        # To the tab the notes are written on, not the edit page's front.
        assert reverse("n26-edit-gang", args=[gang.pk]) + "?tab=notes" in body
        assert reverse("n26-edit-fighter", args=[vex.pk]) in body

    def test_empty_gang_notes_names_the_gap_as_gang_wide(
        self, client, tester, gang, make_profile, make_statline
    ):
        """A gang with no notes of its own can still show a model's.
        The empty line must name that gap, not read as if nothing is
        written at all."""
        profile = make_profile("Ganger", price=0)
        make_statline(profile)
        with operation(gang, actor=tester) as op:
            vex = op.hire(profile, "Vex")
            op.edit_notes(vex, "<p>Remember the toxin reroll.</p>")
        client.force_login(tester)
        body = client.get(notes_url(gang)).content.decode()
        assert "No gang-wide notes yet" in body
        assert "Remember the toxin reroll" in body
        assert reverse("n26-edit-gang", args=[gang.pk]) + "?tab=notes" in body
        assert "Nothing written yet" not in body

    def test_a_reader_gets_none(self, client, gang, roster):
        vex, _ = roster
        body = client.get(notes_url(gang)).content.decode()
        assert reverse("n26-edit-fighter", args=[vex.pk]) not in body


class TestTheWayIn:
    def test_the_sheet_offers_the_owner_the_notes_item(
        self, client, tester, gang, roster
    ):
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert notes_url(gang) in body

    def test_a_signed_in_reader_gets_the_button_too(self, client, gang, roster):
        client.force_login(User.objects.create_user("someone-else"))
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert notes_url(gang) in body

    def test_a_signed_out_reader_gets_it_too(self, client, gang, roster):
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert notes_url(gang) in body
