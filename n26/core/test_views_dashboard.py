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

    def test_the_marks_are_the_registry_drawings(self, header):
        assert icons.ICONS["patreon"][0] in header
        assert icons.ICONS["discord"][0] in header

    def test_patreon_is_drawn_on_its_own_canvas(self, header):
        """The registry keeps the mark as published, on a 1080 grid. On
        the 24 one the rest of the set uses, the page would show the
        top-left corner of it magnified past recognition."""
        assert 'viewBox="0 0 1080 1080"' in header

    def test_the_marks_take_the_colour_of_the_text_around_them(self, header):
        """Filled with currentColor and given no colour of their own, so
        they follow the reader's theme rather than sitting in whatever
        the brand's own artwork was painted."""
        assert 'fill="currentColor"' in header
        assert "#FFFFFF" not in header

    def test_they_fall_behind_the_button_on_a_phone_and_lead_it_at_width(self, header):
        """One row either way. Source order is the phone's — the marks
        are in this slice, which ends at the button — and `order` moves
        them in front once there is room, so the primary is never the
        second thing a narrow screen offers.
        """
        assert "order-last" in header
        assert "sm:order-first" in header
