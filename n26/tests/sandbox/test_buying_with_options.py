"""Buying something with a group of options: the equip page's end of the offer.

Some things offer alternatives when they are acquired. A fighter entry
offers them at hire, and the hire screen has always put them in front of
a player; a piece of wargear offers them when it is bought, and this is
that — the same three modes ("one", "any", "one-or-none"), the same
controls, the same indices read back against the listing the server
re-derives.

The worked case is the Escher Cutter: a mount that comes with grenade
launchers and will swap them for heavy stubbers or plasma guns, dearer
by ten and fifteen. The list prices the mount itself its own way, which
is the case that separates the two numbers involved — what the mount
costs on this list, and what a swap adds to it.

Rule *names* only; the rulebook's words are copyright (CLAUDE.md).
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.tests.sandbox.actions import (
    assign,
    buy,
    create_category,
    create_collection,
    create_option_group,
    create_wargear,
    create_weapon,
    found_gang,
    hire,
    offer_option,
    remove,
    set_statline,
)

pytestmark = pytest.mark.django_db

#: What the author calls the Cutter's second set. Distinctive enough that
#: no template, price or stylesheet could contain it by accident — a walk
#: over the page is only as good as the word it looks for.
SET_LABEL = "Hull fittings (author's shorthand)"


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def gang(gang_type, owner):
    return found_gang("The Bad Girls", gang_type, owner=owner, budget=1000)


@pytest.fixture
def fighter(gang, make_profile, make_statline):
    profile = make_profile("Wyld Runner", price=0)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    return hire(gang, profile, "Sly")


@pytest.fixture
def cutter(default_pack):
    """The mount: comes with a weapon, offers two priced swaps, and has a
    second set that may be left alone.

    No built-ins. "Comes with X, may replace X with Y" is a pick-one set
    whose head is X — a built-in would be granted *as well as* the swap,
    because nothing is ever replaced.
    """
    mount = create_wargear(
        "Escher Cutter", price=120, category=create_category("Wargear", "Mounts", 0)
    )
    for name, price in [
        ("Cutter grenade launchers", 0),
        ("Cutter heavy stubbers", 10),
        ("Cutter plasma guns", 15),
    ]:
        offer_option(
            mount,
            name,
            price=price,
            thing=create_weapon(name, profiles=[("Standard", 0)], is_exclusive=True),
        )
    fittings = create_option_group(mount, SET_LABEL, choose="one-or-none")
    offer_option(
        mount,
        "Smoke dispenser",
        price=20,
        thing=create_wargear("Cutter smoke dispenser", is_exclusive=True),
        group=fittings,
    )
    return mount


@pytest.fixture
def house_list(gang, cutter):
    """One curated list, pricing the mount above its reference price.

    The two numbers a swap has to be told apart: 150 is what this list
    asks for the mount, and 15 is what plasma guns add to it. A house
    pricing a mount at 150 has not made its swaps free.
    """
    collection = create_collection(
        "House Escher Equipment List", entries=[(cutter, {"price_override": 150})]
    )
    assign(collection, gang=gang)
    return collection


def equip_url(fighter, collection):
    return f"{reverse('n26-equip', args=[fighter.pk])}?list={collection.pk}"


def key_of(thing):
    return f"{thing._meta.label_lower}:{thing.pk}"


def choice_field(thing, group):
    """The input name one set's controls share, spelt out rather than
    imported: a test that asks the code under test what it named its
    fields cannot catch the code renaming them."""
    from django.utils.text import slugify

    return f"{slugify(key_of(thing))}:option:{group}"


def price_field(thing):
    from django.utils.text import slugify

    return f"{slugify(key_of(thing))}:price"


def cutter_line(house_list):
    from n26.core.browse import browse

    return next(
        line for line in browse(house_list).all_lines() if line.name == "Escher Cutter"
    )


def row_named(client, owner, fighter, collection, name):
    """The row the page was handed to draw, straight from its context."""
    client.force_login(owner)
    response = client.get(equip_url(fighter, collection))
    return next(
        row for row in response.context["catalogue"].all_rows() if row.name == name
    )


def cutter_row(client, owner, fighter, house_list):
    return row_named(client, owner, fighter, house_list, "Escher Cutter")


def weapons_of(fighter):
    from n26.core.render import build_model_card

    return [weapon.name for weapon in build_model_card(fighter).weapons]


class TestWhatTheRowAsks:
    """The offer, as the structure a screen is drawn from."""

    def test_a_pick_one_set_offers_every_option_with_the_standard_one_marked(
        self, client, owner, fighter, house_list
    ):
        row = cutter_row(client, owner, fighter, house_list)
        launchers, stubbers, plasma = row.choices[0].options

        assert row.choices[0].choose == "one"
        assert launchers.name == "Cutter grenade launchers"
        assert [option.is_default for option in row.choices[0].options] == [
            True,
            False,
            False,
        ]
        assert (stubbers.surcharge, plasma.surcharge) == (10, 15)

    def test_a_surcharge_is_measured_from_the_price_the_row_quotes(
        self, client, owner, fighter, house_list
    ):
        """The row quotes the mount with its standard guns, so what an
        option adds is the distance from there: the standard one adds
        nothing and prints nothing beside it."""
        row = cutter_row(client, owner, fighter, house_list)
        launchers, _, plasma = row.choices[0].options

        assert row.price == 150
        assert (launchers.surcharge, launchers.surcharge_label) == (0, "")
        assert plasma.surcharge_label == "+15¢"

    def test_a_head_the_author_priced_is_still_in_the_quote_once(
        self, client, owner, gang, fighter, default_pack
    ):
        """The Trazior shape: both options carry a real price, so the
        cheaper one is what the quote includes and the dearer one adds
        only the difference. Counted twice, a swap would be sold at the
        price of two."""
        platform = create_wargear("Sentry gun", price=30)
        for name, price in [("Grenade launcher", 45), ("Heavy stubber", 80)]:
            offer_option(
                platform,
                name,
                price=price,
                thing=create_weapon(f"Sentry {name.lower()}", profiles=[("Fire", 0)]),
            )
        collection = create_collection("Gang Equipment", entries=[platform])
        assign(collection, gang=gang)

        row = row_named(client, owner, fighter, collection, "Sentry gun")
        launcher, stubber = row.choices[0].options

        assert row.price == 75
        assert (launcher.surcharge, stubber.surcharge) == (0, 35)

    def test_a_set_with_nothing_to_pick_asks_nothing(
        self, client, owner, gang, fighter, default_pack
    ):
        """A pick-one set with one option is taken unasked. Drawing it
        would ask a reader to consider something they cannot change."""
        harness = create_wargear("Grav harness", price=25)
        offer_option(
            harness, "As standard", thing=create_wargear("Harness webbing", price=0)
        )
        collection = create_collection("Sundries", entries=[harness])
        assign(collection, gang=gang)

        row = row_named(client, owner, fighter, collection, "Grav harness")
        assert row.choices == ()

    def test_the_label_the_author_gave_a_set_reaches_nobody(
        self, client, owner, fighter, house_list
    ):
        """Same rule as the hire row: a set is shown as grouping — the
        controls together, a rule between sets, a line saying how many to
        take — and never as a heading naming it."""
        client.force_login(owner)
        body = client.get(equip_url(fighter, house_list)).content.decode()

        assert "Smoke dispenser" in body
        assert SET_LABEL not in body


class TestWhatTheScreenDraws:
    """Controls on the row, working with no script running."""

    def test_every_option_is_a_radio_named_what_the_purchase_reads_back(
        self, client, owner, fighter, house_list, cutter
    ):
        """Asserted on the rendered page, not on a hand-built POST: the
        scope is slugified, and reading the raw key back would ignore
        every choice made in a real browser while a test posting the raw
        key still passed."""
        client.force_login(owner)
        body = client.get(equip_url(fighter, house_list)).content.decode()

        assert f'name="{choice_field(cutter, 0)}"' in body
        assert body.count(f'name="{choice_field(cutter, 0)}"') == 3
        assert "Cutter plasma guns" in body
        assert "+15¢" in body

    def test_the_standard_option_arrives_already_picked(
        self, client, owner, fighter, house_list, cutter
    ):
        client.force_login(owner)
        body = client.get(equip_url(fighter, house_list)).content.decode()

        field = choice_field(cutter, 0)
        standard = body.index(f'name="{field}"')
        assert "checked" in body[standard : body.index("</label>", standard)]

    def test_a_further_set_says_how_many_to_take_and_offers_none(
        self, client, owner, fighter, house_list, cutter
    ):
        """Radios cannot be unclicked, so "None" is the option that makes
        taking nothing clickable — and its empty value is what the
        purchase skips."""
        client.force_login(owner)
        body = client.get(equip_url(fighter, house_list)).content.decode()

        assert "Choose one, or none" in body
        assert f'name="{choice_field(cutter, 1)}"' in body
        assert ">None</span>" in body

    def test_nothing_the_choice_draws_is_a_second_submit(
        self, client, owner, fighter, house_list
    ):
        """Every submit on this page buys something. An option is a way
        the thing being bought is built, so it rides the row's own Buy."""
        client.force_login(owner)
        body = client.get(equip_url(fighter, house_list)).content.decode()

        assert body.count('type="submit"') == body.count('name="thing"')


