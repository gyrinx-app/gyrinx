"""Collections: equipment lists and trading posts, per design/collections.md.

The load-bearing ideas under test:

* reference price (credits + TP + exclusivity) is the item's own data —
  every kind, no special cases;
* a collection is itself an assignable, so *having* a list is an ordinary
  assignment: built-ins, gang-hosted, or computed grant;
* curated and derived collections browse to the same shape through the
  same pricing function;
* operations never consult collections — an entry pre-fills a purchase,
  the get-out is its absence.
"""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from n26.core.access import collections_for
from n26.core.browse import TRADING_POST, browse
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.library.models import price_of
from n26.tests.sandbox.actions import (
    adds,
    assign,
    buy,
    create_category,
    create_collection,
    create_default_set,
    create_wargear,
    create_weapon,
    found_gang,
    hire_with_option,
    modifier,
    remove,
    targets_model,
)

pytestmark = pytest.mark.django_db


def browse_the_post():
    """The default Trading Post, authored once per test database (two
    sweeps: every weapon, every wargear) — and shopped on TRADING_POST terms,
    because being a trading post is how you shop it, not what it is."""
    from n26.library.models import Collection
    from n26.tests.sandbox.actions import create_trading_post

    post = Collection.objects.filter(name="Trading Post").first()
    return browse(post or create_trading_post(), TRADING_POST)


@pytest.fixture
def player():
    return User.objects.create_user("tom")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)


@pytest.fixture
def fighter(gang, make_profile):
    return hire_with_option(gang, make_profile("Escher Ganger", price=55), "Yolanda")


@pytest.fixture
def taxonomy(db):
    return {
        "auto": create_category("Ranged Weapons", "Auto/Stub Weapons", position=0),
        "las": create_category("Ranged Weapons", "Las Weapons", position=1),
        "armour": create_category("Armour", "Armour", position=10),
    }


@pytest.fixture
def catalogue(taxonomy):
    """A few priced items with homes — a miniature reference library.

    The guns carry TP prices (0 is a real price — free to order) because
    being at the Trading Post *is* having one; the heirloom is Exclusive
    and the sweep never sees it."""
    autogun = create_weapon(
        "Autogun",
        profiles=[("Standard", 0)],
        price=20,
        trade_point_price=0,
        category=taxonomy["auto"],
    )
    lasgun = create_weapon(
        "Lasgun",
        profiles=[("Las bolt", 0)],
        price=15,
        trade_point_price=0,
        category=taxonomy["las"],
    )
    mesh = create_wargear(
        "Mesh Armour", price=15, trade_point_price=1, category=taxonomy["armour"]
    )
    heirloom = create_wargear(
        "House Heirloom Blade-Charm",
        price=40,
        is_exclusive=True,
        category=taxonomy["armour"],
    )
    return {"autogun": autogun, "lasgun": lasgun, "mesh": mesh, "heirloom": heirloom}


class TestReferencePricing:
    def test_every_kind_is_priced_and_starts_off_the_post(self, make_profile):
        """Zero credits by default — and no TP at all: blank means not
        offered at the Trading Post, which is different from TP 0."""
        from n26.tests.sandbox.actions import create_skill, create_subtype

        for thing in (
            create_skill("Fast Shot"),
            create_subtype("Wyrd"),
            create_wargear("Rope"),
        ):
            assert thing.price == 0
            assert thing.trade_point_price is None
            assert thing.is_exclusive is False

    def test_the_printed_pair_is_captured(self, catalogue):
        price = price_of(catalogue["mesh"])
        assert (price.credits, price.trade_points) == (15, 1)
        assert str(price) == "15cr / TP 1"

    def test_exclusive_reads_as_e(self, catalogue):
        assert str(price_of(catalogue["heirloom"])) == "40cr / TP E"

    def test_exclusive_with_a_tp_price_is_unauthorable(self, db):
        """TP "E" and a TP price are contradictory facts — refused at the
        database; is_exclusive wins if code ever has to choose."""
        with pytest.raises(IntegrityError), transaction.atomic():
            create_wargear("Nonsense", trade_point_price=3, is_exclusive=True)

    def test_ammo_prices_its_own_row(self, taxonomy):
        """The book prints per-profile creds and TP — warp rounds cost TP 4
        on an autogun that costs TP 0."""
        gun = create_weapon(
            "Autogun",
            profiles=[("Standard", 0), ("Warp round", 10)],
            price=20,
            trade_point_price=0,
            category=taxonomy["auto"],
        )
        warp = gun.profiles.get(name="Warp round")
        warp.trade_point_price = 4
        warp.save(update_fields=["trade_point_price"])
        assert str(price_of(warp)) == "10cr / TP 4"
        assert str(price_of(gun)) == "20cr / TP 0"


