"""Collection-based gang hire lists and archetype swaps.

Escher and Chem Cults use different fighter lists and prices. These tests
cover choosing the archetype, hiring from its list, equipment-list swaps,
visibility, section grouping, and gang-sheet rendering.

Design: `design/collections.md`.
"""

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.access import collections_for, gang_collections
from n26.core.card import build_gang_card, build_modifier_index
from n26.core.effects import compute_gang
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_gang, roster
from n26.core.render_text import render_gang_sheet
from n26.core.views.equip import buyable_lists
from n26.library.models import Profile
from n26.tests.sandbox.actions import (
    add_built_in,
    add_entry,
    assign,
    choose,
    create_category,
    create_collection,
    create_gang_type,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    create_wargear,
    ef_adds,
    ef_removes,
    found_gang,
    hire,
    is_profile,
    modifier,
    section_of,
    targets_every_model,
    targets_gang,
    targets_gang_alone,
)

pytestmark = pytest.mark.django_db

#: The house's fighter entries: what each is called, what it costs, and
#: which of the gang list's headings it prints under. Pinned as a table
#: so a reader can see at a glance which of them each list keeps.
ESCHER = [
    ("Queen", 145, "Leader"),
    ("Matriarch", 120, "Champion"),
    ("Death-Maiden", 115, "Champion"),
    ("Gang Sister", 55, "Ganger"),
    ("Chem Wytch", 60, "Ganger"),
]

#: Vanilla Escher's list. Chem Wytch is authored under the house — she is
#: an Escher fighter, printed in the Escher pages — and simply is not on
#: the list an ordinary Escher gang hires from.
HOUSE_LIST = ["Queen", "Matriarch", "Death-Maiden", "Gang Sister"]

#: The Chem Cults list. Two entries it shares with the house, one it
#: alone offers, and two of the house's it drops.
CHEM_LIST = ["Death-Maiden", "Gang Sister", "Chem Wytch"]

#: What a Chem Cult pays for a Death-Maiden, where the house pays 115.
CHEM_MAIDEN_PRICE = 130


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def headings(db):
    """The gang list's own headings — Leader, Champion, Ganger — so the
    sections a reader sees are the taxonomy's and not this test's."""
    return {
        name: create_category("Gang List", name, position=position)
        for position, name in enumerate(["Leader", "Champion", "Ganger"])
    }


@pytest.fixture
def escher(db):
    return create_gang_type("Escher", starting_credits=1000)


@pytest.fixture
def equipment(db):
    """Three equipment lists: the house's, the archetype's, and the one
    the archetype gives its Death-Maidens alone.

    Each holds a piece of gear, because a buying screen offers a
    collection for what it contains: a list holding nothing to buy is
    not somewhere to buy from, however it was come by.
    """
    made = {}
    for key, name, gear in [
        ("house", "Escher Equipment List", "Mesh armour"),
        ("chem", "Chem Cults Equipment List", "Chem-thrower"),
        ("maiden", "Chem Cults Death-Maiden Equipment List", "Chem-blade"),
    ]:
        collection = create_collection(name)
        add_entry(collection, create_wargear(gear, price=20))
        made[key] = collection
    return made


@pytest.fixture
def profiles(escher, headings, person_type, make_statline, equipment):
    """Every Escher fighter entry, each carrying the house equipment list
    in its built-ins — the way a house list reaches a fighter."""
    made = {}
    for name, price, heading in ESCHER:
        profile = create_profile(
            name, person_type, escher, price=price, category=headings[heading]
        )
        make_statline(profile, movement=5, weapon_skill=3, toughness=3)
        add_built_in(profile, equipment["house"])
        made[name] = profile
    return made


@pytest.fixture
def house_list(profiles):
    """The gang list the house comes with: a collection of its fighter
    entries whose default section is "Gang List", which is what files its
    fighters as the gang's list rather than as a roster the gang took on."""
    collection = create_collection("Escher Gang List")
    section_of(collection, "Gang List", 0, is_default=True)
    for name in HOUSE_LIST:
        add_entry(collection, profiles[name])
    return collection