class TestBuyingWithNothingPicked:
    """A click with nothing picked takes what comes as standard."""

    def test_it_takes_the_standard_guns_at_the_price_the_list_asked(
        self, client, owner, gang, fighter, house_list, cutter
    ):
        client.force_login(owner)
        response = client.post(
            equip_url(fighter, house_list), {"thing": key_of(cutter)}
        )
        assert response.status_code == 302

        assert weapons_of(fighter) == ["Cutter grenade launchers"]
        gang.refresh_from_db()
        assert gang.credits == 850
        assert gang.rating == 150
        assert_reconciled(gang)


class TestBuyingASwap:
    """What a swap adds lands on the price and on the rating both."""

    def test_the_plasma_guns_arrive_and_the_launchers_never_do(
        self, client, owner, gang, fighter, house_list, cutter
    ):
        client.force_login(owner)
        client.post(
            equip_url(fighter, house_list),
            {"thing": key_of(cutter), choice_field(cutter, 0): "2"},
        )

        assert weapons_of(fighter) == ["Cutter plasma guns"]
        gang.refresh_from_db()
        assert gang.credits == 835  # 1000 - 150 - 15
        assert gang.rating == 165
        assert_reconciled(gang)

    def test_the_entry_says_what_the_list_asked_and_what_was_handed_over(
        self, client, owner, gang, fighter, house_list, cutter
    ):
        """A mount with plasma guns is a dearer mount, not a discounted
        one — so the surcharge is on both figures and the gap between
        them is what was agreed at the table."""
        from n26.core.models import LedgerEntry

        client.force_login(owner)
        client.post(
            equip_url(fighter, house_list),
            {
                "thing": key_of(cutter),
                choice_field(cutter, 0): "2",
                price_field(cutter): "140",
            },
        )

        entry = LedgerEntry.objects.get(assignment__wargear=cutter)
        assert (entry.paid, entry.list_price, entry.discount) == (155, 165, 10)
        assert entry.rating_contribution == 165
        gang.refresh_from_db()
        assert gang.credits == 845
        assert gang.rating == 165
        assert_reconciled(gang)

    def test_the_confirmation_names_what_was_picked(
        self, client, owner, fighter, house_list, cutter
    ):
        client.force_login(owner)
        response = client.post(
            equip_url(fighter, house_list),
            {"thing": key_of(cutter), choice_field(cutter, 0): "2"},
            follow=True,
        )

        said = [str(message) for message in response.context["messages"]]
        assert said == ["Bought Escher Cutter with Cutter plasma guns for Sly — 165¢."]

    def test_selling_the_mount_takes_the_guns_it_was_bought_with(
        self, client, owner, gang, fighter, house_list, cutter
    ):
        """The chosen set materialises *caused by* the purchase, which is
        what makes it leave with it."""
        client.force_login(owner)
        client.post(
            equip_url(fighter, house_list),
            {"thing": key_of(cutter), choice_field(cutter, 0): "1"},
        )
        remove(Assignment.objects.get(wargear=cutter))

        assert weapons_of(fighter) == []
        gang.refresh_from_db()
        assert gang.rating == 0
        assert_reconciled(gang)


