"""What a fighter may select, and what selecting writes.

The founding pick has its own suite (``test_skills_and_powers.py``,
TestPickingASkill). This is the standing half:

* **the grid is the access** — a fighter reaches a skills collection
  exactly where their placements put a category into one of its
  sections, and a profile whose grid nobody authored reaches none;
* **only their tiers** — the browse keeps every unplaced set visible on
  purpose, and the skills screen drops them: another house's sets are not
  this fighter's to select;
* **selecting is free and nobody's consequence** — no credits move, the
  rating follows the thing's own reference price, and the row is caused
  by nothing, so swapping the profile that opened the set up never takes
  one back.
"""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.access import learnable_for, model_collections
from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Reason
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.library.models import Power, Skill, Wargear
from n26.tests.sandbox.actions import (
    add_legacy_profile,
    assign,
    choose,
    create_category,
    create_collection,
    create_power,
    create_skill,
    create_subtype,
    create_wargear,
    found_gang,
    hire_with_option,
    learn,
    modifier,
    offers_choice,
    places,
    remove,
    section_of,
    targets_model,
)

pytestmark = pytest.mark.django_db


# --- The content library ---------------------------------------------------


@pytest.fixture
def sets(db):
    return {
        "agility": create_category("Skills", "Agility", position=0),
        "brawn": create_category("Skills", "Brawn", position=1),
        "savant": create_category("Skills", "Savant", position=3),
        "powers": create_category("Wyrd Powers", "Wyrd Powers", position=10),
    }


@pytest.fixture
def library(sets):
    skills = {}
    for set_key, names in [
        ("agility", ["Catfall", "Dodge"]),
        ("brawn", ["Bull Charge"]),
        ("savant", ["Connected"]),
    ]:
        for number, name in enumerate(names, start=1):
            skills[name] = create_skill(name, category=sets[set_key], position=number)
    powers = {
        "Terrify": create_power(
            "Terrify", "Double", category=sets["powers"], position=1
        )
    }
    return {"skills": skills, "powers": powers}


@pytest.fixture
def catalogue(library):
    """The one collection: every skill and every power, by sweep."""
    return create_collection("Skills & Powers", contains=[Skill, Power])


@pytest.fixture
def tiers(catalogue):
    return {
        "primary": section_of(catalogue, "Primary", 0),
        "secondary": section_of(catalogue, "Secondary", 1),
        "other": section_of(catalogue, "Other", 9, is_default=True),
    }


@pytest.fixture
def gang_sister(make_profile, sets, tiers):
    """A grid: Agility Primary, Savant Secondary. Brawn is nobody's here,
    and the powers are unrevealed."""
    profile = make_profile("Escher Gang Sister", price=55)
    for category, tier in [
        (sets["agility"], tiers["primary"]),
        (sets["savant"], tiers["secondary"]),
    ]:
        modifier(
            f"Gang Sister: {category.name} under {tier.name}",
            targets_model(),
            places(category, tier),
            carried_by=profile,
        )
    return profile


@pytest.fixture
def gridless(make_profile):
    """A profile nobody has written a grid for — the content gap."""
    return make_profile("Sump Scavenger", price=30)


@pytest.fixture
def player(db):
    return User.objects.create_user("tom")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)


@pytest.fixture
def yolanda(gang, gang_sister, catalogue, tiers):
    return hire_with_option(gang, gang_sister, "Yolanda")


def computed_for(miniature):
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def skills_url(miniature):
    return reverse("n26-learn", args=[miniature.pk])


def edit_url(miniature):
    return reverse("n26-edit-fighter", args=[miniature.pk])


def card_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


# --- Standing access -------------------------------------------------------


