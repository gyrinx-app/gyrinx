"""The Affiliation shape: a choice the gang itself is offered.

The second example of the slots-and-picks design. A gang type carrying a
choice in its built-ins, so a gang founded from it is offered one from
the moment it exists; the pick lands on the gang, and what it gives is
scoped to the ranks it names. One of the options opens a second choice,
and changing the first retracts it.

Sandbox content shaped like a gang list that works this way — an
Affiliation domain, four options, ranks named Leader, Champion, Ganger
and Hive Scum. Which affiliations the edition offers, which ranks each
one reaches, and what the lists hold are the maintainer's to state; what
is proved here is the shape.

The library is built with the authoring verbs, because the authoring
pages are ``test_gang_legacy.py``'s walkthrough and this file is about
the playing. Everything a player does goes through the real pages.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_gang
from n26.core.views.choose import link_slots
from n26.library.authoring import (
    add_built_in,
    add_picklist_member,
    create_collection,
    create_gang_type,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    create_subtype,
    create_wargear,
    ef_adds,
    has_subtypes,
    modifier,
    targets_gang,
    targets_model,
)
from n26.tests.sandbox.actions import found_gang

pytestmark = pytest.mark.django_db


#: The four options, in the order the list offers them. Illustrative:
#: what a gang of outcasts may affiliate with is content.
AFFILIATIONS = ("Clanless", "Clan House", "Mutant", "Aranthian")

#: The houses the chained choice offers, once Clan House is the pick.
CLAN_HOUSES = ("Cawdor", "Escher", "Van Saar")

#: The ranks, and the price each is hired at. Hive Scum is the rank no
#: affiliation names: a suite that scoped a give to everyone would prove
#: nothing about scoping.
RANKS = (
    ("Outcast Leader", 120),
    ("Outcast Champion", 90),
    ("Outcast Ganger", 50),
    ("Hive Scum", 20),
)

#: Who the Aranthian list is opened to — every rank but the scum.
ARANTHIAN_RANKS = ("Outcast Leader", "Outcast Champion", "Outcast Ganger")

#: What the two stocked lists sell. A list with nothing on it draws no
#: tab, so the surface a give is read off needs something in stock.
ARANTHIAN_STOCK = ("Aranthian sidearm", 35)
CAWDOR_STOCK = ("Blessed blade", 25)


@pytest.fixture
def owner(db):
    return User.objects.create_user("outcast-player")


@pytest.fixture
def ranks(default_pack):
    return {name: create_subtype(name) for name, _ in RANKS}


@pytest.fixture
def domain(default_pack):
    """One affiliation per gang, so the domain refuses repeats."""
    return create_slot_type("Affiliation", allows_repeats=False)


@pytest.fixture
def house_domain(default_pack):
    """The domain the chained choice draws on."""
    return create_slot_type("Clan House", plural_name="Clan Houses")


@pytest.fixture
def house_choice(house_domain, ranks):
    """The second choice: which house, offered once Clan House is picked.

    Assigned to the gang like the first, because a gang affiliates with
    a house rather than a fighter doing so.
    """
    houses = create_picklist(
        "Clan Houses",
        house_domain,
        members=[
            create_pickable(f"House {name}", house_domain) for name in CLAN_HOUSES
        ],
    )
    cawdor = houses.members.first().pickable
    modifier(
        "House Cawdor: its equipment list",
        targets_model(has_subtypes(ranks["Outcast Leader"])),
        ef_adds(
            create_collection(
                "House Cawdor Equipment List",
                entries=[(create_wargear(CAWDOR_STOCK[0], price=CAWDOR_STOCK[1]), {})],
            )
        ),
        attach_to=cawdor,
    )
    return create_slot(
        "Clan House", house_domain, houses, label="Clan House", assigned_to="gang"
    )


@pytest.fixture
def affiliations(domain, ranks, house_choice):
    """The four options. Aranthian gives its list to three of the four
    ranks; Clan House gives the second choice; Clanless gives nothing,
    which is a perfectly good option."""
    made = {name: create_pickable(name, domain) for name in AFFILIATIONS}
    modifier(
        "Aranthian: its equipment list",
        targets_model(has_subtypes(*[ranks[name] for name in ARANTHIAN_RANKS])),
        ef_adds(
            create_collection(
                "Aranthian Equipment List",
                entries=[
                    (create_wargear(ARANTHIAN_STOCK[0], price=ARANTHIAN_STOCK[1]), {})
                ],
            )
        ),
        attach_to=made["Aranthian"],
    )
    # The gang is what affiliates, so the second choice is given to the
    # gang. Given to its models instead it would be a choice per member,
    # which is a different thing entirely.
    modifier(
        "Clan House: which house",
        targets_gang(),
        ef_adds(house_choice),
        attach_to=made["Clan House"],
    )
    return made


@pytest.fixture
def outcasts(domain, affiliations):
    """The gang type, carrying the choice in its built-ins: founding is
    what asks it, and the pick belongs to the gang."""
    offered = create_picklist("Affiliations", domain)
    for position, name in enumerate(AFFILIATIONS):
        add_picklist_member(offered, affiliations[name], position=position)
    choice = create_slot(
        "Affiliation",
        domain,
        offered,
        label="Affiliation",
        min_picks=1,
        max_picks=1,
        assigned_to="gang",
    )
    gang_type = create_gang_type("Underhive Outcasts", starting_credits=1000)
    add_built_in(gang_type, choice)
    gang_type.refresh_from_db()
    return gang_type


@pytest.fixture
def gang(owner, outcasts):
    return found_gang("The Unmade", outcasts, owner=owner)


@pytest.fixture
def crew(gang, ranks, person_type):
    """One model of each rank, hired straight in."""
    from n26.tests.sandbox.actions import hire

    made = {}
    for name, price in RANKS:
        profile = create_profile(name, person_type, gang.gang_type, price=price)
        add_built_in(profile, ranks[name])
        made[name] = hire(gang, profile, name, paid=price)
    return made


@pytest.fixture
def reader(client, owner):
    client.force_login(owner)
    return client


def sheet_of(gang):
    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    return sheet


def picker_url(gang, label):
    """Where the gang's own choice row leads, or None once it is gone."""
    line = next(
        (line for line in sheet_of(gang).questions if line.kind_label == label), None
    )
    return None if line is None else line.href


