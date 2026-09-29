"""Buying below the full price: which figure the gang's rating takes.

A list may price something below what it is — a profile that may take it
for free — and a player may type a lower price. Either way the thing
keeps its full rating unless the reader ticks the rating box, which the
click asks before anything is written. Where a Trade Point overspend is
also being asked, the box rides that question rather than opening a
second one.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.confirm import CONFIRM_FIELD
from n26.core.models import Gang, LedgerEntry
from n26.core.operations import operation
from n26.core.owned import thing_key
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import (
    create_collection,
    create_trading_post,
    create_wargear,
)

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def tester(db):
    return User.objects.create_user("player")


@pytest.fixture
def gang(gang_type, tester):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=100,
        credits=100,
    )


@pytest.fixture
def fighter(gang, make_profile, make_statline, tester):
    profile = make_profile("Ganger", price=0)
    make_statline(profile)
    with operation(gang, actor=tester) as op:
        return op.hire(profile, "Vex")


@pytest.fixture
def free_list(gang, tester):
    """A list that hands out a 20-credit sword for nothing, beside a
    knife at its own price and a pistol it prices above its own."""
    knife = create_wargear("Knife", price=10)
    sword = create_wargear("Sword", price=20)
    pistol = create_wargear("Pistol", price=15)
    collection = create_collection(
        "House List",
        entries=[
            knife,
            (sword, {"price_override": 0}),
            (pistol, {"price_override": 25}),
        ],
    )
    with operation(gang, actor=tester) as op:
        op.assign(collection, gang=gang)
    return collection


def equip_url(fighter, collection):
    return f"{reverse('n26-equip', args=[fighter.pk])}?list={collection.pk}"


def buying(name, **fields):
    from n26.library.models import Wargear

    return {"thing": thing_key(Wargear.objects.get(name=name)), **fields}


def price_field(name):
    from django.utils.text import slugify

    from n26.library.models import Wargear

    return f"{slugify(thing_key(Wargear.objects.get(name=name)))}:price"


def entry_for(name):
    return LedgerEntry.objects.get(assignment__wargear__name=name)


@pytest.fixture(autouse=True)
def signed_in(client, tester):
    client.force_login(tester)


class TestWhatAsks:
    def test_a_list_pricing_below_the_item_asks_before_buying(
        self, client, fighter, free_list
    ):
        answer = client.post(equip_url(fighter, free_list), buying("Sword"))

        body = answer.content.decode()
        assert answer.status_code == 200
        assert "Match rating to price" in body
        assert 'name="rate"' in body
        assert "keeps its full rating of 20¢" in body
        assert not LedgerEntry.objects.filter(
            assignment__wargear__name="Sword"
        ).exists()

    def test_the_box_starts_unticked(self, client, fighter, free_list):
        body = client.post(
            equip_url(fighter, free_list), buying("Sword")
        ).content.decode()

        box = body[body.index('name="rate"') - 120 : body.index('name="rate"') + 120]
        assert "checked" not in box

    def test_a_price_typed_below_the_item_asks_too(self, client, fighter, free_list):
        answer = client.post(
            equip_url(fighter, free_list),
            buying("Knife", **{price_field("Knife"): "4"}),
        )

        assert answer.status_code == 200
        assert "Match rating to price" in answer.content.decode()

    def test_a_list_at_the_items_own_price_buys_straight_away(
        self, client, fighter, free_list
    ):
        answer = client.post(equip_url(fighter, free_list), buying("Knife"))

        assert answer.status_code == 302
        assert entry_for("Knife").rating_contribution == 10

    def test_a_list_above_the_items_own_price_buys_straight_away(
        self, client, fighter, free_list
    ):
        """A list asking more is the rating: only paying below the full
        price is a question."""
        answer = client.post(equip_url(fighter, free_list), buying("Pistol"))

        assert answer.status_code == 302
        assert entry_for("Pistol").rating_contribution == 25

    def test_a_price_typed_below_a_list_asking_more_asks_too(
        self, client, fighter, free_list
    ):
        """The list's higher price is the full rating, so paying less
        than it is paying below the full price."""
        answer = client.post(
            equip_url(fighter, free_list),
            buying("Pistol", **{price_field("Pistol"): "18"}),
        )

        assert answer.status_code == 200
        assert "keeps its full rating of 25¢" in answer.content.decode()

    def test_the_panel_carries_the_box_for_a_screen_updating_in_place(
        self, client, fighter, free_list
    ):
        body = client.post(
            equip_url(fighter, free_list), buying("Sword"), **HX
        ).content.decode()

        assert 'id="n26-dialog-host"' in body
        assert "Match rating to price" in body


class TestWhatConfirmingRates:
    def test_unticked_keeps_the_full_rating(self, client, gang, fighter, free_list):
        client.post(
            equip_url(fighter, free_list), buying("Sword", **{CONFIRM_FIELD: "1"})
        )

        entry = entry_for("Sword")
        assert (entry.paid, entry.list_price, entry.discount) == (0, 20, 20)
        assert entry.rating_contribution == 20
        gang.refresh_from_db()
        assert gang.credits == 100
        assert gang.rating == 20
        assert_reconciled(gang)

    def test_ticked_rates_it_at_the_price_paid(self, client, gang, fighter, free_list):
        client.post(
            equip_url(fighter, free_list),
            buying("Sword", **{CONFIRM_FIELD: "1", "rate": "paid"}),
        )

        entry = entry_for("Sword")
        # The entry still says what the sword is worth and what the deal was.
        assert (entry.paid, entry.list_price, entry.discount) == (0, 20, 20)
        assert entry.rating_contribution == 0
        gang.refresh_from_db()
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_ticked_on_a_typed_price_rates_it_at_that_price(
        self, client, gang, fighter, free_list
    ):
        client.post(
            equip_url(fighter, free_list),
            buying(
                "Knife",
                **{price_field("Knife"): "4", CONFIRM_FIELD: "1", "rate": "paid"},
            ),
        )

        entry = entry_for("Knife")
        assert (entry.paid, entry.rating_contribution) == (4, 4)
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_tick_posted_with_nothing_below_full_changes_nothing(
        self, client, gang, fighter, free_list
    ):
        """The box is only ever drawn below the full price, so a tick
        arriving with a full-price purchase rates it at full."""
        client.post(equip_url(fighter, free_list), buying("Pistol", rate="paid"))

        assert entry_for("Pistol").rating_contribution == 25


class TestAGunAndItsAmmo:
    """One click can buy a gun and its ammo, each at its own price."""

    @pytest.fixture
    def armoury(self, gang, tester):
        from n26.library.authoring import add_weapon_profile, create_weapon

        autogun = create_weapon("Autogun", profiles=[("", 0)], price=20)
        warp = add_weapon_profile(autogun, name="warp round", price=10)
        collection = create_collection("Armoury", entries=[autogun, warp])
        with operation(gang, actor=tester) as op:
            op.assign(collection, gang=gang)
        return autogun, collection

    @staticmethod
    def click(autogun, gun_price=None, ammo_price=None):
        from django.utils.text import slugify

        scope = slugify(thing_key(autogun))
        fields = {"thing": thing_key(autogun), f"{scope}:parts": "0"}
        if gun_price is not None:
            fields[f"{scope}:price"] = gun_price
        if ammo_price is not None:
            fields[f"{scope}:parts:0:price"] = ammo_price
        return fields

    def test_the_box_names_only_the_ammo_when_only_it_is_below_full(
        self, client, fighter, armoury
    ):
        autogun, collection = armoury
        body = client.post(
            equip_url(fighter, collection), self.click(autogun, ammo_price="4")
        ).content.decode()

        # A named profile reads as the round and its gun.
        assert "round (Autogun) keeps its full rating of 10¢" in body
        assert "Autogun and" not in body
        # The whole click's price, gun and ammo together.
        assert "Autogun — 24¢." in body

    def test_ticked_rates_the_ammo_at_what_was_paid(
        self, client, gang, fighter, armoury
    ):
        autogun, collection = armoury
        client.post(
            equip_url(fighter, collection),
            {**self.click(autogun, ammo_price="4"), CONFIRM_FIELD: "1", "rate": "paid"},
        )

        gun = LedgerEntry.objects.get(assignment__weapon=autogun)
        ammo = LedgerEntry.objects.get(assignment__weapon_profile__name="warp round")
        assert (gun.paid, gun.list_price, gun.rating_contribution) == (20, 20, 20)
        assert (ammo.paid, ammo.list_price, ammo.discount) == (4, 10, 6)
        assert ammo.rating_contribution == 4
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_the_box_names_both_when_both_are_below_full(
        self, client, fighter, armoury
    ):
        autogun, collection = armoury
        body = client.post(
            equip_url(fighter, collection),
            self.click(autogun, gun_price="12", ammo_price="4"),
        ).content.decode()

        assert "round (Autogun) keep their full rating of 30¢" in body
        assert "Autogun and " in body
        assert "Autogun — 16¢." in body


class TestGearPricedBelowNothing:
    def test_a_negative_listing_keeps_its_own_price_as_the_rating(
        self, client, gang, fighter, tester
    ):
        """Taking it pays the gang, and the model is worth less for it."""
        cursed = create_wargear("Cursed trinket", price=0)
        collection = create_collection(
            "Odd List", entries=[(cursed, {"price_override": -5})]
        )
        with operation(gang, actor=tester) as op:
            op.assign(collection, gang=gang)

        answer = client.post(equip_url(fighter, collection), buying("Cursed trinket"))

        assert answer.status_code == 302
        entry = entry_for("Cursed trinket")
        assert (entry.paid, entry.list_price, entry.discount) == (-5, -5, 0)
        assert entry.rating_contribution == -5
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestBuyingIntoTheStash:
    """The stash's equip page reads the click the same way."""

    @pytest.fixture(autouse=True)
    def founded(self, gang, tester):
        # Founding writes the stash.
        with operation(gang, actor=tester) as op:
            op.found(gang.gang_type)

    def url(self, gang, collection):
        return f"{reverse('n26-equip-gang', args=[gang.pk])}?list={collection.pk}"

    def test_the_stash_asks_too(self, client, gang, free_list):
        answer = client.post(self.url(gang, free_list), buying("Sword"))

        assert answer.status_code == 200
        assert "Match rating to price" in answer.content.decode()

    @pytest.mark.parametrize("ticked, rating", [(False, 20), (True, 0)])
    def test_the_box_decides_the_stashs_rating(
        self, client, gang, free_list, ticked, rating
    ):
        fields = {CONFIRM_FIELD: "1", **({"rate": "paid"} if ticked else {})}
        client.post(self.url(gang, free_list), buying("Sword", **fields))

        assert entry_for("Sword").rating_contribution == rating
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestWithAnOverspend:
    """One click, one question: the box rides the overspend panel."""

    @pytest.fixture
    def post(self):
        from n26.library.models import Wargear

        create_wargear("Mesh armour", price=15, trade_point_price=3)
        return create_trading_post("Trading Post", contains=[Wargear])

    def test_both_are_asked_in_the_one_question(self, client, fighter, post):
        body = client.post(
            equip_url(fighter, post),
            buying("Mesh armour", **{price_field("Mesh armour"): "5"}),
        ).content.decode()

        assert "Not enough Trade Points" in body
        assert "Match rating to price" in body
        assert body.count('name="rate"') == 1

    def test_confirming_rates_it_as_the_box_says(self, client, gang, fighter, post):
        client.post(
            equip_url(fighter, post),
            buying(
                "Mesh armour",
                **{price_field("Mesh armour"): "5", CONFIRM_FIELD: "1", "rate": "paid"},
            ),
        )

        entry = entry_for("Mesh armour")
        assert (entry.paid, entry.rating_contribution) == (5, 5)
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_an_overspend_at_full_price_carries_no_box(self, client, fighter, post):
        body = client.post(
            equip_url(fighter, post), buying("Mesh armour")
        ).content.decode()

        assert "Not enough Trade Points" in body
        assert "Match rating to price" not in body
