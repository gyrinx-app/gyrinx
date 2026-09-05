"""The authoring pages' side of staged content.

Where an author holds a row back and where they release it: the switch
beside a creating form, the badge and button on a row's own page, the
badge in a kind's listing, the Staged content page with its one-row and
whole-library releases, the count on the library index, and the switch on
the import page. The player-facing effect of all this is pinned in
``test_staged_content.py``; here only the pages are.
"""

import re

import pytest
from django.contrib.auth.models import User

from n26.library.authoring import (
    create_category,
    create_gang_type,
    create_weapon,
    stage,
)
from n26.library.models import GangType, Weapon, WeaponProfile

pytestmark = pytest.mark.django_db

STAGED_URL = "/n26/authoring/staged/"
PUT_LIVE_URL = "/n26/authoring/staged/put-live/"


def badges(body):
    """The words the page's badges carry — a badge wraps its word in
    whitespace, so the word is read out of the markup rather than matched
    against it."""
    return re.findall(r"<span[^>]*>\s*(Staged|Live)\s*</span>", body)


@pytest.fixture
def author(client):
    user = User.objects.create_user("author", is_staff=True)
    client.force_login(user)
    return user


def gang_type_form(name, **extra):
    """The create form's payload for a gang type, as a browser posts it."""
    return {"name": name, "foundable": "on", **extra}


class TestTheSwitchBesideACreatingForm:
    def test_a_kind_players_are_offered_carries_the_switch(self, client, author):
        body = client.get("/n26/authoring/gang-type/new/").content.decode()
        assert 'name="staged"' in body
        assert "Who can see it" in body

    def test_a_kind_reached_only_through_others_does_not(self, client, author):
        body = client.get("/n26/authoring/category/new/").content.decode()
        assert 'name="staged"' not in body

    def test_the_switch_starts_on(self, client, author):
        """The kit's switch carries its state in the script that draws it."""
        body = client.get("/n26/authoring/gang-type/new/").content.decode()
        assert "switchInput(false, true)" in body

    def test_created_with_the_switch_on_the_row_is_staged(
        self, client, author, default_pack
    ):
        response = client.post(
            "/n26/authoring/gang-type/new/",
            gang_type_form("Ash Wastes Nomads", staged="on"),
            follow=True,
        )
        made = GangType.objects.get(name="Ash Wastes Nomads")
        assert made.staged is True
        assert "It is staged" in response.content.decode()

    def test_created_with_the_switch_off_the_row_is_live(
        self, client, author, default_pack
    ):
        response = client.post(
            "/n26/authoring/gang-type/new/",
            gang_type_form("Ash Wastes Nomads"),
            follow=True,
        )
        assert GangType.objects.get(name="Ash Wastes Nomads").staged is False
        assert "It is staged" not in response.content.decode()


class TestARowsOwnPage:
    @pytest.fixture
    def nomads(self, default_pack):
        return stage(create_gang_type("Ash Wastes Nomads"))

    def url(self, thing):
        return f"/n26/authoring/gang-type/{thing.pk}/"

    def test_a_staged_row_wears_the_badge_and_offers_to_put_it_live(
        self, client, author, nomads
    ):
        body = client.get(self.url(nomads)).content.decode()
        assert badges(body) == ["Staged"]
        assert 'value="put_live"' in body
        assert "Put live" in body

    def test_putting_it_live(self, client, author, nomads):
        response = client.post(self.url(nomads), {"act": "put_live"}, follow=True)
        assert GangType.objects.get(pk=nomads.pk).staged is False
        body = response.content.decode()
        assert "Ash Wastes Nomads is live." in body
        assert badges(body) == ["Live"]
        assert 'value="stage"' in body

    def test_staging_it_again(self, client, author, nomads):
        client.post(self.url(nomads), {"act": "put_live"})
        response = client.post(self.url(nomads), {"act": "stage"}, follow=True)
        assert GangType.objects.get(pk=nomads.pk).staged is True
        assert "Staged Ash Wastes Nomads." in response.content.decode()

    def test_a_kind_that_cannot_be_staged_offers_neither(
        self, client, author, default_pack
    ):
        combat = create_category("Skills", "Combat")
        body = client.get(f"/n26/authoring/category/{combat.pk}/").content.decode()
        assert 'value="put_live"' not in body
        assert 'value="stage"' not in body


