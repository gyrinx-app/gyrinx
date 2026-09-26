"""The gallery's failures are soft, so something has to look at the page.

A catalog entry whose template path does not resolve, and a demo directory
whose name does not match its slug, both render a polite fallback rather than
raising. Registering a component and never loading its page is therefore
indistinguishable from registering it wrongly — which is what this asks.
"""

import re
from html import unescape

import pytest
from django.contrib.auth import get_user_model

from n26.core import icons

pytestmark = pytest.mark.django_db

#: The colour <c-n26.founding-mark> paints itself. One component draws the
#: mark, so finding this on a page is finding the mark.
MARK = "text-violet-600"


@pytest.fixture
def reader(client):
    """Staff, because the gallery is a workshop rather than a page of
    the app."""
    user = get_user_model().objects.create_user(
        "gallery-reader", "gallery-reader@example.com", "password", is_staff=True
    )
    client.force_login(user)
    return client


class TestReactDemo:
    """Staff can compare React and Cotton without seeded library content."""

    def test_sample_comparison_and_source_render_without_library_content(self, reader):
        import json

        from bs4 import BeautifulSoup

        response = reader.get("/n26/design/react/")
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert len(soup.select("table tr")) == 3
        host = soup.select_one("[data-react-module]")
        props = json.loads(soup.find(id=host["data-react-props"]).string)
        assert len(props["rows"]) == 3
        assert props["bulkActionUrl"] is None
        assert 'react_island "authoring-list" demo' in soup.get_text()
        assert "mountRoot" in soup.get_text()

    def test_gallery_requires_staff(self, client):
        assert client.get("/n26/design/react/").status_code == 302


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


class TestTheSharePage:
    """Its props and both demos reach the gallery drawn."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        page = reader.get("/n26/design/c/share/").content.decode()
        assert "message" in page
        assert "url" in page

    def test_the_demos_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/share/").content.decode()
        assert "clicked($event)" in page
        assert "This gang is unlisted" in page


class TestThePictureBoxPage:
    """Its props and both of its states reach the gallery drawn."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        page = reader.get("/n26/design/c/picture-box/").content.decode()
        # Read from the component's own <c-vars>, so a prop added there and
        # nowhere else still has to appear here.
        assert "image_url" in page
        assert "img_class" in page

    def test_both_demos_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/picture-box/").content.decode()
        assert "No picture yet" in page
        assert "A picture stored" in page
        # From the markup the demos rendered, not their titles: the stored
        # state must actually draw its input and its Remove.
        assert 'id="demo-picture-stored"' in page
        assert "Remove picture" in page