class TestTheHomeCategory:
    def test_an_item_sorts_the_same_wherever_it_appears(self, catalogue):
        """Two lists carry the autogun; both group it identically."""
        first = create_collection("List A", entries=[catalogue["autogun"]])
        second = create_collection("List B", entries=[catalogue["autogun"]])

        for collection in (first, second):
            view = browse(collection)
            assert view.sections[0].name == "Ranged Weapons"
            assert view.sections[0].categories[0].name == "Auto/Stub Weapons"

    def test_a_homeless_item_still_shows(self, db):
        stray = create_wargear("Odd Trinket", price=5)
        view = browse(create_collection("Oddments", entries=[stray]))
        (line,) = list(view.all_lines())
        assert line.name == "Odd Trinket"
        assert view.sections[-1].name == ""


class TestCuratedPricing:
    def test_an_entry_without_overrides_sells_at_reference(self, catalogue):
        house_list = create_collection("House List", entries=[catalogue["autogun"]])
        (line,) = list(browse(house_list).all_lines())
        assert (line.credits, line.trade_points) == (20, 0)

    def test_a_price_override_wins_without_touching_tp(self, catalogue):
        house_list = create_collection(
            "House List", entries=[(catalogue["mesh"], {"price_override": 10})]
        )
        (line,) = list(browse(house_list).all_lines())
        assert (line.credits, line.trade_points) == (10, 1)

    def test_the_overrides_are_independent(self, catalogue):
        house_list = create_collection(
            "Variant Post",
            entries=[(catalogue["mesh"], {"trade_point_override": 0})],
        )
        (line,) = list(browse(house_list).all_lines())
        assert (line.credits, line.trade_points) == (15, 0)

    def test_an_exclusive_item_may_be_listed(self, catalogue):
        """Exclusive means "list only", not "nowhere" — the list is exactly
        where it lives."""
        house_list = create_collection("House List", entries=[catalogue["heirloom"]])
        (line,) = list(browse(house_list).all_lines())
        assert line.is_exclusive is True


class TestTheDerivedTradingPost:
    def test_it_carries_everything_not_exclusive_at_reference(self, catalogue):
        lines = {line.name: line for line in browse_the_post().all_lines()}
        assert set(lines) == {"Autogun", "Lasgun", "Mesh Armour"}
        assert (lines["Mesh Armour"].credits, lines["Mesh Armour"].trade_points) == (
            15,
            1,
        )

    def test_exclusive_items_are_simply_absent(self, catalogue):
        names = [line.name for line in browse_the_post().all_lines()]
        assert "House Heirloom Blade-Charm" not in names

    def test_both_species_browse_to_the_same_shape(self, catalogue):
        """A UI drawing one can draw the other — same structure, no entry
        required."""
        curated = browse(create_collection("List", entries=[catalogue["autogun"]]))
        derived = browse_the_post()

        for view in (curated, derived):
            section = view.sections[0]
            assert section.name == "Ranged Weapons"
            line = section.categories[0].lines[0]
            assert line.name == "Autogun"
            assert (line.credits, line.trade_points) == (20, 0)
        assert curated.all_lines().__next__().entry is not None
        assert derived.all_lines().__next__().entry is None

    def test_grouping_follows_taxonomy_order(self, catalogue):
        view = browse_the_post()
        assert [section.name for section in view.sections] == [
            "Ranged Weapons",
            "Armour",
        ]
        assert [c.name for c in view.sections[0].categories] == [
            "Auto/Stub Weapons",
            "Las Weapons",
        ]


class TestBuying:
    def test_through_an_entry_the_list_price_prefills(self, fighter, catalogue):
        house_list = create_collection(
            "House List", entries=[(catalogue["mesh"], {"price_override": 10})]
        )
        (line,) = list(browse(house_list).all_lines())

        assignment = buy(fighter, entry=line.entry)

        entry = assignment.ledger_entry
        assert entry.paid == 10
        assert entry.bought_from == line.entry
        assert entry.trade_points == 0  # list purchases cost no TP

    def test_a_bought_weapon_still_gets_its_free_profiles(self, fighter, catalogue):
        house_list = create_collection("House List", entries=[catalogue["autogun"]])
        (line,) = list(browse(house_list).all_lines())

        buy(fighter, entry=line.entry)
        card = build_model_card(fighter)
        (weapon,) = card.weapons
        assert weapon.name == "Autogun"
        assert weapon.profiles

    def test_trade_points_are_recorded_when_spent(self, fighter, catalogue):
        """The visit flow is deferred, so TP arrives explicitly — and is
        remembered, which is what makes refunds computable later."""
        assignment = buy(fighter, thing=catalogue["mesh"], trade_points=1)
        assert assignment.ledger_entry.trade_points == 1

    def test_the_gang_adds_up_after_list_purchases(self, gang, fighter, catalogue):
        house_list = create_collection("House List", entries=[catalogue["autogun"]])
        (line,) = list(browse(house_list).all_lines())
        buy(fighter, entry=line.entry)

        gang.refresh_from_db()
        assert gang.rating == 55 + 20
        assert gang.credits == 1000 - 55 - 20
        assert_reconciled(gang)

    def test_the_get_out_is_the_same_call_with_no_entry(self, fighter, catalogue):
        """ "Yeah but I want to buy something weird" — off-list, odd price.
        Nothing checks; the ledger just remembers what happened."""
        assignment = buy(fighter, thing=catalogue["heirloom"], paid=25)

        entry = assignment.ledger_entry
        assert entry.paid == 25
        assert entry.bought_from is None

    def test_the_price_can_be_overridden_at_the_till(self, fighter, catalogue):
        house_list = create_collection("House List", entries=[catalogue["mesh"]])
        (line,) = list(browse(house_list).all_lines())

        assignment = buy(fighter, entry=line.entry, paid=3, note="haggled")
        assert assignment.ledger_entry.paid == 3
        assert assignment.ledger_entry.bought_from == line.entry


