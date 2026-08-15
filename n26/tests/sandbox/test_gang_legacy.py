"""Gang Legacy: a domain of choice authored on the pages, then played.

The first example of the slots-and-picks design, walked from an empty
library to a fighter buying from the equipment list his choice opened.
Everything an author does here goes through the real authoring pages,
and everything a player does goes through the real player pages: found,
hire, choose, equip, and leave.

The shape being proved is the example's — one domain, its options, the
list that offers them, one choice at 1..1 assigned to the bearer, and a
second profile carrying the same choice with a starting pick. The house
names and prices below are content for the walkthrough to stand on;
which options the edition offers, and which profiles carry the choice or
arrive already settled, are the maintainer's to state.

The engine underneath is ``test_slots_and_picks.py``'s and the authoring
forms are ``test_authoring_views.py``'s. What is here is the join: that
the two halves meet, in the order a person would do them.
"""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_gang
from n26.core.views.choose import link_slots
from n26.library.models import (
    Collection,
    DefaultAssignment,
    Pickable,
    Picklist,
    Profile,
    Slot,
    SlotType,
    Wargear,
)

pytestmark = pytest.mark.django_db


#: The options, in the order the list offers them. Eight is the point of
#: the example — a domain wide enough that the picker's order is a fact
#: worth pinning — rather than a claim about the edition's content.
HOUSES = (
    "Cawdor",
    "Escher",
    "Goliath",
    "Orlock",
    "Van Saar",
    "Delaque",
    "Ironhead Squats",
    "Ogryn",
)

#: What the stocked lists sell: an item, the price the library prints,
#: and the price the list itself asks. Two of the eight are stocked —
#: the one bought from and the one a starting pick opens — because an
#: empty list has nothing to draw and six more would be six more pages
#: authored to prove nothing.
STOCK = {
    "Cawdor": ("Blessed blade", 25, 15),
    "Ironhead Squats": ("Ancestral hammer", 40, 30),
}

#: The profile that arrives with the choice open, and the one that
#: arrives with it already settled — the slot-with-default.
HUNTER_PRICE = 100
DEFAULT_HOUSE = "Ironhead Squats"

#: An empty condition formset, as the browser sends it on every compose.
NO_CONDITIONS = {
    "conditions-TOTAL_FORMS": "0",
    "conditions-INITIAL_FORMS": "0",
    "conditions-MIN_NUM_FORMS": "0",
    "conditions-MAX_NUM_FORMS": "1000",
}


# --- The two sessions ----------------------------------------------------


@pytest.fixture
def author(db):
    """A staff session that writes the library.

    Its own client, so the player's session below is never the author's
    signed in again: the two halves of this file are two people.
    """
    session = Client()
    session.force_login(User.objects.create_user("author", is_staff=True))
    return session


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


# --- Authoring, page by page ---------------------------------------------


def posted(session, url, data):
    """A form submitted and accepted — a redirect, never a redrawn form.

    A refusal comes back as a 200 with the words on it, so a fixture that
    only checked for 200 would build half a domain and fail somewhere
    else entirely.
    """
    response = session.post(url, data)
    assert response.status_code == 302, response.content.decode()[:2000]
    return response


@pytest.fixture
def domain(author, default_pack):
    """The domain, made on the slot type's create page. Repeats are left
    off, which is the switch untouched: nobody holds two legacies."""
    posted(
        author,
        "/n26/authoring/slot-type/new/",
        {"name": "Gang Legacy", "plural_name": "Gang Legacies"},
    )
    return SlotType.objects.get(name="Gang Legacy")


@pytest.fixture
def house_lists(author, default_pack):
    """One equipment list per house, and stock on the one that is bought
    from — priced by the list rather than by the item."""
    lists = {}
    for house in HOUSES:
        name = f"House {house} Equipment List"
        posted(
            author,
            "/n26/authoring/collection/new/",
            # The form opens with Prices its entries ticked, so a browser
            # posts it. Left out, the list is a menu: it asks for no
            # price, and a fighter buying from it pays the library's.
            {"name": name, "prices_its_entries": "on"},
        )
        lists[house] = Collection.objects.get(name=name)

    for house, (item, reference, here) in STOCK.items():
        posted(
            author,
            "/n26/authoring/wargear/new/",
            {"name": item, "price": str(reference), "trade_point_price": "1"},
        )
        posted(
            author,
            f"/n26/authoring/collection/{lists[house].pk}/",
            {
                "act": "entry",
                "thing_kind": "wargear",
                "thing_wargear": str(Wargear.objects.get(name=item).pk),
                "price_override": str(here),
            },
        )
    return lists


