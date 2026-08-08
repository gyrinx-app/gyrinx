"""Founding House Escher, from a real 2026 gang list.

* **one House Escher Equipment List**, named once and referred to by
  every fighter entry — so it belongs to the *gang type*, arrives
  gang-hosted at founding, and nobody assigns it by hand;
* a **two-level taxonomy** in that list (Ranged Weapons › Auto/Stub
  Weapons, Wargear › Mounts) — the ``Category`` model, unchanged;
* **house prices** differing from reference prices — entry overrides;
* lines marked **"(Wyld Runner only)"** — ``usable_by_profiles``, noted
  in the listing rather than removed from it;
* **gang special rules**, including one that gives Leaders and Champions
  a skill from their own Primary sets — carried by the gang type,
  reaching models through the broadcast;
* a **skill-access grid** of entries against sets — ``PlacesCategory``
  modifiers on each profile;
* a **mount** that comes with a weapon and offers two priced swaps —
  options on a wargear.

Rule *names* only; the rulebook's words are copyright (CLAUDE.md).
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import (
    browse,
    offered_by,
    usability_for,
    with_use_notes,
)
from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.render import build_model_card
from n26.library.models import Profile, ProfileType, Skill
from n26.tests.sandbox.actions import (
    buy,
    create_category,
    create_collection,
    create_default_set,
    create_rule,
    create_skill,
    create_statline_type,
    create_subtype,
    create_trait,
    create_wargear,
    create_weapon,
    found_gang,
    hire_with_option,
    modifier,
    offer_option,
    offers_choice,
    places,
    restrict_use,
    section_of,
    set_statline,
    targets_model,
)

pytestmark = pytest.mark.django_db


# --- The content library --------------------------------------------------


@pytest.fixture
def fighter_type(make_stat, default_pack):
    stats = [
        make_stat("M", "Movement", is_inches=True),
        make_stat("WS", "Weapon Skill", is_target=True, is_inverted=True),
        make_stat("BS", "Ballistic Skill", is_target=True, is_inverted=True),
        make_stat("S", "Strength"),
        make_stat("T", "Toughness"),
        make_stat("W", "Wounds"),
        make_stat("I", "Initiative"),
        make_stat("A", "Attacks"),
        make_stat("Sv", "Save", is_target=True, is_inverted=True),
        make_stat("Ld", "Leadership"),
        make_stat("Cl", "Cool"),
        make_stat("Wil", "Willpower"),
        make_stat("Int", "Intelligence"),
    ]
    return ProfileType.objects.create(
        name="Fighter", statline_type=create_statline_type("Fighter statline", stats)
    )


@pytest.fixture
def taxonomy(db):
    """Two levels, as the list prints them."""
    return {
        "auto_stub": create_category("Ranged Weapons", "Auto/Stub Weapons", 0),
        "primitive": create_category("Ranged Weapons", "Primitive Weapons", 1),
        "toxin_cc": create_category("Close Combat Weapons", "Toxin Weapons", 2),
        "armour": create_category("Wargear", "Armour & Field Armour", 3),
        "mounts": create_category("Wargear", "Mounts", 4),
    }


@pytest.fixture
def sets(db):
    """The six skill sets the grid names."""
    return {
        name.lower(): create_category("Skills", name, position)
        for position, name in enumerate(
            ["Agility", "Brawn", "Combat", "Cunning", "Savant", "Shooting"]
        )
    }


@pytest.fixture
def skills(sets):
    library = {}
    for set_key, names in [
        ("agility", ["Catfall", "Dodge"]),
        ("combat", ["Combat Master", "Parry"]),
        ("savant", ["Connected", "Medicate"]),
        ("brawn", ["Bull Charge"]),
    ]:
        for number, name in enumerate(names, start=1):
            library[name] = create_skill(name, category=sets[set_key], position=number)
    return library


@pytest.fixture
def subtypes(db):
    return {
        name.lower(): create_subtype(name)
        for name in ["Leader", "Champion", "Ganger", "Loner", "Mounted", "Flying"]
    }


@pytest.fixture
def weapons(taxonomy, default_pack):
    """A slice of the list, plus the mount's own guns.

    The mount's guns are priced "–" with TP "E": never bought separately.
    They stay out of the equipment list simply by not being entries in it
    — which is why a curated list is the right shape for a house list and
    sweeps are the trading post's.
    """
    arc = create_trait("Arc", "Centreline")
    twin = create_trait("Twin-linked")
    mounted_gun = {"price": 0, "is_exclusive": True}
    return {
        "autogun": create_weapon(
            "Autogun", profiles=[("Standard", 0)], category=taxonomy["auto_stub"]
        ),
        "stub_gun": create_weapon(
            "Stub gun", profiles=[("Standard", 0)], category=taxonomy["auto_stub"]
        ),
        "wyld_bow": create_weapon(
            "Wyld bow", profiles=[("Standard", 0)], category=taxonomy["primitive"]
        ),
        "venom_claw": create_weapon(
            "Venom claw", profiles=[("Strike", 0)], category=taxonomy["toxin_cc"]
        ),
        "launchers": create_weapon(
            "Cutter grenade launchers",
            profiles=[("Frag grenades", 0, [arc]), ("Krak grenades", 0, [arc])],
            **mounted_gun,
        ),
        "stubbers": create_weapon(
            "Cutter heavy stubbers",
            profiles=[("Standard", 0, [arc, twin])],
            **mounted_gun,
        ),
        "plasma": create_weapon(
            "Cutter plasma guns",
            profiles=[("Standard", 0, [arc, twin])],
            **mounted_gun,
        ),
    }


@pytest.fixture
def cutter(weapons, taxonomy, subtypes, fighter_type):
    """The mount: comes with a weapon, offers two priced swaps.

    Note what is *not* here: no ``built_ins``. "Comes with X, may replace
    X with Y" is a one-of group whose head is X — a built-in would be
    granted as well as the swap, because nothing is ever replaced.
    """
    mount = create_wargear("Escher Cutter", price=150, category=taxonomy["mounts"])
    movement = fighter_type.statline_type.stats.get(stat__short_name="M").stat
    for subtype in (subtypes["mounted"], subtypes["flying"]):
        modifier(
            f"Escher Cutter grants {subtype.name}",
            targets_model(),
            _adds(subtype),
            carried_by=mount,
        )
    modifier(
        "Escher Cutter sets Movement",
        targets_model(),
        _sets_stat(movement, 9),
        carried_by=mount,
    )
    for position, (name, weapon, price) in enumerate(
        [
            ("Cutter grenade launchers", weapons["launchers"], 0),
            ("Cutter heavy stubbers", weapons["stubbers"], 10),
            ("Cutter plasma guns", weapons["plasma"], 15),
        ]
    ):
        offer_option(
            mount,
            create_default_set(name, members=[weapon], price=price),
            position=position,
        )
    return mount


def _adds(thing):
    from n26.tests.sandbox.actions import adds

    return adds(thing)


def _sets_stat(stat, value):
    from n26.tests.sandbox.actions import changes_stat

    return changes_stat(stat, mode="set", amount=value)


@pytest.fixture
def house_list(weapons, cutter, taxonomy, default_pack):
    """One list, curated, at house prices — shared by every entry."""
    return create_collection(
        "House Escher Equipment List",
        entries=[
            (weapons["autogun"], {"price_override": 20}),
            (weapons["stub_gun"], {"price_override": 5}),
            (weapons["wyld_bow"], {"price_override": 15}),
            (weapons["venom_claw"], {"price_override": 50}),
            (
                create_wargear("Mesh armour", category=taxonomy["armour"]),
                {"price_override": 40},
            ),
            (cutter, {"price_override": 150}),
        ],
    )


@pytest.fixture
def catalogue(skills, default_pack):
    """The skills collection, with the tiers the grid's cells name."""
    collection = create_collection("Skills", contains=[Skill])
    return collection, {
        "primary": section_of(collection, "Primary", 0),
        "secondary": section_of(collection, "Secondary", 1),
        "other": section_of(collection, "Other", 9, is_default=True),
    }