class TestHavingAList:
    """Having a list is an assignment — never a table of its own."""

    def test_the_profile_s_list_arrives_at_hire(self, gang, make_profile, catalogue):
        house_list = create_collection("Venator List", entries=[catalogue["autogun"]])
        profile = make_profile("Hunt Champion", price=100)
        profile.built_ins = create_default_set("Champion kit", members=[house_list])
        profile.save()

        fighter = hire_with_option(gang, profile, "Kora")

        (access,) = collections_for(fighter)
        assert access.collection == house_list
        assert access.source == "Hunt Champion"
        assert access.computed is False

    def test_the_gang_s_shared_list_reaches_every_fighter(
        self, gang, fighter, catalogue
    ):
        shared = create_collection("House List", entries=[catalogue["autogun"]])
        assign(shared, gang=gang, paid=0)

        (access,) = collections_for(fighter)
        assert access.collection == shared
        assert access.source == str(gang)

    def test_a_computed_grant_appears_and_disappears(self, gang, fighter, catalogue):
        """Tech Bazaar's standing Trading Post access: granted by a carried
        thing, gone when it goes."""
        variant_post = create_collection("Bazaar Post", entries=[catalogue["mesh"]])
        charm = create_wargear("Bazaar Token")
        modifier(
            "Token grants Bazaar access",
            targets_model(),
            adds(variant_post),
            carried_by=charm,
        )
        carried = assign(charm, miniature=fighter)

        (access,) = collections_for(fighter)
        assert access.collection == variant_post
        assert access.computed is True
        assert access.source == "Bazaar Token"

        remove(carried)
        assert collections_for(fighter) == []

    def test_the_card_draws_lists_apart_from_equipment(
        self, gang, make_profile, catalogue
    ):
        from n26.core.render_text import render_model_card

        house_list = create_collection("Venator List", entries=[catalogue["autogun"]])
        profile = make_profile("Hunt Champion", price=100)
        profile.built_ins = create_default_set("Champion kit", members=[house_list])
        profile.save()
        fighter = hire_with_option(gang, profile, "Kora")

        card = build_model_card(fighter)
        assert [line.name for line in card.collections] == ["Venator List"]
        assert card.equipment == []

        text = "\n".join(render_model_card(card))
        print("\n" + text)
        assert "Buys from: Venator List" in text

    def test_two_sources_of_the_same_list_collapse(self, gang, fighter, catalogue):
        shared = create_collection("House List", entries=[catalogue["autogun"]])
        assign(shared, gang=gang, paid=0)
        assign(shared, miniature=fighter, paid=0)

        assert len(collections_for(fighter)) == 1


class TestRatingFollowsTheRule:
    """A discount leaves the rating at full price; a list's
    own price IS the price, so it is also the rating; and the number
    written at purchase is pinned on that assignment forever."""

    def test_a_discount_counts_at_full_rating(self, gang, fighter, catalogue):
        """Paid 10 for a 15cr item on a deal — it is still a 15cr item."""
        assignment = buy(fighter, thing=catalogue["mesh"], paid=10, discount=5)

        entry = assignment.ledger_entry
        assert entry.paid == 10
        assert entry.list_price == 15
        assert entry.rating_contribution == 15

        gang.refresh_from_db()
        assert gang.rating == 55 + 15
        assert gang.credits == 1000 - 55 - 10
        assert_reconciled(gang)

    def test_a_list_price_is_the_rating(self, gang, fighter, catalogue):
        """Cheaper for this gang is not a discount — it is the price."""
        house_list = create_collection(
            "House List", entries=[(catalogue["mesh"], {"price_override": 10})]
        )
        (line,) = list(browse(house_list).all_lines())
        assignment = buy(fighter, line)

        entry = assignment.ledger_entry
        assert entry.paid == 10
        assert entry.rating_contribution == 10  # not the reference 15

    def test_the_price_is_pinned_forever(self, gang, fighter, catalogue):
        """Repricing the list later never re-prices what was bought."""
        from n26.core.reconcile import repin_everything

        house_list = create_collection(
            "House List", entries=[(catalogue["mesh"], {"price_override": 10})]
        )
        (line,) = list(browse(house_list).all_lines())
        assignment = buy(fighter, line)

        line.entry.price_override = 99
        line.entry.save(update_fields=["price_override"])
        catalogue["mesh"].price = 99
        catalogue["mesh"].save(update_fields=["price"])
        repin_everything(gang)

        gang.refresh_from_db()
        assert assignment.ledger_entry.rating_contribution == 10
        assert gang.rating == 55 + 10
        assert_reconciled(gang)