@pytest.fixture
def chem_list(profiles):
    """The Chem Cults list, which prices its Death-Maiden its own way."""
    collection = create_collection("Chem Cults Gang List")
    section_of(collection, "Gang List", 0, is_default=True)
    for name in CHEM_LIST:
        add_entry(
            collection,
            profiles[name],
            **({"price_override": CHEM_MAIDEN_PRICE} if name == "Death-Maiden" else {}),
        )
    return collection


@pytest.fixture
def house(escher, house_list, equipment):
    """What founding an Escher gang brings: its list of fighters and its
    equipment list, both built into the gang type."""
    add_built_in(escher, house_list)
    modifier(
        "Escher, the gang alone: adds Escher Equipment List",
        targets_gang_alone(),
        ef_adds(equipment["house"]),
        carried_by=escher,
    )
    return escher


@pytest.fixture
def archetype_slot(db):
    """The question a house asks: which archetype, or none. Optional, at
    most one, and answered by the gang rather than by any one fighter."""
    slot_type = create_slot_type("Gang Archetype", allows_repeats=False)
    chem = create_pickable("Chem Cults", slot_type)
    picklist = create_picklist("Escher Gang Archetypes", slot_type, members=[chem])
    slot = create_slot(
        "Gang Archetype",
        slot_type,
        picklist,
        label="Gang Archetype",
        min_picks=0,
        max_picks=1,
        assigned_to="gang",
    )
    return {"pickable": chem, "slot": slot}


@pytest.fixture
def chem_cults(house, archetype_slot, chem_list, house_list, equipment, profiles):
    """The Chem Cults archetype, written out in full.

    Eight rows, in three pairs and a pair: the list it hires from, the
    list the gang itself buys from, the list its fighters buy from, and
    the one its Death-Maidens buy from instead. Each pair takes one
    collection away and gives another, which is the whole of an
    archetype.
    """
    pickable = archetype_slot["pickable"]
    modifier(
        "Escher: the gang is asked its Gang Archetype",
        targets_gang(),
        ef_adds(archetype_slot["slot"]),
        carried_by=house,
    )
    maiden = is_profile(profiles["Death-Maiden"])
    for name, scope, effect in [
        (
            "the gang stops hiring from the Escher list",
            targets_gang_alone(),
            ef_removes(house_list),
        ),
        (
            "the gang hires from the Chem Cults list",
            targets_gang_alone(),
            ef_adds(chem_list),
        ),
        (
            "the gang stops buying from the Escher list",
            targets_gang_alone(),
            ef_removes(equipment["house"]),
        ),
        (
            "the gang buys from the Chem Cults list",
            targets_gang_alone(),
            ef_adds(equipment["chem"]),
        ),
        (
            "its fighters stop buying from the Escher list",
            targets_every_model(),
            ef_removes(equipment["house"]),
        ),
        (
            "its fighters buy from the Chem Cults list",
            targets_every_model(),
            ef_adds(equipment["chem"]),
        ),
        (
            "its Death-Maidens stop buying from the Chem Cults list",
            targets_every_model(maiden),
            ef_removes(equipment["chem"]),
        ),
        (
            "its Death-Maidens buy from their own list",
            targets_every_model(is_profile(profiles["Death-Maiden"])),
            ef_adds(equipment["maiden"]),
        ),
    ]:
        modifier(f"Chem Cults: {name}", scope, effect, carried_by=pickable)
    return pickable


@pytest.fixture
def gang(house, owner):
    return found_gang("The Ashen Choir", house, owner=owner, budget=2000)


def hire_url(gang):
    return reverse("n26-hire-fighter", args=[gang.pk])


def screen(client, gang, owner):
    client.force_login(owner)
    return client.get(hire_url(gang))


def offered(response):
    """Every fighter the screen offers, by the heading it is filed under."""
    return {
        (section.name, category.name): [entry.name for entry in category.entries]
        for section in response.context["hire_list"]
        for category in section.categories
    }


def offered_names(response):
    return sorted(
        entry.name
        for section in response.context["hire_list"]
        for entry in section.all_entries()
    )