class TestTheActivityCardPage:
    """Its props, its body subcomponent and its demos reach the gallery."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        from n26.designsystem.catalog import get

        assert get("activity-card").api is not None
        page = reader.get("/n26/design/c/activity-card/").content.decode()
        # Read from the component's own <c-vars>, so a prop added there and
        # nowhere else still has to appear here.
        assert "boxed" in page
        assert "body" in page

    def test_the_page_names_the_body_subcomponent(self, reader):
        from n26.designsystem.catalog import get

        assert all(api is not None for _, api in get("activity-card").part_apis)
        page = reader.get("/n26/design/c/activity-card/").content.decode()
        assert "c-n26.activity-card.body" in page

    def test_all_three_demos_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/activity-card/").content.decode()
        # The titles come from the demo files; the rest is markup the demos
        # rendered, because a directory the catalog cannot find yields
        # "No examples yet" instead of an error.
        assert "An action with figures" in page
        assert "An action with none" in page
        assert "Inside another box" in page
        assert "Visit Trading Post" in page
        assert "Complete action" in page

    def test_an_action_with_no_figures_draws_no_tally(self, reader):
        """A row of zeroes is worse than nothing: the founding counts
        nothing yet, so it says nothing."""
        page = reader.get("/n26/design/c/activity-card/").content.decode()
        start = page.index("An action with none")
        assert "Remaining" not in page[start:]


class TestTheActivitiesSquarePage:
    """Its props and permission-dependent states reach the gallery drawn."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        page = reader.get("/n26/design/c/activities-square/").content.decode()
        assert "square" in page

    def test_the_open_action_is_badged(self, reader):
        page = reader.get("/n26/design/c/activities-square/").content.decode()
        assert "Current action" in page

    def test_the_open_and_empty_states_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/activities-square/").content.decode()
        assert "Nothing open" in page
        assert "The founding open" in page
        assert "A visit open" in page
        assert "Both open" in page
        assert "Nothing done yet" in page
        # From the markup the demos rendered, not their titles.
        assert "No action is open." in page
        assert "Trading Post visit open" in page
        assert "Complete action" in page

    def test_post_battle_uses_the_shared_steps_with_and_without_other_actions(
        self, reader
    ):
        from bs4 import BeautifulSoup

        from n26.core.activities import POST_BATTLE_HELP

        page = BeautifulSoup(
            reader.get("/n26/design/c/activities-square/").content, "html.parser"
        )
        squares = [
            square
            for square in page.select('[role="region"][aria-label="Actions"]')
            if square.find("a", href="#post-battle")
        ]
        assert len(squares) == 3
        combined, standalone, no_history = squares
        for square in squares:
            assert POST_BATTLE_HELP in square.get_text()
            history = [
                link
                for link in square.find_all("a")
                if link.get_text(strip=True) == "History"
            ]
            assert len(history) == 1
            assert "Recent history" not in square.get_text()
        assert "Current action" in combined.get_text()
        assert "Pay ransom" in combined.get_text()
        assert "Clean House" in combined.get_text()
        for square in (standalone, no_history):
            assert "Current action" not in square.get_text()
            assert square.find("form") is None
        assert "No history for this gang yet." not in no_history.get_text()

    def test_history_is_a_link_and_acts_are_not_listed(self, reader):
        """The header link, not a list of acts. A demo that fell back to
        "No examples yet" would not draw the Actions region at all."""
        page = reader.get("/n26/design/c/activities-square/").content.decode()
        assert "Recent history" not in page
        assert "History" in page
        assert "hired Yolanda, a Ganger" not in page

    def test_a_gang_with_no_story_still_links(self, reader):
        page = reader.get("/n26/design/c/activities-square/").content.decode()
        assert "No history for this gang yet." not in page
        assert "History" in page

    def test_the_start_row_is_a_post_not_a_link(self, reader):
        """Starting an act must never be a link: a link is followed by
        anything that follows links."""
        page = reader.get("/n26/design/c/activities-square/").content.decode()
        start = page.index("Equip the gang using founding Trade Points")
        form = page.rindex("<form", 0, start)
        assert 'method="post"' in page[form:start]


class TestTheFoundingMarkPage:
    """The one place the founding mark's drawing and colour are stated, and
    the four places it is drawn."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        page = reader.get("/n26/design/c/founding-mark/").content.decode()
        assert "label" in page

    def test_the_demos_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/founding-mark/").content.decode()
        assert "The mark" in page
        assert "Sizes" in page
        assert "Where it is drawn" in page
        assert "Both blocks on an equip rail" in page
        # From the markup the demos rendered, not their titles.
        assert MARK in page
        assert "Founding Trade Points" in page
        assert "Trading Post visit" in page

    def test_the_rail_demo_draws_the_real_blocks(self, reader):
        """It includes the page's own partials, so a change to either
        block shows here rather than drifting from a copy."""
        page = reader.get("/n26/design/c/founding-mark/").content.decode()
        assert "Available" in page
        assert "Remaining" in page
        assert "not against the visit" in page
        assert "Manage visit" in page


class TestTheStashPage:
    """The stash's notice slot, filled the way the gang sheet fills it."""

    def test_the_visit_demos_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/stash/").content.decode()
        assert "The Trading Post line in the notice" in page
        assert "A visit that cannot start yet" in page
        assert "Trading Post visit open" in page
        assert "Set up Trading Post visit" in page

    def test_a_visit_that_cannot_start_is_drawn_dead_with_the_reason(self, reader):
        page = reader.get("/n26/design/c/stash/").content.decode()
        label = page.index("Set up Trading Post visit")
        control = page[page.rindex("<", 0, page.rindex("<", 0, label)) : label]
        assert "disabled" in control
        assert "You can have only one of these actions open at a time." in page

    def test_the_old_wording_is_gone(self, reader):
        page = reader.get("/n26/design/c/stash/").content.decode()
        assert "Set up TP visit" not in page

    def test_two_of_one_thing_read_once_with_the_rating_of_one(self, reader):
        page = reader.get("/n26/design/c/stash/").content.decode()
        assert (
            'Mesh armour (x2)</span><span>&nbsp;<span class="tabular-nums">15¢' in page
        )
        assert "Mesh armour, Mesh armour" not in page
        # A weapon is never stacked, so the gallery holds no such specimen.
        assert "Stub gun (x2)" not in page