class TestTheGridIsTheAccess:
    """No grant, no built-in, no access table: a fighter reaches a
    collection where their placements name one of its sections."""

    def test_a_graded_fighter_reaches_the_collection(self, yolanda, catalogue):
        assert learnable_for(computed_for(yolanda)) == [catalogue]

    def test_a_fighter_with_no_grid_reaches_nothing(self, gang, gridless, catalogue):
        nobody = hire_with_option(gang, gridless, "Nobody")
        assert learnable_for(computed_for(nobody)) == []

    def test_a_wargear_that_places_a_set_opens_the_collection(
        self, gang, gridless, sets, tiers, catalogue
    ):
        """Standing access is computed, so anything that places a category
        grants it — and taking that thing away takes the access with it."""
        manual = create_wargear("Combat manual")
        modifier(
            "Combat manual: Brawn under Primary",
            targets_model(),
            places(sets["brawn"], tiers["primary"]),
            carried_by=manual,
        )
        nobody = hire_with_option(gang, gridless, "Nobody")
        carried = assign(manual, miniature=nobody)
        assert learnable_for(computed_for(nobody)) == [catalogue]

        remove(carried)
        assert learnable_for(computed_for(nobody)) == []

    def test_a_gear_collection_is_never_selectable(
        self, gang, gang_sister, sets, catalogue
    ):
        """A placement may aim at any collection's schema, including an
        equipment list's. Learning is about what a model *is*, so a list
        of gear never becomes a skills screen however it is placed."""
        gear_list = create_collection("House List", contains=[Wargear])
        gear_primary = section_of(gear_list, "Primary", 0)
        badge = create_subtype("Quartermaster")
        modifier(
            "Quartermaster: Brawn under the house list's Primary",
            targets_model(),
            places(sets["brawn"], gear_primary),
            carried_by=badge,
        )

        fighter = hire_with_option(gang, gang_sister, "Yolanda")
        assign(badge, miniature=fighter)

        assert gear_list not in learnable_for(computed_for(fighter))
        assert gear_list not in model_collections()

    def test_asking_the_roster_costs_one_query(
        self, gang, gang_sister, catalogue, library
    ):
        """A sheet asks which collections hold what a model selects once
        and tests every card against the answer."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        fighters = [
            hire_with_option(gang, gang_sister, f"Sister {index}") for index in range(3)
        ]
        computed = [computed_for(fighter) for fighter in fighters]

        with CaptureQueriesContext(connection) as captured:
            among = model_collections()
            for one in computed:
                assert learnable_for(one, among=among) == [catalogue]
        assert len(captured.captured_queries) == 1


# --- The screen ------------------------------------------------------------


class TestTheWordForIt:
    """One verb for the act, on every surface that names it: select.

    The screen, the control leading to it and the sentence afterwards each
    used to say something slightly different — learn, pick, learned — for
    one act. A reader deciding what a button will do should not have to
    work out whether three words mean three things.
    """

    def test_the_screen_asks_for_a_selection(self, client, player, yolanda, library):
        client.force_login(player)
        response = client.get(skills_url(yolanda))

        assert response.context["pick_lead"] == f"Select skills for {yolanda.name}."
        assert response.context["submit_label"] == "Select"

    def test_the_sentence_afterwards_says_selected(
        self, client, player, yolanda, library
    ):
        catfall = library["skills"]["Catfall"]
        client.force_login(player)
        response = client.post(
            skills_url(yolanda),
            {"thing": f"{catfall._meta.label_lower}:{catfall.pk}"},
            follow=True,
        )

        assert "Yolanda selected Catfall." in response.content.decode()

    def test_the_control_leading_here_says_selecting_too(
        self, client, player, yolanda, library
    ):
        """The card's Skills row carries the way in, and it is drawn on the
        model's own page — so the word on it is read before the screen's."""
        client.force_login(player)
        body = client.get(edit_url(yolanda)).content.decode()

        assert 'aria-label="Select a skill"' in body

    def test_no_surface_still_says_learn(self, client, player, yolanda, library):
        """A discovering check rather than a list: every rendered word of
        this feature is swept, so a surface added later cannot quietly
        reintroduce the old verb."""
        client.force_login(player)
        pages = [
            client.get(skills_url(yolanda)).content.decode(),
            client.get(edit_url(yolanda)).content.decode(),
        ]

        for body in pages:
            # The href and the URL name keep "learn" — those are code, not
            # words anybody reads. Only drawn text is swept.
            drawn = re.sub(r"<[^>]*>", " ", body)
            assert not re.search(r"\blearn(s|ed|ing)?\b", drawn, re.IGNORECASE)


class TestWhatTheScreenShows:
    """Only the tiers the fighter's grid names."""

    def test_it_lists_the_placed_sets_and_nothing_else(
        self, client, player, yolanda, library
    ):
        client.force_login(player)
        offer = client.get(skills_url(yolanda)).context["offer"]

        assert [group.name for group in offer.groups] == ["Agility", "Savant"]
        names = {option.name for group in offer.groups for option in group.options}
        assert "Catfall" in names  # Agility is Primary for her
        assert "Connected" in names  # Savant is Secondary
        assert "Bull Charge" not in names  # Brawn is nobody's here
        assert "Terrify (Double)" not in names  # the powers are unrevealed

    def test_each_set_says_which_tier_it_is(self, client, player, yolanda, library):
        """The tiers are the whole point of the screen, and a set's name
        does not say which one it sits in."""
        client.force_login(player)
        offer = client.get(skills_url(yolanda)).context["offer"]

        assert [(group.name, group.caption) for group in offer.groups] == [
            ("Agility", "Primary"),
            ("Savant", "Secondary"),
        ]

    def test_a_fighter_with_no_grid_gets_a_page_that_says_so(
        self, client, player, gang, gridless, catalogue
    ):
        """Nothing to select is a thing to say, not a page to withhold: the
        address names the fighter, and the gap is in the content."""
        nobody = hire_with_option(gang, gridless, "Nobody")
        client.force_login(player)
        response = client.get(skills_url(nobody))

        assert response.status_code == 200
        body = response.content.decode()
        assert "not graded in any skill category" in body

    def test_a_fighter_with_no_grid_is_not_asked_to_select_anything(
        self, client, player, gang, gridless, catalogue
    ):
        """No list, so no act at the foot of the page — a Select button with
        nothing selectable above it is a click that can only fail."""
        nobody = hire_with_option(gang, gridless, "Nobody")
        client.force_login(player)
        body = client.get(skills_url(nobody)).content.decode()

        # The page's only act would be Select, and there is nothing to select.
        assert 'type="submit"' not in body

    def test_somebody_else_s_fighter_is_not_there(self, client, yolanda, catalogue):
        stranger = User.objects.create_user("stranger")
        client.force_login(stranger)
        assert client.get(skills_url(yolanda)).status_code == 404

    def test_what_she_already_knows_is_said_rather_than_withheld(
        self, client, player, yolanda, library
    ):
        learn(yolanda, library["skills"]["Catfall"])
        client.force_login(player)
        offer = client.get(skills_url(yolanda)).context["offer"]

        catfall = next(
            option
            for group in offer.groups
            for option in group.options
            if option.name == "Catfall"
        )
        assert "already known" in catfall.detail

    def test_a_restricted_skill_keeps_its_place_with_a_note(
        self, client, player, yolanda, library
    ):
        """Inform, never police — the equip page's rule, on this screen too."""
        from n26.tests.sandbox.actions import restrict_use

        restrict_use(library["skills"]["Catfall"], create_subtype("Walker"))
        client.force_login(player)
        offer = client.get(skills_url(yolanda)).context["offer"]

        catfall = next(
            option
            for group in offer.groups
            for option in group.options
            if option.name == "Catfall"
        )
        assert "only" in catfall.detail


