"""One model's own page: the card in edit mode, the notes box, and the
tabs that make Equip the same place's second face.

The page is the sheet's card over the same derivation — what it says
about a model is what the sheet says — plus the one thing a player
writes rather than earns: their notes, saved here and nowhere else.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang, LedgerEntry

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """Staff, because /n26/ is fenced to staff and testers."""
    return User.objects.create_user("player", is_staff=True)


@pytest.fixture
def gang(tester, gang_type):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=1000,
        credits=1000,
    )


@pytest.fixture
def vex(tester, gang, make_profile, make_statline):
    from n26.core.operations import operation

    profile = make_profile("Ganger", price=0)
    make_statline(profile)
    with operation(gang, actor=tester) as op:
        return op.hire(profile, "Vex")


def edit_url(miniature):
    return reverse("n26-edit-fighter", args=[miniature.pk])


class TestTheModelsOwnPage:
    """The Edit face: the card with its controls out, and the notes box."""

    def test_the_page_wears_the_shared_header(self, client, tester, gang, vex):
        """Name plain in the heading — the tabs say which face is open —
        and both faces addressed as tabs of one place."""
        client.force_login(tester)
        body = client.get(edit_url(vex)).content.decode()
        assert "Vex" in body
        assert "Edit model" in body
        assert reverse("n26-equip", args=[vex.pk]) in body
        assert "Save notes" in body

    def test_the_equip_face_wears_it_too(self, client, tester, gang, vex):
        """The equip screen offers the way back to the Edit face, so the
        two screens read as tabs of one page."""
        client.force_login(tester)
        body = client.get(reverse("n26-equip", args=[vex.pk])).content.decode()
        assert "Edit model" in body
        assert edit_url(vex) in body

    def test_the_sheet_leads_here_and_offers_no_cards_item(
        self, client, tester, gang, vex
    ):
        """Each card carries Edit beside its overflow; the dropdown holds
        the destructive acts and nothing that goes nowhere."""
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert edit_url(vex) in body
        assert ">Cards<" not in body

    def test_a_stranger_gets_a_404(self, client, gang, vex):
        client.force_login(User.objects.create_user("someone-else", is_staff=True))
        assert client.get(edit_url(vex)).status_code == 404


class TestSavingNotes:
    """POST saves the notes; nothing about them touches the books."""

    def test_the_owner_saves_and_lands_back_here(self, client, tester, gang, vex):
        client.force_login(tester)
        response = client.post(edit_url(vex), {"notes": "<p>Owes Kaine a favour.</p>"})
        assert response.status_code == 302
        assert response.url == edit_url(vex)
        vex.refresh_from_db()
        assert vex.notes == "<p>Owes Kaine a favour.</p>"
        # And the page reads them back into the editor.
        assert "Owes Kaine a favour" in client.get(edit_url(vex)).content.decode()

    def test_notes_move_no_money(self, client, tester, gang, vex):
        client.force_login(tester)
        before = LedgerEntry.objects.count()
        client.post(edit_url(vex), {"notes": "<p>New base needed.</p>"})
        assert LedgerEntry.objects.count() == before

    def test_an_emptied_box_clears_them(self, client, tester, gang, vex):
        vex.notes = "<p>Old words.</p>"
        vex.save(update_fields=["notes"])
        client.force_login(tester)
        client.post(edit_url(vex), {"notes": ""})
        vex.refresh_from_db()
        assert vex.notes == ""

    def test_hostile_notes_never_reach_the_page_alive(self, client, tester, gang, vex):
        """Stored as written, sanitised on the way out: the page carries
        the words, never the tag."""
        client.force_login(tester)
        client.post(edit_url(vex), {"notes": "<script>alert(1)</script><p>fine</p>"})
        body = client.get(edit_url(vex)).content.decode()
        assert "<script>alert(1)</script>" not in body
        assert "fine" in body

    def test_a_stranger_saves_nothing(self, client, gang, vex):
        client.force_login(User.objects.create_user("someone-else", is_staff=True))
        response = client.post(edit_url(vex), {"notes": "<p>mine now</p>"})
        assert response.status_code == 404
        vex.refresh_from_db()
        assert vex.notes == ""


class TestRenamingFromHere:
    """The pencil on this page's card opens the dialog here, and the act
    comes back here — ?back=edit is a named place, never a URL."""

    def test_the_url_opens_the_dialog_on_this_page(self, client, tester, gang, vex):
        client.force_login(tester)
        body = client.get(f"{edit_url(vex)}?rename={vex.pk}").content.decode()
        assert "Rename Vex" in body
        assert "?back=edit" in body

    def test_the_act_lands_back_on_the_edit_page(self, client, tester, gang, vex):
        client.force_login(tester)
        response = client.post(
            f"{reverse('n26-rename-fighter', args=[vex.pk])}?back=edit",
            {"name": "Karn"},
        )
        assert response.status_code == 302
        assert response.url == edit_url(vex)
        vex.refresh_from_db()
        assert vex.name == "Karn"

    def test_without_the_word_the_act_lands_on_the_sheet(
        self, client, tester, gang, vex
    ):
        client.force_login(tester)
        response = client.post(
            reverse("n26-rename-fighter", args=[vex.pk]), {"name": "Karn"}
        )
        assert response.url == reverse("n26-gang", args=[gang.pk])