def sections_of(response):
    return [section.name for section in response.context["hire_list"]]


def row(response, name):
    return next(
        entry
        for section in response.context["hire_list"]
        for entry in section.all_entries()
        if entry.name == name
    )


def take_the_archetype(gang, pickable):
    """Answer the gang's own open question, as the picker's press does."""
    card = build_gang_card(gang, with_statlines=False)
    computed = compute_gang(
        card, build_modifier_index([node.assignable for node in card.all_nodes()])
    )
    asked = next(
        choice for choice in computed.choices if choice.kind_label == "Gang Archetype"
    )
    return choose(asked.anchor.assignment, pickable, slot=asked.slot)


def lists_for(miniature):
    """What this fighter may buy from, as the equip screen decides it.

    Not every collection a fighter carries is somewhere to buy kit: a
    gang list is a list of fighters, and the screens ask what a
    collection *holds* rather than how it was come by. So the gang list
    riding a member's card never offers itself as somewhere to buy kit.
    """
    return sorted(
        str(collection)
        for collection in buyable_lists(
            access.collection for access in collections_for(miniature)
        )
    )


def gang_lists_for(gang):
    return sorted(access.name for access in gang_collections(gang))


class TestTheListAGangCarries:
    """A gang hires from the list it carries, and the screen draws that
    list as its own — not as a section named after a collection."""

    def test_the_house_list_arrives_with_the_gang_type(self, client, owner, gang):
        response = screen(client, gang, owner)
        assert offered_names(response) == sorted(HOUSE_LIST)

    def test_its_fighters_sit_under_the_headings_the_taxonomy_gives(
        self, client, owner, gang
    ):
        response = screen(client, gang, owner)
        assert offered(response) == {
            ("Gang List", "Leader"): ["Queen"],
            ("Gang List", "Champion"): ["Death-Maiden", "Matriarch"],
            ("Gang List", "Ganger"): ["Gang Sister"],
        }
        # The collection is not a heading anywhere on the screen: it is
        # the list, so naming it would be naming the page.
        assert "Escher Gang List" not in sections_of(response)
        assert "Escher Gang List" not in response.content.decode()

    def test_a_fighter_the_list_leaves_off_is_not_offered(self, client, owner, gang):
        """Chem Wytch is an Escher profile and perfectly hireable. She is
        simply not on this gang's list, which is what a list is for — and
        is why an archetype's own fighters need no gang type of their own
        to hide behind."""
        response = screen(client, gang, owner)
        assert "Chem Wytch" not in offered_names(response)

    def test_a_list_that_offers_nothing_is_still_the_list(
        self, client, owner, gang, house_list, profiles
    ):
        """Carrying an empty list means an empty list.

        Archive every entry — or stage them while the next book is
        written — and the list offers nobody. Falling back to the gang
        type's profiles there would hand the gang the very fighters its
        list exists to leave out, at prices the list never set.
        """
        for entry in house_list.entries.all():
            entry.archive()

        response = screen(client, gang, owner)
        assert offered_names(response) == []
        assert "Chem Wytch" not in response.content.decode()

    def test_a_gang_type_with_no_list_of_its_own_offers_its_profiles(
        self, client, owner, escher, profiles
    ):
        """Until a house's list is written down, its gang type's own
        fighters are the list, so a house nobody has written down yet
        hires from its gang type's fighter entries."""
        plain = found_gang("The Unwritten", escher, owner=owner, budget=1000)
        response = screen(client, plain, owner)
        assert offered_names(response) == sorted(name for name, _, _ in ESCHER)


