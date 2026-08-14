"""Hiring the fighters a collection offers.

A corrupted gang gains a roster nobody authored onto its gang list: the
corruption's affiliation *gives* a collection, and that collection lists
Genestealer Aberrants and Chaos Spawn at the corruption's own prices. The
hire screen has to grow a section for it, priced as the list says, the
moment the gang carries it — and take it away again when it does not.

The prices are the point. A collection entry's override is what the row
quotes, what the dialog quotes, what leaves the bank and what the gang is
worth for holding the fighter. A price typed over it is still a discount
against *that* quote, because a list's price is a price and not a deal.

The row therefore carries which entry offered it, and the server checks
the offer was really made. That is not policing the hire — any gang may
hire anything hireable at reference price, which is what the all-profiles
scope is for — it is refusing a forged price tag, exactly like a tampered
option index.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Miniature
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.library.models import Category, Collection, Profile, Section
from n26.tests.sandbox.actions import (
    add_entry,
    assign,
    create_affiliation,
    create_collection,
    create_gang_type,
    create_profile,
    ef_adds,
    found_gang,
    modifier,
    targets_gang,
)

pytestmark = pytest.mark.django_db

#: What the corruption offers, and what it asks for each. The prices are
#: the collection's own — every one of these fighters is written at a
#: different reference price, so a row quoting the reference would be
#: visibly wrong rather than accidentally right.
CORRUPTED = [("Genestealer Aberrant", 120), ("Chaos Spawn", 155)]

#: What each is written at in the library, before any list reprices it.
REFERENCE = 200


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def beasts(default_pack):
    """A home category for the corrupted fighters, so the section they
    land in has categories inside it like every other."""
    section = Section.objects.create(name="Corrupted", position=4)
    return Category.objects.create(section=section, name="Beasts", position=0)


@pytest.fixture
def corrupted_profiles(person_type, beasts, make_statline):
    """The fighters a corruption brings, authored on a gang type of their
    own — nobody's house list holds them, which is why the collection is
    the only way to them."""
    theirs = create_gang_type("Corrupted")
    made = {}
    for name, _ in CORRUPTED:
        profile = create_profile(name, person_type, theirs, price=REFERENCE)
        profile.category = beasts
        profile.save()
        make_statline(profile, movement=4, weapon_skill=3, toughness=5)
        made[name] = profile
    return made


@pytest.fixture
def corrupted_list(corrupted_profiles):
    """The collection, listing each fighter at the corruption's price."""
    collection = create_collection("Genestealer Cult Corrupted")
    for name, price in CORRUPTED:
        add_entry(collection, corrupted_profiles[name], price_override=price)
    return collection


@pytest.fixture
def corruption(corrupted_list):
    """The affiliation a corrupted gang carries: targets the gang, gives
    the collection. The recipe's own shape (library/recipes.md)."""
    affiliation = create_affiliation("Genestealer Cult Corrupted")
    modifier(
        "Corruption opens its roster",
        targets_gang(),
        ef_adds(corrupted_list),
        carried_by=affiliation,
    )
    return affiliation


@pytest.fixture
def ganger(make_profile, make_statline):
    """One ordinary fighter on the gang's own list, so the house sections
    are there to be counted against."""
    profile = make_profile("Ganger", price=55)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    return profile


@pytest.fixture
def gang(gang_type, owner, ganger):
    return found_gang("The Ashen Choir", gang_type, owner=owner, budget=1000)


@pytest.fixture
def corrupted_gang(gang, corruption):
    """The gang with the corruption taken on — the affiliation is a
    gang-hosted assignment, and its modifier does the rest."""
    assign(corruption, gang=gang)
    return gang


def hire_url(gang):
    return reverse("n26-hire-fighter", args=[gang.pk])


def sections_of(response):
    return [section.name for section in response.context["hire_list"]]


def rows_of(response, section_name):
    """Every hire entry drawn under one section, by name."""
    return {
        entry.name: entry
        for section in response.context["hire_list"]
        if section.name == section_name
        for entry in section.all_entries()
    }


def click(client, gang, key, **data):
    """Click Hire on a row, as the picker's form does."""
    return client.post(hire_url(gang), {"hire": key, **data})


def hire_through(client, gang, key, name="", **data):
    """The dialog's own submit — the request that hires."""
    return client.post(hire_url(gang), {"profile": key, "name": name, **data})


