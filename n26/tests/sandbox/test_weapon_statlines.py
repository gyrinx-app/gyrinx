"""Weapon statlines, built from the same machinery as fighter statlines.

The rulebook prints a weapon profile as

    | Name    | SR  | LR  | Str | AP | L | Traits         | Creds | TP |
    | Boltgun | 12" | 24" | 4   | -1 | 2 | Rapid Fire (1) | 55    | 2  |

and prints multi-profile weapons exactly the way we model them — the weapon
row carries name and cost, each ammo row carries the stats:

    | Combat shotgun |    |     |   |   |   |                | 35 | 1 |
    | - salvo ammo   | 4" | 12" | 4 | - | 1 | Knockback (6+) | +0 |   |

Traits, Creds and TP are not stats: cost already lives on the weapon
profile, and traits are their own concept, still to be designed.
"""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from n26.core.render import build_model_card
from n26.core.render_text import render_model_card
from n26.library.authoring import add_weapon_profile
from n26.library.models import Statline, StatlineType, StatlineTypeStat, Weapon
from n26.tests.sandbox.actions import (
    buy_weapon_profile,
    create_stat,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    set_statline,
)

pytestmark = pytest.mark.django_db

#: SR, LR, Str, AP, L — the printed weapon profile, minus traits and pricing.
WEAPON_STATS = [
    ("SR", "Short Range", {"is_inches": True}),
    ("LR", "Long Range", {"is_inches": True}),
    ("Str", "Strength", {}),
    ("AP", "Armour Piercing", {}),
    ("L", "Lethality", {}),
]


@pytest.fixture
def weapon_statline_type(db):
    statline_type = StatlineType.objects.create(name="Weapon")
    for position, (short, full, flags) in enumerate(WEAPON_STATS):
        StatlineTypeStat.objects.create(
            statline_type=statline_type,
            stat=create_stat(short, full, **flags),
            position=position,
            is_first_of_group=(position == 0),
        )
    return statline_type


@pytest.fixture
def boltgun(weapon_statline_type):
    """The rulebook's worked example."""
    weapon = create_weapon("Boltgun", profiles=[("Bolt", 0)])
    weapon.statline_type = weapon_statline_type
    weapon.save()
    set_statline(
        weapon.profiles.get(),
        short_range=12,
        long_range=24,
        strength=4,
        armour_piercing=-1,
        lethality=2,
    )
    return weapon


@pytest.fixture
def combat_shotgun(weapon_statline_type):
    """Two ammo types, as the Shotguns table prints them."""
    weapon = create_weapon(
        "Combat shotgun", profiles=[("Salvo ammo", 0), ("Shredder ammo", 0)]
    )
    weapon.statline_type = weapon_statline_type
    weapon.save()
    salvo, shredder = weapon.profiles.order_by("position")
    set_statline(
        salvo,
        short_range=4,
        long_range=12,
        strength=4,
        armour_piercing="-",
        lethality=1,
    )
    set_statline(
        shredder,
        short_range="T",
        long_range="-",
        strength=3,
        armour_piercing="-",
        lethality=1,
    )
    return weapon


class TestTheShape:
    def test_a_weapon_fixes_the_shape_its_profiles_use(
        self, boltgun, weapon_statline_type
    ):
        profile = boltgun.profiles.get()
        assert profile.statline_type == weapon_statline_type
        assert profile.statline.statline_type == weapon_statline_type

    def test_the_shape_is_derived_not_stored(self, boltgun):
        """Same rule as fighters: nothing to drift out of step."""
        assert not hasattr(Statline, "statline_type_id")

    def test_a_statline_belongs_to_exactly_one_owner(self, boltgun, make_profile):
        with pytest.raises(IntegrityError), transaction.atomic():
            Statline.objects.create()

    def test_it_cannot_belong_to_both(self, boltgun, make_profile):
        with pytest.raises(IntegrityError), transaction.atomic():
            Statline.objects.create(
                profile=make_profile("Nobody"),
                weapon_profile=boltgun.profiles.get(),
            )

    def test_clean_says_so_readably(self):
        with pytest.raises(ValidationError, match="exactly one"):
            Statline().clean()

    def test_a_weapon_may_have_no_shape_yet(self, db):
        assert Weapon.objects.create(name="Unstatted").statline_type is None