class TestAFiringLinesOwnPages:
    """A firing line is added and corrected on pages of its own, so the
    switch and the buttons are there too."""

    @pytest.fixture
    def lasgun(self, default_pack):
        return create_weapon("Lasgun")

    def test_adding_a_line_offers_the_switch_and_stages_the_line(
        self, client, author, lasgun
    ):
        url = f"/n26/authoring/weapons/{lasgun.pk}/add-profile/"
        assert 'name="staged"' in client.get(url).content.decode()

        response = client.post(
            url, {"name": "Hotshot", "price": "5", "staged": "on"}, follow=True
        )

        line = WeaponProfile.objects.get(weapon=lasgun, name="Hotshot")
        assert line.staged is True
        assert "It is staged" in response.content.decode()

    def test_a_lines_own_page_puts_it_live_and_stages_it_again(
        self, client, author, lasgun
    ):
        from n26.library.authoring import add_weapon_profile

        line = stage(add_weapon_profile(lasgun, name="Hotshot", price=5))
        url = f"/n26/authoring/weapon-profiles/{line.pk}/"
        body = client.get(url).content.decode()
        assert badges(body) == ["Staged"]
        assert 'value="put_live"' in body

        client.post(url, {"act": "put_live"})
        assert WeaponProfile.objects.get(pk=line.pk).staged is False
        client.post(url, {"act": "stage"})
        assert WeaponProfile.objects.get(pk=line.pk).staged is True


class TestTheListing:
    def test_a_staged_row_is_badged_and_found_by_the_word(
        self, client, author, default_pack
    ):
        stage(create_weapon("Plasma caliver"))
        create_weapon("Lasgun")
        body = client.get("/n26/authoring/weapon/").content.decode()
        assert badges(body) == ["Staged"]
        # The in-page search reads the word, so typing it narrows to the
        # staged rows.
        collapsed = " ".join(body.split())
        assert "haystack: 'plasma caliver staged'" in collapsed
        assert collapsed.count("staged'") == 1


class TestTheStagedContentPage:
    @pytest.fixture
    def held(self, default_pack):
        return {
            "nomads": stage(create_gang_type("Ash Wastes Nomads")),
            "caliver": stage(create_weapon("Plasma caliver")),
            "lasgun": create_weapon("Lasgun"),
        }

    def test_it_lists_what_is_staged_by_kind(self, client, author, held):
        body = client.get(STAGED_URL).content.decode()
        assert "Gang types" in body
        assert "Weapons" in body
        assert "Ash Wastes Nomads" in body
        assert "Plasma caliver" in body
        assert "Lasgun" not in body
        assert "2</span>" in body or "2 things staged" in " ".join(body.split())
        assert "Put everything live" in body

    def test_each_row_leads_to_its_own_page(self, client, author, held):
        body = client.get(STAGED_URL).content.decode()
        assert f"/n26/authoring/gang-type/{held['nomads'].pk}/" in body

    def test_one_row_can_be_put_live_from_here(self, client, author, held):
        response = client.post(
            STAGED_URL,
            {"act": "put_live", "model": "weapon", "pk": str(held["caliver"].pk)},
            follow=True,
        )
        assert Weapon.objects.get(pk=held["caliver"].pk).staged is False
        assert GangType.objects.get(pk=held["nomads"].pk).staged is True
        body = response.content.decode()
        assert "Plasma caliver is live." in body
        assert "Plasma caliver" not in body.split("is live.", 1)[1]

    def test_a_kind_that_is_not_content_is_refused(self, client, author, held):
        assert (
            client.post(
                STAGED_URL, {"act": "put_live", "model": "contentpack", "pk": "x"}
            ).status_code
            == 404
        )
        assert (
            client.post(
                STAGED_URL, {"act": "put_live", "model": "nonsense", "pk": "x"}
            ).status_code
            == 404
        )

    def test_a_pk_that_names_nothing_staged_is_refused(self, client, author, held):
        """A bad link and a live row read the same: this page lists staged
        rows and nothing else, so neither is a row it can put live."""
        for pk in ("x", str(held["lasgun"].pk)):
            response = client.post(
                STAGED_URL, {"act": "put_live", "model": "weapon", "pk": pk}
            )
            assert response.status_code == 404, pk

    def test_with_nothing_staged_it_says_so(self, client, author, default_pack):
        create_weapon("Lasgun")
        body = client.get(STAGED_URL).content.decode()
        assert "Nothing is staged." in body
        assert "Put everything live" not in body

    def test_it_is_for_staff(self, client, db):
        client.force_login(User.objects.create_user("player"))
        assert client.get(STAGED_URL).status_code == 302
        assert client.get(PUT_LIVE_URL).status_code == 302