#: The list's skill-access grid, as printed: entry against set.
GRID = {
    "Escher Gang Queen": {
        "agility": "primary",
        "combat": "secondary",
        "savant": "primary",
        "shooting": "secondary",
    },
    "Escher Gang Matriarch": {
        "agility": "primary",
        "combat": "primary",
        "savant": "secondary",
    },
    "Escher Wyld Runner": {"agility": "primary", "cunning": "secondary"},
}


@pytest.fixture
def profiles(fighter_type, gang_type, subtypes, sets, catalogue, default_pack):
    _, tiers = catalogue
    made = {}
    for name, price, _starting_xp, entry_subtypes, statline in [
        (
            "Escher Gang Queen",
            135,
            61,
            ["leader"],
            dict(
                movement=5,
                weapon_skill=3,
                ballistic_skill=3,
                strength=3,
                toughness=3,
                wounds=3,
                initiative=5,
                attacks=3,
                save=5,
                leadership=8,
                cool=8,
                willpower=7,
                intelligence=7,
            ),
        ),
        (
            "Escher Gang Matriarch",
            100,
            37,
            ["champion"],
            dict(
                movement=5,
                weapon_skill=3,
                ballistic_skill=3,
                strength=3,
                toughness=3,
                wounds=2,
                initiative=5,
                attacks=2,
                save=5,
                leadership=7,
                cool=7,
                willpower=6,
                intelligence=7,
            ),
        ),
        (
            "Escher Wyld Runner",
            45,
            0,
            ["ganger"],
            dict(
                movement=5,
                weapon_skill=4,
                ballistic_skill=4,
                strength=3,
                toughness=3,
                wounds=1,
                initiative=4,
                attacks=1,
                save=6,
                leadership=6,
                cool=6,
                willpower=7,
                intelligence=7,
            ),
        ),
    ]:
        profile = Profile.objects.create(
            name=name, profile_type=fighter_type, gang_type=gang_type, price=price
        )
        set_statline(profile, **statline)
        profile.built_ins = create_default_set(
            f"{name} built-ins",
            members=[subtypes[key] for key in entry_subtypes],
        )
        profile.save()
        for set_key, tier in GRID[name].items():
            modifier(
                f"{name}: {set_key} {tier}",
                targets_model(),
                places(sets[set_key], tiers[tier]),
                carried_by=profile,
            )
        made[name] = profile
    return made