class TestAnArchetypeSwapsTheList:
    """Picking an archetype puts its list where the house's was."""

    def test_the_archetypes_list_replaces_the_houses(
        self, client, owner, gang, chem_cults
    ):
        take_the_archetype(gang, chem_cults)
        response = screen(client, gang, owner)
        assert offered_names(response) == sorted(CHEM_LIST)

    def test_the_screen_reads_the_same_way_it_did(
        self, client, owner, gang, chem_cults
    ):
        """The fighters change and the page does not: the same headings,
        no section named after either collection."""
        take_the_archetype(gang, chem_cults)
        response = screen(client, gang, owner)
        assert offered(response) == {
            ("Gang List", "Champion"): ["Death-Maiden"],
            # Cheapest first within a heading, as everywhere on this
            # screen: a Gang Sister is 55 and a Chem Wytch 60.
            ("Gang List", "Ganger"): ["Gang Sister", "Chem Wytch"],
        }
        assert "Chem Cults Gang List" not in sections_of(response)

    def test_the_list_prices_its_own_rows(self, client, owner, gang, chem_cults):
        """A Chem Cult's Death-Maiden costs what the Chem Cults list says,
        not what the fighter is written at."""
        take_the_archetype(gang, chem_cults)
        response = screen(client, gang, owner)
        assert row(response, "Death-Maiden").base_price == CHEM_MAIDEN_PRICE
        assert f"{CHEM_MAIDEN_PRICE}¢" in response.content.decode()

    def test_a_fighter_only_the_archetype_offers_can_be_hired(
        self, client, owner, gang, chem_cults
    ):
        take_the_archetype(gang, chem_cults)
        client.force_login(owner)
        response = screen(client, gang, owner)
        key = row(response, "Chem Wytch").key

        client.post(hire_url(gang), {"profile": key, "name": "Sela"})

        assert [str(member) for member in roster(gang)] == ["Sela"]
        # At the archetype's price, not the fighter's own: the offer the
        # row was made under is what the books record.
        hired = next(member for member in roster(gang) if str(member) == "Sela")
        assert hired.membership.ledger_entry.paid == 60
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_hiring_uses_the_archetypes_price_for_payment_and_rating(
        self, client, owner, gang, chem_cults
    ):
        take_the_archetype(gang, chem_cults)
        response = screen(client, gang, owner)
        key = row(response, "Death-Maiden").key

        response = client.post(hire_url(gang), {"profile": key, "name": "Ilyanna"})

        assert response.status_code == 302
        hired = next(member for member in roster(gang) if str(member) == "Ilyanna")
        assert hired.membership.ledger_entry.paid == CHEM_MAIDEN_PRICE
        gang.refresh_from_db()
        assert gang.rating == CHEM_MAIDEN_PRICE
        assert_reconciled(gang)

    def test_a_gang_that_picks_nothing_keeps_the_house_list(
        self, client, owner, gang, chem_cults, profiles
    ):
        """The archetype is written and unpicked, so the gang hires and
        buys as any gang of its house does."""
        response = screen(client, gang, owner)
        assert offered_names(response) == sorted(HOUSE_LIST)

        queen = hire(gang, profiles["Queen"], "Yara", paid=145)
        assert lists_for(queen) == ["Escher Equipment List"]
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestTwoListsAtOnce:
    """A gang holding two gang lists has no one list, and the screen says
    so rather than merging them."""

    def test_each_stands_under_its_own_name(
        self, client, owner, gang, chem_list, profiles
    ):
        """The author's likeliest slip: giving the archetype's list
        without taking the house's away. Merged, Death-Maiden would sit
        under one heading twice at two prices with nothing to tell the
        rows apart, so instead each list is drawn under its own name.
        """
        assign(chem_list, gang=gang)

        response = screen(client, gang, owner)
        assert sections_of(response) == [
            "Escher Gang List",
            "Chem Cults Gang List",
        ]
        assert row(response, "Chem Wytch").base_price == 60

    @pytest.mark.parametrize("entry_state", ["archived", "staged"])
    def test_an_empty_second_list_still_uses_collection_headings(
        self, client, owner, gang, chem_list, entry_state
    ):
        assign(chem_list, gang=gang)
        chem_list.entries.update(**{entry_state: True})

        response = screen(client, gang, owner)

        assert sections_of(response) == ["Escher Gang List"]
        assert offered_names(response) == sorted(HOUSE_LIST)

    @pytest.mark.parametrize("collection_state", ["archived", "staged"])
    def test_a_hidden_second_collection_does_not_change_the_live_list(
        self, client, owner, gang, chem_list, collection_state
    ):
        assign(chem_list, gang=gang)
        setattr(chem_list, collection_state, True)
        chem_list.save(update_fields=[collection_state])

        response = screen(client, gang, owner)

        assert sections_of(response) == ["Gang List"]
        assert offered_names(response) == sorted(HOUSE_LIST)