class TestGettingToTheNextFighter:
    """The heading names one fighter, so it carries the way to the others.

    Every row leads to that fighter's own skills screen. Picking skills is
    a job done down a roster, and a row that landed on a different screen
    would break off halfway through it — which is also why the screen
    exists for a fighter with nothing to select.
    """

    def test_the_gang_s_other_fighters_are_offered(
        self, client, player, gang, gang_sister, yolanda, catalogue
    ):
        mad_donna = hire_with_option(gang, gang_sister, "Mad Donna")
        client.force_login(player)
        body = client.get(skills_url(yolanda)).content.decode()

        assert skills_url(mad_donna) in body
        assert "Mad Donna" in body

    def test_a_fighter_with_nothing_to_select_is_still_offered(
        self, client, player, gang, gridless, yolanda, catalogue
    ):
        """The row leads to a page that says there is nothing there, which
        is the reader's answer — a switcher that dropped them would say
        instead that the fighter is not in the gang."""
        nobody = hire_with_option(gang, gridless, "Nobody")
        client.force_login(player)
        body = client.get(skills_url(yolanda)).content.decode()

        assert skills_url(nobody) in body
        assert client.get(skills_url(nobody)).status_code == 200

    def test_the_fighter_whose_screen_this_is_says_so(
        self, client, player, gang, gang_sister, yolanda, catalogue
    ):
        """A tick is a glyph and a tint is a colour; aria-current is what
        tells a reader using neither which fighter they are on."""
        hire_with_option(gang, gang_sister, "Mad Donna")
        client.force_login(player)
        body = client.get(skills_url(yolanda)).content.decode()

        # The href, not the bare path: the page posts to its own address
        # with the collection on the query string, so the path appears in
        # the form's action before it appears in the switcher.
        hers = body.index(f'href="{skills_url(yolanda)}"')
        assert 'aria-current="page"' in body[hers : body.index("</a>", hers)]

    def test_the_control_says_what_it_switches(
        self, client, player, gang, gang_sister, yolanda, catalogue
    ):
        """Two switchers sit on this screen — the bar's gangs and the
        heading's fighters — and a reader who cannot see them apart needs
        their names to differ."""
        hire_with_option(gang, gang_sister, "Mad Donna")
        client.force_login(player)
        body = client.get(skills_url(yolanda)).content.decode()

        assert 'aria-label="Select skills for another fighter"' in body
        assert 'aria-label="Switch to another gang"' in body

    def test_somebody_else_s_roster_is_not_in_it(
        self, client, player, gang_type, gang_sister, yolanda, catalogue
    ):
        """A switcher that could name a stranger's fighter would be a way
        of finding out that they exist."""
        stranger = User.objects.create_user("stranger")
        theirs = found_gang("Other Bad Girls", gang_type, owner=stranger, budget=1000)
        elsewhere = hire_with_option(theirs, gang_sister, "Nobody Of Ours")

        client.force_login(player)
        body = client.get(skills_url(yolanda)).content.decode()

        assert "Nobody Of Ours" not in body
        assert skills_url(elsewhere) not in body