@pytest.fixture
def options(author, domain, house_lists):
    """The eight options, each made on the domain's own page and each
    given its house's equipment list through the modifier composer."""
    made = {}
    for house in HOUSES:
        posted(
            author,
            f"/n26/authoring/slot-type/{domain.pk}/",
            {"act": "pickable", "name": house},
        )
        option = Pickable.objects.get(name=house)
        posted(
            author,
            f"/n26/authoring/pickable/{option.pk}/",
            {
                "act": "compose",
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "collection",
                "what-thing_collection": str(house_lists[house].pk),
                **NO_CONDITIONS,
            },
        )
        made[house] = option
    return made


@pytest.fixture
def legacies(author, domain, options):
    """The list, and the eight options added to it in order."""
    posted(
        author,
        f"/n26/authoring/slot-type/{domain.pk}/",
        {"act": "picklist", "name": "Gang Legacies"},
    )
    picklist = Picklist.objects.get(name="Gang Legacies")
    for position, house in enumerate(HOUSES):
        posted(
            author,
            f"/n26/authoring/picklist/{picklist.pk}/",
            {
                "pickable": str(options[house].pk),
                "label_override": "",
                "position": str(position),
            },
        )
    return picklist


@pytest.fixture
def choice(author, domain, legacies):
    """The choice itself: one pick, landing on whoever was asked."""
    posted(
        author,
        f"/n26/authoring/slot-type/{domain.pk}/",
        {
            "act": "slot",
            "name": "Gang Legacy",
            "picklist": str(legacies.pk),
            "label": "Gang Legacy",
            "min_picks": "1",
            "max_picks": "1",
            "assigned_to": "bearer",
            "position": "0",
        },
    )
    return Slot.objects.get(name="Gang Legacy")


def make_profile(author, name, person_type, gang_type, price=HUNTER_PRICE):
    posted(
        author,
        "/n26/authoring/profile/new/",
        {
            "name": name,
            "profile_type": str(person_type.pk),
            "gang_type": str(gang_type.pk),
            "price": str(price),
            "category": "",
            # The form opens with Offered for hire ticked, so a browser
            # posts it. Left out, the profile is one nobody can hire and
            # the hire screen never lists it.
            "hireable": "on",
        },
    )
    return Profile.objects.get(name=name)


@pytest.fixture
def hunter(author, person_type, gang_type, choice):
    """Hired plain, the choice arrives open."""
    profile = make_profile(author, "Hunter", person_type, gang_type)
    posted(
        author,
        f"/n26/authoring/profile/{profile.pk}/",
        {"act": "built_in", "thing_kind": "slot", "thing_slot": str(choice.pk)},
    )
    profile.refresh_from_db()
    return profile


@pytest.fixture
def squats_hunter(author, person_type, gang_type, choice, options):
    """The slot-with-default: the same choice, carrying a starting pick."""
    profile = make_profile(author, "Squats Hunter", person_type, gang_type)
    posted(
        author,
        f"/n26/authoring/profile/{profile.pk}/",
        {
            "act": "built_in",
            "thing_kind": "slot",
            "thing_slot": str(choice.pk),
            "default_pickable": str(options[DEFAULT_HOUSE].pk),
        },
    )
    profile.refresh_from_db()
    return profile


# --- Playing, page by page -----------------------------------------------


@pytest.fixture
def gang(client, owner, gang_type):
    """Founded through the page that founds one."""
    from n26.core.models import Gang

    client.force_login(owner)
    response = client.post(
        reverse("n26-create-gang"),
        {
            "name": "The Long Hunt",
            "gang_type": str(gang_type.pk),
            "starting_credits": "1000",
            "colour": "",
        },
    )
    assert response.status_code == 302
    return Gang.objects.get(name="The Long Hunt")


def hire(client, gang, profile, name):
    """The hire dialog's submit, and the model it wrote."""
    from n26.core.models import Miniature

    response = client.post(
        reverse("n26-hire-fighter", args=[gang.pk]),
        {"profile": str(profile.pk), "name": name},
    )
    assert response.status_code == 302
    return Miniature.objects.get(name=name, membership__gang=gang)


