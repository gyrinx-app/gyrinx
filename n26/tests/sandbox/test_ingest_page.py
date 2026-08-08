"""The Ingest page: spreadsheets in, a preview, then the rows.

The view is a thin shell over ``n26.library.ingest`` — the planning and
the writing are tested against that API in ``test_ingest.py``. What is
asserted here is only what the page adds: that a preview writes
nothing, that importing writes what the preview said, that a blocking
problem stops the write, and that the danger zone puts the library back
to its foundations.
"""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from n26.library.models import Profile, Wargear, Weapon
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
CLEAR_URL = "/n26/authoring/ingest/clear/"


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


def sheets():
    """The four files, as a browser would send them."""
    return {
        "equipment": upload(EQUIPMENT_CSV, "equipment.csv"),
        "weapon_profiles": upload(WEAPON_PROFILES_CSV, "profiles.csv"),
        "equipment_lists": upload(EQUIPMENT_LISTS_CSV, "lists.csv"),
        "profiles": upload(PROFILES_CSV, "fighters.csv"),
    }


class TestPreviewing:
    def test_the_page_offers_every_sheet_as_a_file_picker(
        self, author, client, foundation
    ):
        """A field the dispatch does not recognise falls through to a
        text box, which looks like a form and cannot take a file."""
        body = client.get(URL).content.decode()
        for field in ("equipment", "weapon_profiles", "equipment_lists", "profiles"):
            assert f'name="{field}"' in body
        assert body.count('type="file"') == 4
        assert 'enctype="multipart/form-data"' in body

    def test_a_preview_writes_nothing(self, author, client, foundation):
        body = client.post(URL, sheets()).content.decode()

        assert Weapon.objects.count() == 0
        assert Profile.objects.count() == 0
        # ...and it still says what an import would do.
        assert "Weapon" in body
        assert "to create" in body

    def test_a_preview_says_what_the_problems_are(self, author, client, foundation):
        body = client.post(URL, sheets()).content.decode()
        # The fixture's Escher list caps a pet per gang, which is not a
        # restriction on use and so is carried past rather than applied.
        assert "not a restriction on use" in body
        assert "noted" in body

    def test_choosing_nothing_says_so(self, author, client, foundation):
        body = client.post(URL, {}, follow=True).content.decode()
        assert "Choose at least one sheet" in body


class TestImporting:
    def test_importing_writes_what_the_preview_said(self, author, client, foundation):
        body = client.post(URL, {**sheets(), "apply": "1"}).content.decode()

        assert Weapon.objects.count() == 6
        assert Wargear.objects.count() == 2
        assert Profile.objects.count() == 3
        assert Collection.objects.filter(name="Escher Equipment List").exists()
        assert "Imported" in body

    def test_a_blocking_problem_writes_nothing(self, author, client, foundation):
        """A catalogue row typed as a priced firing line but naming no
        profile would lose its price on the way in, so the upload waits
        rather than landing something wrong."""
        equipment = """
Assignable,Section,Category,Name,Profile,Cost,TP,ID
Weapon,Close combat weapons,Lances,Frag lance,,-,E,x
Weapon Profile,Close combat weapons,Lances,Frag lance,,45,E,y
"""
        response = client.post(
            URL,
            {"equipment": upload(equipment, "equipment.csv"), "apply": "1"},
            follow=True,
        )
        body = response.content.decode()

        assert Weapon.objects.count() == 0
        assert "block this upload" in body
        assert "names no Profile" in body  # and says which line

    def test_a_list_line_nothing_defines_is_left_off_not_refused(
        self, author, client, foundation
    ):
        """The list arrives one entry short, said in the report — the
        rest of a good upload is not held back for it."""
        lists = """
Collection,Title,Section,Category,Name,Profile,Credits,Restrictions,ID
Equipment List,Escher,Ranged weapons,Web weapons,Web pisol,,90,,x
"""
        body = client.post(
            URL,
            {"equipment_lists": upload(lists, "lists.csv"), "apply": "1"},
            follow=True,
        ).content.decode()

        assert "Web pisol" in body
        assert "arrives without it" in body
        assert "block this upload" not in body

    def test_importing_twice_creates_nothing_the_second_time(
        self, author, client, foundation
    ):
        client.post(URL, {**sheets(), "apply": "1"})
        weapons = Weapon.objects.count()

        client.post(URL, {**sheets(), "apply": "1"})

        assert Weapon.objects.count() == weapons


class TestTheDangerZone:
    """Undoing an import is its own page: it says what would go, and
    only a post takes it."""

    def test_the_ingest_page_only_links_to_it(self, author, client, foundation):
        """Counting is real work, and a page that did it on every visit
        would charge everyone for a button almost nobody presses."""
        body = client.get(URL).content.decode()
        assert "Danger zone" in body
        assert CLEAR_URL in body
        # The count belongs on the confirmation, not here.
        assert "What would go" not in body

    def test_it_says_what_would_go_before_taking_it(self, author, client, foundation):
        client.post(URL, {**sheets(), "apply": "1"})

        body = client.get(CLEAR_URL).content.decode()

        assert "What would go" in body
        assert "weapons" in body
        assert Weapon.objects.count() == 6  # and looking took nothing

    def test_the_count_is_what_actually_goes(self, author, client, foundation):
        """A confirmation promising different numbers from the ones that
        went would be worse than none — so both read one definition."""
        from n26.library.ingest import count_imported

        client.post(URL, {**sheets(), "apply": "1"})
        promised = count_imported()

        client.post(CLEAR_URL, follow=True)

        assert promised["weapons"] == 6
        assert count_imported() == {}

    def test_clearing_leaves_the_foundations_standing(self, author, client, foundation):
        client.post(URL, {**sheets(), "apply": "1"})
        assert Weapon.objects.exists()

        client.post(CLEAR_URL, follow=True)

        assert Weapon.objects.count() == 0
        assert Profile.objects.count() == 0
        for key, seed in STANDARD_CONTENT.items():
            assert seed.status() == "complete", key

    def test_it_says_what_went(self, author, client, foundation):
        client.post(URL, {**sheets(), "apply": "1"})
        body = client.post(CLEAR_URL, follow=True).content.decode()
        assert "Cleared" in body
        assert "weapons" in body

    def test_an_empty_library_offers_nothing_to_delete(
        self, author, client, foundation
    ):
        body = client.get(CLEAR_URL).content.decode()
        assert "Nothing to delete" in body
        assert "Yes, delete" not in body

    def test_content_a_gang_holds_is_refused_in_words(self, author, client, foundation):
        """The content does not go out from under a gang holding it, and
        the page says why rather than showing a database error."""
        from n26.library.models import GangType

        from .actions import found_gang, give_weapon, hire

        client.post(URL, {**sheets(), "apply": "1"})
        gang = found_gang(
            "Clearing",
            GangType.objects.get(name="Escher"),
            owner=author,
            budget=1000,
        )
        model = hire(gang, Profile.objects.get(name="Gang Queen"), "Yolanda")
        give_weapon(model, Weapon.objects.get(name="Autogun"))

        body = client.post(CLEAR_URL, follow=True).content.decode()

        assert "protects it" in body
        assert "Nothing was removed" in body
        assert "assignment" in body  # names what holds it, not a guess
        assert Weapon.objects.exists()


class TestItIsStaffOnly:
    def test_a_signed_out_visitor_cannot_reach_it(self, client, foundation):
        assert client.get(URL).status_code in (302, 404)