class TestWhatElseAGangIsOffered:
    """A collection of fighters that does not name the gang list is an
    addition to whatever list the gang has, drawn as a block of its own."""

    def test_a_roster_with_no_section_is_a_block_named_after_itself(
        self, client, owner, gang, profiles
    ):
        """A roster authored with no sections at all, which is how every
        corruption's roster is written."""
        extra = create_collection("Genestealer Cult Corrupted")
        add_entry(extra, profiles["Chem Wytch"], price_override=200)
        assign(extra, gang=gang)

        response = screen(client, gang, owner)
        assert sections_of(response)[-1] == "Genestealer Cult Corrupted"
        assert row(response, "Chem Wytch").base_price == 200
        # And the gang's own list is untouched beneath it.
        assert offered(response)[("Gang List", "Leader")] == ["Queen"]

    def test_a_roster_naming_its_own_section_is_a_block_of_that_name(
        self, client, owner, gang, profiles
    ):
        """An author may give the block a name other than the
        collection's: the default section is what the screen reads."""
        extra = create_collection("Genestealer Cult Corrupted Fighter Additions")
        section_of(extra, "Genestealer Cult Corrupted", 0, is_default=True)
        add_entry(extra, profiles["Chem Wytch"], price_override=200)
        assign(extra, gang=gang)

        response = screen(client, gang, owner)
        assert sections_of(response)[-1] == "Genestealer Cult Corrupted"
        assert "Fighter Additions" not in sections_of(response)


class TestTheEquipmentListsFollow:
    """An archetype changes what its gang buys from, fighter by fighter,
    and the gang's own list for the stash along with them."""

    @pytest.fixture
    def hired(self, gang, profiles, chem_cults):
        maiden = hire(gang, profiles["Death-Maiden"], "Ilyanna", paid=115)
        sister = hire(gang, profiles["Gang Sister"], "Vasha", paid=55)
        take_the_archetype(gang, chem_cults)
        return gang, maiden, sister

    def test_an_ordinary_fighter_buys_from_the_archetypes_list(self, hired):
        _, _, sister = hired
        assert lists_for(sister) == ["Chem Cults Equipment List"]

    def test_a_fighter_the_archetype_names_buys_from_her_own(self, hired):
        _, maiden, _ = hired
        assert lists_for(maiden) == ["Chem Cults Death-Maiden Equipment List"]

    def test_the_gang_itself_buys_from_the_archetypes_list(self, hired):
        """The stash buys from the archetype's list too, which takes its
        own pair of rows — a swap written for the fighters alone leaves
        the gang still buying from the house list it no longer has."""
        gang, _, _ = hired
        assert [
            str(collection)
            for collection in buyable_lists(
                access.collection for access in gang_collections(gang)
            )
        ] == ["Chem Cults Equipment List"]
        # And what it hires from has moved with it.
        assert "Chem Cults Gang List" in gang_lists_for(gang)
        assert "Escher Gang List" not in gang_lists_for(gang)

    def test_the_books_still_balance(self, hired):
        gang, _, _ = hired
        assert_reconciled(gang)


class TestWhatTheScreenCosts:
    """Reading the list off the gang's card costs a fixed number of
    queries, however many fighters the list holds."""

    def test_the_screen_costs_the_same_however_long_the_list_is(
        self, client, owner, gang, house_list, profiles, person_type, headings
    ):
        client.force_login(owner)
        # Once to warm whatever a first visit settles — the reading being
        # taken is what a length costs, not what a cold cache does.
        client.get(hire_url(gang))
        with CaptureQueriesContext(connection) as short:
            client.get(hire_url(gang))

        for index in range(6):
            extra = create_profile(
                f"Sister {index}",
                person_type,
                gang.gang_type,
                price=50,
                category=headings["Ganger"],
            )
            add_entry(house_list, extra)

        with CaptureQueriesContext(connection) as long:
            response = client.get(hire_url(gang))

        assert len(offered_names(response)) == len(HOUSE_LIST) + 6
        assert len(long) == len(short)


