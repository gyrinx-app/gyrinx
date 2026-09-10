"""The Ingest pages: sheets held, a preview, then the rows.

The views are a thin shell over ``n26.library.ingest`` — the planning and
the writing are tested against that API in ``test_ingest.py``. What is
asserted here is only what the pages add: that an upload is held so the
import after it needs no second choosing of the file, that a preview
writes nothing, that importing writes what the preview said, that a
blocking problem stops the write, and that the danger zone puts the
library back to its foundations.
"""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from n26.library.models import Profile, UploadedSheet, Wargear, Weapon
from n26.library.models.collection import Collection
from n26.library.standard_content import STANDARD_CONTENT
from n26.tests.sandbox.test_ingest import (
    EQUIPMENT_CSV,
    EQUIPMENT_LISTS_CSV,
    PROFILES_CSV,
    WEAPON_PROFILES_CSV,
)

pytestmark = pytest.mark.django_db

URL = "/n26/authoring/ingest/"
PREVIEW_URL = "/n26/authoring/ingest/preview/"


def sheet_url(sheet):
    return f"/n26/authoring/ingest/sheet/{sheet}/"


@pytest.fixture
def author(client):
    user = User.objects.create_user("author", is_staff=True)
    client.force_login(user)
    return user


@pytest.fixture
def foundation(default_pack):
    for item in STANDARD_CONTENT.values():
        item.create()


def upload(text, name):
    """A CSV as a browser would send it — named, because a real upload
    always is and Django reads the name off the file."""
    return SimpleUploadedFile(name, text.strip().encode("utf-8"), "text/csv")


#: The four sheets, as a browser would send them: the sheet's own page,
#: and the file posted to it.
SHEETS = {
    "equipment": (EQUIPMENT_CSV, "equipment.csv"),
    "weapon_profiles": (WEAPON_PROFILES_CSV, "profiles.csv"),
    "equipment_lists": (EQUIPMENT_LISTS_CSV, "lists.csv"),
    "profiles": (PROFILES_CSV, "fighters.csv"),
}


def hold(client, sheet, text=None, name=None):
    """Upload one sheet, the way an author does — one page, one file."""
    default_text, default_name = SHEETS.get(sheet, (None, f"{sheet}.csv"))
    return client.post(
        sheet_url(sheet),
        {"file": upload(text or default_text, name or default_name)},
        follow=True,
    )


def hold_all(client):
    for sheet in SHEETS:
        hold(client, sheet)


