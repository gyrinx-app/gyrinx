"""A catalogue: what is for sale, joined to what the fighter holds.

``browse`` knows a collection and nothing about who is reading it;
``owned_things`` knows a fighter's card and nothing about what is for
sale. ``build_catalogue`` is the join, and this suite is what pins the two
rules the join exists for: owning something *replaces* its row, and the
row it replaces is still there, nested, so a reader can buy another.

The worked case is a fighter carrying two Autoguns with a paid warp round
in one of them — the case where every rule in the structure has to hold
at once: two copies under one row, a part under one copy only, a count
that says two rather than three, and a Buy still on offer.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import browse
from n26.core.card import build_card
from n26.core.listing import (
    DANGER,
    LINK,
    PRIMARY,
    SECONDARY,
    SUBMIT,
    Listing,
    OwnedRow,
    build_catalogue,
    parts_field,
    price_field,
)
from n26.core.owned import owned_things, thing_key
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import add_weapon_profile
from n26.tests.sandbox.actions import (
    assign,
    buy_weapon_profile,
    create_collection,
    create_wargear,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
)

pytestmark = pytest.mark.django_db

#: The page a reader is on. Every confirmation an owned copy offers opens
#: over it, so the addresses in the structure are built from it.
AT = "/n26/fighters/vex/equip/?list=1"


@pytest.fixture
def gang(gang_type):
    player = User.objects.create_user("tom")
    return found_gang("The Ashen Choir", gang_type, owner=player, budget=1000)


@pytest.fixture
def fighter(gang, make_profile, make_statline):
    profile = make_profile("Ganger", price=0)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    return hire(gang, profile, "Vex")


@pytest.fixture
def autogun(default_pack):
    """A gun with three lines: its own, a free firing mode, paid ammo."""
    weapon = create_weapon("Autogun", profiles=[("", 0)], price=20)
    add_weapon_profile(weapon, name="fully automatic", price=0)
    add_weapon_profile(weapon, name="warp round", price=10)
    return weapon


@pytest.fixture
def knife(default_pack):
    return create_wargear("Knife", price=10)


@pytest.fixture
def warp(autogun):
    from n26.library.models import WeaponProfile

    return WeaponProfile.objects.get(weapon=autogun, name="warp round")


@pytest.fixture
def house_list(gang, autogun, knife, warp):
    """The gun, the round the list sells for it, and a knife.

    The gun's free firing mode is deliberately not named: a list carries
    the ammo it names, and a mode that comes with the gun is not for
    sale — see ``TestAmmoRidesUnderTheGun`` in test_collections.py.
    """
    collection = create_collection("House List", entries=[autogun, warp, knife])
    assign(collection, gang=gang)
    return collection


def catalogue_for(fighter, collection):
    card = build_card(fighter)
    return build_catalogue(browse(collection), owned_things(card, AT))


def rows_by_name(catalogue):
    return {row.name: row for row in catalogue.all_rows()}


@pytest.fixture
def armed(gang, fighter, autogun, warp, house_list):
    """Two Autoguns, one of them carrying a paid warp round."""
    first = give_weapon(fighter, autogun, paid=20)
    ammo = buy_weapon_profile(first, warp)
    second = give_weapon(fighter, autogun, paid=20)
    return first, ammo, second


class TestARowNobodyOwns:
    """The ordinary case: a thing on the list, and a way to buy it."""

    def test_a_line_becomes_a_row_that_offers_to_sell_it(
        self, fighter, house_list, knife
    ):
        row = rows_by_name(catalogue_for(fighter, house_list))["Knife"]

        assert isinstance(row, Listing)
        assert row.key == thing_key(knife)
        assert row.price == 10
        assert row.buy.label == "Buy"
        assert row.buy.tone == PRIMARY

    def test_buying_submits_the_rows_identity_and_nothing_else(
        self, fighter, house_list, knife
    ):
        """The catalogue is one form and a purchase is a click within it, so
        Buy carries the key the server looks the line up by — never a
        price, which the server derives for itself."""
        row = rows_by_name(catalogue_for(fighter, house_list))["Knife"]

        assert row.buy.kind == SUBMIT
        assert row.buy.target == thing_key(knife)

    def test_the_input_names_are_the_ones_the_server_reads_back(
        self, fighter, house_list, knife
    ):
        """Derived from the key on both sides. Computed twice from two
        places, they would eventually disagree, and a box a reader typed
        in would be read as belonging to some other row."""
        row = rows_by_name(catalogue_for(fighter, house_list))["Knife"]
        key = thing_key(knife)

        assert row.price_field == price_field(key)
        assert row.parts_field == parts_field(key)


class TestAGunsPaidAmmo:
    """Ammo is a way the gun is built, not a second thing on the list."""

    def test_the_paid_line_is_an_option_and_the_free_one_is_not_offered(
        self, fighter, house_list
    ):
        """An equipment list prices in credits, so what it offers is
        everything paid. The gun's own unnamed line *is* the gun."""
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]

        assert [option.name for option in row.options] == ["warp round"]

    def test_an_option_carries_its_place_and_a_price_box_of_its_own(
        self, fighter, house_list, autogun
    ):
        """A discount on the gun is not a discount on the rounds, so each
        is charged at the figure typed on its own row."""
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        (option,) = row.options

        assert option.index == 0
        assert option.price == 10
        assert option.field == parts_field(thing_key(autogun))
        assert option.price_field == price_field(thing_key(autogun), 0)

    def test_an_option_offers_no_action_of_its_own(self, fighter, house_list):
        """It rides the gun's Buy: one click, one purchase, however many
        boxes are ticked."""
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        (option,) = row.options

        assert not hasattr(option, "buy")


