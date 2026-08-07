"""A gang, its lists, and everything it buys — collections end to end.

Three surfaces, one shape: the gang list you hire from, the equipment
list you always shop, and the Trading Post you visit. Each is a
collection; each browses to the same structure; the same `op.buy` spends
against all of them.

Prices are the rulebook's where the rulebook has them (autogun 20/TP 0,
boltgun 55/TP 2, heavy stubber 70/TP 2). Gang-list entries and house
prices are invented — those live in supplements, not the core book.

Run with ``-s`` to read the rendered output; the prints are the point of
this file as much as the assertions.
"""

import pytest
from django.contrib.auth.models import User

from n26.library.models import Profile, StatlineType, StatlineTypeStat
from n26.core.access import collections_for
from n26.core.browse import TRADING_POST, browse, narrow
from n26.core.reconcile import assert_reconciled
from n26.core.render_text import gang_to_text, ledger_to_text
from n26.tests.sandbox.actions import (
    add_legacy_profile,
    buy,
    create_category,
    create_collection,
    create_default_set,
    create_stat,
    create_wargear,
    create_weapon,
    found_gang,
    hire_with_option,
    set_statline,
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


# --- Showing things ------------------------------------------------------


def show(view, indent=""):
    """A collection, as a shopfront."""
    lines = [f"{indent}┌─ {view.name}"]
    for section in view.sections:
        lines.append(f"{indent}│ {section.name or '(uncategorised)'}")
        for category in section.categories:
            if category.name:
                lines.append(f"{indent}│   {category.name}")
            for line in category.lines:
                trade = "E" if line.is_exclusive else f"TP {line.trade_points}"
                priced = f"{line.credits}cr / {trade}"
                lines.append(f"{indent}│     {line.name:<26} {priced:>12}")
    text = "\n".join(lines)
    print("\n" + text)
    return text


def find(view, name):
    return next(line for line in view.all_lines() if line.name == name)


# --- The content library -------------------------------------------------


@pytest.fixture
def weapon_shape(db):
    """SR / LR / Str / AP / L — the shape every weapon profile prints in."""
    shape = StatlineType.objects.create(name="Weapon")
    for position, (short, full, flags) in enumerate(
        [
            ("SR", "Short Range", {"is_inches": True}),
            ("LR", "Long Range", {"is_inches": True}),
            ("Str", "Weapon Strength", {}),
            ("AP", "Armour Piercing", {"is_modifier": True}),
            ("L", "Lethality", {}),
        ]
    ):
        StatlineTypeStat.objects.create(
            statline_type=shape,
            stat=create_stat(short, full, **flags),
            position=position,
            is_first_of_group=(position == 0),
        )
    return shape


@pytest.fixture
def taxonomy(db):
    """Where everything sorts — fixed per item, shared by every list."""
    return {
        "auto": create_category("Ranged Weapons", "Auto/Stub Weapons", position=0),
        "bolt": create_category("Ranged Weapons", "Bolt Weapons", position=1),
        "las": create_category("Ranged Weapons", "Las Weapons", position=2),
        "melee": create_category("Close Combat Weapons", "Toxin Weapons", position=10),
        "armour": create_category("Armour & Equipment", "Armour", position=20),
        "kit": create_category("Armour & Equipment", "Personal Equipment", position=21),
        "fighters": create_category("Gang List", "Gang Fighters", position=30),
        "hangers": create_category("Gang List", "Hangers-on", position=31),
    }


def arm(name, shape, category, cost, trade_point_price=0, stats=(), **kwargs):
    """A weapon with one free profile, priced and given its statline."""
    weapon = create_weapon(
        name,
        profiles=[(name, 0)],
        price=cost,
        trade_point_price=trade_point_price,
        category=category,
        **kwargs,
    )
    weapon.statline_type = shape
    weapon.save(update_fields=["statline_type"])
    if stats:
        short_range, long_range, strength, armour_piercing, lethality = stats
        set_statline(
            weapon.profiles.get(),
            short_range=short_range,
            long_range=long_range,
            weapon_strength=strength,
            armour_piercing=armour_piercing,
            lethality=lethality,
        )
    return weapon


@pytest.fixture
def catalogue(weapon_shape, taxonomy):
    """Ten priced things: five the house carries, five only the Post has."""
    tax = taxonomy
    return {
        # On the Escher equipment list.
        "autogun": arm(
            "Autogun", weapon_shape, tax["auto"], 20, 0, ("8", "24", "3", "-", "1")
        ),
        "lasgun": arm(
            "Lasgun", weapon_shape, tax["las"], 15, 0, ("12", "24", "3", "-", "1")
        ),
        "stiletto": arm(
            "Stiletto knife",
            weapon_shape,
            tax["melee"],
            20,
            1,
            ("E", "-", "S", "-1", "2"),
        ),
        "mesh": create_wargear(
            "Mesh armour", price=15, trade_point_price=1, category=tax["armour"]
        ),
        "chem": create_wargear(
            "Escher chem-synth", price=30, is_exclusive=True, category=tax["kit"]
        ),
        # Trading Post only — never on the house list.
        "boltgun": arm(
            "Boltgun", weapon_shape, tax["bolt"], 55, 2, ("12", "24", "4", "-1", "2")
        ),
        "stubber": arm(
            "Heavy stubber",
            weapon_shape,
            tax["auto"],
            70,
            2,
            ("20", "40", "4", "-1", "1"),
            slots=2,
        ),
        "plasma": arm(
            "Plasma gun",
            weapon_shape,
            tax["bolt"],
            100,
            3,
            ("12", "24", "5", "-2", "2"),
        ),
        "goggles": create_wargear(
            "Photo-goggles", price=35, trade_point_price=1, category=tax["kit"]
        ),
        "respirator": create_wargear(
            "Respirator", price=15, trade_point_price=0, category=tax["kit"]
        ),
    }


@pytest.fixture
def equipment_list(catalogue):
    """The house list: five things, most at a price the house sets.

    House prices are overrides — a fix to the reference price does not
    reach through them, which is the agreed consequence of the design.
    """
    return create_collection(
        "House Escher Equipment List",
        entries=[
            (catalogue["autogun"], {"price_override": 15}),
            (catalogue["lasgun"], {"price_override": 10}),
            catalogue["stiletto"],  # no override: sells at reference
            (catalogue["mesh"], {"price_override": 10}),
            (catalogue["chem"], {"price_override": 25}),
        ],
    )


@pytest.fixture
def gang_list(person_type, gang_type, taxonomy, equipment_list):
    """Three fighters and two hangers-on, in two categories.

    Every profile carries the house list in its built-ins, so hiring one
    is what gives that fighter somewhere to shop.
    """
    made = {}
    entries = [
        ("Escher Matriarch", 120, taxonomy["fighters"]),
        ("Escher Death-Maiden", 90, taxonomy["fighters"]),
        ("Escher Gang Sister", 55, taxonomy["fighters"]),
        ("Rogue Doc", 80, taxonomy["hangers"]),
        ("Ammo-Jack", 70, taxonomy["hangers"]),
    ]
    for name, rating, category in entries:
        profile = Profile.objects.create(
            name=name,
            profile_type=person_type,
            gang_type=gang_type,
            price=rating,
            category=category,
        )
        set_statline(profile, movement=5, weapon_skill=4, toughness=3)
        profile.built_ins = create_default_set(f"{name} kit", members=[equipment_list])
        profile.save()
        made[name] = profile

    collection = create_collection("Escher Gang List", entries=list(made.values()))
    return collection, made


# --- The story -----------------------------------------------------------


class TestTheThreeSurfaces:
    def test_the_gang_list_groups_hangers_on_apart(self, gang_list):
        collection, _ = gang_list
        text = show(browse(collection))

        assert "Gang Fighters" in text
        assert "Hangers-on" in text
        # Priced by composition, not a stored field: a profile's price is
        # its rating plus its sets.
        assert find(browse(collection), "Escher Matriarch").credits == 120
        assert find(browse(collection), "Rogue Doc").credits == 80

    def test_the_equipment_list_prices_the_house_way(self, equipment_list):
        view = browse(equipment_list)
        text = show(view)

        assert find(view, "Autogun").credits == 15  # reference 20
        assert find(view, "Lasgun").credits == 10  # reference 15
        assert find(view, "Stiletto knife").credits == 20  # no override
        assert find(view, "Escher chem-synth").is_exclusive is True
        assert "25cr / E" in text  # priced by the house, still list-only

    def test_the_trading_post_carries_what_the_house_does_not(self, catalogue):
        view = browse_the_post()
        show(view)

        names = {line.name for line in view.all_lines()}
        assert {"Boltgun", "Heavy stubber", "Plasma gun"} <= names
        # Exclusive things are never at the Post, list or no list.
        assert "Escher chem-synth" not in names
        # And it sells at reference: the house discount is the house's.
        assert find(view, "Autogun").credits == 20

    def test_one_item_sorts_the_same_on_both(self, equipment_list, catalogue):
        """The taxonomy belongs to the item, so the two surfaces agree."""

        def home_of(view):
            for section in view.sections:
                for category in section.categories:
                    if any(line.name == "Autogun" for line in category.lines):
                        return section.name, category.name
            return None

        assert home_of(browse(equipment_list)) == home_of(browse_the_post())


class TestFoundingAndEquipping:
    @pytest.fixture
    def gang(self, gang_type):
        player = User.objects.create_user("tom")
        return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)

    @pytest.fixture
    def crew(self, gang, gang_list):
        _, profiles = gang_list
        return {
            "leader": hire_with_option(gang, profiles["Escher Matriarch"], "Yolanda"),
            "champion": hire_with_option(gang, profiles["Escher Death-Maiden"], "Kora"),
            "ganger": hire_with_option(gang, profiles["Escher Gang Sister"], "Sindi"),
        }

    def test_hiring_gives_everyone_somewhere_to_shop(self, gang, crew, equipment_list):
        print("\n\n== After hiring ==")
        print(gang_to_text(gang))

        for fighter in crew.values():
            (access,) = collections_for(fighter)
            assert access.collection == equipment_list
            assert access.computed is False

        gang.refresh_from_db()
        assert gang.rating == 120 + 90 + 55
        assert gang.credits == 1000 - 265

    def test_equipping_from_the_house_list(self, gang, crew, equipment_list):
        view = browse(equipment_list)
        buy(crew["leader"], entry=find(view, "Autogun").entry)
        buy(crew["leader"], entry=find(view, "Mesh armour").entry)
        buy(crew["champion"], entry=find(view, "Stiletto knife").entry)
        buy(crew["ganger"], entry=find(view, "Lasgun").entry)

        print("\n\n== After equipping from the equipment list ==")
        print(gang_to_text(gang))

        gang.refresh_from_db()
        # House prices, not reference: 15 + 10 + 20 + 10.
        assert gang.rating == 265 + 55
        assert_reconciled(gang)

    def test_then_equipping_from_the_trading_post(self, gang, crew, equipment_list):
        house = browse(equipment_list)
        buy(crew["leader"], entry=find(house, "Autogun").entry)

        post = browse_the_post()
        # A browsed line is the whole purchase: the thing, the price, the
        # Trade Points this surface charges. Nothing is disassembled.
        buy(crew["champion"], find(post, "Boltgun"))
        buy(crew["leader"], find(post, "Photo-goggles"))

        print("\n\n== After a trip to the Trading Post ==")
        print(gang_to_text(gang))

        gang.refresh_from_db()
        assert gang.rating == 265 + 15 + 55 + 35
        assert_reconciled(gang)

    def test_the_ledger_tells_the_whole_story(self, gang, crew, equipment_list):
        house = browse(equipment_list)
        autogun = find(house, "Autogun")
        buy(crew["leader"], entry=autogun.entry)

        post = browse_the_post()
        buy(crew["champion"], find(post, "Boltgun"))

        # And the get-out: something weird, off any list, at a made-up price.
        buy(
            crew["ganger"],
            thing=find(post, "Plasma gun").thing,
            paid=1,
            note="found it in a drain",
        )

        print("\n\n== The ledger ==")
        print(ledger_to_text(gang))

        entries = {
            str(entry.assignable): entry
            for entry in [a.ledger_entry for a in gang.assignments.all()]
        }
        # Bought through a list: the price and the source are both kept.
        assert entries["Autogun"].paid == 15
        assert entries["Autogun"].bought_from == autogun.entry
        # Trade Points are remembered, which is what makes refunds possible.
        assert entries["Boltgun"].trade_points == 2
        # Bought off-list: no source, and nothing objected to the price.
        assert entries["Plasma gun"].paid == 1
        assert entries["Plasma gun"].bought_from is None
        assert_reconciled(gang)