class TestTheSectionACollectionOffers:
    """A collection the gang carries is a section of the hire screen,
    named after the collection, after the house's own sections."""

    def test_a_granted_collection_of_fighters_becomes_a_section(
        self, client, owner, corrupted_gang
    ):
        client.force_login(owner)
        response = client.get(hire_url(corrupted_gang))

        assert sections_of(response)[-1] == "Genestealer Cult Corrupted"
        assert sorted(rows_of(response, "Genestealer Cult Corrupted")) == [
            "Chaos Spawn",
            "Genestealer Aberrant",
        ]

        # And on the page itself: the tab, the fighter, and the price the
        # collection asks — a section built but never drawn would pass
        # every assertion above.
        body = response.content.decode()
        assert "Genestealer Cult Corrupted" in body
        assert "Chaos Spawn" in body
        assert "155¢" in body

    def test_a_gang_without_the_carrier_is_offered_none_of_it(
        self, client, owner, gang, corruption
    ):
        """The collection exists and the fighters are hireable; this gang
        simply was never offered them, so its screen says nothing of it."""
        client.force_login(owner)
        response = client.get(hire_url(gang))

        assert "Genestealer Cult Corrupted" not in sections_of(response)
        body = response.content.decode()
        assert "Chaos Spawn" not in body

    def test_a_list_assigned_to_the_gang_reads_the_same_way(
        self, client, owner, gang, corrupted_list
    ):
        """Nothing about the section depends on a modifier having granted
        it. A list assigned to the gang by hand is carried just as much."""
        assign(corrupted_list, gang=gang)

        client.force_login(owner)
        response = client.get(hire_url(gang))
        assert sections_of(response)[-1] == "Genestealer Cult Corrupted"
        assert "Chaos Spawn" in rows_of(response, "Genestealer Cult Corrupted")

    def test_the_gangs_own_list_comes_first_and_keeps_its_rows(
        self, client, owner, corrupted_gang
    ):
        client.force_login(owner)
        response = client.get(hire_url(corrupted_gang))

        names = sections_of(response)
        assert names[-1] == "Genestealer Cult Corrupted"
        assert any("Ganger" in rows_of(response, name) for name in names[:-1]), (
            "the house's own fighters left the screen"
        )

    def test_the_rows_sit_under_their_own_home_category(
        self, client, owner, corrupted_gang
    ):
        """The collection is the heading; inside it the taxonomy still
        rules, and cheapest comes first as everywhere on this screen."""
        client.force_login(owner)
        response = client.get(hire_url(corrupted_gang))

        (section,) = [
            section
            for section in response.context["hire_list"]
            if section.name == "Genestealer Cult Corrupted"
        ]
        (category,) = section.categories
        assert category.name == "Beasts"
        assert [entry.name for entry in category.entries] == [
            "Genestealer Aberrant",
            "Chaos Spawn",
        ]

    def test_every_section_drawn_has_a_tab_and_every_row_a_category(
        self, client, owner, corrupted_gang
    ):
        """The picker's navigation: a section missing from the strip can
        never be the active tab, and a row registering under a name the
        category filter does not know is served and never shown."""
        client.force_login(owner)
        response = client.get(hire_url(corrupted_gang))

        drawn = set(sections_of(response))
        assert drawn <= set(response.context["sections"])
        registrations = {
            category.name or section.name
            for section in response.context["hire_list"]
            for category in section.categories
        }
        assert registrations <= set(response.context["categories"])

    def test_a_list_something_took_away_offers_nothing(
        self, client, owner, gang, corrupted_list, default_pack
    ):
        """A list a modifier has cancelled is not somewhere to hire from:
        the row stays in the database and stops being drawn, so the
        section goes with it — the same reading a fighter's own screens
        give a suppressed list."""
        from n26.tests.sandbox.actions import create_rule, ef_removes

        assign(corrupted_list, gang=gang)
        purged = create_rule("Purged")
        modifier(
            "The purge closes the roster",
            targets_gang(),
            ef_removes(corrupted_list),
            carried_by=purged,
        )
        assign(purged, gang=gang)

        client.force_login(owner)
        response = client.get(hire_url(gang))
        assert "Genestealer Cult Corrupted" not in sections_of(response)

    def test_a_collection_of_gear_offers_no_fighters(
        self, client, owner, gang, default_pack
    ):
        """Emptiness is the answer. A gang's equipment list is carried the
        same way and lists no profiles, so it is no part of this screen."""
        from n26.tests.sandbox.actions import create_wargear

        kit = create_collection("Corrupted Kit")
        add_entry(kit, create_wargear("Extra Arm", price=20))
        assign(kit, gang=gang)

        client.force_login(owner)
        assert "Corrupted Kit" not in sections_of(client.get(hire_url(gang)))

    def test_a_sweep_of_profiles_offers_them_at_reference(
        self, client, owner, gang, beasts, corrupted_profiles, default_pack
    ):
        """The other species of collection: a selector sweeping a category
        rather than rows written out. Swept fighters are offered at their
        own price, exactly as a swept line in a browse is."""
        swept = create_collection("Corrupted Menagerie", contains=[(Profile, beasts)])
        assign(swept, gang=gang)

        client.force_login(owner)
        response = client.get(hire_url(gang))
        rows = rows_of(response, "Corrupted Menagerie")
        assert sorted(rows) == ["Chaos Spawn", "Genestealer Aberrant"]
        assert rows["Chaos Spawn"].base_price == REFERENCE

    def test_a_fighter_nobody_hires_directly_is_not_offered(
        self, client, owner, gang, corrupted_profiles, default_pack
    ):
        """A pet arrives behind its collar. Listing it in a collection does
        not make a Hire button that could work, so no row is drawn."""
        collared = corrupted_profiles["Chaos Spawn"]
        collared.hireable = False
        collared.save(update_fields=["hireable"])
        listed = create_collection("Corrupted Pets")
        add_entry(listed, collared, price_override=10)
        assign(listed, gang=gang)

        client.force_login(owner)
        response = client.get(hire_url(gang))
        assert "Corrupted Pets" not in sections_of(response)