class TestTheWayOut:
    """Where the screen leads when a reader is done with it.

    The control opening it is drawn on the model's own page and nowhere
    else, so that page is what a reader came from and what leaving owes
    them: the gang sheet is a level above the screen they were working
    on, and the skills control they clicked is not on it.
    """

    def test_cancel_leads_back_to_the_model_s_own_page(
        self, client, player, yolanda, library
    ):
        client.force_login(player)
        response = client.get(skills_url(yolanda))

        assert response.context["cancel_url"] == edit_url(yolanda)
        # The last of them: the breadcrumb leads to the same page from the
        # top of the document, and the footer's way out is the one at the end.
        body = response.content.decode()
        out = body.rindex(f'href="{edit_url(yolanda)}"')
        assert "Cancel" in body[out : body.index("</a>", out)]

    def test_selecting_something_lands_on_the_same_page_cancel_does(
        self, client, player, yolanda, library
    ):
        """A save and a cancel leave by the same door: one of them landing
        somewhere else would make the footer's two buttons disagree about
        where the reader was."""
        catfall = library["skills"]["Catfall"]
        client.force_login(player)
        response = client.post(
            skills_url(yolanda),
            {"thing": f"{catfall._meta.label_lower}:{catfall.pk}"},
        )

        assert response["Location"] == edit_url(yolanda)

    def test_the_breadcrumb_names_the_model_under_the_gang(
        self, client, player, yolanda, library
    ):
        """The model sits between the gang and this page, as it does on
        every other screen addressed by one."""
        client.force_login(player)
        body = client.get(skills_url(yolanda)).content.decode()

        gang_crumb = body.index(f'href="{reverse("n26-gang", args=[yolanda.gang.pk])}"')
        model_crumb = body.index(f'href="{edit_url(yolanda)}"')
        assert gang_crumb < model_crumb
        assert "Yolanda" in body[model_crumb : body.index("</a>", model_crumb)]

    def test_a_fighter_with_nothing_to_select_still_has_the_way_back(
        self, client, player, gang, gridless, catalogue
    ):
        """That page draws no Cancel — there is nothing to cancel — so the
        breadcrumb is the whole of the way out, and it has to reach the
        model whose screen this is."""
        nobody = hire_with_option(gang, gridless, "Nobody")
        client.force_login(player)
        body = client.get(skills_url(nobody)).content.decode()

        assert f'href="{edit_url(nobody)}"' in body