@pytest.fixture
def escher(house_list, profiles, subtypes, catalogue, gang_type):
    """The gang type: its list, and its gang special rules."""
    _, tiers = catalogue
    gang_type.built_ins = create_default_set(
        "House Escher gang built-ins", members=[house_list]
    )
    gang_type.save()

    # A named rule that computes nothing — the card just says it.
    modifier(
        "Escher: Nimble",
        targets_model(),
        _adds(create_rule("Nimble")),
        carried_by=gang_type,
    )
    # The one that must reach a card, and only some models.
    modifier(
        "Escher: Leaders and Champions start with a Primary skill",
        targets_model(with_subtypes=[subtypes["leader"], subtypes["champion"]]),
        offers_choice(Skill, from_section=tiers["primary"]),
        carried_by=gang_type,
    )
    return gang_type


@pytest.fixture
def gang(escher):
    return found_gang("The Bad Girls", escher, owner=User.objects.create_user("tom"))


def _cutter_line(house_list):
    return next(x for x in browse(house_list).all_lines() if x.name == "Escher Cutter")


def computed_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return card, compute(card, index)


# --- Founding -------------------------------------------------------------


class TestFoundingTheGang:
    def test_the_house_list_arrives_without_anyone_assigning_it(
        self, gang, house_list, escher
    ):
        from n26.core.access import collections_for

        queen = hire_with_option(
            gang, Profile.objects.get(name="Escher Gang Queen"), "Yolanda"
        )

        (access,) = collections_for(queen)
        assert access.collection == house_list
        # Named by what brought it: the gang type, through its built-ins.
        assert access.source == str(escher)

    def test_the_budget_comes_from_content(self, escher):
        # Unset everywhere, founding is unlimited: buy what you own, the
        # gang's number is its rating.
        gang = found_gang("Blank Cheque", escher, owner=User.objects.create_user("p"))
        assert gang.starting_credits is None

        escher.starting_credits = 1200
        escher.save()
        richer = found_gang("Flush", escher, owner=User.objects.create_user("q"))
        assert richer.starting_credits == 1200

    def test_the_founding_is_an_assignment_that_costs_nothing(self, gang, escher):
        assert gang.founding.assignable == escher
        assert gang.founding.ledger_entry.paid == 0
        assert gang.rating == 0


