"""A Dustback Helamite: wargear that brings its own weapon.

"A Dustback Helamite is equipped with Helamite claws, which gain the
Additional Attacks (1) trait." The Helamite is a piece of wargear, the
claws are a weapon, and the trait is a modifier the wargear carries.

The claws arrive as the wargear's **built-ins** — free kit, materialised
when the wargear is bought and caused by it. Built-ins do the job: no new
machinery is needed to bring the weapon. What free kit is supposed to
mean is no rating, no ledger entry, no sale, and gone when the thing that
brought it goes; ``TestTheClawsArriveAsFreeKit`` states each separately,
because they are not all true today.

The modifier names the claws outright. Nothing else the fighter carries
answers to "Helamite claws", and no fact about the claws — a trait, a
category — picks them out without also describing weapons the Helamite
never brought. ``TestNoScopeNamesTheseClaws`` shows what the other scopes
do with this rule; ``TestNamingTheClawsOutright`` is the expression the
rule wants.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import LedgerEntry
from n26.core.owned import owned_things
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.library.authoring import (
    add_built_in,
    in_category,
    is_one_of,
    targets_attached_weapon,
    targets_weapons,
)
from n26.library.models import StatlineType, StatlineTypeStat
from n26.tests.sandbox.actions import (
    adds,
    buy,
    create_category,
    create_gang_type,
    create_stat,
    create_trait,
    create_wargear,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    modifier,
    remove,
    sell,
    set_statline,
)

pytestmark = pytest.mark.django_db

WEAPON_STATS = [
    ("SR", "Short Range", {"is_inches": True}),
    ("Str", "Strength", {}),
    ("AP", "Armour Piercing", {"is_inverted": True}),
]


@pytest.fixture
def weapon_statline_type(db):
    statline_type = StatlineType.objects.create(name="Weapon")
    for position, (short, full, flags) in enumerate(WEAPON_STATS):
        StatlineTypeStat.objects.create(
            statline_type=statline_type,
            stat=create_stat(short, full, **flags),
            position=position,
        )
    return statline_type


@pytest.fixture
def gang_type(db):
    return create_gang_type("Ash Waste Nomads", starting_credits=1000)


@pytest.fixture
def beast_weapons(default_pack):
    return create_category("Weapons", "Beast Weapons")


@pytest.fixture
def claws(weapon_statline_type, beast_weapons):
    weapon = create_weapon("Helamite claws", profiles=[("", 0)], category=beast_weapons)
    weapon.statline_type = weapon_statline_type
    weapon.save()
    set_statline(weapon.profiles.get(), short_range="E", strength=4, armour_piercing=-1)
    return weapon


@pytest.fixture
def additional_attacks(default_pack):
    return create_trait("Additional Attacks", annotation="1")


@pytest.fixture
def helamite(claws):
    """The wargear, and the weapon it always comes with."""
    beast = create_wargear("Dustback Helamite", price=45)
    add_built_in(beast, claws)
    return beast


@pytest.fixture
def autogun(weapon_statline_type):
    """Something else the fighter carries — what a scope must not reach."""
    weapon = create_weapon("Autogun", profiles=[("", 0)])
    weapon.statline_type = weapon_statline_type
    weapon.save()
    set_statline(weapon.profiles.get(), short_range=8, strength=3, armour_piercing=0)
    return weapon


@pytest.fixture
def gang(gang_type):
    return found_gang("The Dustriders", gang_type, owner=User.objects.create_user("t"))


@pytest.fixture
def fighter(gang, make_profile):
    profile = make_profile("Nomad", gang_type=gang.gang_type, price=50)
    return hire(gang, profile, "Kalla", paid=50)


def claws_row(fighter, claws):
    """The granted weapon's own assignment."""
    return next(
        assignment
        for assignment in fighter.assignments.all()
        if assignment.weapon_id == claws.pk
    )


def card_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


def traits_on(card, weapon_name):
    weapon = next(w for w in card.weapons if w.name == weapon_name)
    return [trait.name for trait in weapon.profiles[0].traits]