# --- The write -------------------------------------------------------------


class TestSelecting:
    def test_a_click_on_the_screen_writes_it(
        self, client, player, gang, yolanda, library
    ):
        """The whole way through: the button submits an identity, the
        server re-derives the list and writes what it found."""
        catfall = library["skills"]["Catfall"]
        client.force_login(player)
        response = client.post(
            skills_url(yolanda),
            {"thing": f"{catfall._meta.label_lower}:{catfall.pk}"},
        )

        assert response.status_code == 302
        assert "Catfall" in [line.name for line in card_for(yolanda).skills]
        assert_reconciled(gang)

    def test_a_second_copy_is_refused_however_the_first_arrived(
        self, client, player, gang, yolanda, library
    ):
        """A duplicate skill means nothing in the game, so the click is
        refused — and "already has it" covers every route in, a selected
        one and one granted by a settled choice alike. A card reading
        "Marksman, Marksman" is a bug however honestly each row was
        written."""
        catfall = library["skills"]["Catfall"]
        learn(yolanda, catfall)
        client.force_login(player)
        response = client.post(
            skills_url(yolanda),
            {"thing": f"{catfall._meta.label_lower}:{catfall.pk}"},
        )

        assert response.status_code == 302
        names = [line.name for line in card_for(yolanda).skills]
        assert names.count("Catfall") == 1
        assert_reconciled(gang)

    def test_a_click_for_something_off_the_list_writes_nothing(
        self, client, player, gang, yolanda, library
    ):
        """Brawn is nobody's here, so it is not on her screen — and the
        click is answered by the list rather than by the ledger."""
        off_list = library["skills"]["Bull Charge"]
        client.force_login(player)
        client.post(
            skills_url(yolanda),
            {"thing": f"{off_list._meta.label_lower}:{off_list.pk}"},
        )

        assert card_for(yolanda).skills == []
        assert_reconciled(gang)

    def test_it_costs_nothing_and_is_recorded_as_a_reward(self, gang, yolanda, library):
        before = gang.credits
        learned = learn(yolanda, library["skills"]["Catfall"])

        assert learned.ledger_entry.paid == 0
        assert learned.ledger_entry.reason == Reason.REWARD
        gang.refresh_from_db()
        assert gang.credits == before
        assert_reconciled(gang)

    def test_the_rating_follows_the_thing_s_own_price(self, gang, yolanda, sets):
        """Zero for a skill the rules hand out; whatever content says for
        something worth something."""
        plain = create_skill("Spring Up", category=sets["agility"], position=9)
        dear = create_power("Ember Storm", "Double", category=sets["powers"], price=30)

        assert learn(yolanda, plain).ledger_entry.rating_contribution == 0
        assert learn(yolanda, dear).ledger_entry.rating_contribution == 30
        gang.refresh_from_db()
        assert gang.rating == 55 + 30
        assert_reconciled(gang)

    def test_a_selected_skill_survives_the_profile_that_placed_the_set(
        self, gang, yolanda, gang_sister, make_profile, library, sets, tiers
    ):
        """A Legacy profile brings a grid; dropping it takes the tiers
        away and leaves what was selected from them. An earned skill is not
        a consequence of a row still being there."""
        legacy = make_profile("Cawdor Bonepicker", price=40)
        modifier(
            "Bonepicker: Brawn under Primary",
            targets_model(),
            places(sets["brawn"], tiers["primary"]),
            carried_by=legacy,
        )
        carried = add_legacy_profile(yolanda, legacy)
        learned = learn(yolanda, library["skills"]["Bull Charge"])

        remove(carried)
        yolanda.refresh_from_db()
        learned.refresh_from_db()
        assert learned.archived is False
        assert "Bull Charge" in [line.name for line in card_for(yolanda).skills]
        assert_reconciled(gang)

    def test_a_selected_power_draws_on_the_powers_row(self, yolanda, library):
        learn(yolanda, library["powers"]["Terrify"])
        card = card_for(yolanda)
        assert [line.name for line in card.powers] == ["Terrify (Double)"]
        assert card.skills == []