def purse(gang):
    """What the gang has left, read afresh.

    Every act in this file is another request, and the fixture's own
    instance was read before any of them: the numbers on it are the ones
    the gang was founded with.
    """
    gang.refresh_from_db()
    return gang.credits


def reconciled(gang):
    """The pinned totals against the ledger, on the gang as it now stands."""
    gang.refresh_from_db()
    assert_reconciled(gang)


def sheet_of(gang):
    """The gang sheet as the page draws it, pickers linked."""
    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    return sheet


def card_of(gang, name):
    return next(card for card in sheet_of(gang).models if card.name == name)


def picker_url(gang, name, label="Gang Legacy"):
    (line,) = [
        line for line in card_of(gang, name).questions if line.kind_label == label
    ]
    return line.href


def choose(client, gang, name, option, label="Gang Legacy"):
    return client.post(
        picker_url(gang, name, label),
        {"thing": f"library.pickable:{option.pk}"},
    )


def equip_page(client, miniature, collection=None):
    url = reverse("n26-equip", args=[miniature.pk])
    if collection is not None:
        url = f"{url}?list={collection.pk}"
    return client.get(url).content.decode()


def lists_on(gang, name):
    """The equipment lists a model's card reaches, by name."""
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute
    from n26.core.models import Miniature

    miniature = Miniature.objects.get(name=name, membership__gang=gang)
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return [line.name for line in compute(card, index).collections]


class TestTheDomainIsBuiltOnItsOwnPages:
    """An author with an empty library ends with a domain of eight
    options, a list offering them in order, and a choice drawing on that
    list — every step a form on a page."""

    def test_the_domain_page_holds_all_eight_options(
        self, author, client, domain, options
    ):
        body = author.get(f"/n26/authoring/slot-type/{domain.pk}/").content.decode()

        for house in HOUSES:
            assert house in body, house

    def test_each_option_gives_its_own_equipment_list(self, options, house_lists):
        for house, option in options.items():
            (modifier,) = option.modifiers.all()
            assert str(modifier.effect) == f"adds {house_lists[house].name}"

    def test_the_list_offers_them_in_the_order_they_were_added(self, legacies):
        assert [member.label for member in legacies.members.all()] == list(HOUSES)

    def test_the_choice_asks_for_one_of_that_list(self, choice, legacies, domain):
        assert (choice.slot_type, choice.picklist) == (domain, legacies)
        assert (choice.min_picks, choice.max_picks) == (1, 1)
        assert choice.assigned_to == "bearer"
        assert choice.label == "Gang Legacy"

    def test_the_profile_comes_with_the_choice(self, hunter, choice):
        (built_in,) = hunter.built_in_members
        assert built_in.assignable == choice
        assert built_in.default_pickable is None

    def test_the_other_profile_comes_with_the_choice_already_settled(
        self, squats_hunter, choice, options
    ):
        (built_in,) = squats_hunter.built_in_members
        assert built_in.assignable == choice
        assert built_in.default_pickable == options[DEFAULT_HOUSE]

    def test_the_choices_page_says_what_it_asks_for(self, author, choice):
        """The about column is where an author checks their work."""
        body = author.get(f"/n26/authoring/slot/{choice.pk}/").content.decode()

        assert "Asks for one Gang Legacy, chosen from Gang Legacies." in body


class TestHiringIntoAnOpenChoice:
    """Kaustos, hired plain: the choice is on his card from the moment he
    is hired, and leaving it open costs nothing."""

    def test_his_card_asks_it_by_its_label(self, client, gang, hunter):
        hire(client, gang, hunter, "Kaustos")

        (line,) = card_of(gang, "Kaustos").questions
        assert line.kind_label == "Gang Legacy"
        assert line.chosen is None

    def test_the_page_draws_the_choice_row_with_somewhere_to_click(
        self, client, gang, hunter
    ):
        hire(client, gang, hunter, "Kaustos")

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Gang Legacy" in body
        assert picker_url(gang, "Kaustos") in body

    def test_the_card_says_how_short_it_is(self, client, gang, hunter):
        """The under-min note, in the words the design gives it.

        Read off the built card: no page prints a card's remarks yet, so
        this is the note existing rather than the note being seen.
        """
        hire(client, gang, hunter, "Kaustos")

        assert [note.text for note in card_of(gang, "Kaustos").remarks] == [
            "Gang Legacy — 0 of 1 chosen"
        ]

    def test_leaving_it_open_costs_nothing(self, client, gang, hunter):
        hire(client, gang, hunter, "Kaustos")

        assert purse(gang) == 1000 - HUNTER_PRICE
        reconciled(gang)