class TestBuyingALine:
    """What browsing produced is the purchase — nothing is disassembled."""

    def test_a_line_is_the_whole_purchase(self, fighter, catalogue):
        house_list = create_collection(
            "House List", entries=[(catalogue["mesh"], {"price_override": 10})]
        )
        (line,) = list(browse(house_list).all_lines())

        assignment = buy(fighter, line)

        entry = assignment.ledger_entry
        assert entry.paid == 10
        assert entry.bought_from == line.entry
        # The list shows a TP value but never charges it.
        assert entry.trade_points == 0

    def test_a_post_line_charges_its_trade_points(self, fighter, catalogue):
        line = next(
            ln for ln in browse_the_post().all_lines() if ln.name == "Mesh Armour"
        )
        assignment = buy(fighter, line)

        entry = assignment.ledger_entry
        assert entry.paid == 15
        assert entry.trade_points == 1  # no longer droppable by omission
        assert entry.bought_from is None  # a derived collection has no rows

    def test_curated_and_derived_lines_buy_identically(self, fighter, catalogue):
        """The interchangeability the CollectionView shape promises."""
        curated = create_collection("List", entries=[catalogue["autogun"]])
        for line in (
            next(iter(browse(curated).all_lines())),
            next(ln for ln in browse_the_post().all_lines() if ln.name == "Autogun"),
        ):
            assignment = buy(fighter, line)
            assert assignment.ledger_entry.paid == line.credits

    def test_the_till_still_overrides_anything(self, fighter, catalogue):
        line = next(
            ln for ln in browse_the_post().all_lines() if ln.name == "Mesh Armour"
        )
        assignment = buy(fighter, line, paid=3, trade_points=0, note="haggled hard")
        assert assignment.ledger_entry.paid == 3
        assert assignment.ledger_entry.trade_points == 0


class TestSelling:
    """A sale is the third act, and none of the other two: the thing goes,
    and half of what it is *worth* comes back — never half of what was paid
    for it, because those two part company at the first discount."""

    def test_half_of_what_it_is_worth_lands_in_the_bank(self, gang, fighter, catalogue):
        from n26.tests.sandbox.actions import sell

        assignment = buy(fighter, thing=catalogue["autogun"], paid=20)
        gang.refresh_from_db()
        assert gang.credits == 1000 - 55 - 20

        assert sell(assignment) == 10

        gang.refresh_from_db()
        assert gang.credits == 1000 - 55 - 20 + 10
        # The gun stops counting the moment it is gone; the fighter is worth
        # their hire and nothing else.
        assert gang.rating == 55
        assignment.refresh_from_db()
        assert assignment.archived is True
        assert_reconciled(gang)

    def test_a_haggled_price_sells_for_half_of_the_full_one(
        self, gang, fighter, catalogue
    ):
        """Bought at a discount, sold at half of what the gang owns. A sword
        talked down to 60 is still a hundred credits of sword."""
        from n26.tests.sandbox.actions import sell

        assignment = buy(fighter, thing=catalogue["autogun"], paid=12, discount=8)
        gang.refresh_from_db()
        credits_before = gang.credits

        assert sell(assignment) == 10

        gang.refresh_from_db()
        assert gang.credits == credits_before + 10
        assert_reconciled(gang)

    def test_nothing_sells_for_less_than_five(self, gang, fighter):
        """Half of a trinket is a rounding error, and nobody hands a knife
        over for nothing. Half of 9 is 5 by rounding up; half of 8 is 5
        because that is the floor."""
        from n26.tests.sandbox.actions import sell

        for price, expected in ((9, 5), (8, 5), (1, 5)):
            thing = create_wargear(f"Trinket {price}", price=price)
            gang.refresh_from_db()
            before = gang.credits
            assert sell(buy(fighter, thing=thing)) == expected
            gang.refresh_from_db()
            assert gang.credits == before - price + expected
        assert_reconciled(gang)

    def test_a_gun_is_sold_with_its_ammo_and_paid_for_both(
        self, gang, fighter, catalogue
    ):
        """What goes with the gun counts towards what the gun fetches: a
        buyer pays for the thing as it stands, sight and rounds included."""
        from n26.library.models import WeaponProfile
        from n26.tests.sandbox.actions import buy_weapon_profile, sell

        firestorm = WeaponProfile.objects.create(
            name="Firestorm ammo",
            annotation="Autogun",
            weapon=catalogue["autogun"],
            price=30,
            position=1,
        )
        weapon_assignment = buy(fighter, thing=catalogue["autogun"], paid=20)
        ammo = buy_weapon_profile(weapon_assignment, firestorm)
        gang.refresh_from_db()
        credits_before = gang.credits

        # Half of 20 + 30, not half of the gun alone.
        assert sell(weapon_assignment) == 25

        gang.refresh_from_db()
        assert gang.credits == credits_before + 25
        assert gang.rating == 55
        ammo.refresh_from_db()
        assert ammo.archived is True
        assert_reconciled(gang)

    def test_the_ledger_says_sold_rather_than_refunded(self, gang, fighter, catalogue):
        """A sale and a refund move credits the same way and mean different
        things. The log has to be able to say which happened."""
        from n26.core.render_text import ledger_to_text
        from n26.tests.sandbox.actions import sell

        assignment = buy(fighter, thing=catalogue["autogun"], paid=20)
        sell(assignment, note="sold to a passing trader")

        text = ledger_to_text(gang)
        print("\n" + text)
        assert "Sold: -10cr" in text
        assert "Refunded" not in text

    def test_a_sale_is_not_a_refund_of_what_was_paid(self, gang, fighter, catalogue):
        """The two acts on one item, side by side: the whole 20 comes back
        from a refund and half of it from a sale."""
        from n26.tests.sandbox.actions import refund, sell

        gang.refresh_from_db()
        start = gang.credits
        refund(buy(fighter, thing=catalogue["autogun"], paid=20))
        gang.refresh_from_db()
        assert gang.credits == start

        sell(buy(fighter, thing=catalogue["autogun"], paid=20))
        gang.refresh_from_db()
        assert gang.credits == start - 20 + 10
        assert_reconciled(gang)


