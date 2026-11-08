"""Held collections add hireable profiles to the hiring screen at their listed prices.

Collections can be stored assignments or computed grants. Their entry prices
appear in rows, previews and dialogs and become the acquisition's list price
and default rating. Typed payments record a discount against that quote.

The server validates that a submitted entry offers the profile and belongs
to a held collection. Hiring through the unrestricted profile list uses the
reference price instead.
"""

from uuid import uuid4

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

#: Collection prices differ from the reference price to expose incorrect quoting.
CORRUPTED = [("Genestealer Aberrant", 120), ("Chaos Spawn", 155)]

#: What each is written at in the library, before any list reprices it.
REFERENCE = 200


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def beasts(default_pack):
    """Create a category for profiles offered through the corruption collection."""
    section = Section.objects.create(name="Corrupted", position=4)
    return Category.objects.create(section=section, name="Beasts", position=0)


@pytest.fixture
def corrupted_profiles(person_type, beasts, make_statline):
    """Create hireable profiles on another gang type to exercise collection access."""
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
    """Grant the hiring collection through a gang-scoped affiliation modifier."""
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
    """Create an ordinary profile so the gang's own hiring sections remain represented."""
    profile = make_profile("Ganger", price=55)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    return profile


@pytest.fixture
def gang(gang_type, owner, ganger):
    return found_gang("The Ashen Choir", gang_type, owner=owner, budget=1000)


@pytest.fixture
def corrupted_gang(gang, corruption):
    """Assign the affiliation to the gang so its modifier grants collection access."""
    assign(corruption, gang=gang)
    return gang


def hire_url(gang):
    return reverse("n26-hire-fighter", args=[gang.pk])


def sections_of(response):
    return [section.name for section in response.context["hire_list"]]


def rows_of(response, section_name):
    """Return hiring entries from one named section indexed by profile name."""
    return {
        entry.name: entry
        for section in response.context["hire_list"]
        if section.name == section_name
        for entry in section.all_entries()
    }


def click(client, gang, key, **data):
    """Submit a hiring-row selection with its option fields."""
    return client.post(hire_url(gang), {"hire": key, **data})


def hire_through(client, gang, key, name="", **data):
    """Submit the hiring dialog payload."""
    return client.post(
        hire_url(gang),
        {"request_key": str(uuid4()), "profile": key, "name": name, **data},
    )


class TestTheSectionACollectionOffers:
    """Append held profile collections after the gang's own hiring sections."""

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

        # Check rendered content as well as the prepared section structures.
        body = response.content.decode()
        assert "Genestealer Cult Corrupted" in body
        assert "Chaos Spawn" in body
        assert "155¢" in body

    def test_a_gang_without_the_carrier_is_offered_none_of_it(
        self, client, owner, gang, corruption
    ):
        """The default screen must omit collections the gang does not hold."""
        client.force_login(owner)
        response = client.get(hire_url(gang))

        assert "Genestealer Cult Corrupted" not in sections_of(response)
        body = response.content.decode()
        assert "Chaos Spawn" not in body

    def test_a_list_assigned_to_the_gang_reads_the_same_way(
        self, client, owner, gang, corrupted_list
    ):
        """Stored collection assignments provide the same hiring access as computed grants."""
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
        """Group collection profiles by category and order entries by price."""
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
        """Register every displayed section and category so filtering cannot hide otherwise valid rows."""
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
        """Suppressing a held collection removes its hiring section without deleting the assignment."""
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
        """Omit collections containing no profiles from the hiring screen."""
        from n26.tests.sandbox.actions import create_wargear

        kit = create_collection("Corrupted Kit")
        add_entry(kit, create_wargear("Extra Arm", price=20))
        assign(kit, gang=gang)

        client.force_login(owner)
        assert "Corrupted Kit" not in sections_of(client.get(hire_url(gang)))

    def test_a_sweep_of_profiles_offers_them_at_reference(
        self, client, owner, gang, beasts, corrupted_profiles, default_pack
    ):
        """Profile sweeps use reference prices when there are no entry overrides."""
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
        """Listing a non-hireable profile must not expose a hiring action."""
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
    """Use the collection quote consistently for rows, dialogs, payment and default rating."""

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
        """Record the collection entry as the acquisition's price source."""
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
        """Apply entry overrides only when hiring through that collection."""
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
        """A blank entry override uses the profile's reference price."""
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
        """The preview card must use the same collection price as its hiring row."""
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
        """Typed payment changes credits spent while preserving the collection quote as list price and rating."""
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
        """Read the submitted entry key from the rendered row to test a reachable UI action."""
        response = client.get(hire_url(gang))
        rows = rows_of(response, "Genestealer Cult Corrupted")
        found = rows[name]
        assert found.key in response.content.decode()
        return found.key


class TestAForgedPriceTag:
    """Validate the submitted entry's existence, profile and collection access before using its price."""

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
        """Reject a valid entry ID paired with a different profile."""
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
        """A hireable profile remains available at reference price without collection access."""
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
    """Option surcharges add to the collection's base profile price."""

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
        """Preserve the selected option and collection entry through the dialog redirect."""
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
        # The chosen option must materialise its equipment on the hired model.
        assert "Heavy rock drill" in [
            line.name for line in build_model_card(fighter).equipment
        ]
        corrupted_gang.refresh_from_db()
        assert_reconciled(corrupted_gang)

    @pytest.fixture
    def mutated(self, armed, default_pack):
        """Add another option group to test preview pricing for multiple selections."""
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
        """Price the preview from the collection base plus every selected option surcharge."""
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
        """Keep collection entry identity in the base card URL and let controls add selected options."""
        client.force_login(owner)
        response = client.get(hire_url(corrupted_gang))
        row = rows_of(response, "Genestealer Cult Corrupted")["Genestealer Aberrant"]

        assert f"entry={row.entry.pk}" in row.card_url
        assert "option=" not in row.card_url


class TestTheQueryBudget:
    """Adding held profile collections must not increase hiring-page queries."""

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

        # Warm collection and content-type caches before comparing query growth.
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

        # Warm the content-type cache before comparing query growth.
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
