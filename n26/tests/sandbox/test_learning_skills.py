"""What a fighter may learn, and what learning writes.

The founding pick has its own suite (``test_skills_and_powers.py``,
TestPickingASkill). This is the standing half:

* **the grid is the access** — a fighter reaches a skills collection
  exactly where their placements put a category into one of its
  sections, and a profile whose grid nobody authored reaches none;
* **only their tiers** — the browse keeps every unplaced set visible on
  purpose, and the learn screen drops them: another house's sets are not
  this fighter's to learn;
* **learning is free and nobody's consequence** — no credits move, the
  rating follows the thing's own reference price, and the row is caused
  by nothing, so swapping the profile that opened the set up never
  unlearns anything.
"""

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
    # Staff, because the edition is fenced behind the testers gate and a
    # view test that never reaches the view proves nothing.
    return User.objects.create_user("tom", is_staff=True)


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

    def test_a_gear_collection_is_never_learnable(
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
        """A sheet asks which collections hold what a model learns once
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

    def test_a_fighter_with_no_grid_has_no_screen(
        self, client, player, gang, gridless, catalogue
    ):
        nobody = hire_with_option(gang, gridless, "Nobody")
        client.force_login(player)
        assert client.get(skills_url(nobody)).status_code == 404

    def test_somebody_else_s_fighter_is_not_there(self, client, yolanda, catalogue):
        stranger = User.objects.create_user("stranger", is_staff=True)
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
        """Inform, never police — the till's rule, on this screen too."""
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


# --- The write -------------------------------------------------------------


class TestLearning:
    def test_a_press_on_the_screen_writes_it(
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
        """A duplicate skill means nothing in the game, so the press is
        refused — and "already has it" covers every route in, a learned
        one and one granted by an answered choice alike. A card reading
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

    def test_a_press_for_something_off_the_list_writes_nothing(
        self, client, player, gang, yolanda, library
    ):
        """Brawn is nobody's here, so it is not on her screen — and the
        press is answered by the list rather than by the ledger."""
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

    def test_a_learned_skill_survives_the_profile_that_placed_the_set(
        self, gang, yolanda, gang_sister, make_profile, library, sets, tiers
    ):
        """A Legacy profile brings a grid; dropping it takes the tiers
        away and leaves what was learned from them. An earned skill is not
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

    def test_a_learned_power_draws_on_the_powers_row(self, yolanda, library):
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

    def test_answering_names_the_skill_and_takes_the_question_away(
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