# --- Gang-wide rules reaching a fighter -----------------------------------


class TestTheGangRules:
    def test_a_named_rule_reaches_every_fighter(self, gang, profiles):
        runner = hire_with_option(gang, profiles["Escher Wyld Runner"], "Sly")
        card, computed = computed_for(runner)
        drawn = build_model_card(runner, card=card, computed=computed)
        assert [r.name for r in drawn.rules] == ["Nimble"]

    def test_the_starting_skill_offer_reaches_only_leaders_and_champions(
        self, gang, profiles
    ):
        queen = hire_with_option(gang, profiles["Escher Gang Queen"], "Yolanda")
        runner = hire_with_option(gang, profiles["Escher Wyld Runner"], "Sly")

        _, queen_computed = computed_for(queen)
        _, runner_computed = computed_for(runner)

        (slot,) = queen_computed.choices
        assert slot.kind_label == "Primary skill"
        assert runner_computed.choices == []

    def test_the_offer_lists_that_fighter_s_own_primary_sets(
        self, gang, profiles, catalogue
    ):
        """One rule on the gang; a different answer per fighter, because
        the grid gives each entry different Primary sets."""
        queen = hire_with_option(gang, profiles["Escher Gang Queen"], "Yolanda")
        matriarch = hire_with_option(gang, profiles["Escher Gang Matriarch"], "Mags")

        def offered(miniature):
            _, computed = computed_for(miniature)
            (slot,) = computed.choices
            view = offered_by(slot, computed)
            return [c.name for s in view.sections for c in s.categories]

        assert offered(queen) == ["Agility", "Savant"]
        assert offered(matriarch) == ["Agility", "Combat"]

    def test_the_gang_rule_draws_no_row_of_its_own(self, gang, profiles):
        queen = hire_with_option(gang, profiles["Escher Gang Queen"], "Yolanda")
        card, computed = computed_for(queen)
        drawn = build_model_card(queen, card=card, computed=computed)

        # The gang type rides the card but is not the fighter's kit.
        assert "House Escher" not in [e.name for e in drawn.equipment]
        assert drawn.rating == 135


# --- The equipment list ---------------------------------------------------


class TestTheEquipmentList:
    def test_it_sections_by_the_printed_taxonomy(self, gang, house_list):
        view = browse(house_list)
        assert [s.name for s in view.sections] == [
            "Ranged Weapons",
            "Close Combat Weapons",
            "Wargear",
        ]
        assert [c.name for c in view.sections[0].categories] == [
            "Auto/Stub Weapons",
            "Primitive Weapons",
        ]

    def test_house_prices_beat_reference_prices(self, gang, house_list, weapons):
        view = browse(house_list)
        priced = {line.name: line.credits for line in view.all_lines()}
        assert priced["Autogun"] == 20
        assert weapons["autogun"].price == 0  # reference; the list sets the price

    def test_the_mount_s_own_guns_are_not_on_the_list(self, gang, house_list):
        names = [line.name for line in browse(house_list).all_lines()]
        assert "Cutter grenade launchers" not in names
        assert "Escher Cutter" in names

    def test_an_entry_only_line_is_noted_not_hidden(self, gang, profiles, house_list):
        """ "Wyld bow (Wyld Runner only)" — listed for everyone,
        marked for those who may not take it. We inform, never police."""
        restrict_use(
            house_list.entries.get(weapon__name="Wyld bow").assignable,
            profiles["Escher Wyld Runner"],
        )
        queen = hire_with_option(gang, profiles["Escher Gang Queen"], "Yolanda")
        runner = hire_with_option(gang, profiles["Escher Wyld Runner"], "Sly")

        def note_for(miniature):
            _, computed = computed_for(miniature)
            view = with_use_notes(browse(house_list), usability_for(computed))
            line = next(x for x in view.all_lines() if x.name == "Wyld bow")
            return line.notes

        (note,) = note_for(queen)
        assert "Escher Wyld Runner" in note.text
        assert note_for(runner) == ()