# --- The card --------------------------------------------------------------


class TestTheSkillsRow:
    """The two controls a card carries about skills, and where the
    question asking for one stopped being drawn."""

    @pytest.fixture
    def leader(self, tiers):
        subtype = create_subtype("Leader")
        modifier(
            "A Leader starts with a Primary skill",
            targets_model(),
            offers_choice(Skill, from_section=tiers["primary"]),
            carried_by=subtype,
        )
        return subtype

    @pytest.fixture
    def leader_yolanda(self, yolanda, leader):
        assign(leader, miniature=yolanda)
        return yolanda

    def test_an_open_skill_question_is_the_skills_row_s_and_not_a_slot(
        self, leader_yolanda
    ):
        card = card_for(leader_yolanda)
        assert [line.kind_label for line in card.skill_choices] == ["Primary skill"]
        assert [line.kind_label for line in card.choices] == []

    def test_another_kind_of_question_stays_where_it_was(self, yolanda, tiers):
        """Only skills moved. An archetype has no row of its own to move
        into, and is still drawn as a slot."""
        from n26.library.models import Subtype

        badge = create_subtype("Outcast")
        modifier(
            "An Outcast names a favoured archetype",
            targets_model(),
            offers_choice(Subtype),
            carried_by=badge,
        )
        assign(badge, miniature=yolanda)

        card = card_for(yolanda)
        assert [line.kind_label for line in card.choices] == ["Subtype"]
        assert card.skill_choices == []

    def test_choosing_names_the_skill_and_takes_the_question_away(
        self, leader_yolanda, library
    ):
        anchor = leader_yolanda.assignments.get(subtype__name="Leader")
        choose(anchor, library["skills"]["Catfall"])

        card = card_for(leader_yolanda)
        assert card.skill_choices == []
        assert "Catfall" in [line.name for line in card.skills]

    def test_a_card_says_which_collections_its_grid_reaches(
        self, yolanda, catalogue, gang, gridless
    ):
        assert card_for(yolanda).placed_in == (str(catalogue.pk),)

        nobody = hire_with_option(gang, gridless, "Nobody")
        assert card_for(nobody).placed_in == ()

    def test_the_sheet_points_both_controls_somewhere(
        self, client, player, leader_yolanda, catalogue
    ):
        from n26.core.render import render_gang
        from n26.core.views.choose import link_slots
        from n26.core.views.learn import link_skills

        gang = leader_yolanda.gang
        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        link_skills(*sheet.models)

        (card,) = sheet.models
        assert card.learn_href == skills_url(leader_yolanda)
        assert card.skill_choices[0].href.startswith(
            reverse("n26-gang", args=[gang.pk])
        )

    def test_a_gridless_fighter_gets_no_way_in(self, gang, gridless, catalogue):
        from n26.core.render import render_gang
        from n26.core.views.learn import link_skills

        hire_with_option(gang, gridless, "Nobody")
        sheet = render_gang(gang)
        link_skills(*sheet.models)

        (card,) = sheet.models
        assert card.learn_href == ""
        assert card.skill_choices == []
