"""The home page's header: the marks beside the page's own action.

Patreon and Discord are the only things on this screen that lead a reader off
it, and the footer's copies are a scroll away — so these are about the pair up
in the header: that they are there, that they say what they are, and that they
sit on the correct side of the button at each width.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core import icons

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