class TestTheCollectionsPriceIsThePrice:
    """An entry's override is what the row quotes, what the dialog
    quotes, what leaves the bank and what the gang is worth for it."""

    def test_the_row_quotes_the_collections_price(self, client, owner, corrupted_gang):
        client.force_login(owner)
        response = client.get(hire_url(corrupted_gang))
        rows = rows_of(response, "Genestealer Cult Corrupted")

        assert rows["Genestealer Aberrant"].base_price == 120
        assert rows["Chaos Spawn"].base_price == 155
        assert f"{REFERENCE}¢" not in response.content.decode()

    def test_the_dialog_quotes_it_too(self, client, owner, corrupted_gang):
        client.force_login(owner)
        key = self.key(client, corrupted_gang, "Genestealer Aberrant")
        body = client.get(f"{hire_url(corrupted_gang)}?hire={key}").content.decode()

        assert "Hire a Genestealer Aberrant" in body
        assert "120¢" in body
        assert 'value="120"' in body  # the price box, pre-filled with the quote

    def test_hiring_through_the_section_charges_the_collections_price(
        self, client, owner, corrupted_gang
    ):
        client.force_login(owner)
        key = self.key(client, corrupted_gang, "Genestealer Aberrant")
        before = corrupted_gang.credits

        response = hire_through(client, corrupted_gang, key, name="Grist")
        assert response.status_code == 302

        entry = Miniature.objects.get(name="Grist").membership.ledger_entry
        assert entry.paid == 120
        assert entry.list_price == 120
        assert entry.rating_contribution == 120
        assert entry.discount == 0
        corrupted_gang.refresh_from_db()
        assert corrupted_gang.credits == before - 120
        assert corrupted_gang.rating == 120
        assert_reconciled(corrupted_gang)

    def test_the_ledger_says_which_row_it_was_bought_through(
        self, client, owner, corrupted_gang, corrupted_list
    ):
        """The money's provenance, as a shop purchase records it."""
        client.force_login(owner)
        key = self.key(client, corrupted_gang, "Chaos Spawn")
        hire_through(client, corrupted_gang, key, name="Thing")

        entry = Miniature.objects.get(name="Thing").membership.ledger_entry
        assert entry.bought_from is not None
        assert entry.bought_from.collection == corrupted_list
        corrupted_gang.refresh_from_db()
        assert_reconciled(corrupted_gang)

    def test_the_same_fighter_hired_off_the_all_scope_is_the_reference_price(
        self, client, owner, corrupted_gang, corrupted_profiles
    ):
        """The override belongs to the list, not to the fighter: reached
        any other way, the fighter costs what the library says."""
        client.force_login(owner)
        hire_through(
            client,
            corrupted_gang,
            str(corrupted_profiles["Genestealer Aberrant"].pk),
            name="Plain",
            list="all",
        )

        entry = Miniature.objects.get(name="Plain").membership.ledger_entry
        assert entry.paid == REFERENCE
        assert entry.bought_from is None
        corrupted_gang.refresh_from_db()
        assert_reconciled(corrupted_gang)

    def test_a_blank_override_offers_the_usual_price(
        self, client, owner, gang, corrupted_profiles, default_pack
    ):
        """A blank override is an answer, not a gap: it says "at the usual
        price", which is the commonest thing an author writes."""
        plain = create_collection("Corrupted Roster")
        add_entry(plain, corrupted_profiles["Chaos Spawn"])
        assign(plain, gang=gang)

        client.force_login(owner)
        response = client.get(hire_url(gang))
        assert rows_of(response, "Corrupted Roster")["Chaos Spawn"].base_price == (
            REFERENCE
        )

    def test_the_card_behind_the_row_is_drawn_at_the_same_price(
        self, client, owner, corrupted_gang
    ):
        """A card saying 200 under a row saying 120 is a number that has
        quietly stopped being true."""
        client.force_login(owner)
        response = client.get(hire_url(corrupted_gang))
        entry = rows_of(response, "Genestealer Cult Corrupted")["Genestealer Aberrant"]
        address = entry.default_option.card_url
        assert "entry=" in address

        body = client.get(address).content.decode()
        assert "120¢" in body
        assert f"{REFERENCE}¢" not in body

    def test_a_typed_price_is_still_a_discount_against_that_quote(
        self, client, owner, corrupted_gang
    ):
        """The dialog's box is the shop's control: what is typed is what
        leaves the bank, while the collection's price stays the list price
        and the rating — a haggled fighter is not a lesser fighter."""
        client.force_login(owner)
        key = self.key(client, corrupted_gang, "Genestealer Aberrant")
        before = corrupted_gang.credits

        hire_through(client, corrupted_gang, key, name="Cheap", paid="90")

        entry = Miniature.objects.get(name="Cheap").membership.ledger_entry
        assert entry.paid == 90
        assert entry.list_price == 120
        assert entry.discount == 30
        assert entry.rating_contribution == 120
        corrupted_gang.refresh_from_db()
        assert corrupted_gang.credits == before - 90
        assert corrupted_gang.rating == 120
        assert_reconciled(corrupted_gang)

    def key(self, client, gang, name):
        """What the row for ``name`` in the corruption's section submits as.

        Read off the page rather than composed here: the identity a click
        carries is the page's own, and a test that built its own could
        pass against a server nothing on screen can reach.
        """
        response = client.get(hire_url(gang))
        rows = rows_of(response, "Genestealer Cult Corrupted")
        found = rows[name]
        assert found.key in response.content.decode()
        return found.key