class TestChoosingAHouse:
    """One click on the picker settles the choice, and what the option
    gives arrives with it."""

    @pytest.fixture
    def kaustos(self, client, gang, hunter):
        return hire(client, gang, hunter, "Kaustos")

    def test_the_picker_offers_the_list_in_its_own_order(
        self, client, gang, kaustos, options
    ):
        body = client.get(picker_url(gang, "Kaustos")).content.decode()

        # By key rather than by name: the order is the fact, and a name
        # can appear anywhere on a page for its own reasons.
        places = [body.index(f"library.pickable:{options[h].pk}") for h in HOUSES]
        assert places == sorted(places)

    def test_the_picker_names_who_is_being_asked(self, client, gang, kaustos):
        body = client.get(picker_url(gang, "Kaustos")).content.decode()

        assert "For Kaustos." in body

    def test_one_click_settles_it(self, client, gang, kaustos, options):
        response = choose(client, gang, "Kaustos", options["Cawdor"])

        assert response.status_code == 302
        (line,) = card_of(gang, "Kaustos").questions
        assert line.chosen == "Cawdor"

    def test_the_pick_lands_on_the_fighter_and_answers_his_choice(
        self, client, gang, kaustos, options
    ):
        choose(client, gang, "Kaustos", options["Cawdor"])

        pick = Assignment.objects.get(pickable=options["Cawdor"], archived=False)
        slot = Assignment.objects.get(slot__isnull=False, miniature_root=kaustos)
        assert pick.miniature == kaustos
        assert pick.chosen_for == slot
        assert pick.caused_by == slot

    def test_the_shortfall_note_goes_with_the_choice_being_made(
        self, client, gang, kaustos, options
    ):
        choose(client, gang, "Kaustos", options["Cawdor"])

        assert card_of(gang, "Kaustos").remarks == []

    def test_the_pick_is_free(self, client, gang, kaustos, options):
        before = purse(gang)

        choose(client, gang, "Kaustos", options["Cawdor"])

        assert purse(gang) == before
        reconciled(gang)

    def test_his_equip_page_gains_the_house_list(
        self, client, gang, kaustos, options, house_lists
    ):
        item, _, _ = STOCK["Cawdor"]
        assert "House Cawdor Equipment List" not in equip_page(client, kaustos)

        choose(client, gang, "Kaustos", options["Cawdor"])

        body = equip_page(client, kaustos, house_lists["Cawdor"])
        assert "House Cawdor Equipment List" in body
        assert item in body

    def test_buying_from_it_pays_the_price_that_list_asks(
        self, client, gang, kaustos, options, house_lists
    ):
        """A list prices its own stock, and the price the list asks is
        what leaves the bank — not the figure the library prints against
        the item."""
        item, reference, here = STOCK["Cawdor"]
        choose(client, gang, "Kaustos", options["Cawdor"])
        before = purse(gang)

        response = client.post(
            f"{reverse('n26-equip', args=[kaustos.pk])}?list={house_lists['Cawdor'].pk}",
            {"thing": f"library.wargear:{Wargear.objects.get(name=item).pk}"},
        )

        assert response.status_code == 302
        assert purse(gang) == before - here
        assert reference != here  # the two prices really do differ
        assert Assignment.objects.get(wargear__name=item).miniature == kaustos
        reconciled(gang)

    def test_an_option_the_list_never_offered_is_not_settled_by_a_post(
        self, client, gang, kaustos, domain, default_pack
    ):
        """The picker re-derives its list on every submit, so a key typed
        into the form settles nothing. What an owner may still hand over
        off-list goes through the ordinary give, not through this page.
        """
        from n26.library.authoring import create_pickable

        stranger = create_pickable("Helmawr", domain)

        response = choose(client, gang, "Kaustos", stranger)

        assert response.status_code == 302
        assert not Assignment.objects.filter(pickable=stranger).exists()
        assert card_of(gang, "Kaustos").questions[0].chosen is None