class TestVenatorsAndLegacy:
    """A Venator uses from their own list *and* their Legacy's."""

    @pytest.fixture
    def venator_list(self, catalogue):
        return create_collection(
            "Venator Hunt List",
            entries=[
                (catalogue["boltgun"], {"price_override": 50}),
                catalogue["respirator"],
            ],
        )

    @pytest.fixture
    def hunt_champion(self, person_type, gang_type, venator_list, taxonomy):
        profile = Profile.objects.create(
            name="Venator Hunt Champion",
            profile_type=person_type,
            gang_type=gang_type,
            price=100,
            category=taxonomy["fighters"],
        )
        set_statline(profile, movement=5, weapon_skill=3, toughness=3)
        profile.built_ins = create_default_set(
            "Hunt Champion kit", members=[venator_list]
        )
        profile.save()
        return profile

    @pytest.fixture
    def venators(self, gang_type, hunt_champion):
        player = User.objects.create_user("hunter")
        gang = found_gang("The Long Hunt", gang_type, owner=player, budget=1000)
        return gang, hire_with_option(gang, hunt_champion, "Kora")

    def test_before_a_legacy_they_have_only_their_own_list(
        self, venators, venator_list
    ):
        _, champion = venators
        (access,) = collections_for(champion)
        assert access.collection == venator_list

    def test_a_legacy_brings_the_other_gang_s_list(
        self, venators, gang_list, venator_list, equipment_list
    ):
        gang, champion = venators
        _, profiles = gang_list

        add_legacy_profile(champion, profiles["Escher Matriarch"], paid=0)

        access = {a.name: a for a in collections_for(champion)}
        assert set(access) == {"Venator Hunt List", "House Escher Equipment List"}
        assert access["House Escher Equipment List"].source == "Escher Matriarch"

        print("\n\n== A Venator's shopping ==")
        for name, entry in sorted(access.items()):
            print(f"  {name}  (from {entry.source})")
        show(browse(venator_list), indent="  ")
        show(browse(equipment_list), indent="  ")

    def test_a_legacy_is_an_association_not_a_second_hire(self, venators, gang_list):
        """It brings lists, not a second helping of free kit."""
        from n26.core.render import build_model_card

        gang, champion = venators
        _, profiles = gang_list
        add_legacy_profile(champion, profiles["Escher Matriarch"], paid=0)

        card = build_model_card(champion)
        assert card.weapons == []
        assert card.equipment == []
        assert len(card.collections) == 2

    def test_they_can_buy_from_the_legacy_list_at_its_prices(
        self, venators, gang_list, equipment_list
    ):
        gang, champion = venators
        _, profiles = gang_list
        add_legacy_profile(champion, profiles["Escher Matriarch"], paid=0)

        autogun = find(browse(equipment_list), "Autogun")
        buy(champion, entry=autogun.entry)

        print("\n\n== A Venator equipped from their Legacy's list ==")
        print(gang_to_text(gang))

        assert autogun.credits == 15  # the Escher house price, not 20
        gang.refresh_from_db()
        assert gang.rating == 100 + 15
        assert_reconciled(gang)