class TestAForgedPriceTag:
    """The offer a click names is checked, never trusted: the entry must
    exist, name that fighter, and belong to a collection this gang really
    carries. Anything else is a broken link."""

    def test_an_entry_from_a_list_the_gang_does_not_carry_is_refused(
        self, client, owner, gang, corrupted_list, corrupted_profiles
    ):
        aberrant = corrupted_profiles["Genestealer Aberrant"]
        forged = corrupted_list.entries.get(profile=aberrant)

        client.force_login(owner)
        key = f"{aberrant.pk}-{forged.pk}"
        assert client.get(f"{hire_url(gang)}?hire={key}").status_code == 404
        assert click(client, gang, key).status_code == 404
        assert hire_through(client, gang, key, name="Sneaky").status_code == 404
        assert not Miniature.objects.filter(membership__gang=gang).exists()

    def test_an_entry_naming_another_fighter_is_refused(
        self, client, owner, corrupted_gang, corrupted_list, corrupted_profiles
    ):
        """The cheap row's price on the dear fighter: the entry is carried
        and real, and it does not name this profile."""
        cheap = corrupted_list.entries.get(
            profile=corrupted_profiles["Genestealer Aberrant"]
        )
        dear = corrupted_profiles["Chaos Spawn"]

        client.force_login(owner)
        key = f"{dear.pk}-{cheap.pk}"
        assert hire_through(
            client, corrupted_gang, key, name="Bargain"
        ).status_code == (404)
        assert not Miniature.objects.filter(name="Bargain").exists()

    def test_an_entry_that_does_not_exist_is_refused(
        self, client, owner, corrupted_gang, corrupted_profiles
    ):
        aberrant = corrupted_profiles["Genestealer Aberrant"]
        client.force_login(owner)
        for tail in ("nonsense", "01JQK000000000000000000000"):
            response = hire_through(
                client, corrupted_gang, f"{aberrant.pk}-{tail}", name="Ghost"
            )
            assert response.status_code == 404
        assert not Miniature.objects.filter(name="Ghost").exists()

    def test_hiring_at_reference_price_is_never_refused(
        self, client, owner, gang, corrupted_profiles
    ):
        """The line held here is the price tag, not the hire: any gang may
        hire any hireable fighter, and the all-profiles scope says so."""
        client.force_login(owner)
        response = hire_through(
            client,
            gang,
            str(corrupted_profiles["Chaos Spawn"].pk),
            name="Poached",
        )
        assert response.status_code == 302
        assert Miniature.objects.get(name="Poached").membership.ledger_entry.paid == (
            REFERENCE
        )
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestOptionsOnACollectionsRow:
    """A collection prices the fighter, not what the fighter is built
    with: an option still adds its own surcharge on top, and the row's
    controls travel through the click exactly as they do anywhere."""

    @pytest.fixture
    def armed(self, corrupted_profiles, default_pack):
        from n26.tests.sandbox.actions import (
            create_default_set,
            create_wargear,
            offer_option,
        )

        aberrant = corrupted_profiles["Genestealer Aberrant"]
        offer_option(aberrant, "As standard", price=0, position=0)
        offer_option(
            aberrant,
            "With a heavy rock drill",
            default_set=create_default_set(
                "Rock drill", members=[create_wargear("Heavy rock drill")], price=25
            ),
            position=1,
        )
        return aberrant

    def test_the_surcharge_lands_on_top_of_the_collections_price(
        self, client, owner, corrupted_gang, armed
    ):
        client.force_login(owner)
        response = client.get(hire_url(corrupted_gang))
        entry = rows_of(response, "Genestealer Cult Corrupted")["Genestealer Aberrant"]

        assert entry.base_price == 120
        assert [option.total_price for option in entry.options] == [120, 145]

    def test_a_click_carries_the_pick_and_the_offer_together(
        self, client, owner, corrupted_gang, armed
    ):
        """Both halves of the row's answer ride the redirect: the option
        ticked and the offer it was ticked under."""
        from django.utils.text import slugify

        client.force_login(owner)
        response = client.get(hire_url(corrupted_gang))
        key = rows_of(response, "Genestealer Cult Corrupted")[
            "Genestealer Aberrant"
        ].key
        scoped = f"{slugify(key)}:0"

        clicked = click(client, corrupted_gang, key, **{scoped: "1"})
        assert clicked.status_code == 302
        assert f"hire={key}" in clicked.url

        body = client.get(clicked.url).content.decode()
        assert "145¢" in body
        assert "With a heavy rock drill" in body

    def test_the_option_is_charged_with_the_collections_price(
        self, client, owner, corrupted_gang, armed
    ):
        from django.utils.text import slugify

        client.force_login(owner)
        response = client.get(hire_url(corrupted_gang))
        key = rows_of(response, "Genestealer Cult Corrupted")[
            "Genestealer Aberrant"
        ].key

        hire_through(
            client,
            corrupted_gang,
            key,
            name="Driller",
            **{f"{slugify(key)}:0": "1"},
        )
        fighter = Miniature.objects.get(name="Driller")
        assert fighter.membership.ledger_entry.paid == 145
        # The set the option names materialises as the hire's own kit, so
        # what was paid for is on the card.
        assert "Heavy rock drill" in [
            line.name for line in build_model_card(fighter).equipment
        ]
        corrupted_gang.refresh_from_db()
        assert_reconciled(corrupted_gang)

    @pytest.fixture
    def mutated(self, armed, default_pack):
        """A second set of options on the same row, so a selection can be
        more than one answer — which is what the card behind the row has
        to price."""
        from n26.tests.sandbox.actions import (
            create_default_set,
            create_option_group,
            create_wargear,
            offer_option,
        )

        group = create_option_group(armed, "Mutations", choose="any")
        horns = create_default_set(
            "Iron horns", members=[create_wargear("Iron horns")], price=15
        )
        offer_option(armed, "Iron horns", default_set=horns, group=group)
        return armed, horns

    def test_the_card_for_a_selection_is_priced_the_collections_way(
        self, client, owner, corrupted_gang, mutated
    ):
        """The collection's price stands in for the fighter's own and for
        nothing else, so every option ticked still adds on top — and the
        card the row is showing has to say the number the dialog will."""
        aberrant, horns = mutated
        drill = aberrant.grouped_options()[0][1][1]

        client.force_login(owner)
        response = client.get(hire_url(corrupted_gang))
        row = rows_of(response, "Genestealer Cult Corrupted")["Genestealer Aberrant"]

        address = (
            f"{row.card_url}&option={drill.pk}&option={horns.pk}"
            if "?" in row.card_url
            else f"{row.card_url}?option={drill.pk}&option={horns.pk}"
        )
        card = client.get(address).context["card"]

        quoted = aberrant.price_with([drill, horns], base=120)
        assert quoted == 160
        assert card.rating == quoted
        assert [line.name for line in card.equipment] == [
            "Heavy rock drill",
            "Iron horns",
        ]

    def test_the_rows_address_names_the_offer_and_nothing_else(
        self, client, owner, corrupted_gang, mutated
    ):
        """What the row's own address carries is the offer — which list is
        pricing this fighter. The selection is added to it by the controls,
        so the two answers stay separate: one is where the price comes
        from, the other is what was ticked."""
        client.force_login(owner)
        response = client.get(hire_url(corrupted_gang))
        row = rows_of(response, "Genestealer Cult Corrupted")["Genestealer Aberrant"]

        assert f"entry={row.entry.pk}" in row.card_url
        assert "option=" not in row.card_url