class TestTheCountOnAModelCardLine:
    def test_the_gallery_card_draws_two_of_one_thing_once(self, reader):
        page = reader.get("/n26/design/c/model-card/").content.decode()
        assert "Stimm-slug (25¢) (x2)" in page

    def test_the_editable_sample_keeps_one_line_per_assignment(self, reader):
        """The model's own page hangs a menu on every line, and a menu
        names one assignment, so the stacked specimen opens back out
        into two lines there — each with its own menu."""
        from n26.designsystem import sampledata

        lines = [
            line
            for line in sampledata.model_card_editable().equipment
            if line.name == "Stimm-slug (25¢)"
        ]
        assert [(line.count, bool(line.sell)) for line in lines] == [
            (1, True),
            (1, True),
        ]

        page = reader.get("/n26/design/c/model-card/").content.decode()
        assert page.count('aria-label="More for Stimm-slug (25¢)"') == 2


class TestThePetOnAModelCard:
    """A pet's card names its owner, linked where the demo gives the
    anchor; the owner's kit line names the pet after the kit."""

    def test_the_pet_demo_links_the_owners_card(self, reader):
        page = reader.get("/n26/design/c/model-card/").content.decode()
        # A cat among the controls, named for whoever uses a reader.
        assert 'aria-label="Owned by Vesna Krail"' in page
        assert 'href="#model-vesna-krail"' in page
        assert page.count('id="model-vesna-krail"') == 1
        assert str(icons.resolve("cat").body) in page

    @pytest.mark.parametrize(
        "url, at_least",
        [
            ("/n26/design/c/model-card/", 8),
            ("/n26/design/c/view-gang-sheet/", 5),
            ("/n26/design/shell/gang/", 5),
        ],
    )
    def test_every_card_on_the_page_has_an_anchor_of_its_own(
        self, reader, url, at_least
    ):
        """The sample card is drawn many times over — the card page's
        variants, the gang sheet's five members — and each drawing is a
        copy under its own id, so the owner link lands on one card and
        no page holds an id twice."""
        import re

        page = reader.get(url).content.decode()
        anchors = re.findall(r'id="(model-[^"]+)"', page)
        assert len(anchors) >= at_least
        assert sorted(anchors) == sorted(set(anchors))

    def test_the_stashed_pet_demo_says_where_the_collar_is(self, reader):
        page = reader.get("/n26/design/c/model-card/").content.decode()
        assert "In the stash" in page

    def test_the_owners_kit_line_names_the_pet(self, reader):
        page = reader.get("/n26/design/c/model-card/").content.decode()
        assert "Phyrr Cat (pet) (120¢) (Fang)" in page

    def test_the_stash_line_names_the_pet(self, reader):
        page = reader.get("/n26/design/c/stash/").content.decode()
        assert "Cyber-mastiff (pet) (Rust)" in page