class TestCustomViews:
    """Narrowing a list — a search box and a whole shopfront are one screen."""

    def test_by_price(self, equipment_list):
        view = narrow(browse(equipment_list), credits=(0, 15), name="Under 15cr")
        text = show(view)

        assert {line.name for line in view.all_lines()} == {
            "Autogun",
            "Lasgun",
            "Mesh armour",
        }
        assert "Under 15cr" in text

    def test_by_trade_points(self, catalogue):
        """Exclusive items drop out: "E" is not a number in any range."""
        view = narrow(browse_the_post(), trade_points=(0, 1), name="Easy to find")
        show(view)

        assert {line.name for line in view.all_lines()} == {
            "Autogun",
            "Lasgun",
            "Stiletto knife",
            "Mesh armour",
            "Photo-goggles",
            "Respirator",
        }

    def test_by_category(self, equipment_list, taxonomy):
        view = narrow(
            browse(equipment_list),
            categories=[taxonomy["auto"], taxonomy["las"]],
            name="Guns only",
        )
        show(view)
        assert {line.name for line in view.all_lines()} == {"Autogun", "Lasgun"}

    def test_by_all_three_at_once(self, catalogue, taxonomy):
        view = narrow(
            browse_the_post(),
            credits=(20, 80),
            trade_points=(1, 2),
            categories=[taxonomy["auto"], taxonomy["bolt"], taxonomy["kit"]],
            name="Affordable, findable, and a gun or a gadget",
        )
        show(view)
        assert {line.name for line in view.all_lines()} == {
            "Boltgun",
            "Heavy stubber",
            "Photo-goggles",
        }

    def test_a_narrowed_view_is_still_a_view(self, equipment_list):
        """Same type in, same type out — so the same renderer draws it, and
        narrowing composes."""
        whole = browse(equipment_list)
        once = narrow(whole, credits=(0, 20))
        twice = narrow(once, credits=(0, 10))

        assert type(twice) is type(whole)
        assert {line.name for line in twice.all_lines()} == {"Lasgun", "Mesh armour"}

    def test_narrowing_keeps_the_sections(self, equipment_list, taxonomy):
        """Sections and categories survive, so a filtered list still reads
        like the list it came from."""
        view = narrow(browse(equipment_list), credits=(0, 15))
        assert [section.name for section in view.sections] == [
            "Ranged Weapons",
            "Armour & Equipment",
        ]

    def test_an_empty_result_is_an_empty_view(self, equipment_list):
        view = narrow(browse(equipment_list), credits=(500, None))
        assert view.sections == []
        assert list(view.all_lines()) == []