class TestTakingNothingFromAnOptionalSet:
    """A one-or-none set's None option is a pick, not a missing one."""

    def test_the_dispenser_is_left_behind_and_nothing_extra_is_charged(
        self, client, owner, gang, fighter, house_list, cutter
    ):
        client.force_login(owner)
        client.post(
            equip_url(fighter, house_list),
            {
                "thing": key_of(cutter),
                choice_field(cutter, 0): "0",
                choice_field(cutter, 1): "",
            },
        )

        assert not Assignment.objects.filter(
            wargear__name="Cutter smoke dispenser"
        ).exists()
        gang.refresh_from_db()
        assert gang.credits == 850
        assert_reconciled(gang)

    def test_taking_it_adds_its_own_price_on_top(
        self, client, owner, gang, fighter, house_list, cutter
    ):
        client.force_login(owner)
        client.post(
            equip_url(fighter, house_list),
            {
                "thing": key_of(cutter),
                choice_field(cutter, 0): "2",
                choice_field(cutter, 1): "0",
            },
        )

        assert Assignment.objects.filter(
            wargear__name="Cutter smoke dispenser"
        ).exists()
        gang.refresh_from_db()
        assert gang.credits == 815  # 1000 - 150 - 15 - 20
        assert gang.rating == 185
        assert_reconciled(gang)