class TestTheClawsArriveAsFreeKit:
    """Buying the Helamite brings the claws with it, free.

    Free kit means the gang is no richer or poorer for having it: it adds
    nothing to what the gang is worth, cost nothing, cannot be turned
    back into money, and lasts exactly as long as the thing that brought
    it.
    """

    @pytest.fixture
    def bought(self, gang, fighter, helamite):
        return buy(fighter, thing=helamite, paid=45)

    def test_the_claws_arrive_with_the_wargear(self, fighter, bought):
        assert [weapon.name for weapon in card_for(fighter).weapons] == [
            "Helamite claws"
        ]

    def test_the_claws_add_no_rating(self, fighter, bought, claws):
        assert claws_row(fighter, claws).rating == 0

    def test_the_claws_ledger_entry_records_nothing_spent(self, fighter, bought, claws):
        """An entry is written, and it says the gang paid nothing for a
        thing that lists at nothing. Every assignment gets one, which is
        what lets the ledger be folded back into the entry it belongs to;
        what makes this one free kit is that all four numbers are zero."""
        entry = LedgerEntry.objects.get(assignment=claws_row(fighter, claws))
        assert (entry.reason, entry.paid, entry.list_price, entry.discount) == (
            "default",
            0,
            0,
            0,
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Free kit can be sold. A sale pays half the rating or a five "
            "credit floor, whichever is higher, and free kit is worth "
            "nothing — so parting with it invents five credits. The gang "
            "is richer for having been given something."
        ),
    )
    def test_the_claws_cannot_be_sold(self, gang, fighter, bought, claws):
        before = gang.credits
        sell(claws_row(fighter, claws))
        gang.refresh_from_db()
        assert gang.credits == before

    def test_the_claws_are_offered_for_sale_like_anything_carried(
        self, fighter, bought, claws
    ):
        """Why the sale is reachable: the controls ask what *kind* of
        thing this is, and a weapon is gear whoever gave it to you."""
        held = owned_things(build_card(fighter))
        offered = {thing.name for things in held.values() for thing in things}
        assert "Helamite claws" in offered

    def test_removing_the_helamite_takes_the_claws(self, gang, fighter, bought):
        remove(bought)
        gang.refresh_from_db()

        assert card_for(fighter).weapons == []
        assert gang.rating == 50  # the fighter, and nothing they were lent
        assert_reconciled(gang)


class TestNoScopeNamesTheseClaws:
    """The modifier half. The rule is about *these* claws, and no scope
    says that: one reaches every weapon the fighter has, one reaches
    none, and the third gets the right answer by describing the claws
    rather than naming them."""

    @pytest.fixture
    def armed(self, gang, fighter, helamite, autogun):
        def _arm(scope):
            modifier(
                "Helamite claws gain Additional Attacks (1)",
                scope,
                adds(create_trait("Additional Attacks", annotation="1")),
                carried_by=helamite,
            )
            buy(fighter, thing=helamite, paid=45)
            give_weapon(fighter, autogun, paid=15)
            return card_for(fighter)

        return _arm

    def test_the_unfiltered_scope_arms_the_autogun_too(self, armed):
        """ "The weapons of whoever carries this" is every weapon they
        carry — the fighter's own gun included, which is not the rule."""
        card = armed(targets_weapons())

        assert traits_on(card, "Helamite claws") == ["Additional Attacks (1)"]
        assert traits_on(card, "Autogun") == ["Additional Attacks (1)"]

    def test_the_attached_weapon_scope_reaches_nothing(self, armed):
        """That scope is for a thing bolted *to* a weapon, like a sight.
        The claws are brought *by* the wargear and sit beside it on the
        card, so the wargear has nothing hanging off it to find."""
        card = armed(targets_attached_weapon())

        assert traits_on(card, "Helamite claws") == []
        assert traits_on(card, "Autogun") == []

    def test_a_category_narrowing_lands_but_says_the_wrong_thing(
        self, armed, beast_weapons
    ):
        """Homing the claws in a category of their own does reach them
        and nothing else. It states a fact about where claws file, though,
        not about this beast: a second weapon in that category would be
        armed by a Helamite that never brought it."""
        card = armed(targets_weapons(in_category(beast_weapons)))

        assert traits_on(card, "Helamite claws") == ["Additional Attacks (1)"]
        assert traits_on(card, "Autogun") == []


class TestNamingTheClawsOutright:
    """The rule as the book states it: these claws, and nothing else."""

    @pytest.fixture
    def helamite_rule(self, gang, fighter, helamite, claws, autogun):
        modifier(
            "Helamite claws gain Additional Attacks (1)",
            targets_weapons(is_one_of(claws)),
            adds(create_trait("Additional Attacks", annotation="1")),
            carried_by=helamite,
        )
        buy(fighter, thing=helamite, paid=45)
        give_weapon(fighter, autogun, paid=15)
        return fighter

    def test_the_scope_says_the_weapon_by_name(self, claws, default_pack):
        assert str(targets_weapons(is_one_of(claws))) == "weapons named Helamite claws"

    def test_the_claws_gain_the_trait_and_the_autogun_does_not(self, helamite_rule):
        card = card_for(helamite_rule)

        assert traits_on(card, "Helamite claws") == ["Additional Attacks (1)"]
        assert traits_on(card, "Autogun") == []

    def test_selling_the_beast_takes_the_trait_with_the_claws(
        self, gang, helamite_rule, helamite
    ):
        """The trait is the wargear's to give: nothing about it is stored
        on the claws, so parting with the beast leaves no trace of it."""
        beast_row = next(
            assignment
            for assignment in helamite_rule.assignments.all()
            if assignment.wargear_id == helamite.pk
        )
        remove(beast_row)

        card = card_for(helamite_rule)
        assert [weapon.name for weapon in card.weapons] == ["Autogun"]
        assert traits_on(card, "Autogun") == []