class TestRefunds:
    """Distinct acts: remove keeps the money spent; refund gives it back; a
    sale returns half of what the thing is worth."""

    def test_a_refund_returns_the_money_and_the_rating(self, gang, fighter, catalogue):
        from n26.tests.sandbox.actions import refund

        house_list = create_collection("House List", entries=[catalogue["autogun"]])
        (line,) = list(browse(house_list).all_lines())
        assignment = buy(fighter, line)

        gang.refresh_from_db()
        assert gang.credits == 1000 - 55 - 20

        refund(assignment)

        gang.refresh_from_db()
        assert gang.credits == 1000 - 55
        assert gang.rating == 55
        assignment.refresh_from_db()
        assert assignment.archived is True
        assert_reconciled(gang)

    def test_a_refund_returns_what_was_paid_not_the_full_price(
        self, gang, fighter, catalogue
    ):
        """Bought at a discount, refunded at what actually changed hands."""
        from n26.tests.sandbox.actions import refund

        assignment = buy(fighter, thing=catalogue["mesh"], paid=10, discount=5)
        gang.refresh_from_db()
        credits_before = gang.credits

        refund(assignment)

        gang.refresh_from_db()
        assert gang.credits == credits_before + 10
        assert_reconciled(gang)

    def test_a_refund_takes_the_subtree_and_all_its_money(
        self, gang, fighter, catalogue
    ):
        """Refunding a weapon returns the paid ammo bought for it too."""
        from n26.library.models import WeaponProfile
        from n26.tests.sandbox.actions import buy_weapon_profile, refund

        firestorm = WeaponProfile.objects.create(
            name="Firestorm ammo",
            annotation="Autogun",
            weapon=catalogue["autogun"],
            price=30,
            position=1,
        )
        weapon_assignment = buy(fighter, thing=catalogue["autogun"], paid=20)
        buy_weapon_profile(weapon_assignment, firestorm)
        gang.refresh_from_db()
        assert gang.credits == 1000 - 55 - 20 - 30

        refund(weapon_assignment)

        gang.refresh_from_db()
        assert gang.credits == 1000 - 55
        assert gang.rating == 55
        assert_reconciled(gang)

    def test_the_ledger_reads_refunded(self, gang, fighter, catalogue):
        from n26.core.render_text import ledger_to_text
        from n26.tests.sandbox.actions import refund

        assignment = buy(fighter, thing=catalogue["autogun"], paid=20)
        refund(assignment, note="returned to the trader")

        text = ledger_to_text(gang)
        print("\n" + text)
        assert "Refunded: -20cr" in text


