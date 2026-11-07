"""Compare materialised built-in claws with a computed weapon grant from Dustback Helamite
wargear. Both add no separate rating and disappear with their source; only materialised
claws have assignments and ledger entries. Trait modifiers must target the named claws
after the grant has computed.
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
    in_categories,
    is_one_of,
    targets_attached_weapon,
    targets_model,
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
    """Wargear with claws as a materialised built-in."""
    beast = create_wargear("Dustback Helamite", price=45)
    add_built_in(beast, claws)
    return beast


@pytest.fixture
def granting_helamite(claws):
    """Wargear granting computed claws through a modifier."""
    beast = create_wargear("Dustback Helamite", price=45)
    modifier(
        "A Dustback Helamite is equipped with Helamite claws",
        targets_model(),
        adds(claws),
        carried_by=beast,
    )
    return beast


@pytest.fixture
def autogun(weapon_statline_type):
    """An unrelated weapon that the claw modifier must not affect."""
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
    """Find the materialised claw assignment."""
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
    """Built-in claws have zero contribution and are removed with their cause. Their
    assignments still expose sale controls, covered by the strict expected failure.
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
        """Materialised built-ins receive a ledger entry with zero paid, list price and
        discount.
        """
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
        """Owned-gear controls include the materialised weapon assignment."""
        held = owned_things(build_card(fighter), "/n26/fighters/x/equip/")
        offered = {thing.name for things in held.values() for thing in things}
        assert "Helamite claws" in offered

    def test_removing_the_helamite_takes_the_claws(self, gang, fighter, bought):
        remove(bought)
        gang.refresh_from_db()

        assert card_for(fighter).weapons == []
        assert gang.rating == 50  # Fighter contribution only.
        assert_reconciled(gang)


class TestNoScopeNamesTheseClaws:
    """Compare broad, attached-weapon and category scopes with the required named-weapon
    scope.
    """

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
        """An unfiltered weapon scope also changes the unrelated Autogun."""
        card = armed(targets_weapons())

        assert traits_on(card, "Helamite claws") == ["Additional Attacks (1)"]
        assert traits_on(card, "Autogun") == ["Additional Attacks (1)"]

    def test_the_attached_weapon_scope_reaches_nothing(self, armed):
        """The wargear is not attached to a weapon, so the attached-weapon scope has no
        target.
        """
        card = armed(targets_attached_weapon())

        assert traits_on(card, "Helamite claws") == []
        assert traits_on(card, "Autogun") == []

    def test_a_category_narrowing_lands_but_says_the_wrong_thing(
        self, armed, beast_weapons
    ):
        """A category happens to isolate the claws here, but would also target any other
        weapon in that category.
        """
        card = armed(targets_weapons(in_categories(beast_weapons)))

        assert traits_on(card, "Helamite claws") == ["Additional Attacks (1)"]
        assert traits_on(card, "Autogun") == []


class TestNamingTheClawsOutright:
    """The modifier targets the named Helamite claws without affecting the Autogun."""

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
        """Removing the wargear removes its materialised claws and the modifier supplying
        their trait.
        """
        beast_row = next(
            assignment
            for assignment in helamite_rule.assignments.all()
            if assignment.wargear_id == helamite.pk
        )
        remove(beast_row)

        card = card_for(helamite_rule)
        assert [weapon.name for weapon in card.weapons] == ["Autogun"]
        assert traits_on(card, "Autogun") == []


def beast_row(fighter, beast):
    """Find the owned Helamite wargear assignment."""
    return next(
        assignment
        for assignment in fighter.assignments.all()
        if assignment.wargear_id == beast.pk
    )


class TestTheGrantedClawsAreFreeKit:
    """Computed claws have no assignment, ledger entry or sale controls and last only while
    the granting wargear is present.
    """

    @pytest.fixture
    def bought(self, gang, fighter, granting_helamite):
        return buy(fighter, thing=granting_helamite, paid=45)

    def test_the_claws_arrive_with_the_wargear(self, fighter, bought):
        assert [weapon.name for weapon in card_for(fighter).weapons] == [
            "Helamite claws"
        ]

    def test_the_claws_draw_their_profile(self, fighter, bought):
        """Computed weapons retain their declared statline."""
        card = card_for(fighter)
        line = next(w for w in card.weapons if w.name == "Helamite claws").own_line

        assert [(cell.short_name, cell.value) for cell in line.statline.cells] == [
            ("SR", "E"),
            ("Str", "4"),
            ("AP", "-1"),
        ]

    def test_the_claws_say_the_beast_brought_them(self, fighter, bought):
        card = card_for(fighter)
        weapon = next(w for w in card.weapons if w.name == "Helamite claws")

        assert weapon.provenance.source == "Dustback Helamite"
        assert weapon.provenance.computed is True

    def test_the_claws_add_no_rating(self, gang, fighter, bought):
        """Only the fighter and wargear contribute rating."""
        gang.refresh_from_db()

        assert gang.rating == 50 + 45
        assert_reconciled(gang)

    def test_the_claws_are_on_no_ledger(self, fighter, bought, claws):
        """Computed weapons have no assignment or ledger entry."""
        assert not LedgerEntry.objects.filter(assignment__weapon=claws).exists()
        assert not any(
            assignment.weapon_id == claws.pk for assignment in fighter.assignments.all()
        )

    def test_the_claws_cannot_be_sold(self, fighter, bought):
        """Sale controls list stored assignments, excluding computed weapons."""
        held = owned_things(build_card(fighter), "/n26/fighters/x/equip/")
        offered = {thing.name for things in held.values() for thing in things}

        assert "Helamite claws" not in offered

    def test_removing_the_helamite_takes_the_claws(
        self, gang, fighter, bought, granting_helamite
    ):
        remove(beast_row(fighter, granting_helamite))
        gang.refresh_from_db()

        assert card_for(fighter).weapons == []
        assert gang.rating == 50  # Fighter contribution only.
        assert_reconciled(gang)