def chosen_for(gang, label):
    line = next(
        (line for line in sheet_of(gang).questions if line.kind_label == label), None
    )
    return None if line is None else line.chosen


def choose(reader, gang, label, option):
    return reader.post(
        picker_url(gang, label), {"thing": f"library.pickable:{option.pk}"}
    )


def lists_on(miniature):
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return [line.name for line in compute(card, index).collections]


def equip_page(reader, miniature, collection=None):
    url = reverse("n26-equip", args=[miniature.pk])
    if collection is not None:
        url = f"{url}?list={collection.pk}"
    return reader.get(url).content.decode()


class TestTheGangIsTheOneAsked:
    """A choice built into the gang type is the gang's own. It is drawn
    once, on the gang's card, and no member's card repeats it."""

    def test_founding_is_what_offers_it(self, reader, gang):
        assert chosen_for(gang, "Affiliation") is None
        assert picker_url(gang, "Affiliation")

    def test_the_gang_page_draws_the_choice_row_with_somewhere_to_click(
        self, reader, gang
    ):
        body = reader.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Affiliation" in body
        assert picker_url(gang, "Affiliation") in body

    def test_no_members_card_asks_it_again(self, reader, gang, crew):
        sheet = sheet_of(gang)

        assert [card.questions for card in sheet.models] == [[] for _ in crew]
        assert len(sheet.questions) == 1

    def test_the_page_offers_it_once_however_many_members(self, reader, gang, crew):
        body = reader.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert body.count(picker_url(gang, "Affiliation")) == 1

    def test_the_shortfall_is_the_gangs_news(self, reader, gang, crew):
        """The under-min note belongs to whoever was offered the choice.

        Read off the built sheet: no page prints these notes yet, so this
        is the note existing rather than the note being seen.
        """
        assert "Affiliation — 0 of 1 chosen" in [
            note.text for note in render_gang(gang).notes
        ]

    def test_a_stranger_cannot_reach_the_picker(self, client, gang):
        stranger = User.objects.create_user("stranger")
        where = picker_url(gang, "Affiliation")
        client.force_login(stranger)

        assert client.get(where).status_code == 404