class TestPuttingEverythingLive:
    @pytest.fixture
    def held(self, default_pack):
        return {
            "nomads": stage(create_gang_type("Ash Wastes Nomads")),
            "caliver": stage(create_weapon("Plasma caliver")),
            "spear": stage(create_weapon("Spear")),
        }

    def test_the_question_says_how_many_of_what(self, client, author, held):
        body = " ".join(client.get(PUT_LIVE_URL).content.decode().split())
        assert "Gang types" in body
        assert "Weapons" in body
        assert "3 things in all" in body

    def test_the_act_releases_all_of_it(self, client, author, held):
        response = client.post(PUT_LIVE_URL, follow=True)
        assert not GangType.objects.filter(staged=True).exists()
        assert not Weapon.objects.filter(staged=True).exists()
        body = response.content.decode()
        assert "Put 3 things live." in body
        assert "Nothing is staged." in body

    def test_with_nothing_staged_the_question_says_so(
        self, client, author, default_pack
    ):
        body = client.get(PUT_LIVE_URL).content.decode()
        assert "nothing to put live" in body


class TestTheIndex:
    def test_it_counts_what_is_staged(self, client, author, default_pack):
        stage(create_weapon("Plasma caliver"))
        stage(create_weapon("Spear"))
        body = " ".join(client.get("/n26/authoring/").content.decode().split())
        assert "2 things written but not yet put live" in body
        assert STAGED_URL in body

    def test_with_nothing_staged_it_says_so(self, client, author, default_pack):
        body = " ".join(client.get("/n26/authoring/").content.decode().split())
        assert "nothing is waiting to be put live" in body


class TestTheImportPage:
    def test_the_preview_offers_to_stage_what_it_creates_and_does(
        self, client, author, default_pack
    ):
        from n26.library.models import Profile
        from n26.library.standard_content import STANDARD_CONTENT
        from n26.tests.sandbox.test_ingest_page import (
            PREVIEW_URL,
            SHEETS,
            sheet_url,
            upload,
        )

        for item in STANDARD_CONTENT.values():
            item.create()
        for sheet, (text, name) in SHEETS.items():
            client.post(sheet_url(sheet), {"file": upload(text, name)})

        body = client.get(PREVIEW_URL).content.decode()
        assert 'name="staged"' in body
        assert "Stage what this import creates" in body

        response = client.post(PREVIEW_URL, {"staged": "on"}, follow=True)

        assert Profile.objects.exists()
        assert not Profile.objects.filter(staged=False).exists()
        assert "The new rows are staged" in response.content.decode()

    def test_with_the_switch_off_the_import_makes_live_rows(
        self, client, author, default_pack
    ):
        from n26.library.models import Profile
        from n26.library.standard_content import STANDARD_CONTENT
        from n26.tests.sandbox.test_ingest_page import (
            PREVIEW_URL,
            SHEETS,
            sheet_url,
            upload,
        )

        for item in STANDARD_CONTENT.values():
            item.create()
        for sheet, (text, name) in SHEETS.items():
            client.post(sheet_url(sheet), {"file": upload(text, name)})

        client.post(PREVIEW_URL, {})

        assert Profile.objects.exists()
        assert not Profile.objects.filter(staged=True).exists()