class TestFormatting:
    def test_the_boltgun_matches_the_rulebook(self, boltgun):
        assert boltgun.profiles.get().statline.as_dict() == {
            "short_range": '12"',
            "long_range": '24"',
            "strength": "4",
            "armour_piercing": "-1",
            "lethality": "2",
        }

    def test_ranges_may_be_letters(self, combat_shotgun):
        """E for engaged, T for template, - for unusable — all pass through."""
        shredder = combat_shotgun.profiles.get(name="Shredder ammo")
        stats = shredder.statline.as_dict()
        assert stats["short_range"] == "T"
        assert stats["long_range"] == "-"

    def test_strength_may_be_the_wielder_s(self, weapon_statline_type):
        """Close combat weapons print S or S+3 rather than a number."""
        chainaxe = create_weapon("Chainaxe", profiles=[("Blade", 0)])
        chainaxe.statline_type = weapon_statline_type
        chainaxe.save()
        set_statline(
            chainaxe.profiles.get(),
            short_range="E",
            long_range="-",
            strength="S",
            armour_piercing=-1,
            lethality=1,
        )
        assert chainaxe.profiles.get().statline.as_dict() == {
            "short_range": "E",
            "long_range": "-",
            "strength": "S",
            "armour_piercing": "-1",
            "lethality": "1",
        }