class TestTheHeaderBandSpecimens:
    """The four cards that hold the header's whole contents at once, so
    the band can be looked at while the names either side of it grow."""

    def test_the_band_holds_everything_at_once(self, reader):
        from n26.designsystem import sampledata

        card = sampledata.model_card_header_short()
        assert card.trade_points_left is not None and card.founding_budget
        assert card.rating and card.profile_name and card.owned_by
        assert card.image_url
        # No id: the specimen draws its body plain rather than behind the
        # tab strip, and carries no anchor to collide with the pet demo's.
        assert card.id == ""

        page = reader.get("/n26/design/c/model-card/").content.decode()
        assert "3 TP" in page
        assert "390¢" in page
        assert "Escher Death-Maiden" in page
        assert 'aria-label="Owned by Vesna Krail"' in page

    def test_the_live_specimens_draw_the_quiet_active_control(self, reader):
        """A card carrying no status of its own gets Active as a muted
        control rather than a badge — what most of a roster reads, and
        the width the controls row usually has. Four of the five, the
        fifth being the badged one."""
        import re

        page = reader.get("/n26/design/c/model-card/").content.decode()
        band = page.split('id="demo-header"', 1)[1].split('id="demo-digital"')[0]
        assert len(re.findall(r">\s*Active\s*<", band)) == 4

    def test_status_and_rating_share_one_unbroken_figures_line(self, reader):
        from bs4 import BeautifulSoup

        page = reader.get("/n26/design/c/model-card/").content.decode()
        band = page.split('id="demo-header"', 1)[1].split('id="demo-digital"')[0]
        document = BeautifulSoup(band, "html.parser")
        active = document.find(string=lambda value: value and value.strip() == "Active")
        assert active is not None
        figures = active.find_parent("div", class_="tabular-nums")

        assert figures is not None
        assert "whitespace-nowrap" in figures["class"]
        assert "390¢" in figures.get_text(" ", strip=True)

    def test_one_specimen_badges_the_longest_status(self, reader):
        from n26.designsystem import sampledata

        card = sampledata.model_card_header_badged()
        assert card.status_label == "Critically Injured"

        page = reader.get("/n26/design/c/model-card/").content.decode()
        band = page.split('id="demo-header"', 1)[1].split('id="demo-digital"')[0]
        assert "Critically Injured" in band

    def test_both_names_are_drawn_short_and_long(self, reader):
        from n26.designsystem import sampledata

        page = reader.get("/n26/design/c/model-card/").content.decode()
        for name in (
            sampledata.SHORT_HEADER_NAME,
            sampledata.LONG_HEADER_NAME,
            sampledata.SHORT_HEADER_OWNER,
            sampledata.LONG_HEADER_OWNER,
        ):
            assert name in page

    def test_the_specimens_carry_nothing_below_the_statline(self):
        """What makes them readable: a specimen carrying the sample
        card's weapons and gear would bury the band being looked at."""
        from n26.designsystem import sampledata

        for build in (
            sampledata.model_card_header_short,
            sampledata.model_card_header_long_name,
            sampledata.model_card_header_long_owner,
            sampledata.model_card_header_long_both,
        ):
            card = build()
            assert card.statline.cells
            assert not card.weapons
            assert not card.equipment
            assert not card.skills


class TestTheRadioCardsPage:
    """Its props, its card subcomponent and its demos all reach the gallery."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        page = reader.get("/n26/design/c/radio-cards/").content.decode()
        # Read from the component's own <c-vars>, so a prop added there and
        # nowhere else still has to appear here.
        assert "min" in page
        assert "description" in page
        assert "labelled_by" in page

    def test_the_page_names_the_card_subcomponent(self, reader):
        page = reader.get("/n26/design/c/radio-cards/").content.decode()
        assert "c-n26.radio-cards.card" in page

    def test_both_demos_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/radio-cards/").content.decode()
        assert "One of these" in page
        assert "No badges, no detail, and a wider card" in page
        assert "A sentence-long name wraps" in page
        assert "Lines of detail under the description" in page
        # From the markup the demos rendered, not from their titles: a demo
        # directory the catalog cannot find yields "No examples yet" instead.
        assert 'name="demo-gang-type"' in page
        assert 'name="demo-purpose"' in page
        assert 'name="demo-campaign-type"' in page
        assert 'name="demo-scope"' in page


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


class TestTheChoicePicksPage:
    """Its props and both its demos reach the gallery drawn, not as a
    polite fallback."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        page = reader.get("/n26/design/c/choice-picks/").content.decode()
        assert "offer" in page
        assert "name" in page
        assert "labelled_by" in page

    def test_both_demos_draw_real_acts(self, reader):
        page = reader.get("/n26/design/c/choice-picks/").content.decode()
        assert "A choice part-way made" in page
        assert "With no room left" in page
        # From the markup the demos rendered, not from their titles: a
        # demo directory the catalog cannot find yields "No examples yet".
        assert 'name="remove"' in page
        assert 'value="library.pickable:3"' in page

    def test_an_option_names_itself_to_a_reader_who_hears_the_button(self, reader):
        """Twenty-six buttons all called Choose are twenty-six unlabelled
        buttons, so each act says what it acts on."""
        page = reader.get("/n26/design/c/choice-picks/").content.decode()
        assert 'aria-label="Remove Cawdor"' in page
        assert 'aria-label="Add Ironhead Squats"' in page


