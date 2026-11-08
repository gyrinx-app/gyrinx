"""Gang lists, house equipment lists and Trading Posts share collection browsing and
purchase operations. Fixtures use illustrative gang profiles and house-price overrides;
run with -s to inspect the printed catalogue and ledger output.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.access import collections_for
from n26.core.browse import TRADING_POST, browse, narrow
from n26.core.reconcile import assert_reconciled
from n26.core.render_text import gang_to_text, ledger_to_text
from n26.library.models import Profile, StatlineType, StatlineTypeStat
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
    """Reuse or create the default Trading Post and browse it on TRADING_POST terms."""
    from n26.library.models import Collection
    from n26.tests.sandbox.actions import create_trading_post

    post = Collection.objects.filter(name="Trading Post").first()
    return browse(post or create_trading_post(), TRADING_POST)


def show(view, indent=""):
    """Print a collection catalogue and return the text for assertions."""
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


@pytest.fixture
def weapon_shape(db):
    """Weapon columns used by this fixture."""
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
    """Item-owned categories shared across collections."""
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
    """Create a priced weapon with one default profile and optional stats."""
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
    """Five items on the house list and five available only through the Trading Post."""
    tax = taxonomy
    return {
        # House-list items.
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
        # Trading Post items absent from the house list.
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
    """House-price overrides remain independent of later reference-price changes."""
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
    """Five profiles across fighter and hanger-on categories, each with built-in house-list
    access.
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


class TestTheThreeSurfaces:
    def test_the_gang_list_groups_hangers_on_apart(self, gang_list):
        collection, _ = gang_list
        text = show(browse(collection))

        assert "Gang Fighters" in text
        assert "Hangers-on" in text

        assert find(browse(collection), "Escher Matriarch").credits == 120
        assert find(browse(collection), "Rogue Doc").credits == 80

    def test_the_equipment_list_prices_the_house_way(self, equipment_list):
        view = browse(equipment_list)
        text = show(view)

        assert find(view, "Autogun").credits == 15  # reference 20
        assert find(view, "Lasgun").credits == 10  # reference 15
        assert find(view, "Stiletto knife").credits == 20  # no override
        assert find(view, "Escher chem-synth").is_exclusive is True
        assert "25cr / E" in text  # House-price override with exclusive availability.

    def test_the_trading_post_carries_what_the_house_does_not(self, catalogue):
        view = browse_the_post()
        show(view)

        names = {line.name for line in view.all_lines()}
        assert {"Boltgun", "Heavy stubber", "Plasma gun"} <= names
        # Exclusive items are excluded from Trading Post access.
        assert "Escher chem-synth" not in names
        # The Trading Post uses the reference price.
        assert find(view, "Autogun").credits == 20

    def test_one_item_sorts_the_same_on_both(self, equipment_list, catalogue):
        """The item’s category determines its placement in both collections."""

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

    def test_hiring_gives_everyone_somewhere_to_buy_from(
        self, gang, crew, equipment_list
    ):
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
        # The selected house prices total 55.
        assert gang.rating == 265 + 55
        assert_reconciled(gang)

    def test_then_equipping_from_the_trading_post(self, gang, crew, equipment_list):
        house = browse(equipment_list)
        buy(crew["leader"], entry=find(house, "Autogun").entry)

        post = browse_the_post()
        # Pass the browsed line to preserve this access route’s credit and Trade Point
        # prices.
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

        # Direct purchases can record a custom price without a collection source.
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
        # Retain the collection entry and price paid.
        assert entries["Autogun"].paid == 15
        assert entries["Autogun"].bought_from == autogun.entry
        # Recorded Trade Points support refunds.
        assert entries["Boltgun"].trade_points == 2
        # Direct purchase without a collection source.
        assert entries["Plasma gun"].paid == 1
        assert entries["Plasma gun"].bought_from is None
        assert_reconciled(gang)


class TestVenatorsAndLegacy:
    """Legacy profiles add collection access alongside the Venator’s own list."""

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

        print("\n\n== A Venator's buying ==")
        for name, entry in sorted(access.items()):
            print(f"  {name}  (from {entry.source})")
        show(browse(venator_list), indent="  ")
        show(browse(equipment_list), indent="  ")

    def test_a_legacy_is_an_association_not_a_second_hire(self, venators, gang_list):
        """A legacy adds collection access without materialising another profile’s
        equipment.
        """
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
    """Collection filters preserve the browsable view structure."""

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
        """Exclusive items are excluded from numeric Trade Point ranges."""
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
        """Filtering returns the same view type and can be applied repeatedly."""
        whole = browse(equipment_list)
        once = narrow(whole, credits=(0, 20))
        twice = narrow(once, credits=(0, 10))

        assert type(twice) is type(whole)
        assert {line.name for line in twice.all_lines()} == {"Lasgun", "Mesh armour"}

    def test_narrowing_keeps_the_sections(self, equipment_list, taxonomy):
        """Filtered results retain their source sections and categories."""
        view = narrow(browse(equipment_list), credits=(0, 15))
        assert [section.name for section in view.sections] == [
            "Armour & Equipment",
            "Ranged Weapons",
        ]

    def test_an_empty_result_is_an_empty_view(self, equipment_list):
        view = narrow(browse(equipment_list), credits=(500, None))
        assert view.sections == []
        assert list(view.all_lines()) == []