class TestOwningOneReplacesTheRow:
    """A reader looking at a row for a thing they are already carrying is
    asking what to do with the one they have."""

    def test_the_row_becomes_an_owned_row(self, fighter, house_list, armed, autogun):
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]

        assert isinstance(row, OwnedRow)
        assert row.key == thing_key(autogun)

    def test_a_category_holds_one_kind_of_row_or_the_other(
        self, fighter, house_list, armed
    ):
        """Never both for one thing, and never a flag on one type: the
        row a reader sees is the whole answer to whether they own one."""
        catalogue = catalogue_for(fighter, house_list)
        rows = list(catalogue.all_rows())

        assert [type(row).__name__ for row in rows] == ["OwnedRow", "Listing"]
        # One row per thing on the list, whoever owns what.
        assert len({row.key for row in rows}) == len(rows)

    def test_the_count_is_copies_and_not_pieces(self, fighter, house_list, armed):
        """Two guns with a round in one of them is two. Counting the round
        would tell a reader they were carrying three Autoguns."""
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]

        assert row.count == 2
        assert len(row.copies) == 2

    def test_each_copy_can_be_told_apart_from_the_other(
        self, fighter, house_list, armed
    ):
        """Each is its own row in the ledger, and each is sold on its own
        — one line counted twice would be a control acting on whichever
        copy the server happened to pick."""
        first, _, second = armed
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]

        assert {copy.id for copy in row.copies} == {str(first.pk), str(second.pk)}

    def test_the_paid_round_hangs_off_the_gun_it_was_bought_for(
        self, fighter, house_list, armed
    ):
        first, ammo, second = armed
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        parts = {copy.id: [part.name for part in copy.parts] for copy in row.copies}

        assert parts[str(first.pk)] == ["fully automatic", "warp round"]
        assert parts[str(second.pk)] == ["fully automatic"]

    def test_a_part_goes_by_its_own_name(self, fighter, house_list, armed):
        """ "warp round (Autogun)" is what a card prints, where nothing
        above the line says which gun. Here the gun is the row above."""
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        parts = [part.name for copy in row.copies for part in copy.parts]

        assert "warp round (Autogun)" not in parts

    def test_a_thing_the_fighter_does_not_hold_is_untouched(
        self, fighter, house_list, armed
    ):
        row = rows_by_name(catalogue_for(fighter, house_list))["Knife"]

        assert isinstance(row, Listing)


