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
    """Staff, because the gallery is a workshop rather than a page of
    the app."""
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


class TestTheTickListPage:
    """Its props and its demo reach the gallery drawn, not as a polite
    fallback."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        page = reader.get("/n26/design/c/tick-list/").content.decode()
        assert "offer" in page
        assert "name" in page

    def test_the_demo_draws_real_boxes(self, reader):
        page = reader.get("/n26/design/c/tick-list/").content.decode()
        assert "A list to tick" in page
        # From the markup the demo rendered, not from its title: a demo
        # directory the catalog cannot find yields "No examples yet".
        assert 'name="skills"' in page
        assert 'value="library.skill:1"' in page

    def test_a_granted_line_is_drawn_ticked_and_fixed(self, reader):
        """The one state this component has that a pick list does not, and
        the one worth seeing before writing a page that uses it."""
        page = reader.get("/n26/design/c/tick-list/").content.decode()
        assert 'title="From Keen-eyed"' in page
        assert "disabled" in page


class TestTheOwnedDialogsPage:
    """The two questions the panel grew reach the gallery drawn, not as a
    polite fallback."""

    def test_the_accessory_picker_draws_its_list(self, reader):
        page = reader.get("/n26/design/c/owned-dialog/").content.decode()
        assert "Fitting an accessory" in page
        # From the markup the demo rendered: a select of real options, each
        # naming its price, is what tells this apart from "No examples yet".
        assert "Telescopic sight — 25¢" in page
        assert "Gun stabiliser — 30¢" in page

    def test_selling_a_kitted_gun_draws_a_figure_against_each_answer(self, reader):
        page = reader.get("/n26/design/c/owned-dialog/").content.decode()
        assert "Selling a gun with something bolted to it" in page
        assert 'value="stash"' in page
        assert 'value="sell"' in page
        # The two sales, priced apart — the whole reason there are two cards.
        assert "78¢ for the gun alone" in page
        assert "Everything goes together. 91¢." in page


class TestTheFilterSelectsPage:
    """Its props and its demos reach the gallery, and the select survives."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        page = reader.get("/n26/design/c/filter-select/").content.decode()
        # Read from the component's own <c-vars>, so a prop added there and
        # nowhere else still has to appear here.
        assert "min_options" in page
        assert "empty" in page

    def test_all_three_demos_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/filter-select/").content.decode()
        assert "A list worth searching" in page
        assert "Too short to be worth it" in page
        assert "Several at once" in page

    def test_the_demos_draw_a_real_select_carrying_real_option_values(self, reader):
        """The whole point of the component: what a browser with no script
        finds is the select it would have found anyway, values and all."""
        page = reader.get("/n26/design/c/filter-select/").content.decode()
        assert 'name="weapon"' in page
        assert 'value="7"' in page
        assert "Digi-laser" in page
        # Several at once posts through a native multiple select, not a
        # widget of its own.
        assert 'name="traits"' in page


class TestTheStatlineEditorInTheGallery:
    """The writing half of the statline, on the same page as the reading
    half — which is the point of documenting it there: the two are meant to
    show the same columns, and a reader can see whether they do."""

    def test_the_page_names_the_editing_subcomponent(self, reader):
        page = reader.get("/n26/design/c/statline/").content.decode()
        assert "c-n26.statline.edit" in page

    def test_the_editor_draws_a_box_per_characteristic(self, reader):
        page = reader.get("/n26/design/c/statline/").content.decode()
        # Input names are the stat's internal name, which is what the real
        # form posts — a demo drawing anything else would document a page
        # that does not exist.
        for field in ("movement", "weapon_skill", "leadership", "intelligence"):
            assert f'name="{field}"' in page

    def test_a_value_is_shown_as_it_is_stored(self, reader):
        page = reader.get("/n26/design/c/statline/").content.decode()
        # The quote mark survives the trip through the kit's input. Stored
        # canonical and shown as stored, so the box and the card agree.
        assert 'value="5&quot;"' in page

    def test_an_empty_editor_suggests_what_each_box_takes(self, reader):
        page = reader.get("/n26/design/c/statline/").content.decode()
        assert "Nothing typed yet" in page
        assert 'placeholder="3+"' in page

    def test_a_refusal_is_a_sentence_naming_the_characteristic(self, reader):
        page = reader.get("/n26/design/c/statline/").content.decode()
        assert "Movement is longer than 10 characters" in page
        # What the author typed, not what was stored before it.
        assert 'value="five inches or so"' in page


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
            "price_floor",
            "price_ceiling",
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


class TestTheIconPage:
    """The set draws itself from the registry, so a new drawing lands
    here without the demo being touched — including the ones that do not
    share the 24 grid the rest of the set is stated on."""

    def test_the_patreon_mark_is_drawn_on_the_canvas_it_ships_with(self, reader):
        from n26.core import icons

        page = reader.get("/n26/design/c/icon/").content.decode()
        assert "patreon" in page
        assert icons.ICONS["patreon"][0] in page
        assert 'viewBox="0 0 1080 1080"' in page


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

    def test_the_shop_shell_draws_a_listing_with_a_group_of_options(self, reader):
        """One line in the sample catalogue offers alternatives at
        purchase — a mount and its weapon swaps — so this is where that
        control is documented. The sample carries what the real browse
        produces, so a page that draws it is the proof the two agree."""
        page = reader.get("/n26/design/shell/shop/").content.decode()
        assert "Grav-cutter plasma guns" in page
        assert "+15¢" in page
        assert "Choose one, or none" in page