class TestHoldingTheSheets:
    """One sheet at a time, and the file stays put once given."""

    def test_the_page_offers_every_sheet_its_own_upload(
        self, author, client, foundation
    ):
        from n26.library.sheets import SHEET_NAMES

        body = client.get(URL).content.decode()
        assert SHEET_NAMES  # there is something to check
        for sheet in SHEET_NAMES:
            assert sheet_url(sheet) in body
        # The sheets are named as the spreadsheet names them.
        assert "All Profiles" in body
        assert "Equipment lists" in body
        # ...and nothing is held yet.
        assert "Nothing held" in body

    def test_a_sheets_page_takes_one_file(self, author, client, foundation):
        body = client.get(sheet_url("profiles")).content.decode()
        assert 'enctype="multipart/form-data"' in body
        assert body.count('type="file"') == 1
        assert "All Profiles" in body

    def test_an_upload_is_held_and_said_so(self, author, client, foundation):
        body = hold(client, "equipment").content.decode()

        held = UploadedSheet.objects.get(owner=author)
        assert held.sheet == "equipment"
        assert held.filename == "equipment.csv"
        assert held.lines > 0
        # The page names the file, so one export can be told from another.
        assert "equipment.csv" in body

    def test_holding_a_sheet_writes_no_content(self, author, client, foundation):
        hold_all(client)

        assert Weapon.objects.count() == 0
        assert Profile.objects.count() == 0

    def test_uploading_the_same_sheet_again_replaces_it(
        self, author, client, foundation
    ):
        hold(client, "equipment")
        first = UploadedSheet.objects.get(owner=author)

        hold(client, "equipment", name="corrected.csv")

        assert UploadedSheet.objects.filter(owner=author).count() == 1
        held = UploadedSheet.objects.get(owner=author)
        assert held.filename == "corrected.csv"
        assert not held.file.storage.exists(first.file.name)

    def test_a_refused_replacement_leaves_the_held_sheet_standing(
        self, author, client, foundation
    ):
        """An author who uploads the wrong thing over a good sheet still
        holds the good one."""
        hold(client, "equipment")
        standing = UploadedSheet.objects.get(owner=author)

        client.post(
            sheet_url("equipment"),
            {"file": SimpleUploadedFile("notes.png", b"\x89PNG\r\n\x1a\n\x00\x01")},
        )

        held = UploadedSheet.objects.get(owner=author)
        assert held.pk == standing.pk
        assert held.filename == "equipment.csv"
        assert held.file.storage.exists(held.file.name)

    def test_removing_a_sheet_nothing_is_held_for_says_so(
        self, author, client, foundation
    ):
        body = client.post(URL, {"remove": "equipment"}, follow=True).content.decode()
        assert "No Equipment sheet was held" in body

    def test_a_held_sheet_can_be_removed(self, author, client, foundation):
        hold(client, "equipment")
        stored = UploadedSheet.objects.get(owner=author).file.name

        body = client.post(URL, {"remove": "equipment"}, follow=True).content.decode()

        assert not UploadedSheet.objects.filter(owner=author).exists()
        assert "Removed the Equipment sheet" in body

        from django.core.files.storage import default_storage

        assert not default_storage.exists(stored)

    def test_everything_held_can_go_at_once(self, author, client, foundation):
        hold_all(client)

        client.post(URL, {"remove": "everything"}, follow=True)

        assert not UploadedSheet.objects.filter(owner=author).exists()

    def test_a_file_that_cannot_be_read_is_refused_beside_the_picker(
        self, author, client, foundation
    ):
        """Refused where the file was chosen, not previewed as nothing."""
        body = client.post(
            sheet_url("equipment"),
            {"file": SimpleUploadedFile("notes.png", b"\x89PNG\r\n\x1a\n\x00\x01")},
        ).content.decode()

        assert not UploadedSheet.objects.exists()
        assert "not text this can read" in body

    def test_a_sheet_with_no_lines_under_its_heading_is_refused(
        self, author, client, foundation
    ):
        body = client.post(
            sheet_url("equipment"),
            {"file": upload("Assignable,Section,Category,Name", "empty.csv")},
        ).content.decode()

        assert not UploadedSheet.objects.exists()
        assert "nothing under it" in body

    def test_a_sheet_nobody_reads_is_not_a_page(self, author, client, foundation):
        assert client.get(sheet_url("invented")).status_code == 404

    def test_one_authors_sheets_are_not_anothers(self, author, client, foundation):
        """Two authors working at once each hold their own set."""
        hold(client, "equipment")
        other = User.objects.create_user("other", is_staff=True)
        client.force_login(other)

        body = client.get(URL).content.decode()

        assert "equipment.csv" not in body
        assert client.get(PREVIEW_URL, follow=True).request["PATH_INFO"] == URL


class TestPreviewing:
    def test_a_preview_needs_no_second_choosing_of_the_file(
        self, author, client, foundation
    ):
        """The whole point: upload once, then look as often as you like."""
        hold_all(client)

        first = client.get(PREVIEW_URL).content.decode()
        second = client.get(PREVIEW_URL).content.decode()

        for body in (first, second):
            assert "Weapon" in body
            assert "to create" in body
        assert Weapon.objects.count() == 0

    def test_a_preview_writes_nothing(self, author, client, foundation):
        hold_all(client)

        body = client.get(PREVIEW_URL).content.decode()

        assert Weapon.objects.count() == 0
        assert Profile.objects.count() == 0
        assert "to create" in body

    def test_a_preview_names_the_sheets_it_read(self, author, client, foundation):
        hold_all(client)

        body = client.get(PREVIEW_URL).content.decode()

        assert "equipment.csv" in body
        assert "fighters.csv" in body

    def test_a_preview_names_a_sheet_that_is_not_held(self, author, client, foundation):
        """An absence is what an author is checking for, so the sheets
        left out are named rather than silently skipped."""
        for sheet in SHEETS:
            if sheet != "profiles":
                hold(client, sheet)

        body = client.get(PREVIEW_URL).content.decode()

        assert "Not held: All Profiles" in body

    def test_a_preview_says_what_the_problems_are(self, author, client, foundation):
        hold_all(client)

        body = client.get(PREVIEW_URL).content.decode()

        # The fixture's Escher list caps a pet per gang, which is not a
        # restriction on use and so is carried past rather than applied.
        assert "not a restriction on use" in body
        assert "noted" in body

    def test_previewing_nothing_says_to_upload_first(self, author, client, foundation):
        body = client.get(PREVIEW_URL, follow=True).content.decode()
        assert "No sheets uploaded yet" in body


