"""Two-slot weapons carry the book's asterisk wherever their name is drawn.

The book marks a weapon that takes two of a card's three weapon slots
with an asterisk after its name. The library stores that as
``Weapon.slots`` and keeps the asterisk out of the stored name; every
surface that prints the name — the screen card, the print card, the text
card, the equip picker, a held copy, the stash — draws ``name`` and then
``slot_mark``, so the mark is never lost from a surface and never written
into a name. One slot draws nothing, and so does a grenade's nought: the
mark means "this takes two". Nothing explains the mark; the book's
readers know it.
"""

import re
from dataclasses import replace

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.browse import browse
from n26.core.card import build_card
from n26.core.listing import Listing, OwnedRow, build_catalogue
from n26.core.owned import owned_things
from n26.core.render import WeaponLine, build_model_card, render_gang
from n26.core.render_text import gang_to_text, render_gang_sheet, render_model_card
from n26.library.models import slot_mark
from n26.tests.sandbox.actions import (
    assign,
    create_collection,
    create_wargear,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
)

pytestmark = pytest.mark.django_db

#: The page a reader is on; a held copy's addresses are built from it.
AT = "/n26/fighters/vex/equip/?list=1"


class TestTheMark:
    """One rule, in one place: two or more slots is an asterisk."""

    def test_two_slots_is_an_asterisk(self):
        assert slot_mark(2) == "*"

    def test_more_than_two_is_still_an_asterisk(self):
        assert slot_mark(3) == "*"

    def test_one_slot_is_the_ordinary_weapon_and_reads_bare(self):
        assert slot_mark(1) == ""

    def test_a_grenade_takes_no_slot_and_reads_bare(self):
        assert slot_mark(0) == ""

    def test_a_card_line_says_the_same(self):
        assert WeaponLine("Heavy stubber", 0, slots=2).slot_mark == "*"
        assert WeaponLine("Autogun", 0, slots=1).slot_mark == ""
        assert WeaponLine("Frag grenades", 0, slots=0).slot_mark == ""


@pytest.fixture
def player():
    return User.objects.create_user("player")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Ashen Choir", gang_type, owner=player, budget=1000)


@pytest.fixture
def fighter(gang, make_profile, make_statline):
    profile = make_profile("Ganger", price=0)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    return hire(gang, profile, "Vex")


@pytest.fixture
def stubber(default_pack):
    """An asterisked weapon: two of the card's three slots."""
    return create_weapon("Heavy stubber", profiles=[("", 0)], price=130, slots=2)


@pytest.fixture
def autogun(default_pack):
    return create_weapon("Autogun", profiles=[("", 0)], price=15)


@pytest.fixture
def grenades(default_pack):
    """Grenades take no slot at all, and the book leaves them bare."""
    return create_weapon("Frag grenades", profiles=[("", 0)], price=30, slots=0)


@pytest.fixture
def knife(default_pack):
    return create_wargear("Knife", price=10)


@pytest.fixture
def house_list(gang, stubber, autogun, grenades, knife):
    collection = create_collection(
        "House List", entries=[stubber, autogun, grenades, knife]
    )
    assign(collection, gang=gang)
    return collection


@pytest.fixture
def armed(fighter, stubber, autogun, grenades):
    """One of each on the fighter's card."""
    give_weapon(fighter, stubber, paid=130)
    give_weapon(fighter, autogun, paid=15)
    give_weapon(fighter, grenades, paid=30)
    return fighter


def weapons_by_name(card):
    return {weapon.name: weapon for weapon in card.weapons}


class TestTheStoredName:
    """The mark is drawn, never stored: the name stays the book's name."""

    def test_the_weapon_keeps_a_bare_name_and_says_its_mark_apart(self, stubber):
        assert stubber.name == "Heavy stubber"
        assert stubber.slot_mark == "*"

    def test_the_card_line_keeps_the_bare_name_too(self, armed):
        weapons = weapons_by_name(build_model_card(armed))
        assert set(weapons) == {"Heavy stubber", "Autogun", "Frag grenades"}
        assert weapons["Heavy stubber"].slot_mark == "*"
        assert weapons["Autogun"].slot_mark == ""
        assert weapons["Frag grenades"].slot_mark == ""