class TestBuyingAnother:
    """Owning one of something has never been a reason the catalogue stops
    selling it."""

    def test_an_owned_row_still_carries_the_row_it_replaced(
        self, fighter, house_list, armed
    ):
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]

        assert isinstance(row.buy, Listing)
        assert row.buy.buy.kind == SUBMIT
        assert row.buy.buy.target == row.key

    def test_the_nested_row_is_the_one_an_empty_handed_fighter_would_see(
        self, gang, fighter, house_list, armed, make_profile, make_statline
    ):
        """Not a reduced version of it. There is one definition of what
        buying this thing looks like, and both readers get it — ammo
        boxes, price box and all."""
        profile = make_profile("Juve", price=0)
        make_statline(profile, movement=5, weapon_skill=5, toughness=3)
        empty_handed = hire(gang, profile, "Sid")

        theirs = rows_by_name(catalogue_for(empty_handed, house_list))["Autogun"]
        mine = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]

        assert isinstance(theirs, Listing)
        assert mine.buy == theirs


class TestWhatACopyOffers:
    """Four acts, and the row says what each one means rather than how to
    draw it."""

    def test_selling_is_the_act_in_the_open_and_the_rest_share_a_chevron(
        self, fighter, house_list, armed
    ):
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        copy = row.copies[0]

        assert copy.sell.label == "Sell"
        assert copy.sell.tone == DANGER
        assert [action.label for action in copy.more] == [
            "Reassign",
            "Refund",
            "Delete",
        ]
        # The tone is what sorts the menu into groups and colours the last
        # of them, so it is the structure that decides Delete is the one
        # that ends with nothing to show for it.
        assert {action.tone for action in copy.more} == {SECONDARY, DANGER}
        assert [action.label for action in copy.more if action.tone == DANGER] == [
            "Delete"
        ]

    def test_every_act_on_a_copy_is_a_link_to_a_confirmation(
        self, fighter, house_list, armed
    ):
        """A server state, so it survives a reload and works with
        scripting off — and so it stays out of the catalogue's own form,
        which HTML would not nest one inside."""
        first, _, _ = armed
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        copy = next(copy for copy in row.copies if copy.id == str(first.pk))

        assert copy.sell.kind == LINK
        assert copy.sell.target == f"{AT}&sell={first.pk}"
        assert [action.target for action in copy.more] == [
            f"{AT}&reassign={first.pk}",
            f"{AT}&refund={first.pk}",
            f"{AT}&remove={first.pk}",
        ]

    def test_a_part_is_offered_no_move(self, fighter, house_list, armed):
        """A firing line belongs to the gun it names, and
        ``Operation.move`` refuses it — so offering a move here would be
        offering a click that cannot work. It keeps the rest: buying the
        wrong ammunition is as easy a mistake as buying the wrong gun.
        An accessory the gang bought is the other case, and its kebab
        offers Detach."""
        _, ammo, _ = armed
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        (part,) = [
            part
            for copy in row.copies
            for part in copy.parts
            if part.id == str(ammo.pk)
        ]

        assert [action.label for action in part.more] == ["Refund", "Remove"]
        assert part.sell.target == f"{AT}&sell={ammo.pk}"

    def test_a_bought_accessory_offers_detach(self, gang, fighter, house_list, armed):
        """A sight is gear in its own right. Taking it off leaves the
        fighter holding it, so the row asks that before the ways of
        parting with it."""
        from n26.core.operations import operation
        from n26.library.authoring import create_weapon_accessory

        first, _, _ = armed
        sight = create_weapon_accessory("Telescopic sight", price=25)
        with operation(fighter.gang, actor=fighter.gang.owner) as op:
            bolted = op.buy(first, thing=sight)
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        (part,) = [
            part
            for copy in row.copies
            for part in copy.parts
            if part.id == str(bolted.pk)
        ]

        assert [action.label for action in part.more] == [
            "Detach",
            "Fit to a weapon",
            "Refund",
            "Remove",
        ]
        assert part.more[0].target == f"{AT}&detach={bolted.pk}"
        assert part.more[1].target == f"{AT}&fit={bolted.pk}"
        assert_reconciled(gang)