class TestTheRollPages:
    """The roll controls and the roll panel reach the gallery drawn, in
    every state the demos claim, not as a polite fallback."""

    def test_the_controls_page_draws_both_ways_to_record_a_roll(self, reader):
        page = reader.get("/n26/design/c/roll-table/").content.decode()
        assert "table" in page
        assert 'value="roll"' in page
        assert 'name="rolled"' in page

    def test_the_panel_page_draws_its_three_states(self, reader):
        page = reader.get("/n26/design/c/roll-result/").content.decode()
        assert "Landed on a result" in page
        assert "Already applied" in page
        assert 'aria-label="A die showing 2"' in page
        assert 'aria-label="Add Out Cold"' in page
        assert "High enough for" in page


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

    def test_detaching_an_accessory_draws_the_held_destination(self, reader):
        page = reader.get("/n26/design/c/owned-dialog/").content.decode()
        assert "Taking an accessory off a gun" in page
        assert "Take Telescopic sight off Meltagun?" in page
        assert "The fighter will still hold it." in page
        assert 'value="held"' in page

    def test_selling_a_kitted_gun_draws_a_figure_against_each_answer(self, reader):
        page = reader.get("/n26/design/c/owned-dialog/").content.decode()
        assert "Selling a gun with something bolted to it" in page
        assert 'value="stash"' in page
        assert 'value="sell"' in page
        # The two sales, priced apart — the whole reason there are two cards.
        assert "78¢ for the gun alone" in page
        assert "Everything goes together. 91¢." in page


class TestTheSelectPage:
    """Its demos reach the gallery drawn, not as a polite fallback."""

    def test_the_multiple_demo_draws_a_list_not_a_dropdown(self, reader):
        page = reader.get("/n26/design/c/select/").content.decode()
        assert "The chosen row is marked" in page
        assert 'name="demo-profile-types"' in page
        assert "n26-select-multiple" in page
        assert "Fighter" in page
        assert "Vehicle" in page


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
    """The installed library is searchable without rendering it all at once."""

    def test_the_patreon_mark_is_drawn_on_the_canvas_it_ships_with(self, reader):
        from n26.core import icons

        page = reader.get("/n26/design/c/icon/?q=patreon").content.decode()
        assert "patreon" in page
        assert str(icons.resolve("patreon").body) in page
        assert 'viewBox="0 0 1080 1080"' in page

    def test_a_search_returns_a_lucide_icon_by_its_canonical_name(self, reader):
        from n26.core import icons

        page = reader.get("/n26/design/c/icon/?q=zoom-out").content.decode()
        assert "zoom-out" in page
        assert str(icons.resolve("zoom-out").body) in page
        assert "1 of" in page

    def test_a_later_page_of_the_library_is_available(self, reader):
        from n26.core import icons
        from n26.designsystem.views import ICON_PAGE_SIZE

        expected = icons.names()[ICON_PAGE_SIZE]
        page = reader.get("/n26/design/c/icon/?page=2").content.decode()
        assert expected in page
        assert "page=1" in page

    def test_an_empty_search_explains_itself(self, reader):
        page = reader.get(
            "/n26/design/c/icon/?q=definitely-not-an-icon"
        ).content.decode()
        assert "No icons match" in page
        assert "Clear search" in page


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

    def test_the_gang_shell_draws_the_activities_square(self, reader):
        """Whether the square reads as one of the grid's squares depends on
        the stash and the cards beside it, which only the shell has."""
        page = reader.get("/n26/design/shell/gang/").content.decode()
        assert "Found and equip gang" in page
        assert "Complete action" in page
        # The stash card's own heading, not the wealth strip's figure of
        # the same name, which sits further up the page.
        assert page.index("Found and equip gang") < page.index(">Stash</span>")

    def test_a_range_menu_with_two_thumbs_binds_both(self, reader):
        """The gallery's two-thumb range menu draws two real range inputs,
        each bound to the caller's variable — the slider is called once for
        each form rather than with a conditional inside one call."""
        page = reader.get("/n26/design/c/range-menu/").content.decode()
        assert 'aria-label="Minimum"' in page and 'aria-label="Maximum"' in page
        assert ':value="lowCost"' in page and ':value="highCost"' in page
        assert "{% if" not in page

    def test_the_campaign_shell_draws_the_tables(self, reader):
        """The gangs table and an assets table both fill from the sample
        sheet, and every slot the view declares is drawn from the page
        rather than from a context variable of the same name."""
        page = reader.get("/n26/design/shell/campaign/").content.decode()
        assert "Territory campaign" in page
        assert "Gravebolt Kin" in page
        # Each gang names its owner under its name, through the same
        # component the app draws people with — a sample person is a
        # username, so the name comes through and no badge follows it.
        assert re.search(r"Goliath \(HoC\) · <span[^>]*>marta<", page)
        assert re.search(r"Escher \(HoB\) · <span[^>]*>tom<", page)
        # The players and the log name people the same way; the
        # arbitrator's own acts read "You", as the page reads them.
        assert re.search(r"<td[^>]*>\s*<span[^>]*>vey<", page)
        assert re.search(r"<span[^>]*font-medium[^>]*>ossian<", page)
        assert ">You</span>" in page
        assert "Old Ruins by the sump" in page
        assert "Reputation" in page
        assert "Unclaimed" in page
        assert "Record battle" in page
        assert "Old Ruins went to The Ashen Choir" in page

    def test_the_new_gang_shell_offers_its_types(self, reader):
        page = reader.get("/n26/design/shell/new-gang/").content.decode()
        assert 'name="gang_type"' in page
        assert "Escher (HoB)" in page

    def test_the_sample_banner_draws_a_button_that_answers(self, reader):
        """A bar with a call to action is the thing this page is here to
        show, and the button has to survive being followed.

        The shell sends it by way of the click tracker, whose address
        accepts none but a real id — so a sample id that is merely a word
        is an address that cannot be built, and takes every shell page
        down with it. Nothing is stored under the sample's id, so
        following it finds nothing, which it must be able to say.
        """
        page = reader.get("/n26/design/shell/").content.decode()
        start = page.index("n26-announcement")
        bar = page[start : page.index("</aside>", start)]

        assert "n26-announcement-cta" in bar
        href = bar.split('href="')[1].split('"')[0]

        assert reader.get(href).status_code == 404

    def test_the_equip_shell_draws_a_listing_with_a_group_of_options(self, reader):
        """One line in the sample catalogue offers alternatives at
        purchase — a mount and its weapon swaps — so this is where that
        control is documented. The sample carries what the real browse
        produces, so a page that draws it is the proof the two agree."""
        page = reader.get("/n26/design/shell/shop/").content.decode()
        assert "Grav-cutter plasma guns" in page
        assert "+15¢" in page
        assert "Choose one, or none" in page