class TestWhatAnOwnedCopySays:
    """A mount already bought names the guns it was bought with.

    The row above it is about the content — every Cutter there could
    be — so the answer belongs to the copy: two mounts on one fighter
    may carry different guns and a heading cannot say both.
    """

    def buy(self, client, owner, fighter, house_list, cutter, **picked):
        client.force_login(owner)
        client.post(equip_url(fighter, house_list), {"thing": key_of(cutter), **picked})

    def chosen(self, client, owner, fighter, house_list):
        row = cutter_row(client, owner, fighter, house_list)
        return [copy.chosen for copy in row.copies]

    def test_a_swap_is_named_on_the_copy_that_took_it(
        self, client, owner, fighter, house_list, cutter
    ):
        self.buy(
            client, owner, fighter, house_list, cutter, **{choice_field(cutter, 0): "2"}
        )

        assert self.chosen(client, owner, fighter, house_list) == [
            ("Cutter plasma guns",)
        ]

    def test_the_standard_guns_are_named_though_nobody_picked_them(
        self, client, owner, fighter, house_list, cutter
    ):
        """Taking what comes as standard records nothing, because there
        was nothing to record. A reader asking what this mount carries
        still needs telling, so the set answers with its head."""
        self.buy(client, owner, fighter, house_list, cutter)

        assert self.chosen(client, owner, fighter, house_list) == [
            ("Cutter grenade launchers",)
        ]

    def test_both_sets_are_named_in_the_order_the_offer_puts_them(
        self, client, owner, fighter, house_list, cutter
    ):
        self.buy(
            client,
            owner,
            fighter,
            house_list,
            cutter,
            **{choice_field(cutter, 0): "2", choice_field(cutter, 1): "0"},
        )

        assert self.chosen(client, owner, fighter, house_list) == [
            ("Cutter plasma guns", "Smoke dispenser")
        ]

    def test_a_set_nobody_took_anything_from_says_nothing(
        self, client, owner, fighter, house_list, cutter
    ):
        """A one-or-none set left alone is a mount without a dispenser,
        which is a thing it has not got — and a line saying so would be
        the page listing everything nobody bought."""
        self.buy(
            client,
            owner,
            fighter,
            house_list,
            cutter,
            **{choice_field(cutter, 0): "0", choice_field(cutter, 1): ""},
        )

        assert self.chosen(client, owner, fighter, house_list) == [
            ("Cutter grenade launchers",)
        ]

    def test_two_copies_each_say_what_they_took(
        self, client, owner, fighter, house_list, cutter
    ):
        self.buy(
            client, owner, fighter, house_list, cutter, **{choice_field(cutter, 0): "2"}
        )
        self.buy(
            client,
            owner,
            fighter,
            house_list,
            cutter,
            **{choice_field(cutter, 0): "1", choice_field(cutter, 1): "0"},
        )

        assert sorted(self.chosen(client, owner, fighter, house_list)) == [
            ("Cutter heavy stubbers", "Smoke dispenser"),
            ("Cutter plasma guns",),
        ]

    def test_something_that_asked_nothing_says_nothing(
        self, client, owner, gang, fighter, house_list, default_pack
    ):
        knife = create_wargear("Stiletto knife", price=10)
        house_list.entries.create(wargear=knife)

        client.force_login(owner)
        client.post(equip_url(fighter, house_list), {"thing": key_of(knife)})

        row = row_named(client, owner, fighter, house_list, "Stiletto knife")
        assert [copy.chosen for copy in row.copies] == [()]


