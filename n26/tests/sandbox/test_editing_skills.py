"""Ticking a model's skills and powers on their own page.

The skills screen learns one thing at a time, at its own address. This is
the same list as a box on the model's edit page: everything their grid
puts within reach, ticked where they have it, settled in one press.

The rules this file pins:

* **The grid is the list.** The square draws the fighter's own view of
  the collections their placements reach, tier by tier — the same browse
  the skills screen makes, so the two cannot come to disagree about what
  is theirs. A set nobody placed for them is not on it, and neither is
  the tier the unplaced fall into.
* **Skills and powers alike.** A tier holds whatever the content swept
  into it, so a family of powers placed for a fighter ticks like a skill
  set does.
* **A tick learns and a cleared box takes away**, in one operation: a
  save that fails writes nothing at all.
* **What a rule grants is fixed.** It is drawn ticked and disabled,
  saying what grants it — there is no stored row behind it, so the
  square never offers a removal it could not do.
* None of it is money. Learning is free, and a gang still reconciles.
"""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import LedgerEntry
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.library.models import Power, Skill
from n26.tests.sandbox.actions import (
    adds,
    assign,
    create_category,
    create_collection,
    create_power,
    create_skill,
    create_subtype,
    found_gang,
    hire_with_option,
    learn,
    modifier,
    places,
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


@pytest.fixture
def wyrd(sets, tiers):
    """A subtype that reveals the powers, as a Primary set."""
    subtype = create_subtype("Wyrd")
    modifier(
        "A Wyrd's powers are Primary",
        targets_model(),
        places(sets["powers"], tiers["primary"]),
        carried_by=subtype,
    )
    return subtype


# --- Reading the page ------------------------------------------------------


def edit_url(miniature):
    return reverse("n26-edit-fighter", args=[miniature.pk])


def key_of(thing):
    return f"{thing._meta.label_lower}:{thing.pk}"


def box(page, thing):
    """One thing's box, as its attributes read.

    The whole tag, so an assertion about ticked or fixed is about *that*
    box: a page carrying a dozen of them is checked somewhere whatever
    the one under test says.
    """
    match = re.search(rf"<input[^>]*value=\"{re.escape(key_of(thing))}\"[^>]*>", page)
    assert match, f"no box for {thing} on the page"
    return match.group(0)


def offer_on(client, miniature):
    return client.get(edit_url(miniature)).context["skills"]


def named(offer):
    return {option.name for group in offer.groups for option in group.options}


def post_skills(client, miniature, *ticked, follow=False):
    """Save the skills form as a browser sends it: the act, and one entry
    per ticked box. Boxes left alone send nothing, which is the whole of
    how a browser says a thing was cleared."""
    return client.post(
        edit_url(miniature),
        {"act": "skills", "skills": [key_of(thing) for thing in ticked]},
        follow=follow,
    )


def card_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


def held_by(miniature):
    card = card_for(miniature)
    return [line.name for line in (*card.skills, *card.powers)]


# --- What is on it ---------------------------------------------------------


class TestWhatTheSquareShows:
    """The fighter's own view of their collections, tier by tier."""

    def test_it_lists_the_sets_their_grid_reaches(
        self, client, player, yolanda, library
    ):
        client.force_login(player)
        offer = offer_on(client, yolanda)

        assert [group.name for group in offer.groups] == ["Agility", "Savant"]
        assert "Catfall" in named(offer)  # Agility is Primary for her
        assert "Connected" in named(offer)  # Savant is Secondary

    def test_each_set_says_which_tier_it_is(self, client, player, yolanda, library):
        """The tiers are what the square is arranged by, and a set's name
        does not say which one it sits in."""
        client.force_login(player)
        offer = offer_on(client, yolanda)

        assert [(group.name, group.caption) for group in offer.groups] == [
            ("Agility", "Primary"),
            ("Savant", "Secondary"),
        ]

    def test_the_tier_the_unplaced_fall_into_stays_off_it(
        self, client, player, yolanda, library
    ):
        """Brawn is nobody's here, so the browse files it under the
        collection's fallback tier. That tier is not this fighter's grid,
        and a set another house was graded in is not theirs to take."""
        client.force_login(player)
        offer = offer_on(client, yolanda)

        assert [group.caption for group in offer.groups] == ["Primary", "Secondary"]
        assert "Bull Charge" not in named(offer)

    def test_a_placed_family_of_powers_ticks_like_a_skill_set(
        self, client, player, gang, gang_sister, wyrd, library
    ):
        """A tier holds whatever the content swept into it, so the square
        offers powers wherever a fighter's placements put them."""
        thalia = hire_with_option(gang, gang_sister, "Thalia")
        assign(wyrd, miniature=thalia)
        client.force_login(player)
        offer = offer_on(client, thalia)

        assert "Wyrd Powers" in [group.name for group in offer.groups]
        assert "Terrify (Double)" in named(offer)

    def test_powers_nobody_placed_are_not_on_it(self, client, player, yolanda, library):
        client.force_login(player)
        assert "Terrify (Double)" not in named(offer_on(client, yolanda))

    def test_what_she_already_knows_arrives_ticked(
        self, client, player, yolanda, library
    ):
        learn(yolanda, library["skills"]["Catfall"])
        client.force_login(player)
        page = client.get(edit_url(yolanda)).content.decode()

        assert "checked" in box(page, library["skills"]["Catfall"])
        assert "checked" not in box(page, library["skills"]["Dodge"])

    def test_a_model_nobody_graded_is_not_asked(
        self, client, player, gang, gridless, catalogue
    ):
        """No grid, no sets within reach — and a heading over an empty
        square would read as a list that failed to load."""
        nobody = hire_with_option(gang, gridless, "Nobody")
        client.force_login(player)
        response = client.get(edit_url(nobody))

        assert response.context["skills"] is None
        assert "Save skills" not in response.content.decode()

    def test_a_granted_skill_is_drawn_ticked_and_fixed(
        self, client, player, yolanda, sets, library
    ):
        """A rule gives it, so nothing stored is behind it: the box says
        what grants it and cannot be cleared, because the square must
        never offer a removal it could not do."""
        keen = create_subtype("Keen-eyed")
        modifier(
            "Keen-eyed knows how to fall",
            targets_model(),
            adds(library["skills"]["Catfall"]),
            carried_by=keen,
        )
        assign(keen, miniature=yolanda)
        client.force_login(player)
        page = client.get(edit_url(yolanda)).content.decode()

        drawn = box(page, library["skills"]["Catfall"])
        assert "checked" in drawn
        assert "disabled" in drawn
        assert 'title="From Keen-eyed"' in page

    def test_a_restricted_skill_keeps_its_place_with_a_note(
        self, client, player, yolanda, library
    ):
        """Inform, never police — the till's rule, on this square too."""
        from n26.tests.sandbox.actions import restrict_use

        restrict_use(library["skills"]["Catfall"], create_subtype("Walker"))
        client.force_login(player)
        offer = offer_on(client, yolanda)

        catfall = next(
            option
            for group in offer.groups
            for option in group.options
            if option.name == "Catfall"
        )
        assert "only" in catfall.detail

    def test_somebody_elses_model_has_no_page(self, client, yolanda, catalogue):
        client.force_login(User.objects.create_user("stranger", is_staff=True))
        assert client.get(edit_url(yolanda)).status_code == 404


# --- The press -------------------------------------------------------------


class TestSavingTheSquare:
    """The whole flow through the page an owner uses."""

    def test_a_ticked_skill_lands_on_the_card(
        self, client, player, gang, yolanda, library
    ):
        client.force_login(player)
        response = post_skills(client, yolanda, library["skills"]["Catfall"])

        assert response.status_code == 302
        assert response.url == edit_url(yolanda)
        assert "Catfall" in held_by(yolanda)
        assert_reconciled(gang)

    def test_a_ticked_power_lands_on_its_own_row(
        self, client, player, gang, gang_sister, wyrd, library
    ):
        thalia = hire_with_option(gang, gang_sister, "Thalia")
        assign(wyrd, miniature=thalia)
        client.force_login(player)
        post_skills(client, thalia, library["powers"]["Terrify"])

        card = card_for(thalia)
        assert [line.name for line in card.powers] == ["Terrify (Double)"]
        assert card.skills == []
        assert_reconciled(gang)

    def test_several_go_in_one_press(self, client, player, gang, yolanda, library):
        client.force_login(player)
        post_skills(
            client,
            yolanda,
            library["skills"]["Catfall"],
            library["skills"]["Connected"],
        )

        assert sorted(held_by(yolanda)) == ["Catfall", "Connected"]
        assert_reconciled(gang)

    def test_a_cleared_box_takes_the_skill_away(
        self, client, player, gang, yolanda, library
    ):
        """The row is archived rather than deleted — the ledger goes on
        saying she once had it — so what the card shows is what changed."""
        learn(yolanda, library["skills"]["Catfall"])
        client.force_login(player)
        post_skills(client, yolanda)

        assert held_by(yolanda) == []
        assert_reconciled(gang)

    def test_a_press_keeps_what_was_left_ticked(
        self, client, player, gang, yolanda, library
    ):
        """Two she knows and one box cleared: settling the whole list must
        not take away the one nobody touched."""
        learn(yolanda, library["skills"]["Catfall"])
        learn(yolanda, library["skills"]["Connected"])
        client.force_login(player)
        post_skills(client, yolanda, library["skills"]["Connected"])

        assert held_by(yolanda) == ["Connected"]
        assert_reconciled(gang)

    def test_a_second_copy_is_never_written(
        self, client, player, gang, yolanda, library
    ):
        """A duplicate skill means nothing in the game, and a card reading
        "Catfall, Catfall" is a bug however honestly each row was
        written."""
        learn(yolanda, library["skills"]["Catfall"])
        client.force_login(player)
        post_skills(client, yolanda, library["skills"]["Catfall"])

        assert held_by(yolanda) == ["Catfall"]
        assert_reconciled(gang)

    def test_a_granted_skill_survives_a_save_untouched(
        self, client, player, gang, yolanda, library
    ):
        """Its box is fixed, so a browser submits nothing for it. Reading
        that silence as a clearing would take away the row of anything a
        rule also grants — so grants sit outside the difference."""
        keen = create_subtype("Keen-eyed")
        modifier(
            "Keen-eyed knows how to fall",
            targets_model(),
            adds(library["skills"]["Catfall"]),
            carried_by=keen,
        )
        assign(keen, miniature=yolanda)
        client.force_login(player)
        post_skills(client, yolanda, library["skills"]["Connected"])

        assert sorted(held_by(yolanda)) == ["Catfall", "Connected"]
        assert_reconciled(gang)

    def test_a_press_naming_something_off_the_list_writes_nothing(
        self, client, player, gang, yolanda, library
    ):
        """Brawn is nobody's here, so it is not on her square — and the
        press is answered by the list rather than by the ledger."""
        client.force_login(player)
        post_skills(client, yolanda, library["skills"]["Bull Charge"])

        assert held_by(yolanda) == []
        assert_reconciled(gang)

    def test_a_skill_from_a_set_no_longer_reached_is_left_alone(
        self, client, player, gang, gang_sister, wyrd, library
    ):
        """What is not offered cannot have been cleared. A power learned
        while a subtype revealed the family keeps its row once the subtype
        goes: an earned thing is nobody's consequence."""
        from n26.tests.sandbox.actions import remove

        thalia = hire_with_option(gang, gang_sister, "Thalia")
        badge = assign(wyrd, miniature=thalia)
        learn(thalia, library["powers"]["Terrify"])
        remove(badge)

        client.force_login(player)
        post_skills(client, thalia)

        assert held_by(thalia) == ["Terrify (Double)"]
        assert_reconciled(gang)

    def test_the_page_says_what_moved(self, client, player, yolanda, library):
        client.force_login(player)
        response = post_skills(
            client, yolanda, library["skills"]["Catfall"], follow=True
        )

        assert "Yolanda learned Catfall." in response.content.decode()

    def test_saving_the_notes_leaves_the_skills_alone(
        self, client, player, gang, yolanda, library
    ):
        """Three forms on one page: pressing one must not clear another's
        answers."""
        client.force_login(player)
        post_skills(client, yolanda, library["skills"]["Catfall"])
        client.post(edit_url(yolanda), {"act": "notes", "notes": "<p>Owes Kaine.</p>"})

        assert held_by(yolanda) == ["Catfall"]
        assert_reconciled(gang)

    def test_a_stranger_cannot_tick_anything(self, client, gang, yolanda, library):
        client.force_login(User.objects.create_user("someone-else", is_staff=True))
        response = post_skills(client, yolanda, library["skills"]["Catfall"])

        assert response.status_code == 404
        assert held_by(yolanda) == []
        assert_reconciled(gang)

    def test_none_of_it_is_money(self, client, player, gang, yolanda, library):
        """Learning is earned rather than bought: no credits move, and a
        skill the rules hand out is worth nothing to the gang."""
        client.force_login(player)
        gang.refresh_from_db()
        before = (gang.rating, gang.credits)

        post_skills(
            client,
            yolanda,
            library["skills"]["Catfall"],
            library["skills"]["Connected"],
        )

        gang.refresh_from_db()
        assert (gang.rating, gang.credits) == before
        assert LedgerEntry.objects.filter(paid__gt=0).count() == 1  # the hire
        assert_reconciled(gang)


# --- The budget ------------------------------------------------------------


class TestTheQueryBudget:
    """The square is read with the model's own card, so a fighter who
    knows everything costs what one who knows nothing costs."""

    def test_the_page_costs_the_same_however_much_she_knows(
        self, client, player, gang, yolanda, sets, library
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(player)
        stock = [
            create_skill(f"Trick {index}", category=sets["agility"], position=index)
            for index in range(2, 10)
        ]

        def measure():
            with CaptureQueriesContext(connection) as captured:
                response = client.get(edit_url(yolanda))
                assert response.status_code == 200
                assert response.context["skills"] is not None
            return len(captured.captured_queries)

        for skill in stock[:2]:
            learn(yolanda, skill)
        # The first reading pays one-time caches that no later one does.
        measure()
        few = measure()

        for skill in stock[2:]:
            learn(yolanda, skill)
        many = measure()

        assert few == many, f"{few} queries knowing 2, {many} knowing 8"
        assert_reconciled(gang)