class TestTheWholeRuleAsTwoModifiers:
    """The unconditional weapon grant computes before the conditional named-weapon trait
    modifier.
    """

    @pytest.fixture
    def armed_beast(self, granting_helamite, claws, additional_attacks):
        modifier(
            "Helamite claws gain Additional Attacks (1)",
            targets_weapons(is_one_of(claws)),
            adds(additional_attacks),
            carried_by=granting_helamite,
        )
        return granting_helamite

    @pytest.fixture
    def bought(self, gang, fighter, armed_beast, autogun):
        give_weapon(fighter, autogun, paid=15)
        return buy(fighter, thing=armed_beast, paid=45)

    def test_buying_the_beast_puts_armed_claws_on_the_card(self, fighter, bought):
        card = card_for(fighter)

        assert traits_on(card, "Helamite claws") == ["Additional Attacks (1)"]

    def test_the_fighters_own_gun_is_left_alone(self, fighter, bought):
        """Named targeting leaves the Autogun unchanged."""
        assert traits_on(card_for(fighter), "Autogun") == []

    def test_removing_the_beast_takes_the_armed_claws_away(
        self, gang, fighter, bought, armed_beast
    ):
        remove(beast_row(fighter, armed_beast))
        gang.refresh_from_db()

        assert [weapon.name for weapon in card_for(fighter).weapons] == ["Autogun"]
        assert gang.rating == 50 + 15
        assert_reconciled(gang)

    def test_the_grant_is_asked_before_the_arming(self, fighter, bought):
        """The grant runs in round 0; the conditional named-weapon modifier runs in round
        1.
        """
        card = build_card(fighter, with_statlines=True)
        index = build_modifier_index([node.assignable for node in card.all_nodes()])

        assert [
            (step.ran_in, step.modifier.name, step.outcome)
            for step in compute(card, index).plan
        ] == [
            (0, "A Dustback Helamite is equipped with Helamite claws", "reached"),
            (1, "Helamite claws gain Additional Attacks (1)", "reached"),
        ]

    def test_working_the_claws_out_costs_no_queries(
        self, django_assert_num_queries, fighter, bought
    ):
        """Fetch granted profiles, stats and traits before computing so rendering needs no
        SQL.
        """
        card = build_card(fighter, with_statlines=True)
        index = build_modifier_index([node.assignable for node in card.all_nodes()])

        with django_assert_num_queries(0):
            build_model_card(fighter, card=card, computed=compute(card, index))


class TestAnUnfilteredArmingModifierMissesTheClaws:
    """An unconditioned weapon modifier runs in the same round as the grant, before the
    newly granted claws can be targeted.
    """

    @pytest.fixture
    def sweeping_beast(self, granting_helamite, additional_attacks):
        modifier(
            "The bearer's weapons gain Additional Attacks (1)",
            targets_weapons(),
            adds(additional_attacks),
            carried_by=granting_helamite,
        )
        return granting_helamite

    def test_the_autogun_is_armed_and_the_granted_claws_are_not(
        self, fighter, sweeping_beast, autogun
    ):
        give_weapon(fighter, autogun, paid=15)
        buy(fighter, thing=sweeping_beast, paid=45)
        card = card_for(fighter)

        assert traits_on(card, "Autogun") == ["Additional Attacks (1)"]
        assert traits_on(card, "Helamite claws") == []


class TestWhatTheTwoRoutesDiffer:
    """Materialised claws can be moved or sold through their assignment. Computed claws
    have no writable row for movement, accessories or purchased ammunition.
    """

    def test_a_built_in_is_a_row_and_a_grant_is_not(self, fighter, helamite, claws):
        """Purchasing materialises built-in claws as a zero-contribution assignment."""
        buy(fighter, thing=helamite, paid=45)

        assert claws_row(fighter, claws).rating == 0

    def test_a_grant_leaves_nothing_to_move_or_sell(
        self, fighter, granting_helamite, claws
    ):
        """Computed claws render without creating an assignment."""
        buy(fighter, thing=granting_helamite, paid=45)

        assert not any(
            assignment.weapon_id == claws.pk for assignment in fighter.assignments.all()
        )
        assert [weapon.name for weapon in card_for(fighter).weapons] == [
            "Helamite claws"
        ]

    def test_a_granted_weapon_offers_no_paid_ammo(self, fighter, granting_helamite):
        """A computed weapon exposes its default profiles without controls for purchased
        profiles or accessories.
        """
        buy(fighter, thing=granting_helamite, paid=45)
        weapon = next(
            w for w in card_for(fighter).weapons if w.name == "Helamite claws"
        )

        assert weapon.named_profiles == []
        assert weapon.id == ""
        assert weapon.total_rating == 0
