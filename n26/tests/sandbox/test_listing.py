"""Join catalogue offers with a model's owned equipment through build_catalogue. Owned
entries contain each assignment and a nested purchase entry for buying another.

Use two Autoguns with paid ammunition attached to one to verify copy counts, part
ownership and purchase controls together.
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

#: Base URL used to build each assignment's confirmation links.
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
    """An Autogun with its base profile, a free firing mode and paid ammunition."""
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
    """Offer the weapon, paid ammunition and knife. The free firing mode is built into the
    weapon and does not require a collection entry.
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
    """Two Autogun assignments, one carrying a paid warp round."""
    first = give_weapon(fighter, autogun, paid=20)
    ammo = buy_weapon_profile(first, warp)
    second = give_weapon(fighter, autogun, paid=20)
    return first, ammo, second


class TestARowNobodyOwns:
    """Display a priced purchase entry for equipment the model does not hold."""

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
        """Submit the catalogue identity so the server can derive its offer again."""
        row = rows_by_name(catalogue_for(fighter, house_list))["Knife"]

        assert row.buy.kind == SUBMIT
        assert row.buy.target == thing_key(knife)

    def test_the_input_names_are_the_ones_the_server_reads_back(
        self, fighter, house_list, knife
    ):
        """Derive price and part field names from the same content key used by the server."""
        row = rows_by_name(catalogue_for(fighter, house_list))["Knife"]
        key = thing_key(knife)

        assert row.price_field == price_field(key)
        assert row.parts_field == parts_field(key)


class TestAGunsPaidAmmo:
    """Purchase ammunition through its parent weapon's options."""

    def test_the_paid_line_is_an_option_and_the_free_one_is_not_offered(
        self, fighter, house_list
    ):
        """Offer paid ammunition as an option while keeping the base profile implicit."""
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]

        assert [option.name for option in row.options] == ["warp round"]

    def test_an_option_carries_its_place_and_a_price_box_of_its_own(
        self, fighter, house_list, autogun
    ):
        """Give each paid part an independent price input so gun discounts do not change
        ammunition prices.
        """
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        (option,) = row.options

        assert option.index == 0
        assert option.price == 10
        assert option.field == parts_field(thing_key(autogun))
        assert option.price_field == price_field(thing_key(autogun), 0)

    def test_an_option_offers_no_action_of_its_own(self, fighter, house_list):
        """Selected parts use the parent weapon's purchase action."""
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        (option,) = row.options

        assert not hasattr(option, "buy")


class TestOwningOneReplacesTheRow:
    """Replace the sale entry with an owned entry containing the model's assignments."""

    def test_the_row_becomes_an_owned_row(self, fighter, house_list, armed, autogun):
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]

        assert isinstance(row, OwnedRow)
        assert row.key == thing_key(autogun)

    def test_a_category_holds_one_kind_of_row_or_the_other(
        self, fighter, house_list, armed
    ):
        """Display one listing entry per content key, using owned state when an assignment
        exists.
        """
        catalogue = catalogue_for(fighter, house_list)
        rows = list(catalogue.all_rows())

        assert [type(row).__name__ for row in rows] == ["OwnedRow", "Listing"]

        assert len({row.key for row in rows}) == len(rows)

    def test_the_count_is_copies_and_not_pieces(self, fighter, house_list, armed):
        """Count weapon assignments without counting attached ammunition as additional
        weapons.
        """
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]

        assert row.count == 2
        assert len(row.copies) == 2

    def test_each_copy_can_be_told_apart_from_the_other(
        self, fighter, house_list, armed
    ):
        """Identify each assignment separately so actions target the selected copy."""
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
        """Omit the weapon-name suffix because the parent entry already identifies the
        weapon.
        """
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        parts = [part.name for copy in row.copies for part in copy.parts]

        assert "warp round (Autogun)" not in parts

    def test_a_thing_the_fighter_does_not_hold_is_untouched(
        self, fighter, house_list, armed
    ):
        row = rows_by_name(catalogue_for(fighter, house_list))["Knife"]

        assert isinstance(row, Listing)


class TestBuyingAnother:
    """Retain the full purchase entry beneath owned copies."""

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
        """Retain the same purchase controls, ammunition options and prices beneath an
        owned entry.
        """
        profile = make_profile("Juve", price=0)
        make_statline(profile, movement=5, weapon_skill=5, toughness=3)
        empty_handed = hire(gang, profile, "Sid")

        theirs = rows_by_name(catalogue_for(empty_handed, house_list))["Autogun"]
        mine = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]

        assert isinstance(theirs, Listing)
        assert mine.buy == theirs


class TestWhatACopyOffers:
    """Describe available equipment actions in the listing structure."""

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
        # Action tones determine grouping and destructive styling.
        assert {action.tone for action in copy.more} == {SECONDARY, DANGER}
        assert [action.label for action in copy.more if action.tone == DANGER] == [
            "Delete"
        ]

    def test_every_act_on_a_copy_is_a_link_to_a_confirmation(
        self, fighter, house_list, armed
    ):
        """Use URL-addressed confirmations outside the catalogue form to avoid nested forms
        and preserve reload behaviour.
        """
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
        """Weapon profiles remain attached to their weapon, so omit reassignment. Paid
        profiles still offer sale, refund and removal actions.
        """
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

    def test_a_weapons_own_named_profile_is_offered_no_way_to_leave(
        self, fighter, house_list, armed
    ):
        """Built-in firing profiles remain with the weapon and have no independent removal
        actions.
        """
        first, _, _ = armed
        mode = first.children.get(weapon_profile__name="fully automatic")
        row = rows_by_name(catalogue_for(fighter, house_list))["Autogun"]
        (part,) = [
            part
            for copy in row.copies
            for part in copy.parts
            if part.id == str(mode.pk)
        ]

        assert part.sell is None
        assert part.more == ()

    def test_a_bought_accessory_offers_detach(self, gang, fighter, house_list, armed):
        """Detaching purchased accessories leaves them owned, while sale and removal
        relinquish them.
        """
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
    """Show Trade Point and exclusive availability only for collections using those terms.
    Preserve the underlying browse values for authoring.
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
        # Preserve credit prices independently of availability display.
        assert rows["Rope"].price == 5
        assert rows["Heirloom"].price == 40

    def test_the_line_underneath_still_knows_the_truth(
        self, gang, fighter, default_pack
    ):
        """Keep Trade Point values in browse data even when player display omits them."""
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
    """Preserve browse section and category order."""

    def test_a_section_the_content_never_named_gets_a_word_on_it(
        self, fighter, house_list
    ):
        """Give unnamed sections a visible label so their entries remain reachable through
        tabs.
        """
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