class TestOnTheCard:
    @pytest.fixture
    def armed(self, gang_type, make_profile, combat_shotgun):
        player = User.objects.create_user("player")
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        mini = hire(gang, make_profile("Escher Ganger"), "Yolanda", paid=55)
        give_weapon(mini, combat_shotgun, paid=35)
        return mini

    def test_each_ammo_carries_its_own_statline(self, armed):
        weapon = build_model_card(armed).weapons[0]
        by_name = {p.name: p for p in weapon.profiles}

        salvo = by_name["Salvo ammo"]
        assert [(c.short_name, c.value) for c in salvo.statline.cells] == [
            ("SR", '4"'),
            ("LR", '12"'),
            ("Str", "4"),
            ("AP", "-"),
            ("L", "1"),
        ]
        shredder = by_name["Shredder ammo"]
        assert shredder.statline.get("SR").value == "T"

    def test_the_text_renderer_shows_them(self, armed):
        text = "\n".join(render_model_card(build_model_card(armed)))
        print("\n" + text)

        assert 'SR 4"  LR 12"  Str 4  AP -  L 1' in text
        assert "SR T  LR -  Str 3  AP -  L 1" in text

    def test_more_weapons_do_not_mean_more_queries(
        self, armed, weapon_statline_type, combat_shotgun
    ):
        """Weapon statlines ride along on the same prefetch as fighter ones."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.core.card import build_card

        def measure():
            with CaptureQueriesContext(connection) as captured:
                card = build_card(armed, with_statlines=True)
                for weapon in card.roots:
                    for child in weapon.children:
                        assert child.assignable.statline.as_dict()
            return len(captured.captured_queries)

        few = measure()

        for index in range(5):
            extra = create_weapon(f"Spare {index}", profiles=[("Shot", 0)])
            extra.statline_type = weapon_statline_type
            extra.save()
            set_statline(
                extra.profiles.get(),
                short_range=8,
                long_range=16,
                strength=3,
                armour_piercing="-",
                lethality=1,
            )
            give_weapon(armed, extra, paid=10)

        many = measure()
        assert few == many, f"{few} queries with one weapon, {many} with six"


class TestAStatlineShortOfStats:
    """A card draws a weapon to the columns its statline type calls for,
    whatever the statline happens to hold.

    Content can arrive missing a stat — the completeness check lives in
    ``clean()``, which importers and the authoring verbs never call. Drawn
    from the stored values alone, such a line is short a cell, and every
    number after the gap slides one column left: a player reading a Phase
    sword found its Lethality under Armour Piercing and its last column
    blank.
    """

    @pytest.fixture
    def player(self, db):
        return User.objects.create_user("shorthanded")

    @pytest.fixture
    def armed(self, gang_type, make_profile, player, weapon_statline_type):
        gang = found_gang("The Shorthanded", gang_type, owner=player, budget=1000)
        return hire(gang, make_profile("Ganger"), "Yolanda", paid=55)

    def test_a_gap_in_the_middle_reads_as_a_dash_in_its_own_column(
        self, armed, weapon_statline_type
    ):
        sword = create_weapon("Phase sword", profiles=[("", 0)])
        sword.statline_type = weapon_statline_type
        sword.save()
        # No Long Range: a melee weapon's authoring simply leaves it out.
        set_statline(
            sword.profiles.get(),
            short_range="E",
            strength="S+1",
            armour_piercing=-4,
            lethality=2,
        )
        give_weapon(armed, sword, paid=25)

        weapon = build_model_card(armed).weapons[0]
        assert [(c.short_name, c.value) for c in weapon.own_stats] == [
            ("SR", "E"),
            ("LR", "-"),
            ("Str", "S+1"),
            ("AP", "-4"),
            ("L", "2"),
        ]

    def test_a_line_with_nothing_stored_still_draws_its_columns(
        self, armed, weapon_statline_type
    ):
        projectors = create_weapon("Medusian projectors", profiles=[("", 0)])
        projectors.statline_type = weapon_statline_type
        projectors.save()
        set_statline(projectors.profiles.get(), short_range=4, long_range=12)
        give_weapon(armed, projectors, paid=30)

        weapon = build_model_card(armed).weapons[0]
        assert [c.value for c in weapon.own_stats] == ['4"', '12"', "-", "-", "-"]

    def test_the_columns_come_from_a_line_that_has_some(
        self, armed, weapon_statline_type
    ):
        """A combi-weapon's own line carries the name and no numbers.

        Sorted first on a card, it used to decide the header for every
        weapon below it — so the table lost its headings entirely while
        each row went on printing five stats.
        """
        spear = create_weapon(
            "Combi-spear", profiles=[("", 0), ("melee", 0), ("ranged", 0)]
        )
        spear.statline_type = weapon_statline_type
        spear.save()
        for profile in spear.profiles.exclude(name=""):
            set_statline(profile, short_range=4, long_range=8, strength=4)
        give_weapon(armed, spear, paid=40)

        card = build_model_card(armed)
        assert card.weapons[0].name == "Combi-spear"
        assert not card.weapons[0].own_stats
        assert [c.short_name for c in card.weapon_columns] == [
            "SR",
            "LR",
            "Str",
            "AP",
            "L",
        ]

    def test_a_card_with_no_weapon_stats_anywhere_asks_for_no_columns(self, armed):
        bare = create_weapon("Sharpened stick", profiles=[("", 0)])
        give_weapon(armed, bare, paid=5)

        assert build_model_card(armed).weapon_columns == []


class TestTheFourPrintedShapes:
    """One rule decides how a weapon's lines are drawn: an unnamed
    profile *is* the weapon, so its stats ride the weapon's own row,
    and every named one gets a row beneath. Nothing about what was paid
    for enters into it — these are the four shapes that fall out.
    """

    @pytest.fixture
    def armed_gang(self, gang_type, make_profile, weapon_statline_type):
        from django.contrib.auth.models import User

        gang = found_gang(
            "The Shapes",
            gang_type,
            owner=User.objects.create_user("shapes"),
            budget=1000,
        )
        return gang, hire(gang, make_profile("Ganger"), "Yolanda", paid=50)

    def lines_for(self, fighter):
        text = "\n".join(render_model_card(build_model_card(fighter)))
        print("\n" + text)
        return [line.strip() for line in text.splitlines()]

    def test_one_unnamed_line_reads_as_the_weapon(
        self, armed_gang, weapon_statline_type
    ):
        gang, fighter = armed_gang
        autogun = create_weapon(
            "Autogun", profiles=[("", 0)], statline_type=weapon_statline_type
        )
        set_statline(autogun.profiles.get(), short_range=8, long_range=24)
        give_weapon(fighter, autogun, paid=20)

        lines = self.lines_for(fighter)
        assert any(line.startswith("Autogun") and 'SR 8"' in line for line in lines)
        assert not any(line.startswith("- ") for line in lines)

    def test_several_named_lines_hang_under_a_bare_heading(
        self, armed_gang, weapon_statline_type
    ):
        gang, fighter = armed_gang
        shotgun = create_weapon(
            "Combat shotgun",
            profiles=[("Salvo ammo", 0), ("Shredder ammo", 0)],
            statline_type=weapon_statline_type,
        )
        for profile, reach in zip(shotgun.profiles.all(), (8, 4), strict=True):
            set_statline(profile, short_range=reach)
        give_weapon(fighter, shotgun, paid=30)

        lines = self.lines_for(fighter)
        heading = next(line for line in lines if line.startswith("Combat shotgun"))
        assert "SR" not in heading  # a bare heading; the modes carry the stats
        assert any(line.startswith("- Salvo ammo   SR") for line in lines)
        assert any(line.startswith("- Shredder ammo   SR") for line in lines)

    def test_an_unnamed_line_keeps_its_row_when_ammo_is_bought(
        self, armed_gang, weapon_statline_type
    ):
        gang, fighter = armed_gang
        autogun = create_weapon(
            "Autogun",
            profiles=[("", 0), ("Warp round", 10)],
            statline_type=weapon_statline_type,
        )
        for profile in autogun.profiles.all():
            set_statline(profile, short_range=8)
        held = give_weapon(fighter, autogun, paid=20)
        buy_weapon_profile(held, autogun.profiles.get(name="Warp round"))

        lines = self.lines_for(fighter)
        assert any(line.startswith("Autogun") and 'SR 8"' in line for line in lines)
        assert any(line.startswith("- Warp round (+10cr)") for line in lines)

    def test_named_lines_and_bought_ammo_read_alike(
        self, armed_gang, weapon_statline_type
    ):
        """Nothing marks a bought line out: it is a named line like the
        others, save for what it added."""
        gang, fighter = armed_gang
        shotgun = create_weapon(
            "Combat shotgun",
            profiles=[("Salvo ammo", 0), ("Shredder ammo", 0), ("Inferno ammo", 30)],
            statline_type=weapon_statline_type,
        )
        for profile in shotgun.profiles.all():
            set_statline(profile, short_range=8)
        held = give_weapon(fighter, shotgun, paid=30)
        buy_weapon_profile(held, shotgun.profiles.get(name="Inferno ammo"))

        lines = self.lines_for(fighter)
        heading = next(line for line in lines if line.startswith("Combat shotgun"))
        assert "SR" not in heading
        # Only Short Range is set on these, and the rest of the shape still
        # prints: a line is drawn to the columns its statline type calls
        # for, so a stat nobody filled in reads as a dash rather than
        # sliding the next number under the wrong heading.
        assert [line for line in lines if line.startswith("- ")] == [
            '- Salvo ammo   SR 8"  LR -  Str -  AP -  L -',
            '- Shredder ammo   SR 8"  LR -  Str -  AP -  L -',
            '- Inferno ammo (+30cr)   SR 8"  LR -  Str -  AP -  L -',
        ]

    def test_a_weapon_may_have_only_one_unnamed_line(self, weapon_statline_type):
        """Two would print as the weapon twice, indistinguishably."""
        autogun = create_weapon(
            "Autogun", profiles=[("", 0)], statline_type=weapon_statline_type
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            add_weapon_profile(autogun, "")


class TestValuesAreStoredAsTheyRead:
    """An author types 8 for a range and means 8". Normalising on save
    rather than in clean, because objects.create never calls full_clean
    — the verbs and any importer must land what a form lands."""

    def test_a_distance_gains_its_mark(self, weapon_statline_type):
        weapon = create_weapon(
            "Autogun", profiles=[("", 0)], statline_type=weapon_statline_type
        )
        statline = set_statline(weapon.profiles.get(), short_range=8, long_range=24)
        stored = {s.short_name: s.value for s in statline.stats.all()}
        assert stored["SR"] == '8"'
        assert stored["LR"] == '24"'

    def test_typing_it_already_formatted_changes_nothing(self, weapon_statline_type):
        weapon = create_weapon(
            "Autopistol", profiles=[("", 0)], statline_type=weapon_statline_type
        )
        statline = set_statline(weapon.profiles.get(), short_range='4"')
        assert statline.stats.get().value == '4"'

    def test_a_roll_target_gains_its_plus(self, make_stat):
        """The other display rule, on the shape that uses it."""
        from n26.library.models import StatlineType, StatlineTypeStat

        shape = StatlineType.objects.create(name="Save only")
        StatlineTypeStat.objects.create(
            statline_type=shape,
            stat=make_stat("Sv", "Save", is_target=True, is_inverted=True),
            position=0,
        )
        weapon = create_weapon("Shield", profiles=[("", 0)], statline_type=shape)
        statline = set_statline(weapon.profiles.get(), save=5)
        assert statline.stats.get().value == "5+"

    def test_values_that_are_not_numbers_pass_through(self, weapon_statline_type):
        """S is the wielder's Strength and E is engaged-only: both are
        legitimate, and neither is a distance."""
        weapon = create_weapon(
            "Chainsword", profiles=[("", 0)], statline_type=weapon_statline_type
        )
        statline = set_statline(weapon.profiles.get(), short_range="E", strength="S")
        stored = {s.short_name: s.value for s in statline.stats.all()}
        assert stored == {"SR": "E", "Str": "S"}
