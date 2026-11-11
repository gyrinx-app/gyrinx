"""Skill access follows category placements into selectable collection sections.

The skills screen offers the model's placed tiers and omits unplaced sets.
Standalone selections spend no credits, use the content's reference rating
and have no cause, so losing access later does not remove them. A selection
matching an open offer instead settles that offer and records its cause.
See test_skills_and_powers.py for founding skill-choice coverage.
"""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.access import model_collections, selectable_for
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
    modifier,
    offers_choice,
    places,
    remove,
    section_of,
    select,
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
    """Place Agility as Primary and Savant as Secondary, leaving Brawn and powers unplaced."""
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
    """Create a profile with no category placements."""
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
    return reverse("n26-skills", args=[miniature.pk])


def skill_submission(client, miniature, thing):
    values = dict(client.get(skills_url(miniature)).context["skills_props"]["values"])
    values["thing"] = f"{thing._meta.label_lower}:{thing.pk}"
    return values


def edit_url(miniature):
    return reverse("n26-edit-fighter", args=[miniature.pk])


def card_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


# --- Standing access -------------------------------------------------------


class TestTheGridIsTheAccess:
    """Category placements provide access to selectable collections without a separate grant."""

    def test_a_graded_fighter_reaches_the_collection(self, yolanda, catalogue):
        assert selectable_for(computed_for(yolanda)) == [catalogue]

    def test_a_fighter_with_no_grid_reaches_nothing(self, gang, gridless, catalogue):
        nobody = hire_with_option(gang, gridless, "Nobody")
        assert selectable_for(computed_for(nobody)) == []

    def test_a_wargear_that_places_a_set_opens_the_collection(
        self, gang, gridless, sets, tiers, catalogue
    ):
        """Equipment placements grant collection access only while that equipment remains held."""
        manual = create_wargear("Combat manual")
        modifier(
            "Combat manual: Brawn under Primary",
            targets_model(),
            places(sets["brawn"], tiers["primary"]),
            carried_by=manual,
        )
        nobody = hire_with_option(gang, gridless, "Nobody")
        carried = assign(manual, miniature=nobody)
        assert selectable_for(computed_for(nobody)) == [catalogue]

        remove(carried)
        assert selectable_for(computed_for(nobody)) == []

    def test_a_gear_collection_is_never_selectable(
        self, gang, gang_sister, sets, catalogue
    ):
        """Placements into an equipment-only collection must not expose a skill-selection screen."""
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

        assert gear_list not in selectable_for(computed_for(fighter))
        assert gear_list not in model_collections()

    def test_asking_the_roster_costs_one_query(
        self, gang, gang_sister, catalogue, library
    ):
        """Load selectable collection kinds once and reuse them across model cards."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        fighters = [
            hire_with_option(gang, gang_sister, f"Sister {index}") for index in range(3)
        ]
        computed = [computed_for(fighter) for fighter in fighters]

        with CaptureQueriesContext(connection) as captured:
            among = model_collections()
            for one in computed:
                assert selectable_for(one, among=among) == [catalogue]
        assert len(captured.captured_queries) == 1


# --- The screen ------------------------------------------------------------


class TestTheWordForIt:
    """Use select consistently in controls, headings and completion messages."""

    def test_the_screen_asks_for_a_selection(self, client, player, yolanda, library):
        client.force_login(player)
        response = client.get(skills_url(yolanda))

        assert (
            response.context["skills_props"]["lead"]
            == f"Select skills for {yolanda.name}."
        )
        assert response.context["skills_props"]["groups"]

    def test_the_sentence_afterwards_says_selected(
        self, client, player, yolanda, library
    ):
        catfall = library["skills"]["Catfall"]
        client.force_login(player)
        response = client.post(
            skills_url(yolanda),
            skill_submission(client, yolanda, catfall),
            follow=True,
        )

        assert "Yolanda selected Catfall." in response.content.decode()

    def test_the_pencil_opens_the_checkbox_editor(
        self, client, player, yolanda, library
    ):
        """Link the model card's Skills edit control to its checkbox editor."""
        from bs4 import BeautifulSoup

        client.force_login(player)
        page = BeautifulSoup(client.get(edit_url(yolanda)).content, "html.parser")
        control = page.find("a", attrs={"aria-label": "Edit skills & powers"})
        rename = page.find("a", attrs={"aria-label": f"Rename {yolanda.name}"})

        assert control["href"] == edit_url(yolanda) + "#n26-skills-box"
        assert control.find_parent("dt").get_text(" ", strip=True) == "Skills"
        assert set(control["class"]) == set(rename["class"])

    def test_no_surface_says_learn(self, client, player, yolanda, library):
        """Scan rendered feature text for inconsistent skill-selection terminology."""
        client.force_login(player)
        pages = [
            client.get(skills_url(yolanda)).content.decode(),
            client.get(edit_url(yolanda)).content.decode(),
        ]

        for body in pages:
            # Only text between tags is swept. Attribute values — a class,
            # an id, an aria-label — are stripped with the tag around them.
            drawn = re.sub(r"<[^>]*>", " ", body)
            assert not re.search(r"\blearn(s|ed|ing)?\b", drawn, re.IGNORECASE)


