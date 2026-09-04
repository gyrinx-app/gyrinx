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
from n26.core.operations import operation

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


class TestKitActionsOnTheCard:
    """Sell, refund, delete and Add accessory sit on the Edit card, so
    taking something off does not mean finding it on the Equip tab."""

    @pytest.fixture
    def sword(self, gang, vex, tester):
        from n26.library.authoring import create_wargear

        thing = create_wargear("Sword", price=20)
        with operation(gang, actor=tester) as op:
            return op.buy(vex, thing=thing, paid=20)

    @pytest.fixture
    def gun(self, gang, vex, tester):
        from n26.library.authoring import create_weapon

        weapon = create_weapon("Lasgun", price=15, profiles=[("", 0)])
        with operation(gang, actor=tester) as op:
            return op.buy(vex, thing=weapon, paid=15)

    def test_gear_offers_sell_and_the_rest_behind_one_menu(
        self, client, tester, vex, sword
    ):
        client.force_login(tester)
        body = client.get(edit_url(vex)).content.decode()
        at = edit_url(vex)
        assert f"{at}?sell={sword.pk}" in body
        assert f"{at}?refund={sword.pk}" in body
        assert f"{at}?remove={sword.pk}" in body
        assert f"{at}?reassign={sword.pk}" in body
        assert "More for Sword" in body
        # One quiet chevron holds every act; the listing's red Sell button
        # is not drawn on this card.
        assert "bg-red-500" not in body

    def test_a_weapon_offers_add_accessory(self, client, tester, vex, gun):
        client.force_login(tester)
        body = client.get(edit_url(vex)).content.decode()
        at = edit_url(vex)
        assert f"{at}?sell={gun.pk}" in body
        assert f"{at}?accessorise={gun.pk}" in body
        assert "Add accessory" in body

    def test_the_url_opens_the_sell_dialog_on_this_page(
        self, client, tester, vex, sword
    ):
        client.force_login(tester)
        body = client.get(f"{edit_url(vex)}?sell={sword.pk}").content.decode()
        assert "Sell Sword?" in body
        assert "<dialog" in body
        assert reverse("n26-sell", args=[sword.pk]) in body

    def test_a_bolted_accessory_offers_detach_and_not_fit_alone(
        self, client, tester, gang, vex, gun
    ):
        from n26.library.authoring import create_weapon_accessory

        sight = create_weapon_accessory("Telescopic sight", price=25)
        with operation(gang, actor=tester) as op:
            bolted = op.buy(gun, thing=sight)

        client.force_login(tester)
        body = client.get(edit_url(vex)).content.decode()
        at = edit_url(vex)

        assert "Detach" in body
        assert f"{at}?detach={bolted.pk}" in body
        assert f"{at}?remove={bolted.pk}" in body
        assert f"{at}?fit={bolted.pk}" not in body
        assert "More for Telescopic sight" in body

    def test_a_second_gun_lets_the_accessory_be_fitted_to_it(
        self, client, tester, gang, vex, gun
    ):
        from n26.library.authoring import create_weapon, create_weapon_accessory

        sight = create_weapon_accessory("Telescopic sight", price=25)
        stub = create_weapon("Stub gun", price=5, profiles=[("", 0)])
        with operation(gang, actor=tester) as op:
            bolted = op.buy(gun, thing=sight)
            op.buy(vex, thing=stub, paid=5)

        client.force_login(tester)
        body = client.get(edit_url(vex)).content.decode()
        at = edit_url(vex)

        assert f"{at}?detach={bolted.pk}" in body
        assert f"{at}?fit={bolted.pk}" in body
        assert "Fit to a weapon" in body

    def test_the_url_opens_the_detach_dialog_on_this_page(
        self, client, tester, gang, vex, gun
    ):
        from n26.library.authoring import create_weapon_accessory

        sight = create_weapon_accessory("Telescopic sight", price=25)
        with operation(gang, actor=tester) as op:
            bolted = op.buy(gun, thing=sight)

        client.force_login(tester)
        body = client.get(f"{edit_url(vex)}?detach={bolted.pk}").content.decode()

        assert "Take Telescopic sight off Lasgun?" in body
        assert "The fighter will still hold it." in body
        assert reverse("n26-reassign", args=[bolted.pk]) in body
        assert 'name="to" value="held"' in body

    def test_the_url_opens_the_accessory_dialog_on_this_page(
        self, client, tester, vex, gun
    ):
        from n26.library.authoring import create_weapon_accessory

        create_weapon_accessory("Telescopic sight", price=25)
        client.force_login(tester)
        body = client.get(f"{edit_url(vex)}?accessorise={gun.pk}").content.decode()
        assert "Add an accessory to Lasgun" in body
        assert "Telescopic sight" in body

    def test_a_kit_menu_item_fetches_its_panel(self, client, tester, vex, sword):
        """The card's menu items ask for the confirmation alone, and the
        page holds the host the answer lands in. Without script they are
        still links, and the server draws the page with the panel open."""
        client.force_login(tester)
        body = client.get(edit_url(vex)).content.decode()

        assert f'hx-get="{edit_url(vex)}?sell={sword.pk}"' in body
        assert 'id="n26-dialog-host"' in body

    def test_the_weapon_menu_fetches_its_panel_too(self, client, tester, vex, gun):
        """A gun's name draws its own menu, through a different route
        from the rest of the kit; it carries the same acts the same way."""
        client.force_login(tester)
        body = client.get(edit_url(vex)).content.decode()

        assert f'hx-get="{edit_url(vex)}?accessorise={gun.pk}"' in body
        assert f'hx-get="{edit_url(vex)}?sell={gun.pk}"' in body

    def test_the_page_asked_for_whole_is_drawn_whole(self, client, tester, vex, sword):
        """Only a click that named a panel gets the panel."""
        client.force_login(tester)
        body = client.get(
            edit_url(vex), headers={"HX-Request": "true"}
        ).content.decode()

        assert "<html" in body
        assert "Characteristics" in body

    def test_a_click_with_script_is_answered_with_the_panel_alone(
        self, client, tester, vex, sword
    ):
        """The question is about one thing the model holds, so the card,
        the edit boxes and the roster are not drawn to ask it. The panel
        replaces the host by id and corrects the address to the one that
        draws it on a plain visit."""
        client.force_login(tester)
        response = client.get(
            f"{edit_url(vex)}?sell={sword.pk}", headers={"HX-Request": "true"}
        )
        body = response.content.decode()

        assert response["HX-Replace-Url"] == f"{edit_url(vex)}?sell={sword.pk}"
        assert 'id="n26-dialog-host" hx-swap-oob="true"' in body
        assert "<dialog" in body
        assert reverse("n26-sell", args=[sword.pk]) in body
        assert "Characteristics" not in body
        # The panel's own submit is not partial here (see panel_response).
        assert "hx-post" not in body

    def test_the_accessory_question_is_answered_the_same_way(
        self, client, tester, vex, gun
    ):
        from n26.library.authoring import create_weapon_accessory

        create_weapon_accessory("Telescopic sight", price=25)
        client.force_login(tester)
        response = client.get(
            f"{edit_url(vex)}?accessorise={gun.pk}", headers={"HX-Request": "true"}
        )
        body = response.content.decode()

        assert 'id="n26-dialog-host" hx-swap-oob="true"' in body
        assert "Add an accessory to Lasgun" in body
        assert "Telescopic sight" in body

    def test_the_panel_alone_costs_fewer_queries_than_the_page(
        self, client, tester, vex, sword
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(tester)
        with CaptureQueriesContext(connection) as whole:
            client.get(f"{edit_url(vex)}?sell={sword.pk}")
        with CaptureQueriesContext(connection) as panel:
            client.get(
                f"{edit_url(vex)}?sell={sword.pk}", headers={"HX-Request": "true"}
            )

        assert len(panel) < len(whole)

    def test_a_click_naming_nothing_closes_the_panel(self, client, tester, vex):
        """An address naming a dialog for something that is not there
        answers with an empty host, which closes whatever was open."""
        client.force_login(tester)
        response = client.get(
            f"{edit_url(vex)}?sell=nothing", headers={"HX-Request": "true"}
        )
        body = response.content.decode()

        assert 'id="n26-dialog-host" hx-swap-oob="true"' in body
        assert "<dialog" not in body

    def test_selling_lands_back_on_the_edit_page(
        self, client, tester, gang, vex, sword
    ):
        client.force_login(tester)
        response = client.post(
            reverse("n26-sell", args=[sword.pk]),
            {"return": edit_url(vex)},
        )
        assert response.status_code == 302
        assert response.url == edit_url(vex)
        sword.refresh_from_db()
        assert sword.archived is True
        gang.refresh_from_db()
        from n26.core.reconcile import assert_reconciled

        assert_reconciled(gang)

    def test_the_sheet_does_not_offer_them(self, client, tester, gang, vex, sword):
        """The gang sheet is mid-game reading. Taking kit off is the
        model's own page, and a card on the sheet that offered Sell
        would be offering it next to every other fighter too."""
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert f"sell={sword.pk}" not in body
        assert "More for Sword" not in body


class TestTheQueryBudget:
    """One model's page asks about one model.

    The count is pinned so it changes deliberately, and measured against
    a roster to hold the shape of it: what this page draws is a fact
    about the model in the address, so the rest of the gang costs
    nothing. A page that walks the roster to find one card reads the
    same and passes every other test here.

    Measured after one warm request. The first request of a session
    writes its own row and reads the site, which would pin the session
    machinery alongside the page.
    """

    def measure(self, client, url):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        assert client.get(url).status_code == 200
        with CaptureQueriesContext(connection) as captured:
            assert client.get(url).status_code == 200
        return len(captured.captured_queries)

    def crowd(self, gang, tester, make_profile, make_statline, how_many):
        """Fill the gang out, so a count that follows the roster shows."""
        from n26.core.operations import operation

        profile = make_profile("Juve", price=0)
        make_statline(profile)
        for n in range(how_many):
            with operation(gang, actor=tester) as op:
                op.hire(profile, f"Extra {n}")

    def test_the_page_costs_a_fixed_number(self, client, tester, gang, vex):
        client.force_login(tester)
        assert self.measure(client, edit_url(vex)) == 40

    def test_the_rest_of_the_gang_costs_nothing(
        self, client, tester, gang, vex, make_profile, make_statline
    ):
        client.force_login(tester)
        alone = self.measure(client, edit_url(vex))
        self.crowd(gang, tester, make_profile, make_statline, 12)
        assert self.measure(client, edit_url(vex)) == alone

    def test_the_kit_costs_nothing_per_copy(self, client, tester, gang, vex):
        """Each piece of kit now carries Sell and the rest, and saying
        what a copy was bought with must come off the card already built,
        never from a query per copy."""
        from n26.library.authoring import create_wargear, create_weapon

        sword = create_wargear("Sword", price=20)
        gun = create_weapon("Lasgun", price=15, profiles=[("", 0)])
        with operation(gang, actor=tester) as op:
            op.buy(vex, thing=sword, paid=20)
            op.buy(vex, thing=gun, paid=15)
        client.force_login(tester)
        one_each = self.measure(client, edit_url(vex))
        with operation(gang, actor=tester) as op:
            for _ in range(4):
                op.buy(vex, thing=sword, paid=20)
                op.buy(vex, thing=gun, paid=15)
        assert self.measure(client, edit_url(vex)) == one_each
