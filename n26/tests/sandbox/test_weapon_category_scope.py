"""Weapon-category scopes: "Van Saar gangs get an AP improvement of 1 on
all Las weapons".

A rule of that shape names no trait. What the weapons have in common is
where they sort — the Las Weapons category their kind is homed in — so a
weapon-targeting scope narrows by category as well as by trait, and by
both at once when a rule wants the weapons that satisfy each.

The category lives on the weapon, while what a modifier reaches is a
weapon's firing lines. A line has no home of its own and takes its gun's,
which is what lets "all Las weapons" mean every line of every Las weapon.
Both halves of the selector say so: the tests here pin the matching, and
a sweep of the same category pins the query.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.library.authoring import (
    create_collection,
    has_trait,
    in_category,
    is_one_of,
    targets_weapons,
)
from n26.library.models import StatlineType, StatlineTypeStat, WeaponProfile
from n26.tests.sandbox.actions import (
    changes_stat,
    create_category,
    create_gang_type,
    create_stat,
    create_trait,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    modifier,
    set_statline,
)

pytestmark = pytest.mark.django_db

#: The printed weapon profile, minus traits and pricing. AP is inverted
#: because improving it means a lower number: an AP of -1 improved by one
#: is -2, which is the better gun.
WEAPON_STATS = [
    ("SR", "Short Range", {"is_inches": True}),
    ("LR", "Long Range", {"is_inches": True}),
    ("Str", "Strength", {}),
    ("AP", "Armour Piercing", {"is_inverted": True}),
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
def gang_type(db):
    """The house whose rule this is. Overrides the shared fixture so the
    profiles the other fixtures make belong to this house."""
    return create_gang_type("Van Saar", starting_credits=1000)


@pytest.fixture
def las_weapons(default_pack):
    return create_category("Weapons", "Las Weapons")


@pytest.fixture
def solid_projectile(default_pack):
    return create_category("Weapons", "Solid Projectile Weapons")


@pytest.fixture
def make_gun(weapon_statline_type):
    """A gun with one firing line, homed where the book files it."""

    def _make(name, category, armour_piercing=-1, profiles=(("", 0),), traits=()):
        weapon = create_weapon(name, profiles=profiles, category=category)
        weapon.statline_type = weapon_statline_type
        weapon.save()
        for profile in weapon.profiles.all():
            set_statline(
                profile,
                short_range=8,
                long_range=16,
                strength=3,
                armour_piercing=armour_piercing,
                lethality=1,
            )
            profile.traits.set(traits)
        return weapon

    return _make


@pytest.fixture
def lasgun(make_gun, las_weapons):
    return make_gun("Lasgun", las_weapons)


@pytest.fixture
def laspistol(make_gun, las_weapons):
    return make_gun("Laspistol", las_weapons)


@pytest.fixture
def autogun(make_gun, solid_projectile):
    return make_gun("Autogun", solid_projectile)


@pytest.fixture
def armour_piercing(weapon_statline_type):
    return weapon_statline_type.stats.get(stat__short_name="AP").stat


@pytest.fixture
def gang(gang_type):
    return found_gang(
        "The Sanctioned", gang_type, owner=User.objects.create_user("tom")
    )


@pytest.fixture
def fighter(gang, make_profile):
    profile = make_profile("Neoteck", gang_type=gang.gang_type, price=50)
    return hire(gang, profile, "Sten", paid=50)


def guns_of(miniature):
    """Each weapon line on the card, by name, with its effects worked out."""
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    drawn = build_model_card(miniature, card=card, computed=compute(card, index))
    return {weapon.name: weapon for weapon in drawn.weapons}


def ap_of(weapon):
    return weapon.profiles[0].statline.get("AP").value


class TestAHouseImprovesOneCategoryOfWeapon:
    """The Van Saar case, end to end: a rule the gang type carries, an AP
    improvement, and Las weapons the only ones that get it."""

    @pytest.fixture
    def house_rule(self, gang_type, las_weapons, armour_piercing):
        return modifier(
            "Van Saar: Las weapons pierce deeper",
            targets_weapons(in_category(las_weapons)),
            changes_stat(armour_piercing, mode="improve", amount=1),
            carried_by=gang_type,
        )

    def test_the_scope_says_which_weapons_it_means(self, house_rule):
        assert str(house_rule.scope) == "weapons in Las Weapons"

    def test_every_las_weapon_improves_and_the_autogun_does_not(
        self, gang, fighter, lasgun, laspistol, autogun, house_rule
    ):
        give_weapon(fighter, lasgun, paid=15)
        give_weapon(fighter, laspistol, paid=10)
        give_weapon(fighter, autogun, paid=15)

        guns = guns_of(fighter)
        assert ap_of(guns["Lasgun"]) == "-2"
        assert ap_of(guns["Laspistol"]) == "-2"
        assert ap_of(guns["Autogun"]) == "-1"
        assert_reconciled(gang)

    def test_the_improvement_says_where_it_came_from(
        self, gang, fighter, lasgun, house_rule
    ):
        """A changed number on a card names its source, so a player can
        see the house rule rather than a value they cannot account for."""
        give_weapon(fighter, lasgun, paid=15)

        cell = guns_of(fighter)["Lasgun"].profiles[0].statline.get("AP")
        (source,) = cell.modified_by
        assert source.computed
        assert str(source.source) == "Van Saar"
        assert_reconciled(gang)

    def test_taking_the_gun_off_takes_the_improvement_with_it(
        self, gang, fighter, lasgun, autogun, house_rule
    ):
        give_weapon(fighter, autogun, paid=15)

        assert "Lasgun" not in guns_of(fighter)
        assert ap_of(guns_of(fighter)["Autogun"]) == "-1"
        assert_reconciled(gang)


class TestTheTraitFilterIsUntouched:
    """Narrowing by trait behaves exactly as it did before there was a
    second filter — the category is an addition, not a replacement."""

    @pytest.fixture
    def melee(self, default_pack):
        return create_trait("Melee")

    @pytest.fixture
    def knife(self, make_gun, solid_projectile, melee):
        return make_gun("Stiletto knife", solid_projectile, traits=[melee])

    def test_the_scope_still_reads_as_it_always_did(self, melee):
        assert str(targets_weapons(has_trait(melee))) == "weapons with Melee"
        assert str(targets_weapons()) == "all weapons"

    def test_only_the_melee_weapon_is_reached(
        self, gang, gang_type, fighter, knife, autogun, melee, armour_piercing
    ):
        modifier(
            "Sharpened",
            targets_weapons(has_trait(melee)),
            changes_stat(armour_piercing, mode="improve", amount=1),
            carried_by=gang_type,
        )
        give_weapon(fighter, knife, paid=10)
        give_weapon(fighter, autogun, paid=15)

        guns = guns_of(fighter)
        assert ap_of(guns["Stiletto knife"]) == "-2"
        assert ap_of(guns["Autogun"]) == "-1"
        assert_reconciled(gang)


class TestBothFiltersTogether:
    """Two filters on one scope stack: a weapon must be homed in the
    category *and* carry the trait. Either alone is not enough."""

    @pytest.fixture
    def unstable(self, default_pack):
        return create_trait("Unstable")

    @pytest.fixture
    def plasma_gun(self, make_gun, las_weapons, unstable):
        return make_gun("Plasma gun", las_weapons, traits=[unstable])

    @pytest.fixture
    def scoped(self, gang_type, las_weapons, unstable, armour_piercing):
        return modifier(
            "Van Saar: stabilised plasma",
            targets_weapons(in_category(las_weapons), has_trait(unstable)),
            changes_stat(armour_piercing, mode="improve", amount=1),
            carried_by=gang_type,
        )

    def test_the_scope_says_both_halves(self, scoped):
        assert str(scoped.scope) == "weapons in Las Weapons, with Unstable"

    def test_only_the_weapon_answering_both_is_reached(
        self,
        gang,
        fighter,
        make_gun,
        solid_projectile,
        unstable,
        plasma_gun,
        lasgun,
        scoped,
    ):
        unstable_but_elsewhere = make_gun(
            "Grav gun", solid_projectile, traits=[unstable]
        )
        give_weapon(fighter, plasma_gun, paid=100)
        give_weapon(fighter, lasgun, paid=15)
        give_weapon(fighter, unstable_but_elsewhere, paid=90)

        guns = guns_of(fighter)
        assert ap_of(guns["Plasma gun"]) == "-2"
        assert ap_of(guns["Lasgun"]) == "-1"  # right category, no trait
        assert ap_of(guns["Grav gun"]) == "-1"  # right trait, wrong category
        assert_reconciled(gang)


class TestAnUnfilteredScopeStillMeansEveryWeapon:
    """Saying nothing narrows nothing — the default-open rule the whole
    scope grammar shares."""

    def test_both_weapons_are_reached(
        self, gang, gang_type, fighter, lasgun, autogun, armour_piercing
    ):
        modifier(
            "Van Saar: better guns all round",
            targets_weapons(),
            changes_stat(armour_piercing, mode="improve", amount=1),
            carried_by=gang_type,
        )
        give_weapon(fighter, lasgun, paid=15)
        give_weapon(fighter, autogun, paid=15)

        guns = guns_of(fighter)
        assert ap_of(guns["Lasgun"]) == "-2"
        assert ap_of(guns["Autogun"]) == "-2"
        assert_reconciled(gang)


class TestASweepFindsTheLinesOfACategory:
    """The query half of the same sentence. A collection sweeping weapon
    profiles by category collects the lines of the guns homed there,
    because a line sorts where its gun does — the answer the in-memory
    match gives, asked of the database."""

    def test_the_sweep_collects_las_lines_and_no_others(
        self, las_weapons, lasgun, autogun
    ):
        swept = create_collection("Las lines", contains=[(WeaponProfile, las_weapons)])

        (found,) = swept.selectors.get().contents()
        assert found.weapon == lasgun


class TestComposingCategoryRulesInTheApp:
    """The authoring composer, where the naming rule bites: a modifier
    left unnamed is called after its carrier and its scope, and one
    carrier may not hold two modifiers of the same name."""

    #: A prefilled formset's bookkeeping, as the browser sends it back.
    @staticmethod
    def chips(count=0):
        return {
            "conditions-TOTAL_FORMS": str(count),
            "conditions-INITIAL_FORMS": str(count),
            "conditions-MIN_NUM_FORMS": "0",
            "conditions-MAX_NUM_FORMS": "1000",
        }

    @pytest.fixture
    def author(self, client):
        user = User.objects.create_user("author", is_staff=True)
        client.force_login(user)
        return user

    def compose(self, client, carrier, categories, stat, amount="1"):
        if not isinstance(categories, (list, tuple)):
            categories = [categories]
        return client.post(
            f"/n26/authoring/gang-type/{carrier.pk}/",
            {
                "act": "compose",
                "scope_kind": "targets_weapons",
                "effect_kind": "ef_changes_stat",
                "what-stat": str(stat.pk),
                "what-mode": "improve",
                "what-amount": amount,
                **self.chips(1),
                "conditions-0-kind": "in_category",
                "conditions-0-categories": [str(one.pk) for one in categories],
            },
        )

    def test_two_categories_on_one_carrier_are_two_named_modifiers(
        self,
        author,
        client,
        gang_type,
        las_weapons,
        solid_projectile,
        armour_piercing,
        default_pack,
    ):
        """Both are an AP improvement on the same house, so the category
        is the only thing telling their names apart. Without it in the
        name the second would be refused by the unique-name rule."""
        assert (
            self.compose(client, gang_type, las_weapons, armour_piercing).status_code
            == 302
        )
        assert (
            self.compose(
                client, gang_type, solid_projectile, armour_piercing
            ).status_code
            == 302
        )

        named = sorted(row.name for row in gang_type.modifiers.all())
        assert named == [
            "Van Saar, weapons in Las Weapons: improve AP by 1",
            "Van Saar, weapons in Solid Projectile Weapons: improve AP by 1",
        ]

    def test_two_overlapping_filters_on_one_carrier_are_still_two_names(
        self,
        author,
        client,
        gang_type,
        las_weapons,
        solid_projectile,
        armour_piercing,
        default_pack,
    ):
        """A filter naming more values says more in the name it writes.
        Two rules on one house, one for Las and one for Las or Solid
        Projectile, differ only in that — and the second would be refused
        outright if the extra value went unsaid."""
        assert (
            self.compose(client, gang_type, las_weapons, armour_piercing).status_code
            == 302
        )
        assert (
            self.compose(
                client, gang_type, [las_weapons, solid_projectile], armour_piercing
            ).status_code
            == 302
        )

        named = sorted(row.name for row in gang_type.modifiers.all())
        assert named == [
            "Van Saar, weapons in Las Weapons or Solid Projectile Weapons: "
            "improve AP by 1",
            "Van Saar, weapons in Las Weapons: improve AP by 1",
        ]

    def test_reopening_a_category_rule_keeps_its_narrowing(
        self, author, client, gang_type, las_weapons, armour_piercing, default_pack
    ):
        """The page fills its chips from the stored scope. A narrowing it
        cannot read back is one the next save silently drops, leaving a
        rule that reaches every weapon in the game."""
        self.compose(client, gang_type, las_weapons, armour_piercing)
        (made,) = gang_type.modifiers.all()

        page = client.get(f"/n26/authoring/modifiers/{made.pk}/")
        (chip,) = page.context["form"].condition_formset.initial
        assert chip["kind"] == "in_category"
        assert list(chip["categories"]) == [las_weapons]

        client.post(
            f"/n26/authoring/modifiers/{made.pk}/",
            {
                "name": made.name,
                "what-stat": str(armour_piercing.pk),
                "what-mode": "improve",
                "what-amount": "2",
                **self.chips(1),
                "conditions-0-kind": "in_category",
                "conditions-0-categories": [str(las_weapons.pk)],
            },
        )

        made.refresh_from_db()
        assert str(made.scope) == "weapons in Las Weapons"
        assert made.effect.amount == 2


class TestAFilterMayNameSeveralValues:
    """Any one of the values in a filter is enough, and every filter must
    be satisfied. "Las or Plasma weapons" is one filter naming two
    categories; "Las weapons that are also Unstable" is two filters."""

    @pytest.fixture
    def plasma_weapons(self, default_pack):
        return create_category("Weapons", "Plasma Weapons")

    @pytest.fixture
    def plasma_gun(self, make_gun, plasma_weapons):
        return make_gun("Plasma gun", plasma_weapons)

    def test_naming_two_categories_reaches_either(
        self,
        gang,
        gang_type,
        fighter,
        lasgun,
        plasma_gun,
        autogun,
        armour_piercing,
        las_weapons,
        plasma_weapons,
    ):
        modifier(
            "Van Saar: energy weapons pierce deeper",
            targets_weapons(in_category(las_weapons, plasma_weapons)),
            changes_stat(armour_piercing, mode="improve", amount=1),
            carried_by=gang_type,
        )
        give_weapon(fighter, lasgun, paid=15)
        give_weapon(fighter, plasma_gun, paid=100)
        give_weapon(fighter, autogun, paid=15)

        guns = guns_of(fighter)
        assert ap_of(guns["Lasgun"]) == "-2"
        assert ap_of(guns["Plasma gun"]) == "-2"
        assert ap_of(guns["Autogun"]) == "-1"
        assert_reconciled(gang)

    def test_the_scope_says_either_of_them(self, las_weapons, plasma_weapons):
        scope = targets_weapons(in_category(las_weapons, plasma_weapons))
        assert str(scope) == "weapons in Las Weapons or Plasma Weapons"

    def test_naming_two_traits_reaches_either(
        self, gang, gang_type, fighter, make_gun, solid_projectile, armour_piercing
    ):
        unwieldy = create_trait("Unwieldy")
        unstable = create_trait("Unstable")
        heavy = make_gun("Heavy stubber", solid_projectile, traits=[unwieldy])
        volatile = make_gun("Plasma pistol", solid_projectile, traits=[unstable])
        plain = make_gun("Stub gun", solid_projectile)
        modifier(
            "Van Saar: stabilised firing",
            targets_weapons(has_trait(unwieldy, unstable)),
            changes_stat(armour_piercing, mode="improve", amount=1),
            carried_by=gang_type,
        )
        for gun in (heavy, volatile, plain):
            give_weapon(fighter, gun, paid=10)

        guns = guns_of(fighter)
        assert ap_of(guns["Heavy stubber"]) == "-2"
        assert ap_of(guns["Plasma pistol"]) == "-2"
        assert ap_of(guns["Stub gun"]) == "-1"
        assert_reconciled(gang)

    def test_naming_two_weapons_reaches_either(
        self, gang, gang_type, fighter, lasgun, laspistol, autogun, armour_piercing
    ):
        modifier(
            "Van Saar: the master-crafted pair",
            targets_weapons(is_one_of(lasgun, laspistol)),
            changes_stat(armour_piercing, mode="improve", amount=1),
            carried_by=gang_type,
        )
        for gun in (lasgun, laspistol, autogun):
            give_weapon(fighter, gun, paid=15)

        guns = guns_of(fighter)
        assert ap_of(guns["Lasgun"]) == "-2"
        assert ap_of(guns["Laspistol"]) == "-2"
        assert ap_of(guns["Autogun"]) == "-1"
        assert_reconciled(gang)

    def test_two_filters_of_one_kind_must_both_be_answered(
        self, gang, gang_type, fighter, make_gun, solid_projectile, armour_piercing
    ):
        """Alternatives live inside a filter, so wanting both is two of
        them — the same rule the model scope's conditions follow."""
        unwieldy = create_trait("Unwieldy")
        unstable = create_trait("Unstable")
        both = make_gun("Plasma cannon", solid_projectile, traits=[unwieldy, unstable])
        one = make_gun("Heavy stubber", solid_projectile, traits=[unwieldy])
        modifier(
            "Van Saar: the difficult guns",
            targets_weapons(has_trait(unwieldy), has_trait(unstable)),
            changes_stat(armour_piercing, mode="improve", amount=1),
            carried_by=gang_type,
        )
        give_weapon(fighter, both, paid=100)
        give_weapon(fighter, one, paid=50)

        guns = guns_of(fighter)
        assert ap_of(guns["Plasma cannon"]) == "-2"
        assert ap_of(guns["Heavy stubber"]) == "-1"
        assert_reconciled(gang)