class TestWhatTheScreenShows:
    """Only the tiers the fighter's grid names."""

    def test_it_lists_the_placed_sets_and_nothing_else(
        self, client, player, yolanda, library
    ):
        client.force_login(player)
        offer = client.get(skills_url(yolanda)).context["skills_props"]

        assert [group["name"] for group in offer["groups"]] == ["Agility", "Savant"]
        names = {
            option["name"] for group in offer["groups"] for option in group["options"]
        }
        assert "Catfall" in names  # Agility is Primary for her
        assert "Connected" in names  # Savant is Secondary
        assert "Bull Charge" not in names  # Brawn is nobody's here
        assert "Terrify (Double)" not in names  # the powers are unrevealed

    def test_each_set_says_which_tier_it_is(self, client, player, yolanda, library):
        """Label each skill set with its placed tier."""
        client.force_login(player)
        offer = client.get(skills_url(yolanda)).context["skills_props"]

        assert [(group["name"], group["caption"]) for group in offer["groups"]] == [
            ("Agility", "Primary"),
            ("Savant", "Secondary"),
        ]

    def test_a_fighter_with_no_grid_gets_a_page_that_says_so(
        self, client, player, gang, gridless, catalogue
    ):
        """Render an explanation for missing category placements rather than withholding the model page."""
        nobody = hire_with_option(gang, gridless, "Nobody")
        client.force_login(player)
        response = client.get(skills_url(nobody))

        assert response.status_code == 200
        assert response.context["skills_props"]["nothingToSelect"]

    def test_a_fighter_with_no_grid_is_not_asked_to_select_anything(
        self, client, player, gang, gridless, catalogue
    ):
        """Omit the submit action when no skills are selectable."""
        nobody = hire_with_option(gang, gridless, "Nobody")
        client.force_login(player)
        assert client.get(skills_url(nobody)).context["skills_props"]["nothingToSelect"]

    def test_somebody_else_s_fighter_is_not_there(self, client, yolanda, catalogue):
        stranger = User.objects.create_user("stranger")
        client.force_login(stranger)
        assert client.get(skills_url(yolanda)).status_code == 404

    def test_what_she_already_knows_is_said_rather_than_withheld(
        self, client, player, yolanda, library
    ):
        select(yolanda, library["skills"]["Catfall"])
        client.force_login(player)
        offer = client.get(skills_url(yolanda)).context["skills_props"]

        catfall = next(
            option
            for group in offer["groups"]
            for option in group["options"]
            if option["name"] == "Catfall"
        )
        assert "already known" in catfall["remark"]

    def test_a_restricted_skill_keeps_its_place_with_a_note(
        self, client, player, yolanda, library
    ):
        """Keep restricted skills visible with a use restriction note."""
        from n26.tests.sandbox.actions import restrict_use

        restrict_use(library["skills"]["Catfall"], create_subtype("Walker"))
        client.force_login(player)
        offer = client.get(skills_url(yolanda)).context["skills_props"]

        catfall = next(
            option
            for group in offer["groups"]
            for option in group["options"]
            if option["name"] == "Catfall"
        )
        assert "only" in catfall["remark"]


class TestGettingToTheNextFighter:
    """Link the roster switcher to each model's own skills page, including models without selectable sets."""

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
        """Retain gridless models in the switcher and link to their explanatory page."""
        nobody = hire_with_option(gang, gridless, "Nobody")
        client.force_login(player)
        body = client.get(skills_url(yolanda)).content.decode()

        assert skills_url(nobody) in body
        assert client.get(skills_url(nobody)).status_code == 200

    def test_the_fighter_whose_screen_this_is_says_so(
        self, client, player, gang, gang_sister, yolanda, catalogue
    ):
        """Use aria-current to identify the selected model independently of icons or colour."""
        hire_with_option(gang, gang_sister, "Mad Donna")
        client.force_login(player)
        switcher = client.get(skills_url(yolanda)).context["skills_props"]["switcher"]
        assert switcher["current"] == skills_url(yolanda)

    def test_the_control_says_what_it_switches(
        self, client, player, gang, gang_sister, yolanda, catalogue
    ):
        """Give the model and gang switchers distinct accessible labels."""
        hire_with_option(gang, gang_sister, "Mad Donna")
        client.force_login(player)
        body = client.get(skills_url(yolanda)).content.decode()

        assert (
            client.get(skills_url(yolanda)).context["skills_props"]["switcher"][
                "menuLabel"
            ]
            == "Select skills for another fighter"
        )
        assert 'aria-label="Switch to another gang"' in body

    def test_somebody_else_s_roster_is_not_in_it(
        self, client, player, gang_type, gang_sister, yolanda, catalogue
    ):
        """Do not expose another owner's models through the switcher."""
        stranger = User.objects.create_user("stranger")
        theirs = found_gang("Other Bad Girls", gang_type, owner=stranger, budget=1000)
        elsewhere = hire_with_option(theirs, gang_sister, "Nobody Of Ours")

        client.force_login(player)
        body = client.get(skills_url(yolanda)).content.decode()

        assert "Nobody Of Ours" not in body
        assert skills_url(elsewhere) not in body