class TestImporting:
    def test_importing_writes_what_the_preview_said(self, author, client, foundation):
        hold_all(client)
        client.get(PREVIEW_URL)

        body = client.post(PREVIEW_URL, follow=True).content.decode()

        assert Weapon.objects.count() == 6
        assert Wargear.objects.count() == 2
        assert Profile.objects.count() == 3
        assert Collection.objects.filter(name="Escher Equipment List").exists()
        assert "Created" in body

    def test_an_import_lands_back_on_a_fresh_reading(self, author, client, foundation):
        """A reload must not offer to run the import a second time, and
        the honest confirmation is the same plan finding nothing to do."""
        hold_all(client)

        response = client.post(PREVIEW_URL, follow=True)

        assert response.redirect_chain[-1][0] == PREVIEW_URL
        body = response.content.decode()
        assert "0 to create" in body

    def test_the_sheets_are_still_held_after_an_import(
        self, author, client, foundation
    ):
        hold_all(client)

        client.post(PREVIEW_URL, follow=True)

        assert UploadedSheet.objects.filter(owner=author).count() == len(SHEETS)

    def test_a_blocking_problem_writes_nothing(self, author, client, foundation):
        """A catalogue row typed as a priced weapon profile but naming no
        profile would lose its price on the way in, so the upload waits
        rather than landing something wrong."""
        equipment = """
Assignable,Section,Category,Name,Profile,Cost,TP,ID
Weapon,Close combat weapons,Lances,Frag lance,,-,E,x
Weapon Profile,Close combat weapons,Lances,Frag lance,,45,E,y
"""
        hold(client, "equipment", text=equipment)

        body = client.post(PREVIEW_URL, follow=True).content.decode()

        assert Weapon.objects.count() == 0
        assert "block this upload" in body
        assert "names no Profile" in body  # and says which line

    def test_a_blocked_upload_is_not_offered_an_import_button(
        self, author, client, foundation
    ):
        equipment = """
Assignable,Section,Category,Name,Profile,Cost,TP,ID
Weapon,Close combat weapons,Lances,Frag lance,,-,E,x
Weapon Profile,Close combat weapons,Lances,Frag lance,,45,E,y
"""
        hold(client, "equipment", text=equipment)

        body = client.get(PREVIEW_URL).content.decode()

        assert "block this upload" in body
        assert ">Import<" not in body

    def test_a_list_line_nothing_defines_is_left_off_not_refused(
        self, author, client, foundation
    ):
        """The list arrives one entry short, said in the report — the
        rest of a good upload is not held back for it."""
        lists = """
Collection,Title,Section,Category,Name,Profile,Credits,Restrictions,ID
Equipment List,Escher,Ranged weapons,Web weapons,Web pisol,,90,,x
"""
        hold(client, "equipment_lists", text=lists)

        body = client.post(PREVIEW_URL, follow=True).content.decode()

        assert "Web pisol" in body
        assert "arrives without it" in body
        assert "block this upload" not in body

    def test_importing_twice_creates_nothing_the_second_time(
        self, author, client, foundation
    ):
        hold_all(client)
        client.post(PREVIEW_URL, follow=True)
        weapons = Weapon.objects.count()

        client.post(PREVIEW_URL, follow=True)

        assert Weapon.objects.count() == weapons


class TestItIsStaffOnly:
    def test_a_signed_out_visitor_cannot_reach_it(self, client, foundation):
        assert client.get(URL).status_code in (302, 404)

    def test_a_signed_out_visitor_cannot_upload_a_sheet(self, client, foundation):
        assert client.get(sheet_url("equipment")).status_code in (302, 404)

    def test_a_signed_out_visitor_cannot_preview(self, client, foundation):
        assert client.get(PREVIEW_URL).status_code in (302, 404)
