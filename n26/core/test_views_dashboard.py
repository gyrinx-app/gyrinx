"""The home page's header: the marks beside the page's own action.

Patreon and Discord are the only things on this screen that lead a reader off
it, and the footer's copies are a scroll away — so these are about the pair up
in the header: that they are there, that they say what they are, and that they
sit on the correct side of the button at each width.
"""

import json

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core import icons
from n26.core.models import Gang

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
    return User.objects.create_user("player")


@pytest.fixture
def header(client, tester):
    """The page from the greeting to the button, and nothing after it.

    Sliced rather than searched, because the footer links to Discord as
    well: a bare substring search over the page could not tell the
    header's mark from the one three screens down. The slice ends at the
    button's label, so anything it finds also came *before* that button
    in the source — which is the phone's order.
    """
    client.force_login(tester)
    body = client.get(reverse("n26-dashboard")).content.decode()
    return body[body.index("Hello,") : body.index("Create Gang")]


class TestTheMarksBesideTheAction:
    """Two links, drawn as logos, in the row that holds Create Gang."""

    def test_patreon_leads_to_the_project_page(self, header):
        assert 'href="https://www.patreon.com/c/Gyrinx"' in header

    def test_discord_leads_to_the_same_room_the_footer_does(self, header):
        assert 'href="https://discord.gg/WnJFKfyEuj"' in header

    def test_the_marks_open_in_a_new_tab(self, header):
        # Both marks leave the app; rel=noopener rides every target=_blank.
        assert header.count('target="_blank"') >= 2
        assert header.count('rel="noopener"') >= 2

    def test_each_one_says_what_it_is(self, header):
        """A link whose whole content is a drawing has no text to read
        out, so the name is on the link itself."""
        assert 'aria-label="Gyrinx on Patreon"' in header
        assert 'aria-label="Gyrinx on Discord"' in header

    def test_the_marks_are_the_approved_drawings(self, header):
        assert str(icons.resolve("patreon").body) in header
        assert str(icons.resolve("discord").body) in header

    def test_patreon_is_drawn_on_its_own_canvas(self, header):
        """The resolver keeps the mark as published, on a 1080 grid. On
        the 24 one the rest of the set uses, the page would show the
        top-left corner of it magnified past recognition."""
        assert 'viewBox="0 0 1080 1080"' in header

    def test_the_marks_take_the_colour_of_the_text_around_them(self, header):
        """Filled with currentColor and given no colour of their own, so
        they follow the reader's theme rather than sitting in whatever
        the brand's own artwork was painted."""
        assert 'fill="currentColor"' in header
        assert "#FFFFFF" not in header


class TestTheHomeTabQuery:
    """?tab= is the URL for the home strip. An unknown name falls back
    to Gangs so Alpine cannot hide every panel."""

    def test_campaigns_is_the_open_tab_when_the_query_says_so(self, client, tester):
        client.force_login(tester)
        body = client.get(
            reverse("n26-dashboard"), {"tab": "Campaigns"}
        ).content.decode()
        assert "activeTab: 'Campaigns'" in body

    def test_an_unknown_name_opens_gangs(self, client, tester):
        client.force_login(tester)
        body = client.get(reverse("n26-dashboard"), {"tab": "Nope"}).content.decode()
        assert "activeTab: 'Gangs'" in body


class TestTheHomeTabsOnAPhone:
    """Gangs, Campaigns and Content Packs are the home page's main choice,
    so the narrow strip draws all three instead of folding two behind
    "+2 more"."""

    def test_the_narrow_strip_holds_three_tabs(self, client, tester):
        client.force_login(tester)
        body = client.get(reverse("n26-dashboard")).content.decode()
        assert 'x-show="tabs.length <= 3 || isActive(tab.name)"' in body
        assert 'x-show="tabs.length > 3"' in body


ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<circle cx="12" cy="12" r="9" fill="currentColor"/></svg>'
)


def flat(body):
    return body.replace(" ", "").replace("\n", "")


class TestTheGangRows:
    """A home row draws the gang type's artwork beside the wealth strip and
    an actions menu in place of the Edit button. The Gangs page keeps its
    button."""

    @pytest.fixture
    def gang(self, tester, gang_type):
        return Gang.objects.create(
            name="The Ashen Choir", owner=tester, gang_type=gang_type
        )

    def test_a_home_row_has_no_edit_button(self, client, tester, gang):
        client.force_login(tester)
        body = client.get(reverse("n26-dashboard")).content.decode()
        assert "The Ashen Choir" in body
        assert ">Edit<" not in flat(body)

    def test_a_home_row_has_a_menu_of_gang_actions(self, client, tester, gang):
        client.force_login(tester)
        body = client.get(reverse("n26-dashboard")).content.decode()
        # The page draws the menu's button until the island mounts.
        assert body.count('aria-label="Actions for The Ashen Choir"') == 1
        soup = BeautifulSoup(body, "html.parser")
        (host,) = soup.select('[data-react-name="action-menu"]')
        props = json.loads(soup.find(id=host["data-react-props"]).string)
        assert props["label"] == "Actions for The Ashen Choir"
        assert props["align"] == "end"
        assert props["variant"] == "ghost"
        assert [(item["label"], item["href"]) for item in props["items"]] == [
            ("View gang", reverse("n26-gang", args=[gang.pk])),
            ("Edit gang settings", reverse("n26-edit-gang", args=[gang.pk])),
            ("Print", reverse("n26-print-setup", args=[gang.pk])),
        ]
        assert not any(item["separatorBefore"] for item in props["items"])

    def test_the_home_rows_cost_no_query_per_gang(
        self, client, tester, gang, gang_type
    ):
        """Each row draws its menu from the row's own addresses, so the
        page asks the database the same questions however many gangs it
        lists."""
        client.force_login(tester)
        url = reverse("n26-dashboard")
        client.get(url)
        with CaptureQueriesContext(connection) as one:
            client.get(url)

        for name in ("The Bad Girls", "Cold Iron", "Rust Choir"):
            Gang.objects.create(name=name, owner=tester, gang_type=gang_type)
        with CaptureQueriesContext(connection) as four:
            body = client.get(url).content.decode()

        assert body.count('data-react-name="action-menu"') == 4
        assert len(four) == len(one)

    def test_a_home_row_draws_the_gang_type_artwork(
        self, client, tester, gang, store_artwork
    ):
        gang.gang_type.icon_url = store_artwork(ICON, "choir.svg")
        gang.gang_type.save(update_fields=["icon_url"])
        client.force_login(tester)
        body = client.get(reverse("n26-dashboard")).content.decode()
        assert "[--n26-icon-size:2.25rem]" in body
        assert 'r="9"' in body

    def test_the_gangs_page_still_has_the_edit_button(self, client, tester, gang):
        client.force_login(tester)
        body = client.get(reverse("n26-gangs")).content.decode()
        assert ">Edit<" in flat(body)
        assert "Actions for The Ashen Choir" not in body