class TestTheWayOut:
    """Return to the model page from which the skills editor is opened."""

    def test_cancel_leads_back_to_the_model_s_own_page(
        self, client, player, yolanda, library
    ):
        client.force_login(player)
        response = client.get(skills_url(yolanda))

        assert response.context["skills_props"]["back"] == edit_url(yolanda)

    def test_selecting_something_lands_on_the_same_page_cancel_does(
        self, client, player, yolanda, library
    ):
        """Save and Cancel return to the same model page."""
        catfall = library["skills"]["Catfall"]
        client.force_login(player)
        response = client.post(
            skills_url(yolanda),
            skill_submission(client, yolanda, catfall),
        )

        assert response["Location"] == edit_url(yolanda)

    def test_the_breadcrumb_names_the_model_under_the_gang(
        self, client, player, yolanda, library
    ):
        """Place the model breadcrumb between its gang and the skills editor."""
        client.force_login(player)
        page = client.get(skills_url(yolanda)).context["skills_props"]
        assert page["gangHref"] == reverse("n26-gang", args=[yolanda.gang.pk])
        assert page["back"] == edit_url(yolanda)
        assert page["name"] == "Yolanda"

    def test_a_fighter_with_nothing_to_select_still_has_the_way_back(
        self, client, player, gang, gridless, catalogue
    ):
        """Keep a model breadcrumb when no selectable content or Cancel action is shown."""
        nobody = hire_with_option(gang, gridless, "Nobody")
        client.force_login(player)
        assert client.get(skills_url(nobody)).context["skills_props"][
            "back"
        ] == edit_url(nobody)


# --- The write -------------------------------------------------------------


class TestSelecting:
    def test_a_click_on_the_screen_writes_it(
        self, client, player, gang, yolanda, library
    ):
        """Resolve the submitted identity against the server-derived offer before recording the selection."""
        catfall = library["skills"]["Catfall"]
        client.force_login(player)
        response = client.post(
            skills_url(yolanda),
            skill_submission(client, yolanda, catfall),
        )

        assert response.status_code == 302
        assert "Catfall" in [line.name for line in card_for(yolanda).skills]
        assert_reconciled(gang)

    def test_a_second_copy_is_refused_however_the_first_arrived(
        self, client, player, gang, yolanda, library
    ):
        """Refuse a duplicate selection so the card displays one copy of the skill."""
        catfall = library["skills"]["Catfall"]
        select(yolanda, catfall)
        client.force_login(player)
        response = client.post(
            skills_url(yolanda),
            skill_submission(client, yolanda, catfall),
        )

        assert response.status_code == 422
        names = [line.name for line in card_for(yolanda).skills]
        assert names.count("Catfall") == 1
        assert_reconciled(gang)

    def test_a_click_for_something_off_the_list_writes_nothing(
        self, client, player, gang, yolanda, library
    ):
        """Reject skills outside the model's placed sets without creating an assignment."""
        off_list = library["skills"]["Bull Charge"]
        client.force_login(player)
        client.post(
            skills_url(yolanda),
            skill_submission(client, yolanda, off_list),
        )

        assert card_for(yolanda).skills == []
        assert_reconciled(gang)

    def test_it_costs_nothing_and_is_recorded_as_a_reward(self, gang, yolanda, library):
        before = gang.credits
        selected = select(yolanda, library["skills"]["Catfall"])

        assert selected.ledger_entry.paid == 0
        assert selected.ledger_entry.reason == Reason.REWARD
        gang.refresh_from_db()
        assert gang.credits == before
        assert_reconciled(gang)

    def test_the_rating_follows_the_thing_s_own_price(self, gang, yolanda, sets):
        """Record the selected content's reference price as its rating contribution."""
        plain = create_skill("Spring Up", category=sets["agility"])
        dear = create_power("Ember Storm", "Double", category=sets["powers"], price=30)

        assert select(yolanda, plain).ledger_entry.rating_contribution == 0
        assert select(yolanda, dear).ledger_entry.rating_contribution == 30
        gang.refresh_from_db()
        assert gang.rating == 55 + 30
        assert_reconciled(gang)

    def test_a_selected_skill_survives_the_profile_that_placed_the_set(
        self, gang, yolanda, gang_sister, make_profile, library, sets, tiers
    ):
        """Removing a legacy profile revokes its access placements but preserves standalone selections."""
        legacy = make_profile("Cawdor Bonepicker", price=40)
        modifier(
            "Bonepicker: Brawn under Primary",
            targets_model(),
            places(sets["brawn"], tiers["primary"]),
            carried_by=legacy,
        )
        carried = add_legacy_profile(yolanda, legacy)
        selected = select(yolanda, library["skills"]["Bull Charge"])

        remove(carried)
        yolanda.refresh_from_db()
        selected.refresh_from_db()
        assert selected.archived is False
        assert "Bull Charge" in [line.name for line in card_for(yolanda).skills]
        assert_reconciled(gang)

    def test_a_selected_power_draws_on_the_powers_row(self, yolanda, library):
        select(yolanda, library["powers"]["Terrify"])
        card = card_for(yolanda)
        assert [line.name for line in card.powers] == ["Terrify (Double)"]
        assert card.skills == []