class TestWhatARowPrints:
    """A row prints the collection's own terms and nothing borrowed.

    An equipment list prices in credits. The Trade Point figure an item
    carries is a fact about the Trading Post, and printed on a house
    list it invites a reader to compare two lists by a number only one
    of them charges. "E" goes the same way: it is what the catalogue's
    TP column says for a thing the post never stocks, so on a list where
    everything is list-only it says nothing at all.

    The browsed line keeps both figures. This is about the row.
    """

    def test_a_house_list_prints_no_trade_points_and_no_marker(
        self, gang, fighter, default_pack
    ):
        exclusive = create_wargear("Heirloom", price=40, is_exclusive=True)
        posted = create_wargear("Rope", price=5, trade_point_price=3)
        collection = create_collection("House List", entries=[exclusive, posted])
        assign(collection, gang=gang)

        rows = rows_by_name(catalogue_for(fighter, collection))

        assert rows["Rope"].trade_points is None
        assert rows["Heirloom"].is_exclusive is False
        # The prices themselves are untouched — this is about what the
        # list deals in, not about what anything costs.
        assert rows["Rope"].price == 5
        assert rows["Heirloom"].price == 40

    def test_the_line_underneath_still_knows_the_truth(
        self, gang, fighter, default_pack
    ):
        """An authoring preview shows a writer what the catalogue says,
        so hiding a figure from a player must not lose it."""
        posted = create_wargear("Rope", price=5, trade_point_price=3)
        collection = create_collection("House List", entries=[posted])
        assign(collection, gang=gang)

        (line,) = browse(collection).all_lines()

        assert line.trade_points == 3
        assert line.shows_trade_points is False

    def test_a_trading_post_prints_its_trade_points(self, gang, fighter, default_pack):
        from n26.tests.sandbox.actions import create_trading_post

        create_wargear("Rope", price=5, trade_point_price=3)
        post = create_trading_post()
        assign(post, gang=gang)

        rows = rows_by_name(catalogue_for(fighter, post))

        assert rows["Rope"].trade_points == 3

    def test_a_guns_rounds_print_the_same_way_the_gun_does(
        self, gang, fighter, autogun, warp, house_list
    ):
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        (option,) = row.options

        assert row.trade_points is None
        assert option.trade_points is None


class TestTheShapeAScreenDraws:
    """Sections and categories, in the order the browse gave them."""

    def test_a_section_the_content_never_named_gets_a_word_on_it(
        self, fighter, house_list
    ):
        """A catalogue is drawn as a strip of tabs, and a tab with no word
        on it is one nobody can click — so its rows would be served with
        no way to reach them."""
        catalogue = catalogue_for(fighter, house_list)

        assert [section.name for section in catalogue.sections] == ["Uncategorised"]

    def test_a_named_category_keeps_its_heading(self, fighter, gang, autogun, knife):
        from n26.tests.sandbox.actions import create_category

        blades = create_category("Armoury", "Blades", position=0)
        knife.category = blades
        knife.save()
        collection = create_collection("Armoury List", entries=[knife])
        assign(collection, gang=gang)

        catalogue = catalogue_for(fighter, collection)
        (section,) = catalogue.sections
        (category,) = section.categories

        assert section.name == "Armoury"
        assert category.name == "Blades"
        assert [row.name for row in category.rows] == ["Knife"]

    def test_the_catalogue_goes_by_the_collections_name(self, fighter, house_list):
        assert catalogue_for(fighter, house_list).name == str(house_list)