class TestWhatATradingPostStocks:
    """A trading post is a collection shopped on TRADING_POST terms: selector
    sweeps define what exists, entries customise prices, and everything
    about charging belongs to the terms of the browse — not to the
    collection, which only declares contents and prices."""

    def test_contents_are_defined_by_selectors_not_kinds_in_code(self, catalogue):
        """A priced subtype exists; the default post's sweeps do not reach
        it. Adding a sweep row — content, not code — puts it in the listing."""
        from n26.library.models import CollectionSelector, Subtype
        from n26.tests.sandbox.actions import create_trading_post

        Subtype.objects.create(name="Bought Title", price=50)
        post = create_trading_post()

        names = {line.name for line in browse(post, TRADING_POST).all_lines()}
        assert "Bought Title" not in names

        CollectionSelector.of(post, Subtype)
        lines = {line.name: line for line in browse(post, TRADING_POST).all_lines()}
        assert lines["Bought Title"].credits == 50
        assert lines["Bought Title"].charges_trade_points is True

    def test_a_sweep_can_be_narrowed_to_a_category(self, catalogue, taxonomy):
        from n26.library.models import Weapon
        from n26.tests.sandbox.actions import create_collection

        guns_only = create_collection(
            "Backstreet Arms Dealer",
            contains=[(Weapon, taxonomy["auto"])],
        )
        names = {line.name for line in browse(guns_only, TRADING_POST).all_lines()}
        assert names == {"Autogun"}

    def test_an_entry_overrides_the_sweep_for_one_item(self, catalogue):
        """The Nomad pattern: Imperial equipment appears via the sweep but
        is harder to obtain than usual — one entry reprices it."""
        from n26.tests.sandbox.actions import create_trading_post

        nomad_post = create_trading_post(
            "Nomad Trading Post",
            entries=[(catalogue["autogun"], {"trade_point_override": 4})],
        )

        lines = {
            line.name: line for line in browse(nomad_post, TRADING_POST).all_lines()
        }
        # Swept in with everything else, but at the post's own TP price.
        assert lines["Autogun"].trade_points == 4
        assert lines["Autogun"].entry is not None
        # The rest of the sweep is untouched, at reference prices.
        assert lines["Lasgun"].trade_points == 0
        assert lines["Lasgun"].entry is None

    def test_two_posts_are_two_collections(self, catalogue, gang, make_profile):
        """Access falls out of the existing machinery: assign the Nomad
        post to the nomad profile, and only its fighters see it."""
        from n26.tests.sandbox.actions import create_trading_post

        nomad_post = create_trading_post("Nomad Trading Post")
        nomad = make_profile("Nomad Prospect", price=40)
        nomad.built_ins = create_default_set("Nomad kit", members=[nomad_post])
        nomad.save()

        fighter = hire_with_option(gang, nomad, "Ash")
        (access,) = collections_for(fighter)
        assert access.collection == nomad_post

    def test_the_sweep_hides_exclusive_items_an_equipment_list_does_not(
        self, catalogue
    ):
        """The whole separation in one test: ONE collection, two terms.
        As a list, the sweep carries Exclusive items and nothing charges
        Trade Points; as a trading trip, "E" is withheld and TP is
        charged. Charging is not a concern of the collection."""
        from n26.library.models import Wargear
        from n26.tests.sandbox.actions import create_collection

        gear = create_collection("Everything, swept", contains=[Wargear])

        as_a_list = {line.name: line for line in browse(gear).all_lines()}
        trading = {line.name: line for line in browse(gear, TRADING_POST).all_lines()}

        assert "House Heirloom Blade-Charm" in as_a_list
        assert "House Heirloom Blade-Charm" not in trading
        assert as_a_list["Mesh Armour"].charges_trade_points is False
        assert trading["Mesh Armour"].charges_trade_points is True

    def test_unsweepable_kinds_are_refused_at_authoring_time(self, db):
        from django.core.exceptions import ValidationError

        from n26.library.models import Trait
        from n26.tests.sandbox.actions import create_trading_post

        post = create_trading_post()
        from n26.library.models import CollectionSelector

        with pytest.raises(ValidationError, match="cannot sweep"):
            CollectionSelector.of(post, Trait).clean()