class TestTheScreenCard:
    """The gang sheet draws the mark after the name, and the fighter's own
    page — where the weapon has a menu — gives the menu the same name, so
    a screen reader hears what a sighted reader sees."""

    def test_the_gang_sheet_carries_the_mark(self, client, gang, armed):
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Heavy stubber*" in body

    def test_the_weapons_menu_is_named_with_the_mark(self, client, gang, armed):
        client.force_login(gang.owner)
        url = reverse("n26-edit-fighter", args=[armed.pk])
        body = client.get(url).content.decode()

        assert "Heavy stubber*" in body
        assert 'aria-label="More for Heavy stubber*"' in body
        assert 'aria-label="More for Autogun"' in body

    def test_a_one_slot_weapon_and_a_grenade_read_bare(self, client, gang, armed):
        client.force_login(gang.owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Autogun" in body and "Autogun*" not in body
        assert "Frag grenades" in body and "Frag grenades*" not in body


class TestThePrintCard:
    def test_the_printed_name_carries_the_mark(self, client, gang, armed):
        client.force_login(gang.owner)
        paper = client.get(reverse("n26-print", args=[gang.pk])).content.decode()

        assert "Heavy stubber*" in paper
        assert "Autogun*" not in paper
        assert "Frag grenades*" not in paper


class TestTheTextCard:
    def test_the_line_carries_the_mark_before_its_rating(self, armed):
        text = "\n".join(render_model_card(build_model_card(armed)))
        print("\n" + text)

        assert "Heavy stubber* — 130cr" in text
        assert "Autogun — 15cr" in text
        assert "Frag grenades — 30cr" in text


def catalogue_for(fighter, collection):
    card = build_card(fighter)
    return build_catalogue(browse(collection), owned_things(card, AT))


def rows_by_name(catalogue):
    return {row.name: row for row in catalogue.all_rows()}


class TestTheEquipPicker:
    """A row for sale, a row for something held, and each held copy all
    carry the weapon's slots, so the picker marks what the card marks."""

    def test_a_listing_carries_its_slots_and_the_mark(self, fighter, house_list):
        rows = rows_by_name(catalogue_for(fighter, house_list))

        assert isinstance(rows["Heavy stubber"], Listing)
        assert rows["Heavy stubber"].slots == 2
        assert rows["Heavy stubber"].slot_mark == "*"
        assert rows["Autogun"].slot_mark == ""
        assert rows["Frag grenades"].slot_mark == ""
        # Wargear takes no weapon slot and draws no mark either.
        assert rows["Knife"].slot_mark == ""

    def test_a_held_row_and_its_copies_carry_the_mark(self, fighter, house_list, armed):
        rows = rows_by_name(catalogue_for(fighter, house_list))

        held = rows["Heavy stubber"]
        assert isinstance(held, OwnedRow)
        assert held.slot_mark == "*"
        assert [copy.slot_mark for copy in held.copies] == ["*"]
        assert held.buy.slot_mark == "*"
        assert rows["Frag grenades"].slot_mark == ""
        assert [copy.slot_mark for copy in rows["Frag grenades"].copies] == [""]

    def test_the_page_draws_the_mark_on_the_row(
        self, client, gang, fighter, house_list
    ):
        client.force_login(gang.owner)
        url = reverse("n26-equip", args=[fighter.pk])
        body = client.get(f"{url}?list={house_list.pk}").content.decode()

        assert "Heavy stubber*" in body
        assert "Autogun*" not in body
        assert "Frag grenades*" not in body

    def test_the_page_draws_the_mark_on_a_held_copys_menu(
        self, client, gang, fighter, house_list, armed, stubber
    ):
        client.force_login(gang.owner)
        url = reverse("n26-equip", args=[fighter.pk])
        key = f"{stubber._meta.label_lower}:{stubber.pk}"
        body = client.get(f"{url}?list={house_list.pk}&owned={key}").content.decode()

        assert 'aria-label="More for Heavy stubber*"' in body
        assert 'aria-label="Add accessory to Heavy stubber*"' in body


class TestThePriceBoxes:
    """The box a price is typed into is named the way its row is, so a
    screen reader hears the mark there too."""

    def test_a_listings_price_box_is_named_with_the_mark(
        self, client, gang, fighter, house_list
    ):
        client.force_login(gang.owner)
        url = reverse("n26-equip", args=[fighter.pk])
        body = client.get(f"{url}?list={house_list.pk}").content.decode()

        assert 'aria-label="Price for Heavy stubber*"' in body
        assert 'aria-label="Price for Autogun"' in body

    def test_buy_anothers_price_box_is_named_with_the_mark(
        self, client, gang, fighter, house_list, armed, stubber
    ):
        client.force_login(gang.owner)
        url = reverse("n26-equip", args=[fighter.pk])
        key = f"{stubber._meta.label_lower}:{stubber.pk}"
        body = client.get(f"{url}?list={house_list.pk}&owned={key}").content.decode()

        # Owning one replaces the listing's row, so the only price box
        # for the stubber on this page is the one under "Buy another".
        assert "Buy another" in body
        assert 'aria-label="Price for Heavy stubber*"' in body


class TestThePrintSetupPicker:
    def test_the_weapon_to_tick_is_named_with_the_mark(self, client, gang, armed):
        client.force_login(gang.owner)
        setup = client.get(reverse("n26-print-setup", args=[gang.pk])).content.decode()

        assert "Heavy stubber*" in setup
        # Beside the mark, the picker still counts the slots in words.
        assert "2 slots" in setup
        assert "Autogun*" not in setup
        assert "Frag grenades*" not in setup


@pytest.fixture
def stashed(gang, stubber, grenades):
    """A two-slot weapon and a grenade in the gang's stash."""
    assign(stubber, stash=gang.stash, paid=130)
    assign(grenades, stash=gang.stash, paid=30)
    return gang


class TestTheStash:
    """The stash draws a line's name the way a card does — on the gang's
    equip page, on the gang sheet with its actions, and on paper."""

    def test_the_stash_line_carries_its_slots(self, stashed):
        stashed.refresh_from_db()
        lines = {line.name: line for line in render_gang(stashed).stash}

        assert lines["Heavy stubber"].slots == 2
        assert lines["Heavy stubber"].slot_mark == "*"
        assert lines["Frag grenades"].slot_mark == ""

    def test_a_stashed_weapon_is_marked_on_the_gangs_own_page(self, client, stashed):
        client.force_login(stashed.owner)
        url = reverse("n26-equip-gang", args=[stashed.pk])
        body = client.get(f"{url}?list=stash").content.decode()

        assert "Heavy stubber*" in body
        assert "Frag grenades" in body and "Frag grenades*" not in body

    def test_the_gang_sheet_marks_it_and_its_actions(self, client, stashed):
        client.force_login(stashed.owner)
        body = client.get(reverse("n26-gang", args=[stashed.pk])).content.decode()

        assert "Heavy stubber*" in body
        assert 'aria-label="Actions for Heavy stubber*"' in body
        assert 'aria-label="Actions for Frag grenades"' in body
        assert "Frag grenades*" not in body

    def test_the_printed_stash_marks_it(self, client, stashed):
        client.force_login(stashed.owner)
        paper = client.get(reverse("n26-print", args=[stashed.pk])).content.decode()

        assert "Heavy stubber*" in paper
        assert "Frag grenades*" not in paper

    def test_a_reader_who_does_not_own_the_gang_sees_the_mark(self, client, stashed):
        """The sheet a reader who owns nothing here sees draws the stash
        without menus, through the same lines a card's kit uses — and
        the mark goes with the name there too."""
        body = client.get(reverse("n26-gang", args=[stashed.pk])).content.decode()

        assert "Heavy stubber*" in body
        assert "Actions for" not in body
        assert "Frag grenades*" not in body


class TestTwoOfATwoSlotWeapon:
    """A weapon is never folded into a count — two guns of one name may
    differ in their ammo, their accessories and their choices — so two of
    a two-slot weapon are two marked lines. Where a line does stand for
    more than one, the mark sits between the name and the count."""

    @pytest.fixture
    def doubled(self, gang, stubber):
        assign(stubber, stash=gang.stash, paid=130)
        assign(stubber, stash=gang.stash, paid=130)
        gang.refresh_from_db()
        return gang

    def test_the_sheet_keeps_two_marked_lines(self, doubled):
        lines = render_gang(doubled).stash

        assert [(line.name, line.slot_mark, line.count) for line in lines] == [
            ("Heavy stubber", "*", 1),
            ("Heavy stubber", "*", 1),
        ]

    def test_a_reader_sees_two_marked_lines_and_no_count(self, client, doubled):
        body = client.get(reverse("n26-gang", args=[doubled.pk])).content.decode()

        assert body.count("Heavy stubber*") >= 2
        assert "(x2)" not in body

    def test_the_print_page_writes_both_marked(self, client, doubled):
        client.force_login(doubled.owner)
        paper = client.get(reverse("n26-print", args=[doubled.pk])).content.decode()

        assert paper.count("<td>Heavy stubber*</td>") == 2
        assert "(x2)" not in paper

    def test_the_text_sheet_writes_both_marked(self, doubled):
        text = gang_to_text(doubled)
        print("\n" + text)

        assert text.count("  Heavy stubber* — 130cr") == 2
        assert "(x2)" not in text

    def test_a_line_standing_for_two_puts_the_mark_before_the_count(self, doubled):
        """Pinned on the text sheet, whose stash line is composed the way
        the print page's is: name, then the asterisk, then the count."""
        sheet = render_gang(doubled)
        first, _ = sheet.stash
        sheet.stash = [replace(first, count=2)]

        text = render_gang_sheet(sheet)

        assert "  Heavy stubber* (x2) — 130cr" in text


class TestTheDialogs:
    """A dialog opened from a marked line names the weapon the same way,
    in its title and wherever it offers the weapon as somewhere to go."""

    def test_selling_asks_with_the_mark(
        self, client, gang, fighter, house_list, stubber
    ):
        held = give_weapon(fighter, stubber, paid=130)
        client.force_login(gang.owner)
        url = reverse("n26-equip", args=[fighter.pk])
        body = client.get(f"{url}?list={house_list.pk}&sell={held.pk}").content.decode()

        assert "Sell Heavy stubber*?" in body

    def test_a_loose_accessory_is_offered_the_marked_gun(
        self, client, gang, fighter, house_list, stubber, autogun
    ):
        from n26.tests.sandbox.actions import create_weapon_accessory

        give_weapon(fighter, stubber, paid=130)
        give_weapon(fighter, autogun, paid=15)
        loose = assign(
            create_weapon_accessory("Telescopic sight", price=25),
            miniature=fighter,
            paid=25,
        )
        client.force_login(gang.owner)
        url = reverse("n26-equip", args=[fighter.pk])
        body = client.get(f"{url}?list={house_list.pk}&fit={loose.pk}").content.decode()

        assert "Fit Telescopic sight to a weapon" in body
        assert re.search(r"<option[^>]*>\s*Heavy stubber\*\s*</option>", body)
        assert re.search(r"<option[^>]*>\s*Autogun\s*</option>", body)

    def test_a_stashed_accessory_is_offered_the_marked_gun(
        self, client, gang, fighter, stubber
    ):
        from n26.tests.sandbox.actions import create_weapon_accessory

        give_weapon(fighter, stubber, paid=130)
        loose = assign(
            create_weapon_accessory("Telescopic sight", price=25),
            stash=gang.stash,
            paid=25,
        )
        client.force_login(gang.owner)
        url = reverse("n26-equip-gang", args=[gang.pk])
        body = client.get(f"{url}?list=stash&reassign={loose.pk}").content.decode()

        assert "Fit Telescopic sight to a weapon" in body
        assert re.search(r"<option[^>]*>\s*Heavy stubber\* \(Vex\)\s*</option>", body)


class TestAuthoringAWeapon:
    """A hand-authored weapon can be marked: the authoring page offers the
    slots field with the model's own help text, and saves what is typed."""

    @pytest.fixture
    def author(self, client):
        user = User.objects.create_user("author", is_staff=True)
        client.force_login(user)
        return user

    def test_the_weapon_page_offers_slots(self, author, client, stubber):
        body = client.get(f"/n26/authoring/weapon/{stubber.pk}/").content.decode()

        assert 'name="edit-slots"' in body
        assert "Asterisked weapons take 2." in body

    def test_typing_two_marks_the_weapon(self, author, client, autogun):
        response = client.post(
            f"/n26/authoring/weapon/{autogun.pk}/",
            {
                "act": "edit",
                "edit-name": "Autogun",
                "edit-slots": "2",
                "edit-price": "15",
                "edit-trade_point_price": "",
            },
        )
        assert response.status_code in (302, 200), response.content.decode()[:500]

        autogun.refresh_from_db()
        assert autogun.slots == 2
        assert autogun.slot_mark == "*"
        assert autogun.name == "Autogun"