class TestWhatTheOwnedCopyDraws:
    """The same, on the page — where the offer is drawn a second time."""

    def test_the_page_prints_what_the_copy_took(
        self, client, owner, fighter, house_list, cutter
    ):
        """The picks run together, which is the substring the radios
        below cannot make: "Buy another" redraws every option this mount
        offers, so either name on its own proves nothing."""
        client.force_login(owner)
        client.post(
            equip_url(fighter, house_list),
            {
                "thing": key_of(cutter),
                choice_field(cutter, 0): "2",
                choice_field(cutter, 1): "0",
            },
        )
        body = client.get(equip_url(fighter, house_list)).content.decode()

        assert "Cutter plasma guns · Smoke dispenser" in body

    def test_the_label_the_author_gave_a_set_still_reaches_nobody(
        self, client, owner, fighter, house_list, cutter
    ):
        """Naming the sets would be the tidy way to draw two picks, and
        it is the one way that is not ours to draw: the label is the
        author's note to themselves."""
        client.force_login(owner)
        client.post(
            equip_url(fighter, house_list),
            {
                "thing": key_of(cutter),
                choice_field(cutter, 0): "2",
                choice_field(cutter, 1): "0",
            },
        )
        body = client.get(equip_url(fighter, house_list)).content.decode()

        assert SET_LABEL not in body