class TestScaling:
    def test_a_bigger_list_costs_no_more_queries_to_browse(self, taxonomy):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def arsenal(count):
            return [
                create_weapon(
                    f"Gun {count}-{index}",
                    profiles=[("Standard", 0)],
                    price=10 + index,
                    category=taxonomy["auto"],
                )
                for index in range(count)
            ]

        small = create_collection("Small", entries=arsenal(2))
        big = create_collection("Big", entries=arsenal(12))

        def measure(collection):
            with CaptureQueriesContext(connection) as captured:
                view = browse(collection)
                assert list(view.all_lines())
            return len(captured.captured_queries)

        assert measure(small) == measure(big)

    def test_marking_usability_costs_no_more_queries_as_restrictions_grow(
        self, taxonomy, person_type, make_profile
    ):
        """A restricted line is noted by reading its use lists — all four
        of them, on every kind that carries them. The lists load with the
        listing, so a section of narrowed guns costs what an open one
        does."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core import select
        from n26.core.browse import with_use_notes
        from n26.library.authoring import create_subtype

        walker = create_subtype("Walker")
        shopper = select.matchable(make_profile("Shopper"))

        def restricted(count):
            items = []
            for index in range(count):
                weapon = create_weapon(
                    f"Narrow gun {count}-{index}",
                    profiles=[("Standard", 0)],
                    category=taxonomy["auto"],
                )
                weapon.usable_by_profile_types.add(person_type)
                weapon.usable_by_subtypes.add(walker)
                items.append(weapon)
            return items

        small = create_collection("Small armoury", entries=restricted(2))
        big = create_collection("Big armoury", entries=restricted(12))

        def measure(collection):
            with CaptureQueriesContext(connection) as captured:
                noted = with_use_notes(browse(collection), shopper)
                assert list(noted.all_lines())
            return len(captured.captured_queries)

        assert measure(small) == measure(big)


class TestTradingPostMembership:
    """The Trading Post's membership is *having a trade point price* —
    a selector predicate, never a hand-kept list. Author a weapon with
    a TP and it is simply there; blank TP means not offered; Exclusive
    means equipment list only. And a weapon's TP-priced ammo rows ride
    under the gun, the way the book's table prints them."""

    @pytest.fixture
    def armoury(self, taxonomy):
        from n26.library.authoring import add_weapon_profile

        boltgun = create_weapon(
            "Boltgun",
            profiles=[("Standard", 0)],
            price=55,
            trade_point_price=3,
            category=taxonomy["auto"],
        )
        add_weapon_profile(boltgun, name="Kraken round", price=15, trade_point_price=5)
        add_weapon_profile(boltgun, name="House-cast slug", price=5)
        house_special = create_weapon(
            "House-pattern needler",
            profiles=[("Standard", 0)],
            price=40,
            category=taxonomy["las"],
        )
        return {"boltgun": boltgun, "house_special": house_special}

    def test_membership_is_having_a_tp_price(self, catalogue, armoury):
        """The needler has no TP — not offered — so the sweep never
        carries it; everything with a TP (0 counts) is simply there."""
        from n26.tests.sandbox.actions import create_trading_post

        post = create_trading_post()
        names = {line.name for line in browse(post, TRADING_POST).all_lines()}
        assert "Boltgun" in names
        assert "Autogun" in names  # TP 0 is a real price
        assert "Mesh Armour" in names
        assert "House-pattern needler" not in names
        assert "House Heirloom Blade-Charm" not in names  # Exclusive

    def test_tp_priced_ammo_rides_under_its_gun(self, catalogue, armoury):
        """Nested lines: the kraken round (TP 5) is a part of the
        boltgun's line; the house-cast slug has no TP and stays off."""
        from n26.tests.sandbox.actions import create_trading_post

        post = create_trading_post()
        lines = {line.name: line for line in browse(post, TRADING_POST).all_lines()}

        (kraken,) = lines["Boltgun"].parts
        # The bare name: a nested row draws under its gun, so the
        # bracket annotation is the renderer's to drop — same rule as
        # the model card's ammo rows.
        assert kraken.thing.name == "Kraken round"
        assert (kraken.credits, kraken.trade_points) == (15, 5)
        assert kraken.charges_trade_points is True
        assert lines["Autogun"].parts == ()

    def test_the_whole_listing_is_a_fixed_number_of_queries(
        self, catalogue, armoury, django_assert_num_queries
    ):
        """The prefetch strategy under test: the count follows the
        post's *definition*, never its size. One for the selector rows,
        one per sweep, one for the weapon sweep's nested profiles, four
        use-restriction prefetches for each sweep whose kind can carry
        them (an accessory cannot), one for the entries."""
        from n26.tests.sandbox.actions import create_trading_post

        post = create_trading_post()
        with django_assert_num_queries(14):
            view = browse(post, TRADING_POST)
            for line in view.all_lines():
                for part in line.parts:
                    str(part.thing)

    def test_the_foundations_button_makes_it(self, default_pack):
        from n26.library.models import Collection
        from n26.library.standard_content import STANDARD_CONTENT

        seed = STANDARD_CONTENT["trading-post"]
        assert seed.status() == "missing"
        seed.create()
        assert seed.status() == "complete"
        seed.create()  # idempotent
        assert Collection.objects.filter(name="Trading Post").count() == 1

        post = Collection.objects.get(name="Trading Post")
        sweeps = [str(sweep) for sweep in post.selectors.all()]
        assert sweeps == [
            "every weapon with a TP price",
            "every wargear with a TP price",
            "every weapon accessory with a TP price",
        ]