class TestAChoiceThatArrivesMade:
    """Grendel, hired from the profile carrying a starting pick: the same
    assignments Kaustos ends up with, written at the hire."""

    @pytest.fixture
    def grendel(self, client, gang, squats_hunter):
        return hire(client, gang, squats_hunter, "Grendel")

    def test_his_card_reads_as_settled(self, client, gang, grendel):
        (line,) = card_of(gang, "Grendel").questions

        assert line.chosen == DEFAULT_HOUSE
        assert card_of(gang, "Grendel").remarks == []

    def test_the_pick_answers_the_choice_that_brought_it(
        self, client, gang, grendel, options
    ):
        slot = Assignment.objects.get(slot__isnull=False, miniature_root=grendel)
        pick = Assignment.objects.get(pickable=options[DEFAULT_HOUSE])

        assert (pick.chosen_for, pick.caused_by) == (slot, slot)
        assert pick.miniature == grendel

    def test_what_it_gives_is_on_his_equip_page(
        self, client, gang, grendel, house_lists
    ):
        item, _, here = STOCK[DEFAULT_HOUSE]

        assert f"House {DEFAULT_HOUSE} Equipment List" in equip_page(client, grendel)
        stocked = equip_page(client, grendel, house_lists[DEFAULT_HOUSE])
        assert item in stocked
        assert str(here) in stocked

    def test_rechoosing_swaps_it_and_the_list_follows(
        self, client, gang, grendel, options
    ):
        choose(client, gang, "Grendel", options["Cawdor"])

        (line,) = card_of(gang, "Grendel").questions
        assert line.chosen == "Cawdor"
        assert lists_on(gang, "Grendel") == ["House Cawdor Equipment List"]
        assert not Assignment.objects.filter(
            pickable=options[DEFAULT_HOUSE], archived=False
        ).exists()
        reconciled(gang)

    def test_the_swap_leaves_one_pick_and_one_choice(
        self, client, gang, grendel, options
    ):
        choose(client, gang, "Grendel", options["Cawdor"])

        assert (
            Assignment.objects.filter(
                pickable__isnull=False, archived=False, miniature_root=grendel
            ).count()
            == 1
        )
        assert len(card_of(gang, "Grendel").questions) == 1


class TestWhenTheChoiceGoes:
    """What a pick gives is held by the pick, and the pick is held by the
    choice: take away what carries the choice and the whole run of it
    retracts."""

    @pytest.fixture
    def kaustos(self, client, gang, hunter, options):
        made = hire(client, gang, hunter, "Kaustos")
        choose(client, gang, "Kaustos", options["Cawdor"])
        return made

    def test_the_fighter_leaving_takes_his_legacy_with_him(
        self, client, gang, kaustos, options
    ):
        """His membership is what carries the choice, so dismissing him
        must not leave a pick alive on the gang's books."""
        response = client.post(reverse("n26-delete-fighter", args=[kaustos.pk]), {})

        assert response.status_code == 302
        assert not Assignment.objects.filter(
            pickable=options["Cawdor"], archived=False
        ).exists()
        assert not Assignment.objects.filter(
            slot__isnull=False, archived=False, miniature_root=kaustos
        ).exists()
        reconciled(gang)

    def test_taking_the_built_in_off_changes_only_the_next_hire(
        self, author, client, gang, kaustos, hunter
    ):
        """The library page that withdraws a built-in says it changes
        what is acquired next. A fighter already carrying the choice
        keeps it; the one hired afterwards is never offered it."""
        built_in = DefaultAssignment.objects.get(
            default_set=hunter.built_ins, slot__isnull=False
        )

        posted(author, f"/n26/authoring/built-ins/{built_in.pk}/remove/", {})
        hire(client, gang, hunter, "Later")

        assert card_of(gang, "Kaustos").questions[0].chosen == "Cawdor"
        assert card_of(gang, "Later").questions == []
        reconciled(gang)


class TestTheWholePageStaysFlat:
    """The gang page is one fixed run of queries however wide the domain
    grows: eight options behind a choice must not be eight round trips,
    and neither must eighty."""

    def test_more_options_do_not_mean_more_queries(
        self, client, gang, hunter, domain, legacies, options, django_assert_num_queries
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import add_picklist_member, create_pickable

        hire(client, gang, hunter, "Kaustos")
        choose(client, gang, "Kaustos", options["Cawdor"])
        page = reverse("n26-gang", args=[gang.pk])

        with CaptureQueriesContext(connection) as few:
            assert client.get(page).status_code == 200

        for index in range(20):
            add_picklist_member(legacies, create_pickable(f"House {index}", domain))

        with django_assert_num_queries(len(few), exact=False):
            assert client.get(page).status_code == 200