class TestTheModelHeaderPage:
    """Its card slot reaches the gallery drawn, above the tab strip."""

    def test_both_demos_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/model-header/").content.decode()
        assert "One model's screens" in page or "One model&#x27;s screens" in page
        assert "With the model" in page
        assert 'id="n26-model-card-host"' in page

    def test_the_card_sits_between_the_heading_and_the_tabs(self, reader):
        # The component page, since the second demo is the one with the
        # card, and the plain preview draws a component's first alone.
        page = reader.get("/n26/design/c/model-header/").content.decode()
        demo = page.index("With the model")
        card = page.index('id="n26-model-card-host"', demo)
        assert page.index("Vesna Krail", demo) < card < page.index("This model", card)


class TestTheModelEditPage:
    """The card above the tabs, then the boxes in their order, Lore last."""

    def test_the_card_sits_above_the_tabs(self, reader):
        page = reader.get("/n26/design/view/view-model-edit/").content.decode()
        card = page.index('id="n26-model-card-host"')
        assert page.index("<h1") < card < page.index("This model")

    def test_the_demos_name_action_reaches_the_card(self, reader):
        """The demo passes a rename link of its own — there is no model
        to rename — and the host include draws it in place of the real
        pencil. A slot that went unforwarded would draw the pencil
        pointing at an Edit page for a model that does not exist."""
        page = reader.get("/n26/design/view/view-model-edit/").content.decode()
        card = page[page.index('id="n26-model-card-host"') : page.index("This model")]
        assert 'href="#rename"' in card
        assert "?rename=" not in card

    def test_the_boxes_run_picture_notes_skills_characteristics_lore(self, reader):
        page = reader.get("/n26/design/view/view-model-edit/").content.decode()

        def heading(name):
            return page.index(f'<span class="font-semibold">{name}</span>')

        assert (
            heading("Picture")
            < heading("Notes")
            < heading("Skills &amp; Powers")
            < heading("Characteristics")
            < heading("Lore")
        )

    def test_action_panels_share_the_card_row_above_the_tabs(self, reader):
        page = reader.get("/n26/design/view/view-model-edit/").content.decode()
        card = page.index('id="n26-model-card-host"')
        actions = page.index('id="n26-action-panels"', card)
        evolution = page.index("Suit Evolution", card)
        advancement = page.index("Advancement", evolution)
        notes = page.index('<span class="font-semibold">Notes</span>', advancement)
        tabs = page.index("This model", advancement)
        history = page.index('<span class="font-semibold">Action history</span>', notes)

        assert card < actions < evolution < advancement < tabs < notes < history
        assert "lg:grid-cols-2" in page[card - 500 : actions]
        assert "Kill Count" in page[evolution:advancement]
        assert "After payment" not in page[evolution:advancement]
        assert '<span class="font-semibold">Actions</span>' not in page[actions:tabs]
        assert (
            'aria-label="Start Suit Evolution flow"' not in page[evolution:advancement]
        )
        assert "Resume Suit Evolution flow" in page[evolution:advancement]
        assert "1 use available" in page[advancement:notes]
        assert 'aria-label="Start Advancement flow"' in page[advancement:notes]
        assert "Resume Advancement flow" not in page[advancement:notes]
        assert "Hunting Rig Augmentation" not in page[actions:tabs]
        assert "Hunting Rig Augmentation" in page[history:]
        assert "Hunting rig: Tier 1. Improve S by 1" in page[history:]
        assert "minutes ago" in page[history:]


