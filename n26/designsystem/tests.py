"""The gallery's failures are soft, so something has to look at the page.

A catalog entry whose template path does not resolve, and a demo directory
whose name does not match its slug, both render a polite fallback rather than
raising. Registering a component and never loading its page is therefore
indistinguishable from registering it wrongly — which is what this asks.
"""

import pytest
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db


@pytest.fixture
def reader(client):
    """Staff, because the edition is fenced and the gallery sits behind it."""
    user = get_user_model().objects.create_user(
        "gallery-reader", "gallery-reader@example.com", "password", is_staff=True
    )
    client.force_login(user)
    return client


class TestTheQuickSwitchersPage:
    """Its props, its subcomponent and its demos all reach the gallery."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        page = reader.get("/n26/design/c/quick-switcher/").content.decode()
        # Read from the component's own <c-vars>, so a prop added there and
        # nowhere else still has to appear here.
        assert "menu_label" in page
        assert "min_width" in page

    def test_the_page_names_the_item_subcomponent(self, reader):
        page = reader.get("/n26/design/c/quick-switcher/").content.decode()
        assert "c-n26.quick-switcher.item" in page

    def test_all_three_demos_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/quick-switcher/").content.decode()
        # The titles come from the demo files; the destination comes from the
        # markup they rendered. Both, because a directory the catalog cannot
        # find yields "No examples yet" instead of an error.
        assert "The chevron on its own" in page
        assert "A long list, narrowed" in page
        assert "#the-rust-sermon" in page


class TestTheRadioCardsPage:
    """Its props, its card subcomponent and its demos all reach the gallery."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        page = reader.get("/n26/design/c/radio-cards/").content.decode()
        # Read from the component's own <c-vars>, so a prop added there and
        # nowhere else still has to appear here.
        assert "min" in page
        assert "description" in page

    def test_the_page_names_the_card_subcomponent(self, reader):
        page = reader.get("/n26/design/c/radio-cards/").content.decode()
        assert "c-n26.radio-cards.card" in page

    def test_both_demos_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/radio-cards/").content.decode()
        assert "One of these" in page
        assert "No badges, no detail, and a wider card" in page
        # From the markup the demos rendered, not from their titles: a demo
        # directory the catalog cannot find yields "No examples yet" instead.
        assert 'name="demo-gang-type"' in page
        assert 'name="demo-purpose"' in page


class TestTheGangTypeBadgeInTheGallery:
    """The one badge that is content rather than a drawing we ship."""

    def test_the_flair_page_names_it_and_draws_it(self, reader):
        page = reader.get("/n26/design/c/flair-link/").content.decode()
        assert "c-n26.flair.gang-type" in page
        # The sample artwork, cleaned and inlined by the component.
        assert 'fill="currentColor"' in page

    def test_a_type_with_no_artwork_is_shown_drawing_nothing(self, reader):
        page = reader.get("/n26/design/c/flair-link/").content.decode()
        assert "Underhive Outcasts" in page


class TestProseInsideCVarsIsNotAPropList:
    """A component may write a {% comment %} among its props to explain one of
    them. Tokenised as declarations, that prose became props: a reader of the
    profile picker's page was shown forty-three, among them "and", "from" and
    "endcomment", and the page is meant to be the reference the spec agrees
    with.

    The quieter half is what the noise did to the slots. A name counted as
    declared is a name the slot scan skips, so the word "empty" in a sentence
    took the component's real `empty` slot off its own page.
    """

    def test_only_the_declared_props_are_listed(self):
        from n26.designsystem.introspect import api_for

        api = api_for("n26/profile_picker/index.html")

        assert [prop.name for prop in api.props] == [
            "categories",
            "sections",
            "tabs",
            "cost_floor",
            "cost_ceiling",
            "noun",
            "class",
        ]

    def test_a_slot_named_by_the_prose_is_still_documented(self):
        from n26.designsystem.introspect import api_for

        api = api_for("n26/profile_picker/index.html")

        assert "empty" in api.slots

    def test_there_is_something_to_check(self):
        """Worth nothing if that component stops explaining itself in place,
        which is how this would quietly pass forever."""
        import re

        from n26.designsystem.introspect import _CVARS, api_for

        raw = api_for("n26/profile_picker/index.html").path.read_text()
        assert re.search(r"\{%\s*comment\s*%\}", _CVARS.search(raw).group(1))


class TestTheShellStillDraws:
    """The shell pages are the gallery's claim that the library composes.

    The dashboard's rows carry their type's artwork now, which changed the
    shape of the sample data they loop over — a page that renders is the
    cheapest proof the two agree.
    """

    def test_the_home_shell_lists_its_gangs(self, reader):
        page = reader.get("/n26/design/shell/").content.decode()
        assert "The Ashen Choir" in page
        assert "Goliath (HoC)" in page

    def test_the_new_gang_shell_offers_its_types(self, reader):
        page = reader.get("/n26/design/shell/new-gang/").content.decode()
        assert 'name="gang_type"' in page
        assert "Escher (HoB)" in page
