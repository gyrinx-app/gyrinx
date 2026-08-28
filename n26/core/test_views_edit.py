"""One model's own page: the card in edit mode, the notes box, and the
tabs that make Equip the same place's second face.

The page is the sheet's card over the same derivation — what it says
about a model is what the sheet says — plus the one thing a player
writes rather than earns: their notes, saved here and nowhere else.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang, LedgerEntry, LedgerEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
    return User.objects.create_user("player")


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
        assert ">Edit<" in body
        assert reverse("n26-equip", args=[vex.pk]) in body
        assert "Save notes" in body
        # The gang's figures and the roster tally ride the header's far
        # corner, the same corner the sheet keeps its wealth strip in.
        assert "Models in the gang" in body
        assert "Roster breakdown" in body

    def test_the_equip_face_wears_it_too(self, client, tester, gang, vex):
        """The equip screen offers the way back to the Edit face, so the
        two screens read as tabs of one page."""
        client.force_login(tester)
        body = client.get(reverse("n26-equip", args=[vex.pk])).content.decode()
        assert ">Edit<" in body
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
        client.force_login(User.objects.create_user("someone-else"))
        assert client.get(edit_url(vex)).status_code == 404


class TestSavingNotes:
    """POST saves the notes; nothing about them touches the books."""

    def test_the_owner_saves_and_lands_back_here(self, client, tester, gang, vex):
        client.force_login(tester)
        response = client.post(
            edit_url(vex), {"act": "notes", "notes": "<p>Owes Kaine a favour.</p>"}
        )
        assert response.status_code == 302
        assert response.url == edit_url(vex)
        vex.refresh_from_db()
        assert vex.notes == "<p>Owes Kaine a favour.</p>"
        # And the page reads them back into the editor.
        assert "Owes Kaine a favour" in client.get(edit_url(vex)).content.decode()

    def test_notes_move_no_money(self, client, tester, gang, vex):
        client.force_login(tester)
        before = LedgerEntry.objects.count()
        client.post(edit_url(vex), {"act": "notes", "notes": "<p>New base needed.</p>"})
        assert LedgerEntry.objects.count() == before

    def test_an_emptied_box_clears_them(self, client, tester, gang, vex):
        vex.notes = "<p>Old words.</p>"
        vex.save(update_fields=["notes"])
        client.force_login(tester)
        client.post(edit_url(vex), {"act": "notes", "notes": ""})
        vex.refresh_from_db()
        assert vex.notes == ""

    def test_hostile_notes_never_reach_the_page_alive(self, client, tester, gang, vex):
        """Stored as written, sanitised on the way out: the page carries
        the words, never the tag."""
        client.force_login(tester)
        client.post(
            edit_url(vex),
            {"act": "notes", "notes": "<script>alert(1)</script><p>fine</p>"},
        )
        body = client.get(edit_url(vex)).content.decode()
        assert "<script>alert(1)</script>" not in body
        assert "fine" in body

    def test_a_stranger_saves_nothing(self, client, gang, vex):
        client.force_login(User.objects.create_user("someone-else"))
        response = client.post(
            edit_url(vex), {"act": "notes", "notes": "<p>mine now</p>"}
        )
        assert response.status_code == 404
        vex.refresh_from_db()
        assert vex.notes == ""


def png_upload(name="vex.png"):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (10, 8), "purple").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class TestSavingLore:
    """The lore box: its own form, its own act, its own journal verb."""

    def test_the_owner_saves_and_lands_back_here(self, client, tester, gang, vex):
        client.force_login(tester)
        response = client.post(
            edit_url(vex), {"act": "lore", "lore": "<p>Third dome, third life.</p>"}
        )
        assert response.status_code == 302
        assert response.url == edit_url(vex)
        vex.refresh_from_db()
        assert vex.lore == "<p>Third dome, third life.</p>"
        assert LedgerEvent.objects.filter(
            miniature=vex, kind=LedgerEvent.Kind.LORE_EDITED
        ).exists()

    def test_hostile_lore_never_reaches_the_page_alive(self, client, tester, gang, vex):
        client.force_login(tester)
        client.post(
            edit_url(vex),
            {"act": "lore", "lore": "<script>alert(1)</script><p>a story</p>"},
        )
        body = client.get(edit_url(vex)).content.decode()
        assert "<script>alert(1)</script>" not in body
        assert "a story" in body

    def test_a_stranger_saves_nothing(self, client, gang, vex):
        client.force_login(User.objects.create_user("someone-else"))
        assert (
            client.post(edit_url(vex), {"act": "lore", "lore": "<p>x</p>"}).status_code
            == 404
        )
        vex.refresh_from_db()
        assert vex.lore == ""


class TestSavingWithoutRebuildingThePage:
    """Notes and lore sit on the same screen. Rebuilding it when one
    saves throws away whatever is typed in the other box, so htmx
    answers with nothing to draw and a toast — TinyMCE stays put."""

    def asked(self, client, vex, **data):
        return client.post(edit_url(vex), data, headers={"HX-Request": "true"})

    def test_saving_notes_answers_with_a_toast_and_not_a_page(
        self, client, tester, gang, vex
    ):
        import json

        client.force_login(tester)
        response = self.asked(
            client, vex, act="notes", notes="<p>Owes Kaine a favour.</p>"
        )
        assert response.status_code == 204
        assert "<html" not in response.content.decode()
        said = json.loads(response["HX-Trigger"])["n26-toasts"]
        assert said[0]["variant"] == "success"
        assert said[0]["message"] == "Notes saved."
        vex.refresh_from_db()
        assert vex.notes == "<p>Owes Kaine a favour.</p>"

    def test_saving_lore_leaves_the_notes_alone(self, client, tester, gang, vex):
        vex.notes = "<p>Owes Kaine a favour.</p>"
        vex.save(update_fields=["notes"])
        client.force_login(tester)
        self.asked(client, vex, act="lore", lore="<p>Third dome, third life.</p>")
        vex.refresh_from_db()
        assert vex.lore == "<p>Third dome, third life.</p>"
        assert vex.notes == "<p>Owes Kaine a favour.</p>"

    def test_saving_notes_leaves_the_lore_alone(self, client, tester, gang, vex):
        vex.lore = "<p>Third dome, third life.</p>"
        vex.save(update_fields=["lore"])
        client.force_login(tester)
        self.asked(client, vex, act="notes", notes="<p>Owes Kaine a favour.</p>")
        vex.refresh_from_db()
        assert vex.notes == "<p>Owes Kaine a favour.</p>"
        assert vex.lore == "<p>Third dome, third life.</p>"

    def test_the_boxes_post_in_place(self, client, tester, gang, vex):
        """Each box is its own form, posting to this page, swapping
        nothing — so the other editor is not rebuilt."""
        client.force_login(tester)
        body = client.get(edit_url(vex)).content.decode()
        assert body.count('hx-swap="none"') == 2
        assert f'hx-post="{edit_url(vex)}"' in body
        assert 'name="act" value="notes"' in body
        assert 'name="act" value="lore"' in body
        # Skills and the rest still rebuild the page: they are ticks, not
        # a live editor sitting next to another one.
        assert "Save notes" in body
        assert "Save lore" in body

    def test_the_editor_copies_live_content_before_htmx_reads_the_form(self):
        """TinyMCE keeps what you type in an iframe. htmx serialises the
        textarea, so without copying first a save would store whatever
        was in the box when the page loaded."""
        from pathlib import Path

        import n26.core

        js = (
            Path(n26.core.__file__).parent / "static" / "n26" / "richtext.js"
        ).read_text()
        assert "tinymce.triggerSave()" in js
        assert 'addEventListener(\n        "submit"' in js


class TestThePicture:
    """The picture is an act of its own: a file replaces, the remove
    button clears, and the notes never ride along."""

    def test_an_upload_is_stored_and_recorded(
        self, client, tester, gang, vex, own_storage
    ):
        client.force_login(tester)
        client.post(edit_url(vex), {"act": "picture", "image": png_upload()})
        vex.refresh_from_db()
        assert vex.image.name.startswith("model-images/")
        assert LedgerEvent.objects.filter(
            miniature=vex, kind=LedgerEvent.Kind.IMAGE_SET
        ).exists()
        # The card's picture control appears with it.
        assert vex.image.url in client.get(edit_url(vex)).content.decode()

    def test_the_remove_button_clears_it(self, client, tester, gang, vex, own_storage):
        client.force_login(tester)
        client.post(edit_url(vex), {"act": "picture", "image": png_upload()})
        client.post(edit_url(vex), {"act": "picture", "remove_image": "on"})
        vex.refresh_from_db()
        assert not vex.image
        assert LedgerEvent.objects.filter(
            miniature=vex, kind=LedgerEvent.Kind.IMAGE_CLEARED
        ).exists()

    def test_saving_notes_leaves_the_picture_be(
        self, client, tester, gang, vex, own_storage
    ):
        client.force_login(tester)
        client.post(edit_url(vex), {"act": "picture", "image": png_upload()})
        vex.refresh_from_db()
        held = vex.image.name
        client.post(edit_url(vex), {"act": "notes", "notes": "<p>New base needed.</p>"})
        vex.refresh_from_db()
        assert vex.image.name == held

    def test_a_file_that_is_not_an_image_is_refused(
        self, client, tester, gang, vex, own_storage
    ):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(tester)
        response = client.post(
            edit_url(vex),
            {
                "act": "picture",
                "image": SimpleUploadedFile(
                    "story.txt", b"not a picture", content_type="text/plain"
                ),
            },
            follow=True,
        )
        vex.refresh_from_db()
        assert not vex.image
        # Refused with a reason on the page, never a server error.
        assert response.status_code == 200

    def test_a_refusal_says_which_level_it_is(
        self, client, tester, gang, vex, own_storage
    ):
        """The crop dialog saves in the background and shows a refusal
        where the reader is standing, so it has to tell a refusal from a
        save by reading the page it fetched. Every alert states its level
        (n26/includes/messages.html); without that the dialog draws an
        empty box and the reason is lost with the page nobody sees."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(tester)
        body = client.post(
            edit_url(vex),
            {
                "act": "picture",
                "image": SimpleUploadedFile(
                    "story.txt", b"not a picture", content_type="text/plain"
                ),
            },
            follow=True,
        ).content.decode()

        assert 'data-message="error"' in body
        # And the reason is inside that alert, which is what gets read out.
        reason = body.split('data-message="error"', 1)[1]
        assert "valid image" in reason

    def test_a_save_that_landed_says_so_the_same_way(
        self, client, tester, gang, vex, own_storage
    ):
        """A background save leaves nothing on screen to say it worked, so
        the dialog reads the same alerts and repeats the success as a
        toast."""
        client.force_login(tester)
        body = client.post(
            edit_url(vex),
            {"act": "picture", "image": png_upload()},
            follow=True,
        ).content.decode()

        assert 'data-message="success"' in body
        assert "Picture saved." in body

    def test_the_dialog_carries_the_place_a_refusal_is_drawn(
        self, client, tester, gang, vex
    ):
        """Drawn empty and hidden by the component, filled by the script.
        Missing, a refused save would leave the dialog open saying
        nothing."""
        client.force_login(tester)
        body = client.get(edit_url(vex)).content.decode()

        assert "data-crop-error" in body
        assert "data-crop-error-text" in body

    def test_the_crop_dialog_is_told_the_servers_own_shape(
        self, client, tester, gang, vex
    ):
        """The shape and cap on the file input are str() of the constants
        the server crops with, so the dialog and the store cannot come
        apart."""
        from n26.core.images import MAX_PX, PORTRAIT

        client.force_login(tester)
        body = client.get(edit_url(vex)).content.decode()
        assert f'data-crop="{PORTRAIT}"' in body
        assert f'data-crop-max="{MAX_PX}"' in body


class TestRenamingFromHere:
    """The pencil on this page's card opens the dialog here, and the act
    comes back here — ?back=edit is a named place, never a URL."""

    def test_the_card_offers_the_rename(self, client, tester, gang, vex):
        client.force_login(tester)
        body = client.get(edit_url(vex)).content.decode()
        assert 'aria-label="Rename Vex"' in body
        assert f"?rename={vex.pk}" in body

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