class TestAListNobodyMaySeeIsNotTheList:
    """A gang list that is staged, or archived, is not a list this reader
    hires from — so it must not switch the fallback off and leave them
    with an empty tab. Staff, who see staged content, are offered from
    it: that is how an author rehearses a house's list before it goes
    live, while every player goes on hiring from the gang type."""

    @staticmethod
    def rehearsal(escher, profiles, owner):
        """The house list authored the way the authoring pages author
        everything: staged, with a staged section and staged entries —
        and a gang of the house founded on top of it."""
        collection = create_collection("Escher Gang List", staged=True)
        section_of(collection, "Gang List", 0, is_default=True, staged=True)
        for name in HOUSE_LIST:
            add_entry(collection, profiles[name], staged=True)
        add_built_in(escher, collection)
        return found_gang("The Rehearsal", escher, owner=owner, budget=1000)

    def test_a_player_still_hires_from_the_gang_type(
        self, client, owner, escher, profiles, equipment
    ):
        gang = self.rehearsal(escher, profiles, owner)
        response = screen(client, gang, owner)
        assert offered_names(response) == sorted(name for name, _, _ in ESCHER)

    def test_a_staff_reader_is_offered_from_the_staged_list(
        self, client, escher, profiles, equipment
    ):
        staff = User.objects.create_user("author", is_staff=True)
        gang = self.rehearsal(escher, profiles, staff)
        response = screen(client, gang, staff)
        assert offered_names(response) == sorted(HOUSE_LIST)

    def test_an_archived_list_is_not_the_list_either(
        self, client, owner, gang, house_list
    ):
        house_list.archive()
        response = screen(client, gang, owner)
        assert offered_names(response) == sorted(name for name, _, _ in ESCHER)


class TestWhatCountsAsTheGangListsName:
    """The default section's name is matched the way section names are
    kept unique — without regard to case — and only on a collection that
    holds fighters."""

    def test_the_name_is_read_however_it_is_cased(
        self, client, owner, escher, profiles
    ):
        collection = create_collection("Escher Gang List")
        section_of(collection, "gang list", 0, is_default=True)
        for name in HOUSE_LIST:
            add_entry(collection, profiles[name])
        add_built_in(escher, collection)
        gang = found_gang("The Lower Case", escher, owner=owner, budget=1000)

        response = screen(client, gang, owner)
        assert offered_names(response) == sorted(HOUSE_LIST)
        assert sections_of(response) == ["Gang List"]

    def test_a_list_of_gear_by_that_name_is_nobodys_gang_list(
        self, client, owner, escher, profiles
    ):
        """A gear list given the section name by mistake must not switch
        the gang type's fighters off and leave an empty tab."""
        gear = create_collection("Oddly named kit")
        section_of(gear, "Gang List", 0, is_default=True)
        add_entry(gear, create_wargear("Odd knife", price=10))
        add_built_in(escher, gear)
        gang = found_gang("The Unlucky", escher, owner=owner, budget=1000)

        response = screen(client, gang, owner)
        assert offered_names(response) == sorted(name for name, _, _ in ESCHER)