class TestTheQueryBudget:
    """The invariance the whole screen is built on: a gang carrying six
    collections of fighters costs what a gang carrying one does."""

    def another_corruption(self, gang, corrupted_profiles, number):
        """One more collection of the same fighters, carried by the gang."""
        extra = create_collection(f"Another Corruption {number}")
        for name, price in CORRUPTED:
            add_entry(extra, corrupted_profiles[name], price_override=price + number)
        assign(extra, gang=gang)
        return extra

    def test_more_carried_collections_cost_no_more_queries(
        self, client, owner, corrupted_gang, corrupted_profiles, beasts, default_pack
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(owner)

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert client.get(hire_url(corrupted_gang)).status_code == 200
            return len(captured.captured_queries)

        # One collection first, and one request discarded: the count is
        # about *growth*, and both a gang's first carried list and the
        # content-type table's first read are one-off steps a real
        # per-collection query could otherwise hide inside.
        self.another_corruption(corrupted_gang, corrupted_profiles, 0)
        measure()

        one = measure()

        for number in range(1, 6):
            self.another_corruption(corrupted_gang, corrupted_profiles, number)

        response = client.get(hire_url(corrupted_gang))
        assert len(sections_of(response)) >= 7
        assert measure() == one

    def test_more_offered_fighters_cost_no_more_queries(
        self, client, owner, corrupted_gang, corrupted_list, person_type, make_statline
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(owner)

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert client.get(hire_url(corrupted_gang)).status_code == 200
            return len(captured.captured_queries)

        # One request discarded first: the content-type table is read once
        # per process and cached, and counting that warming as this page's
        # work would let a real per-profile query hide inside it.
        measure()

        few = measure()

        theirs = Collection.objects.get(pk=corrupted_list.pk)
        gang_type = create_gang_type("Corrupted Too")
        for number in range(8):
            profile = create_profile(
                f"Spawn {number}", person_type, gang_type, price=REFERENCE
            )
            make_statline(profile, movement=4, weapon_skill=3, toughness=5)
            add_entry(theirs, profile, price_override=100 + number)

        response = client.get(hire_url(corrupted_gang))
        assert len(rows_of(response, "Genestealer Cult Corrupted")) == 10
        assert measure() == few