class TestCounterLinesInTheGallery:
    """Only one sample card offers to move a number.

    The base sample is what the gang sheet's sample, the hire previews
    and the print specimens are all built from, so an address on its
    counters would put a pair of buttons on every one of them — screens
    that never carry the control in the app. It would also give XP a
    line beside the statline cell that already holds it, which is the
    doubled reading the card exists to avoid.
    """

    def test_the_base_sample_offers_nothing_to_click(self):
        from n26.designsystem import sampledata

        assert all(not line.href for line in sampledata.model_card().counter_lines)

    def test_the_base_sample_keeps_xp_to_its_cell(self):
        from n26.designsystem import sampledata

        assert not [
            line for line in sampledata.model_card().counter_lines if line.is_xp
        ]

    def test_the_gang_sheets_members_offer_nothing_either(self):
        from n26.designsystem import sampledata

        member = sampledata.gang_sheet().models[0]
        assert all(not line.href for line in member.counter_lines)

    def test_the_editable_sample_carries_every_line_and_its_address(self):
        from n26.designsystem import sampledata

        lines = sampledata.model_card_editable().counter_lines
        assert [line.name for line in lines] == [
            "XP",
            "Kill Count",
            "Glitch Count",
            "Bounty",
        ]
        assert all(line.href for line in lines)

    def test_the_editable_sample_offers_the_listing_acts_on_its_kit(self):
        """The model's own page is where kit is taken off, so the
        sample that documents that page carries Sell and Add accessory.
        The base sample is the gang sheet's card and must not."""
        from n26.designsystem import sampledata

        base = sampledata.model_card()
        assert all(not line.sell for line in base.equipment)
        assert all(not weapon.sell for weapon in base.weapons)

        card = sampledata.model_card_editable()
        assert all(line.sell for line in card.equipment)
        assert all(weapon.sell and weapon.accessorise for weapon in card.weapons)


