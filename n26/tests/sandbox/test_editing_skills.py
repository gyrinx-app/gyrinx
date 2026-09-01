"""Ticking a model's skills and powers on their own page.

The skills screen selects one thing at a time, at its own address. This is
a box on the model's edit page instead: every skill and power the library
holds, ticked where they have it, settled in one click.

The rules this file pins:

* **The placements sort the list; they do not shorten it.** Two tabs
  draw the same options. The first holds the sets somebody placed in a
  tier for this model, plus any set they already hold something in, so
  what is theirs is what they see; the second holds every set the
  library has. A panel on the first searches what it leaves out, so
  both listings reach the whole library and which tab a save came from
  settles nothing.
* **What is offered can be taken away.** A skill from a set nobody
  placed can be cleared, which is only true because it is on the list.
* **Skills and powers alike.** A tier holds whatever the content swept
  into it, so a family of powers placed for a fighter ticks like a skill
  set does.
* **A tick selects and a cleared box takes away**, in one operation: a
  save that fails writes nothing at all.
* **What a rule grants is fixed.** It is drawn ticked and disabled,
  saying what grants it — there is no stored row behind it, so the
  square never offers a removal it could not do.
* **An open starting-skill question is answered only by a tick on that
  question's Choose list.** A Leader asking for a Primary skill is
  settled by Catfall, not by Connected. A Secondary tick is a standing
  selection and leaves the question open.
* None of it is money. Selecting is free, and a gang still reconciles.
"""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment, LedgerEntry
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.core.views.edit import ALL_SETS, OWN_SETS
from n26.library.models import Power, Skill
from n26.tests.sandbox.actions import (
    adds,
    assign,
    choose,
    create_category,
    create_collection,
    create_power,
    create_skill,
    create_subtype,
    found_gang,
    hire_with_option,
    modifier,
    offers_choice,
    places,
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


def at_tab(miniature, tab=""):
    return edit_url(miniature) + (f"?skills={tab}" if tab else "")


def offer_on(client, miniature, tab=""):
    """The listing the box draws, on whichever tab the address names."""
    return client.get(at_tab(miniature, tab)).context["skills"]


def more_on(client, miniature, tab=""):
    """What the panel searches: the sets the drawn listing leaves out."""
    return client.get(at_tab(miniature, tab)).context["skills_more"]


def named(offer):
    return {option.name for group in offer.groups for option in group.options}


def post_skills(client, miniature, *ticked, follow=False, tab=""):
    """Save the skills form as a browser sends it: the act, and one entry
    per ticked box. Boxes left alone send nothing, which is the whole of
    how a browser says a thing was cleared."""
    sent = {"act": "skills", "skills": [key_of(thing) for thing in ticked]}
    if tab:
        sent["tab"] = tab
    return client.post(edit_url(miniature), sent, follow=follow)


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
        select(yolanda, library["skills"]["Catfall"])
        client.force_login(player)
        page = client.get(edit_url(yolanda)).content.decode()

        assert "checked" in box(page, library["skills"]["Catfall"])
        assert "checked" not in box(page, library["skills"]["Dodge"])

    def test_a_model_no_placement_names_is_asked_about_every_set(
        self, client, player, gang, gridless, catalogue, library
    ):
        """Nobody has put a set in a tier for them. That is a gap in the
        content, not a rule about the model: the library is still theirs
        to take from, so the box opens on the listing holding every set
        and says why the other one is bare."""
        nobody = hire_with_option(gang, gridless, "Nobody")
        client.force_login(player)
        response = client.get(edit_url(nobody))

        assert response.context["skills_tab"] == ALL_SETS
        assert "Bull Charge" in named(response.context["skills"])
        assert "Save skills" in response.content.decode()

    def test_their_own_listing_says_when_no_set_is_theirs(
        self, client, player, gang, gridless, catalogue, library
    ):
        """Asked for the listing that is empty, the box draws it empty
        and says so, rather than sending the reader somewhere else."""
        nobody = hire_with_option(gang, gridless, "Nobody")
        client.force_login(player)
        page = client.get(at_tab(nobody, OWN_SETS)).content.decode()

        assert "No skill set has been put in a tier for Nobody." in page

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

    def test_a_granted_skill_reads_without_a_space_before_its_comma(
        self, client, player, yolanda, library
    ):
        """A granted skill's name sits inside a tooltip component that
        carries line breaks of its own; the run joining it to the next
        skill must swallow those, not let one land beside the comma as a
        visible gap before the mark. The two separators differ on
        purpose: a granted skill's comma rides inside its tooltip
        trigger with a non-breaking space, and a plain skill's comma is
        followed by a breaking one so the run can wrap between names."""
        keen = create_subtype("Keen-eyed")
        modifier(
            "Keen-eyed knows how to fall",
            targets_model(),
            adds(library["skills"]["Catfall"]),
            carried_by=keen,
        )
        assign(keen, miniature=yolanda)
        select(yolanda, library["skills"]["Connected"])
        select(yolanda, library["skills"]["Dodge"])
        client.force_login(player)
        page = client.get(edit_url(yolanda)).content.decode()

        start = page.index(">Skills<")
        row = page[start : page.index(">Gear<", start)]
        assert " ," not in row
        # Catfall (granted) sorts first: its comma is the trigger's own.
        assert ",&nbsp;" in row
        # Connected (plain) is next: its comma allows a wrap after it.
        assert "<span>, </span>" in row
        assert "Catfall" in row and "Connected" in row and "Dodge" in row

    def test_a_restricted_skill_keeps_its_place_with_a_note(
        self, client, player, yolanda, library
    ):
        """Inform, never police — the equip page's rule, on this square too."""
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
        client.force_login(User.objects.create_user("stranger"))
        assert client.get(edit_url(yolanda)).status_code == 404


# --- The sets that are not theirs ------------------------------------------


class TestTheRestOfTheLibrary:
    """Every set is reachable from the box, one tab or one search away."""

    def test_the_other_tab_lists_the_sets_nobody_placed(
        self, client, player, yolanda, library
    ):
        """Brawn is nobody's here, so it is not among her own sets — but
        it is a set the game has, and the second listing holds it."""
        client.force_login(player)

        assert "Bull Charge" not in named(offer_on(client, yolanda, OWN_SETS))
        assert "Bull Charge" in named(offer_on(client, yolanda, ALL_SETS))

    def test_the_other_tab_keeps_the_sets_that_are_theirs(
        self, client, player, yolanda, library
    ):
        """The wider listing is the whole library, not the remainder of
        it: a reader who switches tabs to find one skill does not lose
        sight of what the model already has."""
        client.force_login(player)
        offer = offer_on(client, yolanda, ALL_SETS)

        assert {"Catfall", "Connected", "Bull Charge"} <= named(offer)

    def test_each_set_says_its_tier_on_the_wider_listing(
        self, client, player, yolanda, sets, tiers, library
    ):
        """A set nobody placed is filed under the collection's own
        default tier, and says so, so the reader can tell the two that
        are theirs from the rest without counting headings."""
        client.force_login(player)
        tier = {
            group.name: group.caption
            for group in offer_on(client, yolanda, ALL_SETS).groups
        }

        assert tier["Agility"] == "Primary"
        assert tier["Savant"] == "Secondary"
        assert tier["Brawn"] == "Other"

    def test_the_panel_searches_what_their_own_listing_leaves_out(
        self, client, player, yolanda, library
    ):
        """The first tab is not a dead end: the sets it does not draw
        are the ones its search offers, so a skill can be added without
        leaving it."""
        client.force_login(player)
        offered = {option.name for option in more_on(client, yolanda, OWN_SETS)}

        assert "Bull Charge" in offered
        assert "Catfall" not in offered

    def test_the_wider_listing_needs_no_panel(self, client, player, yolanda, library):
        """Everything is already a box there, and a search offering what
        is drawn a few lines above would be a second way to do the same
        thing."""
        client.force_login(player)

        assert more_on(client, yolanda, ALL_SETS) == []

    def test_a_skill_from_another_set_can_be_selected(
        self, client, player, gang, yolanda, library
    ):
        """The whole of the ask: a skill nobody placed for her, ticked
        and saved from the page she was already on."""
        client.force_login(player)
        post_skills(client, yolanda, library["skills"]["Bull Charge"], tab=ALL_SETS)

        assert held_by(yolanda) == ["Bull Charge"]
        assert_reconciled(gang)

    def test_a_skill_from_another_set_can_be_cleared_again(
        self, client, player, gang, yolanda, library
    ):
        """And the other half of it, which the narrower listing could
        not do at all: what was selected can be taken away."""
        select(yolanda, library["skills"]["Bull Charge"])
        client.force_login(player)
        post_skills(client, yolanda, tab=ALL_SETS)

        assert held_by(yolanda) == []
        assert_reconciled(gang)

    def test_a_set_they_hold_something_in_is_drawn_among_their_own(
        self, client, player, yolanda, library
    ):
        """Held, so it is theirs whatever the placements say — and it is
        drawn where they will look for it rather than a tab away, since
        the reader wanting to clear it is looking at what she has."""
        select(yolanda, library["skills"]["Bull Charge"])
        client.force_login(player)
        offer = offer_on(client, yolanda, OWN_SETS)

        assert "Brawn" in [group.name for group in offer.groups]
        assert "Bull Charge" in named(offer)

    def test_a_held_set_is_not_offered_twice(self, client, player, yolanda, library):
        """Drawn among their own, it is off the panel: a box and a
        search row for the same skill would be two controls settling one
        thing."""
        select(yolanda, library["skills"]["Bull Charge"])
        client.force_login(player)
        offered = {option.name for option in more_on(client, yolanda, OWN_SETS)}

        assert "Bull Charge" not in offered
        assert "Terrify (Double)" in offered

    def test_a_save_comes_back_to_the_tab_it_was_made_from(
        self, client, player, yolanda, library
    ):
        client.force_login(player)
        response = post_skills(
            client, yolanda, library["skills"]["Bull Charge"], tab=ALL_SETS
        )

        assert response.status_code == 302
        assert response["Location"] == at_tab(yolanda, ALL_SETS)

    def test_a_subtype_in_a_collection_is_not_on_the_listing(
        self, client, player, gang, yolanda, sets, tiers, catalogue, library
    ):
        """A subtype is the same family as a skill, so a collection may
        hold one and this box would otherwise offer it — and a save that
        left it unticked would take it away, by the write that archives
        a selection rather than the one that records an owner's edit,
        and from a box whose heading says skills.

        What a model is belongs to the edits box beside this one, so
        only skills and powers are on the list here.
        """
        from n26.library.authoring import add_entry

        badge = create_subtype("Hardened")
        add_entry(catalogue, badge)
        assign(badge, miniature=yolanda)
        client.force_login(player)

        assert "Hardened" not in named(offer_on(client, yolanda, ALL_SETS))

        post_skills(client, yolanda, tab=ALL_SETS)

        assert "Hardened" in [line.name for line in card_for(yolanda).subtypes]
        assert_reconciled(gang)

    def test_a_stranger_cannot_reach_the_wider_listing_either(
        self, client, yolanda, library
    ):
        client.force_login(User.objects.create_user("interloper"))
        assert client.get(at_tab(yolanda, ALL_SETS)).status_code == 404


# --- The click -------------------------------------------------------------


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

    def test_several_go_in_one_click(self, client, player, gang, yolanda, library):
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
        select(yolanda, library["skills"]["Catfall"])
        client.force_login(player)
        post_skills(client, yolanda)

        assert held_by(yolanda) == []
        assert_reconciled(gang)

    def test_a_click_keeps_what_was_left_ticked(
        self, client, player, gang, yolanda, library
    ):
        """Two she knows and one box cleared: settling the whole list must
        not take away the one nobody touched."""
        select(yolanda, library["skills"]["Catfall"])
        select(yolanda, library["skills"]["Connected"])
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
        select(yolanda, library["skills"]["Catfall"])
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

    def test_a_click_naming_something_off_the_list_writes_nothing(
        self, client, player, gang, yolanda, wyrd, library
    ):
        """The listing holds what the collection sweeps, which here is
        skills and powers. A click naming anything else — a subtype — is
        answered by the list rather than by the ledger."""
        client.force_login(player)
        post_skills(client, yolanda, wyrd)

        assert held_by(yolanda) == []
        assert_reconciled(gang)

    def test_a_power_from_a_set_nothing_places_can_be_cleared(
        self, client, player, gang, gang_sister, wyrd, library
    ):
        """Every set is on the listing, so a power selected while a
        subtype placed its family is still offered once the subtype
        goes — and what is offered can be taken away.

        The price of that is on show here: an empty save clears it, the
        way an empty save clears whatever it does not name. A stale form
        therefore reaches the whole library rather than one corner of
        it, which is what being able to remove a skill nobody placed
        costs."""
        from n26.tests.sandbox.actions import remove

        thalia = hire_with_option(gang, gang_sister, "Thalia")
        badge = assign(wyrd, miniature=thalia)
        select(thalia, library["powers"]["Terrify"])
        remove(badge)

        client.force_login(player)
        assert "Terrify (Double)" in named(offer_on(client, thalia))

        post_skills(client, thalia)

        assert held_by(thalia) == []
        assert_reconciled(gang)

    def test_the_page_says_what_moved(self, client, player, yolanda, library):
        client.force_login(player)
        response = post_skills(
            client, yolanda, library["skills"]["Catfall"], follow=True
        )

        assert "Yolanda selected Catfall." in response.content.decode()

    def test_saving_the_notes_leaves_the_skills_alone(
        self, client, player, gang, yolanda, library
    ):
        """Three forms on one page: clicking one must not clear another's
        answers."""
        client.force_login(player)
        post_skills(client, yolanda, library["skills"]["Catfall"])
        client.post(edit_url(yolanda), {"act": "notes", "notes": "<p>Owes Kaine.</p>"})

        assert held_by(yolanda) == ["Catfall"]
        assert_reconciled(gang)

    def test_a_stranger_cannot_tick_anything(self, client, gang, yolanda, library):
        client.force_login(User.objects.create_user("someone-else"))
        response = post_skills(client, yolanda, library["skills"]["Catfall"])

        assert response.status_code == 404
        assert held_by(yolanda) == []
        assert_reconciled(gang)

    def test_none_of_it_is_money(self, client, player, gang, yolanda, library):
        """A selection is earned rather than bought: no credits move, and a
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


# --- An open starting-skill question ---------------------------------------


def _live_skill(miniature, skill):
    return miniature.assignments.get(skill=skill, archived=False)


class TestAnOpenStartingSkill:
    """While the card still asks, a tick on that question's Choose list
    is the starting skill. A Secondary skill is not Primary, so it does
    not close the question."""

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

    def test_ticking_a_primary_skill_answers_the_question(
        self, client, player, gang, leader_yolanda, library
    ):
        catfall = library["skills"]["Catfall"]
        client.force_login(player)
        post_skills(client, leader_yolanda, catfall)

        card = card_for(leader_yolanda)
        assert card.skill_choices == []
        assert "Catfall" in held_by(leader_yolanda)
        row = _live_skill(leader_yolanda, catfall)
        assert row.chosen_for_offer_id is not None
        assert row.caused_by_id is not None
        assert_reconciled(gang)

    def test_replacing_the_starting_skill_keeps_the_question_closed(
        self, client, player, gang, leader_yolanda, library
    ):
        """Choose Catfall, then Edit to Dodge: the new tick is the
        starting skill, not a second one beside a reopened prompt."""
        catfall = library["skills"]["Catfall"]
        dodge = library["skills"]["Dodge"]
        choose(
            leader_yolanda.assignments.get(subtype__name="Leader"),
            catfall,
        )
        client.force_login(player)
        post_skills(client, leader_yolanda, dodge)

        card = card_for(leader_yolanda)
        assert card.skill_choices == []
        assert held_by(leader_yolanda) == ["Dodge"]
        row = _live_skill(leader_yolanda, dodge)
        assert row.chosen_for_offer_id is not None
        assert row.caused_by_id is not None
        assert not Assignment.objects.filter(
            miniature_root=leader_yolanda, skill=catfall, archived=False
        ).exists()
        assert_reconciled(gang)

    def test_a_secondary_tick_does_not_answer_the_question(
        self, client, player, gang, leader_yolanda, library
    ):
        """Connected is on the edit square (Savant is Secondary) but not
        on the Choose page for a Primary skill."""
        connected = library["skills"]["Connected"]
        client.force_login(player)
        post_skills(client, leader_yolanda, connected)

        card = card_for(leader_yolanda)
        assert [line.kind_label for line in card.skill_choices] == ["Primary skill"]
        assert held_by(leader_yolanda) == ["Connected"]
        row = _live_skill(leader_yolanda, connected)
        assert row.chosen_for_offer_id is None
        assert row.caused_by_id is None
        assert_reconciled(gang)

    def test_a_primary_tick_answers_and_a_secondary_tick_is_extra(
        self, client, player, gang, leader_yolanda, library
    ):
        catfall = library["skills"]["Catfall"]
        connected = library["skills"]["Connected"]
        client.force_login(player)
        post_skills(client, leader_yolanda, catfall, connected)

        card = card_for(leader_yolanda)
        assert card.skill_choices == []
        assert sorted(held_by(leader_yolanda)) == ["Catfall", "Connected"]
        starting = _live_skill(leader_yolanda, catfall)
        extra = _live_skill(leader_yolanda, connected)
        assert starting.chosen_for_offer_id is not None
        assert extra.chosen_for_offer_id is None
        assert extra.caused_by_id is None
        assert_reconciled(gang)

    def test_clearing_the_starting_skill_reopens_the_question(
        self, client, player, gang, leader_yolanda, library
    ):
        catfall = library["skills"]["Catfall"]
        choose(
            leader_yolanda.assignments.get(subtype__name="Leader"),
            catfall,
        )
        client.force_login(player)
        post_skills(client, leader_yolanda)

        card = card_for(leader_yolanda)
        assert [line.kind_label for line in card.skill_choices] == ["Primary skill"]
        assert held_by(leader_yolanda) == []
        assert_reconciled(gang)

    def test_keeping_the_starting_skill_and_ticking_another_selects_the_extra(
        self, client, player, gang, leader_yolanda, library
    ):
        catfall = library["skills"]["Catfall"]
        dodge = library["skills"]["Dodge"]
        choose(
            leader_yolanda.assignments.get(subtype__name="Leader"),
            catfall,
        )
        client.force_login(player)
        post_skills(client, leader_yolanda, catfall, dodge)

        card = card_for(leader_yolanda)
        assert card.skill_choices == []
        assert sorted(held_by(leader_yolanda)) == ["Catfall", "Dodge"]
        starting = _live_skill(leader_yolanda, catfall)
        extra = _live_skill(leader_yolanda, dodge)
        assert starting.chosen_for_offer_id is not None
        assert extra.chosen_for_offer_id is None
        assert extra.caused_by_id is None
        assert_reconciled(gang)

    def test_one_new_matching_skill_answers_and_further_ticks_are_ordinary(
        self, client, player, gang, leader_yolanda, library
    ):
        catfall = library["skills"]["Catfall"]
        dodge = library["skills"]["Dodge"]
        client.force_login(player)
        post_skills(client, leader_yolanda, catfall, dodge)

        card = card_for(leader_yolanda)
        assert card.skill_choices == []
        rows = [
            _live_skill(leader_yolanda, catfall),
            _live_skill(leader_yolanda, dodge),
        ]
        picks = [row for row in rows if row.chosen_for_offer_id is not None]
        extras = [row for row in rows if row.chosen_for_offer_id is None]
        assert len(picks) == 1
        assert len(extras) == 1
        assert extras[0].caused_by_id is None
        assert_reconciled(gang)

    def test_the_edit_page_stops_asking_once_a_primary_skill_is_ticked(
        self, client, player, leader_yolanda, library
    ):
        client.force_login(player)
        page = post_skills(
            client, leader_yolanda, library["skills"]["Catfall"], follow=True
        ).content.decode()

        assert "Choose primary skill" not in page
        assert "Catfall" in held_by(leader_yolanda)


class TestSwitchingTabs:
    """Which sets are listed is in the address, so a reload draws the
    same screen and a link points at one. With script the click is
    answered with the box alone; without it, with the page."""

    HTMX = {"HX-Request": "true"}

    def test_the_address_says_which_listing_is_open(
        self, client, player, yolanda, library
    ):
        client.force_login(player)
        page = client.get(at_tab(yolanda, ALL_SETS))

        assert page.status_code == 200
        assert page.context["skills_tab"] == ALL_SETS
        assert "<html" in page.content.decode()

    def test_an_address_naming_no_listing_opens_their_own(
        self, client, player, yolanda, library
    ):
        client.force_login(player)
        assert client.get(edit_url(yolanda)).context["skills_tab"] == OWN_SETS

    def test_an_address_naming_nonsense_opens_their_own(
        self, client, player, yolanda, library
    ):
        """A hand-typed address settles on the everyday listing rather
        than drawing nothing."""
        client.force_login(player)
        page = client.get(edit_url(yolanda) + "?skills=whatever")

        assert page.status_code == 200
        assert page.context["skills_tab"] == OWN_SETS

    def test_a_tab_clicked_with_script_is_answered_with_the_box(
        self, client, player, yolanda, library
    ):
        """Changing which sets are listed changes nothing else on the
        page, so nothing else is sent — and the answer says which
        element it replaces, because a click on a link targets none."""
        client.force_login(player)
        answer = client.get(at_tab(yolanda, ALL_SETS), headers=self.HTMX)
        body = answer.content.decode()

        assert answer.status_code == 200
        assert "<html" not in body
        assert 'id="n26-skills-box"' in body
        assert 'hx-swap-oob="true"' in body
        assert "Bull Charge" in body

    def test_the_answer_moves_the_address_to_the_tab_it_opened(
        self, client, player, yolanda, library
    ):
        """Replaced rather than pushed: a tab is not somewhere to go
        back to, but a reload must draw what is on screen."""
        client.force_login(player)
        answer = client.get(at_tab(yolanda, ALL_SETS), headers=self.HTMX)

        assert answer["HX-Replace-Url"] == at_tab(yolanda, ALL_SETS)

    def test_the_page_itself_is_never_answered_with_a_fragment(
        self, client, player, yolanda, library
    ):
        """Only a tab click is: the box is handed back for the act that
        changes it, and a page asked for as a whole is drawn whole
        however it was asked for."""
        client.force_login(player)
        body = client.get(edit_url(yolanda), headers=self.HTMX).content.decode()

        assert "<html" in body

    def test_the_same_address_without_script_draws_the_whole_page(
        self, client, player, yolanda, library
    ):
        client.force_login(player)
        body = client.get(at_tab(yolanda, ALL_SETS)).content.decode()

        assert "<html" in body
        assert 'id="n26-skills-box"' in body
        assert "Bull Charge" in body

    def test_the_tabs_are_links_that_script_turns_into_clicks(
        self, client, player, yolanda, library
    ):
        """An ordinary href, so the tab works with no script and can be
        opened in another window; the htmx attribute beside it is what
        makes the click stay on the page."""
        client.force_login(player)
        body = client.get(edit_url(yolanda)).content.decode()

        assert f'href="{at_tab(yolanda, ALL_SETS)}"' in body
        assert f'hx-get="{at_tab(yolanda, ALL_SETS)}"' in body

    def test_the_form_says_which_listing_drew_it(
        self, client, player, yolanda, library
    ):
        client.force_login(player)
        body = client.get(at_tab(yolanda, ALL_SETS)).content.decode()

        assert f'name="tab" value="{ALL_SETS}"' in body


class TestTheQueryBudget:
    """The square is read with the model's own card, so a fighter who
    knows everything costs what one who knows nothing costs."""

    def test_which_tab_is_open_costs_nothing(
        self, client, player, yolanda, sets, library
    ):
        """One derivation serves both listings, so the tab only picks
        which of its shapes reaches the template.

        This says nothing about what the widening itself costs — the
        listing below is what pins that.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(player)

        def measure(tab):
            with CaptureQueriesContext(connection) as captured:
                assert client.get(at_tab(yolanda, tab)).status_code == 200
            return len(captured.captured_queries)

        # The first reading pays one-time caches that no later one does.
        measure(OWN_SETS)
        theirs = measure(OWN_SETS)
        assert measure(ALL_SETS) == theirs

    def test_the_listing_costs_the_same_however_big_the_library(
        self, client, player, yolanda, sets, library
    ):
        """What a collection holds is asked in a fixed number of
        queries, so widening the offer to every set is paid per
        collection and never per skill. A library that doubles asks
        the database exactly as much.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(player)

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert client.get(at_tab(yolanda, ALL_SETS)).status_code == 200
            return len(captured.captured_queries)

        measure()
        small = measure()
        for index in range(2, 30):
            create_skill(f"Trick {index}", category=sets["brawn"], position=index)

        assert measure() == small

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
            select(yolanda, skill)
        # The first reading pays one-time caches that no later one does.
        measure()
        few = measure()

        for skill in stock[2:]:
            select(yolanda, skill)
        many = measure()

        assert few == many, f"{few} queries knowing 2, {many} knowing 8"
        assert_reconciled(gang)


def _gang_url(gang):
    return reverse("n26-gang", args=[gang.pk])


def _skills_url(miniature):
    return reverse("n26-select", args=[miniature.pk])


def _select_views():
    """The select *module* — ``n26.core.views.select`` is the view function
    on the package, which shadows the submodule for a normal import."""
    import importlib

    return importlib.import_module("n26.core.views.select")


class TestAnsweringDoesNotTouchTheReadPath:
    """The Choose-list match is a write. Drawing the sheet, the edit
    page or the skills screen must not browse that list to decide what
    to show."""

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

    def test_reading_the_edit_page_does_not_build_the_choose_list(
        self, client, player, leader_yolanda, monkeypatch
    ):
        select_views = _select_views()

        calls = []
        monkeypatch.setattr(
            select_views,
            "_offered_keys",
            lambda *args, **kwargs: calls.append(1) or frozenset(),
        )
        client.force_login(player)
        assert client.get(edit_url(leader_yolanda)).status_code == 200
        assert calls == []

    def test_reading_the_gang_sheet_does_not_build_the_choose_list(
        self, client, player, leader_yolanda, monkeypatch
    ):
        select_views = _select_views()

        calls = []
        monkeypatch.setattr(
            select_views,
            "_offered_keys",
            lambda *args, **kwargs: calls.append(1) or frozenset(),
        )
        client.force_login(player)
        assert client.get(_gang_url(leader_yolanda.gang)).status_code == 200
        assert calls == []

    def test_reading_the_skills_screen_does_not_build_the_choose_list(
        self, client, player, leader_yolanda, monkeypatch
    ):
        select_views = _select_views()

        calls = []
        monkeypatch.setattr(
            select_views,
            "_offered_keys",
            lambda *args, **kwargs: calls.append(1) or frozenset(),
        )
        client.force_login(player)
        assert client.get(_skills_url(leader_yolanda)).status_code == 200
        assert calls == []

    def test_saving_a_tick_builds_the_choose_list_once(
        self, client, player, leader_yolanda, library, monkeypatch
    ):
        select_views = _select_views()

        real = select_views._offered_keys
        calls = []

        def counted(*args, **kwargs):
            result = real(*args, **kwargs)
            calls.append(result)
            return result

        monkeypatch.setattr(select_views, "_offered_keys", counted)
        client.force_login(player)
        post_skills(client, leader_yolanda, library["skills"]["Catfall"])
        assert len(calls) == 1

    def test_the_choose_list_lookup_does_not_grow_with_skills_already_held(
        self, client, player, leader_yolanda, sets, library, monkeypatch
    ):
        """One browse of the offer, not one query per skill on the card."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        select_views = _select_views()

        real = select_views._offered_keys
        counts = []

        def wrapped(*args, **kwargs):
            with CaptureQueriesContext(connection) as captured:
                result = real(*args, **kwargs)
            counts.append(len(captured.captured_queries))
            return result

        monkeypatch.setattr(select_views, "_offered_keys", wrapped)
        extras = [
            create_skill(f"Trick {index}", category=sets["agility"], position=index)
            for index in range(10, 18)
        ]
        client.force_login(player)

        post_skills(client, leader_yolanda, library["skills"]["Connected"])
        few = counts[-1]
        counts.clear()

        post_skills(
            client,
            leader_yolanda,
            library["skills"]["Connected"],
            *extras,
        )
        many = counts[-1]

        assert few == many, f"{few} queries holding 1, {many} holding 9"
        assert few > 0

    def test_the_gang_sheet_stays_flat_as_leaders_accumulate(
        self, client, player, gang, gang_sister, leader, monkeypatch
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        select_views = _select_views()

        calls = []
        monkeypatch.setattr(
            select_views,
            "_offered_keys",
            lambda *args, **kwargs: calls.append(1) or frozenset(),
        )
        client.force_login(player)

        first = hire_with_option(gang, gang_sister, "Leader 0")
        assign(leader, miniature=first)

        def measure():
            with CaptureQueriesContext(connection) as captured:
                response = client.get(_gang_url(gang))
                assert response.status_code == 200
            return len(captured.captured_queries)

        measure()
        few = measure()
        for index in range(1, 5):
            fighter = hire_with_option(gang, gang_sister, f"Leader {index}")
            assign(leader, miniature=fighter)
        many = measure()

        assert calls == []
        assert few == many, f"{few} queries for 1 Leader, {many} for 5"