# --- The card --------------------------------------------------------------


class TestTheSkillsRow:
    """Display skill offers in the Skills row while retaining other choices in the general choice area."""

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
        """Keep non-skill offers in the general choice area."""
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

    def test_selecting_a_primary_skill_on_the_skills_screen_answers_the_question(
        self, client, player, leader_yolanda, library
    ):
        catfall = library["skills"]["Catfall"]
        client.force_login(player)
        client.post(
            skills_url(leader_yolanda),
            skill_submission(client, leader_yolanda, catfall),
        )

        card = card_for(leader_yolanda)
        assert card.skill_choices == []
        assert "Catfall" in [line.name for line in card.skills]
        row = leader_yolanda.assignments.get(skill=catfall, archived=False)
        assert row.chosen_for_offer_id is not None
        assert row.caused_by_id is not None

    def test_selecting_a_secondary_skill_on_the_skills_screen_leaves_the_question_open(
        self, client, player, leader_yolanda, library
    ):
        """A standalone Secondary selection does not settle the open Primary skill offer."""
        connected = library["skills"]["Connected"]
        client.force_login(player)
        client.post(
            skills_url(leader_yolanda),
            skill_submission(client, leader_yolanda, connected),
        )

        card = card_for(leader_yolanda)
        assert [line.kind_label for line in card.skill_choices] == ["Primary skill"]
        assert "Connected" in [line.name for line in card.skills]
        row = leader_yolanda.assignments.get(skill=connected, archived=False)
        assert row.chosen_for_offer_id is None
        assert row.caused_by_id is None

    @pytest.mark.parametrize("legacy", [False, True])
    def test_an_offered_skill_is_labelled_as_chosen_not_automatically_granted(
        self, leader_yolanda, library, legacy
    ):
        anchor = leader_yolanda.assignments.get(subtype__name="Leader")
        catfall = library["skills"]["Catfall"]
        choose(anchor, catfall)
        assignment = leader_yolanda.assignments.get(skill=catfall, archived=False)
        if legacy:
            # Exercise assignments with a cause but no explicit offer identity.
            assignment.chosen_for_offer = None
            assignment.save(update_fields=["chosen_for_offer"])

        card = card_for(leader_yolanda)
        skill = next(line for line in card.skills if line.name == "Catfall")
        assert skill.provenance.chosen
        assert skill.provenance.description == "Chosen from Leader (subtype)"
        assert skill.provenance.annotated
        assignment.refresh_from_db()
        assert assignment.caused_by_id == anchor.pk

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
        from n26.core.views.skills import link_skills

        gang = leader_yolanda.gang
        sheet = render_gang(gang)
        link_slots(gang, sheet, *sheet.models)
        link_skills(*sheet.models)

        (card,) = sheet.models
        assert card.skills_href == edit_url(leader_yolanda) + "#n26-skills-box"
        assert card.skill_choices[0].href.startswith(
            reverse("n26-gang", args=[gang.pk])
        )

    def test_a_gridless_fighter_gets_no_way_in(self, gang, gridless, catalogue):
        from n26.core.render import render_gang
        from n26.core.views.skills import link_skills

        hire_with_option(gang, gridless, "Nobody")
        sheet = render_gang(gang)
        link_skills(*sheet.models)

        (card,) = sheet.models
        assert card.skills_href == ""
        assert card.skill_choices == []