class TestAmmoRidesUnderTheGun:
    """A gun's paid ammo and firing modes are parts of the gun's line, on
    a curated equipment list as much as on a swept trading post.

    Which profiles ride is the same question either way: named, because a
    blank profile is the weapon's own firing line rather than an
    alternative to it; paid, because a free one already comes with the
    weapon and selling it would put the same ammo on the gun twice.
    """

    @pytest.fixture
    def autogun(self, taxonomy):
        from n26.library.authoring import add_weapon_profile

        weapon = create_weapon(
            "Autogun",
            profiles=[("", 0)],
            price=20,
            trade_point_price=0,
            category=taxonomy["auto"],
        )
        add_weapon_profile(weapon, name="warp round", price=10, trade_point_price=4)
        add_weapon_profile(weapon, name="fully automatic", price=0)
        return weapon

    def test_a_curated_entry_carries_its_guns_ammo(self, autogun):
        """What a player saw: a house equipment list is curated entries
        throughout, and a gun on one offered no ammo at all."""
        house = create_collection("House List", entries=[autogun])
        (line,) = browse(house).all_lines()

        (warp,) = line.parts
        assert warp.thing.name == "warp round"
        assert warp.credits == 10

    def test_a_free_mode_is_never_offered_for_sale(self, autogun):
        """It rides along with the gun already, so a player who bought it
        would be given a second copy of a profile they already have."""
        house = create_collection("House List", entries=[autogun])
        (line,) = browse(house).all_lines()

        assert [part.thing.name for part in line.parts] == ["warp round"]

    def test_a_lists_own_price_does_not_reprice_the_ammo(self, autogun):
        """An entry's override replaces the gun's own price and nothing
        else — the rule ``price_with(base=…)`` follows everywhere."""
        house = create_collection(
            "House List", entries=[(autogun, {"price_override": 15})]
        )
        (line,) = browse(house).all_lines()

        assert line.credits == 15
        assert line.parts[0].credits == 10

    def test_a_longer_list_costs_no_more_queries_to_browse(self, taxonomy):
        """The ammo prefetch follows the list's definition, not its
        length: one query for every gun's profiles, however many guns."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import add_weapon_profile

        def arsenal(count):
            guns = []
            for index in range(count):
                gun = create_weapon(
                    f"Gun {count}-{index}",
                    profiles=[("", 0)],
                    price=10,
                    category=taxonomy["auto"],
                )
                add_weapon_profile(gun, name="hot shot", price=5)
                guns.append(gun)
            return guns

        small = create_collection("Small", entries=arsenal(2))
        big = create_collection("Big", entries=arsenal(12))

        def measure(collection):
            with CaptureQueriesContext(connection) as captured:
                for line in browse(collection).all_lines():
                    for part in line.parts:
                        str(part.thing)
            return len(captured.captured_queries)

        assert measure(small) == measure(big)


class TestWhatACollectionHolds:
    """A collection says what it is by what is in it.

    Surfaces ask that question to decide whether a collection belongs on
    them at all — a screen for buying kit wants the ones with gear in
    them, a screen for learning skills the ones with skills. The question
    is asked by family rather than by naming kinds, so a new sort of gear
    puts its collections on the buying screen the day it exists.
    """

    def test_a_curated_list_of_gear_holds_gear(self):
        from n26.library.models import Collection, Family

        create_collection("House List", entries=[create_wargear("Knife", price=10)])
        held = Collection.objects.containing(Family.GEAR)

        assert [collection.name for collection in held] == ["House List"]

    def test_a_curated_list_of_skills_holds_none(self):
        """The case the buying screen turns on: a fighter's skill sets
        arrive on their card exactly as their equipment list does, so
        only the contents tell the two apart."""
        from n26.library.models import Collection, Family
        from n26.tests.sandbox.actions import create_skill

        create_collection("Skills & Powers", entries=[create_skill("Catfall")])

        assert not Collection.objects.containing(Family.GEAR).exists()
        assert [c.name for c in Collection.objects.containing(Family.MODEL)] == [
            "Skills & Powers"
        ]

    def test_a_sweep_counts_as_much_as_an_entry(self):
        """A collection with no rows of its own still holds what it
        sweeps in — the shape of the standard Trading Post."""
        from n26.library.models import Collection, CollectionSelector, Family, Wargear

        post = create_collection("Trading Post")
        CollectionSelector.of(post, Wargear)

        assert [c.name for c in Collection.objects.containing(Family.GEAR)] == [
            "Trading Post"
        ]

    def test_an_empty_collection_holds_nothing(self):
        """Emptiness is an answer, not a special case: a collection with
        neither entries nor sweeps is on no surface that asks."""
        from n26.library.models import Collection, Family

        create_collection("Blank")

        assert not Collection.objects.containing(Family.GEAR).exists()
        assert not Collection.objects.containing(Family.MODEL).exists()

    def test_asking_costs_one_query_however_much_is_held(self):
        """The containment tests are subqueries, so the count follows the
        question and never the contents."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.models import Collection, Family

        create_collection("Small", entries=[create_wargear("Knife", price=1)])
        create_collection(
            "Big",
            entries=[create_wargear(f"Thing {index}", price=1) for index in range(20)],
        )

        with CaptureQueriesContext(connection) as captured:
            names = [c.name for c in Collection.objects.containing(Family.GEAR)]

        assert sorted(names) == ["Big", "Small"]
        assert len(captured.captured_queries) == 1