# --- Buying the mount -----------------------------------------------------


class TestBuyingTheCutter:
    def test_it_comes_with_its_launchers_at_the_list_price(
        self, gang, profiles, house_list
    ):
        queen = hire_with_option(gang, profiles["Escher Gang Queen"], "Yolanda")
        line = next(
            x for x in browse(house_list).all_lines() if x.name == "Escher Cutter"
        )
        assert line.credits == 150

        buy(queen, line)
        card, computed = computed_for(queen)
        drawn = build_model_card(queen, card=card, computed=computed)

        assert [w.name for w in drawn.weapons] == ["Cutter grenade launchers"]
        assert [e.name for e in drawn.equipment] == ["Escher Cutter"]
        assert drawn.rating == 135 + 150

    def test_a_swap_costs_its_surcharge_and_replaces_the_default(
        self, gang, profiles, house_list, cutter
    ):
        queen = hire_with_option(gang, profiles["Escher Gang Queen"], "Yolanda")
        line = next(
            x for x in browse(house_list).all_lines() if x.name == "Escher Cutter"
        )
        plasma = cutter.options.get(default_set__name="Cutter plasma guns").default_set

        buy(queen, line, option=[plasma])
        card, computed = computed_for(queen)
        drawn = build_model_card(queen, card=card, computed=computed)

        assert drawn.rating == 135 + 165
        assert [w.name for w in drawn.weapons] == ["Cutter plasma guns"]

    def test_the_mount_s_effects_land_on_the_rider(self, gang, profiles, house_list):
        queen = hire_with_option(gang, profiles["Escher Gang Queen"], "Yolanda")
        line = next(
            x for x in browse(house_list).all_lines() if x.name == "Escher Cutter"
        )
        buy(queen, line)

        card, computed = computed_for(queen)
        drawn = build_model_card(queen, card=card, computed=computed)

        assert drawn.type_line == "Fighter (Flying, Leader, Mounted)"
        movement = drawn.statline.get("M")
        assert movement.value == '9"'
        assert [p.source for p in movement.modified_by] == ["Escher Cutter"]

    def test_selling_the_mount_takes_its_weapon(self, gang, profiles, house_list):
        from n26.tests.sandbox.actions import remove

        queen = hire_with_option(gang, profiles["Escher Gang Queen"], "Yolanda")
        line = next(
            x for x in browse(house_list).all_lines() if x.name == "Escher Cutter"
        )
        mount = buy(queen, line)
        remove(mount)

        card, computed = computed_for(queen)
        drawn = build_model_card(queen, card=card, computed=computed)
        assert drawn.weapons == []
        assert drawn.statline.get("M").value == '5"'


# --- The whole gang -------------------------------------------------------


class TestTheWholeRoster:
    def test_a_gang_renders_and_reconciles(self, gang, profiles, house_list, cutter):
        from n26.core.reconcile import assert_reconciled
        from n26.core.render_text import gang_to_text

        queen = hire_with_option(gang, profiles["Escher Gang Queen"], "Yolanda")
        hire_with_option(gang, profiles["Escher Gang Matriarch"], "Mags")
        hire_with_option(gang, profiles["Escher Wyld Runner"], "Sly")

        line = next(
            x for x in browse(house_list).all_lines() if x.name == "Escher Cutter"
        )
        stubbers = cutter.options.get(
            default_set__name="Cutter heavy stubbers"
        ).default_set
        buy(queen, line, option=[stubbers])

        text = gang_to_text(gang)
        print("\n" + text)
        assert "Yolanda — 295cr" in text  # 135 + 150 + 10
        assert "Fighter (Flying, Leader, Mounted)" in text
        assert "Rules: Nimble" in text
        assert_reconciled(gang)

    def test_a_bigger_gang_costs_no_more_queries(self, gang, profiles):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.render import render_gang

        hire_with_option(gang, profiles["Escher Gang Queen"], "Yolanda")

        def measure():
            with CaptureQueriesContext(connection) as captured:
                assert render_gang(gang).models
            return len(captured.captured_queries)

        few = measure()
        for index in range(4):
            hire_with_option(gang, profiles["Escher Wyld Runner"], f"Sly {index}")
        assert measure() == few