class TestNamingWhatIsOwnedCostsNothing:
    """Describing a copy reads the recorded sets and the offer they came
    from, both already in hand — so a fighter buying more mounts asks the
    database no more than one who bought a single mount."""

    def test_it_costs_no_query_per_copy(
        self, client, owner, fighter, house_list, cutter
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.card import build_card
        from n26.core.owned import owned_things

        def buy(pick):
            client.force_login(owner)
            client.post(
                equip_url(fighter, house_list),
                {"thing": key_of(cutter), choice_field(cutter, 0): pick},
            )

        def measure():
            with CaptureQueriesContext(connection) as captured:
                card = build_card(fighter, with_options=True)
                owned = owned_things(card, "/equip")
                named = [thing.chosen for thing in owned[key_of(cutter)]]
                assert all(named), named
            return len(captured.captured_queries)

        buy("2")
        one = measure()
        for pick in ["0", "1", "2"]:
            buy(pick)
        assert measure() == one


class TestAPickTheListingNeverOffered:
    """A tampered index is a broken link, not a rule to explain — and it
    buys nothing at all, not even the mount."""

    @pytest.mark.parametrize("tampered", ["3", "-1", "nonsense", "0.5"])
    def test_it_is_refused_and_writes_nothing(
        self, client, owner, gang, fighter, house_list, cutter, tampered
    ):
        client.force_login(owner)
        response = client.post(
            equip_url(fighter, house_list),
            {"thing": key_of(cutter), choice_field(cutter, 0): tampered},
        )

        assert response.status_code == 404
        assert not Assignment.objects.filter(wargear=cutter).exists()
        gang.refresh_from_db()
        assert gang.credits == 1000

    def test_two_picks_in_one_set_are_refused(
        self, client, owner, gang, fighter, house_list, cutter
    ):
        """Radios cannot both be clicked, so two values for one set is a
        tampered form — and one click was never an order for two mounts'
        worth of guns."""
        client.force_login(owner)
        response = client.post(
            equip_url(fighter, house_list),
            {"thing": key_of(cutter), choice_field(cutter, 0): ["1", "2"]},
        )

        assert response.status_code == 404
        assert not Assignment.objects.filter(wargear=cutter).exists()
        gang.refresh_from_db()
        assert gang.credits == 1000

    def test_a_pick_scoped_to_another_listing_rides_along_and_is_ignored(
        self, client, owner, gang, fighter, house_list, cutter, default_pack
    ):
        """With no script running, a click submits every control on the
        page. Only the ones scoped to the clicked line may decide
        anything."""
        knife = create_wargear("Stiletto knife", price=10)
        house_list.entries.create(wargear=knife)

        client.force_login(owner)
        client.post(
            equip_url(fighter, house_list),
            {"thing": key_of(knife), choice_field(cutter, 0): "2"},
        )

        assert not Assignment.objects.filter(wargear=cutter).exists()
        gang.refresh_from_db()
        assert gang.credits == 990
        assert_reconciled(gang)


class TestScaling:
    """The offer rides the listing's own prefetches: a collection full of
    mounts asks the database no more than a collection with one."""

    def test_a_list_of_optioned_things_costs_no_more_queries_to_browse(
        self, gang, default_pack
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.browse import browse

        def mounts(count):
            made = []
            for index in range(count):
                mount = create_wargear(f"Mount {count}-{index}", price=100)
                for name, price in [("Standard guns", 0), ("Better guns", 20)]:
                    offer_option(
                        mount,
                        f"{name} {count}-{index}",
                        price=price,
                        thing=create_weapon(
                            f"{name} {count}-{index}", profiles=[("Fire", 0)]
                        ),
                    )
                made.append(mount)
            return made

        small = create_collection("Small yard", entries=mounts(2))
        big = create_collection("Big yard", entries=mounts(12))

        def measure(collection):
            with CaptureQueriesContext(connection) as captured:
                for line in browse(collection).all_lines():
                    assert line.choices
            return len(captured.captured_queries)

        assert measure(small) == measure(big)

    def test_the_same_holds_for_a_swept_listing(self, gang, default_pack):
        """A trading post finds its stock by rule rather than by row, so
        its sweep needs the offer prefetched too."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.browse import TRADING_POST, browse
        from n26.library.models import Wargear

        def posted(count):
            for index in range(count):
                mount = create_wargear(
                    f"Posted mount {count}-{index}", price=100, trade_point_price=3
                )
                for name, price in [("Standard guns", 0), ("Better guns", 20)]:
                    offer_option(
                        mount,
                        f"{name} {count}-{index}",
                        price=price,
                        thing=create_weapon(
                            f"{name} {count}-{index}", profiles=[("Fire", 0)]
                        ),
                    )

        yard = create_collection("The yard", contains=[Wargear])

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert list(browse(yard, TRADING_POST).all_lines())
            return len(captured.captured_queries)

        posted(2)
        few = measure()
        posted(10)
        assert measure() == few


class TestTheActionAndTheScreenAgree:
    """The purchase's arithmetic is the operation's own, reached two ways."""

    def test_a_swap_bought_through_the_page_is_priced_as_the_verb_prices_it(
        self, client, owner, gang, fighter, house_list, cutter, make_profile
    ):
        """One fighter buys through the equip page, another through
        ``Operation.buy`` with the set named. The ledger must not be able
        to tell them apart — the page is a way to the operation, never a
        second pricing of it."""
        from n26.core.models import LedgerEntry

        plasma = cutter.options.get(name="Cutter plasma guns").default_set
        other = make_profile("Second Runner", price=0)
        set_statline(other, movement=5, weapon_skill=4, toughness=3)
        theirs = hire(gang, other, "Nell")
        buy(theirs, cutter_line(house_list), option=[plasma])

        client.force_login(owner)
        client.post(
            equip_url(fighter, house_list),
            {"thing": key_of(cutter), choice_field(cutter, 0): "2"},
        )

        entries = LedgerEntry.objects.filter(assignment__wargear=cutter)
        assert {(entry.paid, entry.list_price) for entry in entries} == {(165, 165)}
        gang.refresh_from_db()
        assert_reconciled(gang)
