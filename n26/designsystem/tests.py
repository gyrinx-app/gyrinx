"""The gallery's failures are soft, so something has to look at the page.

A catalog entry whose template path does not resolve, and a demo directory
whose name does not match its slug, both render a polite fallback rather than
raising. Registering a component and never loading its page is therefore
indistinguishable from registering it wrongly — which is what this asks.
"""

import pytest
from django.contrib.auth import get_user_model

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


class TestTheActionCardPage:
    """Its props, its body subcomponent and its demos reach the gallery."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        page = reader.get("/n26/design/c/action-card/").content.decode()
        # Read from the component's own <c-vars>, so a prop added there and
        # nowhere else still has to appear here.
        assert "boxed" in page
        assert "body" in page

    def test_the_page_names_the_body_subcomponent(self, reader):
        page = reader.get("/n26/design/c/action-card/").content.decode()
        assert "c-n26.action-card.body" in page

    def test_all_three_demos_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/action-card/").content.decode()
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
        page = reader.get("/n26/design/c/action-card/").content.decode()
        start = page.index("An action with none")
        assert "Remaining" not in page[start:]


class TestTheActionsSquarePage:
    """Its props and all five states reach the gallery drawn."""

    def test_the_page_documents_the_props_declared_in_the_template(self, reader):
        page = reader.get("/n26/design/c/actions-square/").content.decode()
        assert "square" in page

    def test_the_open_action_is_badged(self, reader):
        page = reader.get("/n26/design/c/actions-square/").content.decode()
        assert "Current action" in page

    def test_all_five_demos_render_rather_than_falling_back(self, reader):
        page = reader.get("/n26/design/c/actions-square/").content.decode()
        assert "Nothing open" in page
        assert "The founding open" in page
        assert "A visit open" in page
        assert "Both open" in page
        assert "Nothing done yet" in page
        # From the markup the demos rendered, not their titles.
        assert "No action is open." in page
        assert "Trading Post visit open" in page
        assert "Complete action" in page

    def test_the_story_under_the_square_is_drawn(self, reader):
        """The snapshot's own markup, and one of the sample sentences —
        a demo that fell back to "No examples yet" would carry the
        heading from no state at all."""
        page = reader.get("/n26/design/c/actions-square/").content.decode()
        assert "Recent history" in page
        assert "Full history" in page
        assert "hired Yolanda, a Ganger" in page

    def test_a_gang_with_no_story_says_so(self, reader):
        page = reader.get("/n26/design/c/actions-square/").content.decode()
        assert "No history for this gang yet." in page

    def test_the_start_row_is_a_post_not_a_link(self, reader):
        """Starting an act must never be a link: a link is followed by
        anything that follows links."""
        page = reader.get("/n26/design/c/actions-square/").content.decode()
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
        assert "counts against the" in page
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

    def test_the_gang_shell_draws_the_actions_square(self, reader):
        """Whether the square reads as one of the grid's squares depends on
        the stash and the cards beside it, which only the shell has."""
        page = reader.get("/n26/design/shell/gang/").content.decode()
        assert "Found and equip gang" in page
        assert "Complete action" in page
        # The stash card's own heading, not the wealth strip's figure of
        # the same name, which sits further up the page.
        assert page.index("Found and equip gang") < page.index(">Stash</span>")

    def test_the_campaign_shell_draws_the_tables(self, reader):
        """The gangs table and an assets table both fill from the sample
        sheet, and every slot the view declares is drawn from the page
        rather than from a context variable of the same name."""
        page = reader.get("/n26/design/shell/campaign/").content.decode()
        assert "Territory campaign" in page
        assert "Gravebolt Kin" in page
        assert "Old Ruins by the sump" in page
        assert "Reputation" in page
        assert "Unclaimed" in page
        assert "Record battle" in page
        assert "granted the territory" in page

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
        assert "can spend while the Found and equip gang action is open" in page

    def test_both_kinds_of_open_choice_draw_their_way_in(self, reader):
        """The sample carries an open one-pick choice and a several-pick
        choice with room left. A line built without a slot behind it
        defaults to the one-pick rule, so the open one must still prompt
        — a sample that quietly drew nothing would document the wrong
        thing."""
        page = reader.get("/n26/design/c/model-card/").content.decode()
        legacy = page[page.index("Gang Legacy</dt>") :]
        legacy_dd = legacy[: legacy.index("</dd>")]
        assert ">Choose</" in legacy_dd
        assert "text-xs" in legacy_dd
        injuries = page[page.index("Lasting Injuries</dt>") :]
        injuries_dd = injuries[: injuries.index("</dd>")]
        assert ">Add</" in injuries_dd
        assert "text-xs" in injuries_dd


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