class TestChoosingAnAffiliation:
    """The picker offers the list, one click settles it, and the pick is
    the gang's — not the card's that drew the control."""

    def test_the_picker_offers_the_four_in_order(self, reader, gang, affiliations):
        body = reader.get(picker_url(gang, "Affiliation")).content.decode()

        places = [
            body.index(f"library.pickable:{affiliations[name].pk}")
            for name in AFFILIATIONS
        ]
        assert places == sorted(places)

    def test_the_picker_names_the_gang_as_the_one_choosing(self, reader, gang):
        body = reader.get(picker_url(gang, "Affiliation")).content.decode()

        assert f"For {gang.name}." in body

    def test_one_click_settles_it_on_the_gang(self, reader, gang, affiliations):
        response = choose(reader, gang, "Affiliation", affiliations["Aranthian"])

        assert response.status_code == 302
        assert chosen_for(gang, "Affiliation") == "Aranthian"
        pick = Assignment.objects.get(pickable=affiliations["Aranthian"])
        assert pick.gang == gang
        assert pick.miniature is None

    def test_the_pick_is_free(self, reader, gang, crew, affiliations):
        gang.refresh_from_db()
        before = gang.credits

        choose(reader, gang, "Affiliation", affiliations["Aranthian"])

        gang.refresh_from_db()
        assert gang.credits == before
        assert_reconciled(gang)

    def test_choosing_again_replaces_rather_than_stacks(
        self, reader, gang, affiliations
    ):
        choose(reader, gang, "Affiliation", affiliations["Clanless"])
        choose(reader, gang, "Affiliation", affiliations["Mutant"])

        assert chosen_for(gang, "Affiliation") == "Mutant"
        assert (
            Assignment.objects.filter(pickable__isnull=False, archived=False).count()
            == 1
        )


class TestWhatTheGangsPickReaches:
    """The pick is the gang's, so its gives are broadcast — and scoped, so
    they stop at the ranks the option names."""

    @pytest.fixture
    def affiliated(self, reader, gang, crew, affiliations):
        choose(reader, gang, "Affiliation", affiliations["Aranthian"])
        return crew

    def test_the_named_ranks_get_the_list(self, affiliated):
        for rank in ARANTHIAN_RANKS:
            assert "Aranthian Equipment List" in lists_on(affiliated[rank]), rank

    def test_the_rank_it_does_not_name_does_not(self, affiliated):
        assert lists_on(affiliated["Hive Scum"]) == []

    def test_it_is_on_the_named_ranks_equip_page_to_buy_from(self, reader, affiliated):
        body = equip_page(reader, affiliated["Outcast Champion"])

        assert "Aranthian Equipment List" in body

    def test_and_not_on_the_others(self, reader, affiliated):
        body = equip_page(reader, affiliated["Hive Scum"])

        assert "Aranthian Equipment List" not in body

    def test_no_members_card_draws_a_line_for_it(self, reader, gang, affiliated):
        """What the gang holds reaches every member and is listed on
        none of them: the gang's card is where its own things are said."""
        for card in sheet_of(gang).models:
            assert [line.name for line in card.equipment] == []

    def test_the_gang_page_says_the_gang_is_affiliated(self, reader, gang, affiliated):
        body = reader.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Aranthian" in body