class TestSectionsThatShareAName:
    """Two sections reading alike would be one tab with half its rows
    unreachable, so they become one section."""

    def test_a_block_named_after_a_taxonomy_section_joins_it(
        self, client, owner, gang, house_list, escher, person_type, make_statline
    ):
        """The house list reaches two taxonomy sections, and a carried
        collection names the second as its own block. The block and the
        section are one heading, holding both sets of rows."""
        hanger = create_category("Hangers-on", "Shivver", position=0)
        shivver = create_profile(
            "Shivver", person_type, escher, price=80, category=hanger
        )
        make_statline(shivver, movement=5, weapon_skill=4, toughness=3)
        add_entry(house_list, shivver)

        extra = create_collection("A friend of the gang")
        section_of(extra, "Hangers-on", 0, is_default=True)
        hired_gun = create_profile(
            "Hired gun", person_type, escher, price=95, category=hanger
        )
        make_statline(hired_gun, movement=5, weapon_skill=3, toughness=3)
        add_entry(extra, hired_gun, price_override=200)
        assign(extra, gang=gang)

        response = screen(client, gang, owner)
        names = sections_of(response)
        assert names == ["Gang List", "Hangers-on"], names
        merged = next(
            section
            for section in response.context["hire_list"]
            if section.name == "Hangers-on"
        )
        headings = [category.name for category in merged.categories]
        assert len(headings) == len(set(headings)), headings
        # One heading, both the list's fighter and the collection's.
        assert sorted(
            entry.name
            for section in response.context["hire_list"]
            if section.name == "Hangers-on"
            for entry in section.all_entries()
        ) == ["Hired gun", "Shivver"]
        assert row(response, "Hired gun").base_price == 200


class TestTheGangSheetDrawsNoLineForTheList:
    """The gang's hire list is what the hire screen *is*, so it draws no
    line on the gang sheet: a gang whose house gains a written-down list,
    or whose archetype swaps one for another, draws the same rows
    either way. Its equipment list, which is somewhere to buy from, keeps
    its line."""

    def test_a_carried_list_is_not_a_row_on_the_sheet(self, gang):
        names = [line.name for line in render_gang(gang).rows]
        assert "Escher Gang List" not in names
        assert "Escher Equipment List" in names

    def test_nor_is_the_list_an_archetype_gives(self, gang, chem_cults):
        take_the_archetype(gang, chem_cults)
        names = [line.name for line in render_gang(gang).rows]
        assert "Chem Cults Gang List" not in names
        assert "Escher Gang List" not in names

    def test_the_text_sheet_says_nothing_of_it_either(self, gang):
        text = render_gang_sheet(render_gang(gang))
        assert "Gang List" not in text

    @pytest.mark.parametrize("with_effects", [True, False])
    def test_an_archived_list_stays_hidden_when_hiring_falls_back(
        self, client, owner, gang, house_list, with_effects
    ):
        house_list.archive()

        sheet = render_gang(gang, with_effects=with_effects)
        assert "Escher Gang List" not in [line.name for line in sheet.rows]
        assert "Escher Gang List" not in render_gang_sheet(sheet)
        if with_effects:
            assert "Escher Equipment List" in [line.name for line in sheet.rows]
        assert offered_names(screen(client, gang, owner)) == sorted(
            name for name, _, _ in ESCHER
        )

    def test_an_archived_granted_list_stays_hidden(self, gang, chem_cults, chem_list):
        take_the_archetype(gang, chem_cults)
        chem_list.archive()

        sheet = render_gang(gang)

        assert "Chem Cults Gang List" not in [line.name for line in sheet.rows]
        assert "Chem Cults Gang List" not in render_gang_sheet(sheet)

    def test_a_list_with_an_archived_default_section_stays_hidden(
        self, gang, house_list
    ):
        house_list.sections.get(is_default=True).archive()

        assert "Escher Gang List" not in [line.name for line in render_gang(gang).rows]


class TestASweepThatWasWithdrawn:
    """A sweep is content like the entries beside it: archived, it
    gathers nobody, and staged, it gathers nobody for a player."""

    def test_an_archived_sweep_offers_none_of_its_fighters(
        self, client, owner, gang, profiles, headings
    ):
        swept = create_collection(
            "Corrupted beasts", contains=[(Profile, headings["Ganger"])]
        )
        section_of(swept, "Corrupted beasts", 0, is_default=True)
        assign(swept, gang=gang)

        response = screen(client, gang, owner)
        assert "Corrupted beasts" in sections_of(response)

        swept.selectors.get().archive()
        response = screen(client, gang, owner)
        assert "Corrupted beasts" not in sections_of(response)