class TestTheModelCardsTooltips:
    """The card's tooltips are real components, never a native title —
    which shows only under a mouse and never on touch."""

    def test_the_page_draws_the_card_at_all(self, reader):
        # Guards the assertions below against passing vacuously: a card
        # rendered without its context draws none of the markup the
        # other tests refuse.
        page = reader.get("/n26/design/c/model-card/").content.decode()
        assert "Vesna Krail" in page

    def test_no_native_title_survives_on_the_card(self, reader):
        page = reader.get("/n26/design/c/model-card/").content.decode()
        assert 'title="Rating' not in page
        assert 'title="Select' not in page
        assert 'title="From' not in page
        assert 'title="Granted' not in page
        assert 'title="Trade Points' not in page

    def test_the_provenance_and_rating_bubbles_are_drawn(self, reader):
        page = reader.get("/n26/design/c/model-card/").content.decode()
        assert 'role="tooltip"' in page
        assert "From Leader" in page
        assert "Rating, including weapons and wargear" in page
        assert (
            "can spend these founding Trade Points at the Trading Post while the "
            "Found and equip gang action is open" in page
        )

    def test_both_kinds_of_open_choice_draw_their_way_in(self, reader):
        """The sample carries an open one-pick choice and a several-pick
        choice with room left. A line built without a slot behind it
        defaults to the one-pick rule, so the open one must still prompt
        — a sample that quietly drew nothing would document the wrong
        thing."""
        page = reader.get("/n26/design/c/model-card/").content.decode()
        legacy = page[page.index("Gang Legacy</dt>") :]
        legacy_dd = legacy[: legacy.index("</dd>")]
        assert "Choose" in legacy_dd
        injuries = page[page.index("Lasting Injuries</dt>") :]
        injuries_dd = injuries[: injuries.index("</dd>")]
        assert "Add" in injuries_dd


class TestThePrintSheet:
    """Paper shows what a slot holds, not the control that fills it.

    The sample card carries lasting injuries with room left, so the
    screen card draws Add beside them. A printed card is read away from
    the picker, and the Add has nowhere to go.
    """

    def test_a_partial_several_pick_does_not_print_add(self, reader):
        page = reader.get("/n26/design/print/sheet/?specimen=cards").content.decode()
        assert "Lasting Injuries" in page
        assert "Eye Injury, Out Cold" in page
        assert "(add)" not in page


class TestTheArrivalBlockPage:
    """The screen after an act, block by block, and the shell page that
    draws the whole screen from sample data."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        body = reader.get("/n26/design/c/arrival-block/").content.decode()
        assert "c-n26.arrival-block" in body
        assert ":block" in body

    def test_the_page_names_the_question_subcomponent(self, reader):
        body = reader.get("/n26/design/c/arrival-block/").content.decode()
        assert "c-n26.arrival-question" in body

    def test_all_three_demos_render_rather_than_falling_back(self, reader):
        body = reader.get("/n26/design/c/arrival-block/").content.decode()
        assert "Choose a gang archetype" in body
        assert "Chosen: Chaos Corrupted" in body
        assert "Choose a Chaos god" in body
        # A block draws no control of its own: Continue and Skip sit once
        # at the foot of the whole screen, which the shell page draws.
        # Matched on the control, because the page's own words name it
        # and the layout carries a "Skip to main content" link.
        assert not re.search(r"<a[^>]*>\s*Skip\s*</a>", body)
        assert "could not be rendered" not in body.lower()

    def test_the_shell_page_renders_on_an_empty_database(self, reader):
        body = reader.get("/n26/design/shell/next/").content.decode()
        assert "Choices for The Forgotten" in body
        assert "Founded The Forgotten." in body
        # The Chaos god may be skipped, so it never holds Continue.
        assert "Choose Gang archetype to continue." in unescape(body)
        # Each picker is named by the heading that asks its question.
        assert 'id="ask-1-gang-1-1"' in body
        assert 'aria-labelledby="ask-1-gang-1-1' in body
        assert "nterstitial" not in body

    def test_the_founding_shell_asks_only_the_gangs_own_questions(self, reader):
        """Founding brings the gang type's slots and nothing else, so a
        model's question cannot appear on this screen. The sample says
        so too: every question here is the gang's."""
        body = unescape(reader.get("/n26/design/shell/next/").content.decode())
        assert "The Forgotten" in body
        for key in ("gang:1:1", "gang:1:2", "gang:1:3"):
            assert key in body
        # No question hosted on a model: those keys lead with its pk.
        assert 'value="1:' not in body and 'value="2:' not in body

    def test_the_shells_forms_post_nowhere(self, reader):
        response = reader.post("/n26/design/shell/next/", {"ask": "gang:1:1"})
        assert response.status_code == 302
        assert response["Location"] == "/n26/design/shell/next/"