class TestOnePickOpensAnother:
    """An option may give a further choice. Making the first offers the
    second, and changing the first takes the second away with everything
    it settled — the chain retracts through what caused it.

    Removing a pick outright is the engine's own act and is proved in
    ``test_slots_and_picks.py``; what a player has on the page is the
    rechoose, which is the same removal with a replacement behind it.
    """

    @pytest.fixture
    def clan_house(self, reader, gang, crew, affiliations):
        choose(reader, gang, "Affiliation", affiliations["Clan House"])
        return affiliations

    def test_no_house_is_asked_for_until_the_first_pick_is_made(
        self, reader, gang, crew, affiliations
    ):
        assert picker_url(gang, "Clan House") is None

        choose(reader, gang, "Affiliation", affiliations["Clan House"])

        assert picker_url(gang, "Clan House")
        assert chosen_for(gang, "Clan House") is None

    def test_the_second_picker_offers_the_houses_and_nothing_else(
        self, reader, gang, clan_house
    ):
        body = reader.get(picker_url(gang, "Clan House")).content.decode()

        for house in CLAN_HOUSES:
            assert f"House {house}" in body, house
        # By key: the page's heading is the label "Clan House", which is
        # also what one of the affiliations is called.
        for name in AFFILIATIONS:
            assert f"library.pickable:{clan_house[name].pk}" not in body, name

    def test_the_second_pick_lands_on_the_gang_too(self, reader, gang, clan_house):
        choose(reader, gang, "Clan House", _house("Cawdor"))

        assert chosen_for(gang, "Clan House") == "House Cawdor"
        pick = Assignment.objects.get(pickable__name="House Cawdor")
        assert (pick.gang, pick.miniature) == (gang, None)

    def test_what_the_second_pick_gives_reaches_the_rank_it_names(
        self, reader, gang, crew, clan_house
    ):
        choose(reader, gang, "Clan House", _house("Cawdor"))

        assert "House Cawdor Equipment List" in lists_on(crew["Outcast Leader"])
        assert "House Cawdor Equipment List" not in lists_on(crew["Outcast Ganger"])

    def test_changing_the_first_takes_the_whole_chain(
        self, reader, gang, crew, clan_house
    ):
        """A Mutant gang affiliated with a house is not a thing the
        content can express, so nothing of the house may survive the
        change: not the second choice, not its pick, not what it gave."""
        choose(reader, gang, "Clan House", _house("Cawdor"))

        choose(reader, gang, "Affiliation", clan_house["Mutant"])

        assert chosen_for(gang, "Affiliation") == "Mutant"
        assert picker_url(gang, "Clan House") is None
        assert not Assignment.objects.filter(
            pickable__name="House Cawdor", archived=False
        ).exists()
        assert lists_on(crew["Outcast Leader"]) == []
        gang.refresh_from_db()
        assert_reconciled(gang)


def _house(name):
    """One of the houses the chained choice offers."""
    from n26.library.models import Pickable

    return Pickable.objects.get(name=f"House {name}")


class TestTheGangPageStaysFlat:
    """A gang page is one fixed run of queries whatever the domain holds:
    a list that grows is rows to read, never round trips to make."""

    def test_more_options_do_not_mean_more_queries(
        self, reader, gang, crew, affiliations, domain, django_assert_num_queries
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.models import Picklist

        choose(reader, gang, "Affiliation", affiliations["Aranthian"])
        page = reverse("n26-gang", args=[gang.pk])

        with CaptureQueriesContext(connection) as few:
            assert reader.get(page).status_code == 200

        offered = Picklist.objects.get(name="Affiliations")
        for index in range(20):
            add_picklist_member(offered, create_pickable(f"Affiliate {index}", domain))

        with django_assert_num_queries(len(few), exact=False):
            assert reader.get(page).status_code == 200
