"""A Dustback Helamite: wargear that brings its own weapon.

"A Dustback Helamite is equipped with Helamite claws, which gain the
Additional Attacks (1) trait." The Helamite is a piece of wargear, the
claws are a weapon, and the trait is a modifier the wargear carries.

There are two ways to bring the claws, and this file states both.

As the wargear's **built-ins**: free kit, materialised when the wargear
is bought and caused by it. What free kit is supposed to mean is no
rating, no ledger entry, no sale, and gone when the thing that brought it
goes; ``TestTheClawsArriveAsFreeKit`` states each separately, because
they are not all true of a built-in.

As a **grant** — a modifier on the wargear whose effect adds the claws.
Nothing is bought, so there is no row: the weapon and its firing lines
are worked out afresh on every read and written nowhere.
``TestTheGrantedClawsAreFreeKit`` states the same four properties of this
route, where all four hold, and ``TestWhatTheTwoRoutesDiffer`` says what
a reader gains and loses by choosing one.

The trait half is the same either way. The modifier names the claws
outright: nothing else the fighter carries answers to "Helamite claws",
and no fact about the claws — a trait, a category — picks them out
without also describing weapons the Helamite never brought.
``TestNoScopeNamesTheseClaws`` shows what the other scopes do with this
rule; ``TestNamingTheClawsOutright`` is the expression the rule wants,
and ``TestTheWholeRuleAsTwoModifiers`` puts both halves on one wargear.
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
    """The wargear, and the weapon it always comes with."""
    beast = create_wargear("Dustback Helamite", price=45)
    add_built_in(beast, claws)
    return beast


@pytest.fixture
def granting_helamite(claws):
    """The same beast, bringing its claws by modifier instead."""
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
        held = owned_things(build_card(fighter), "/n26/fighters/x/equip/")
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
        card = armed(targets_weapons(in_categories(beast_weapons)))

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


def beast_row(fighter, beast):
    """The wargear's own assignment."""
    return next(
        assignment
        for assignment in fighter.assignments.all()
        if assignment.wargear_id == beast.pk
    )


class TestTheGrantedClawsAreFreeKit:
    """The other way to bring the claws: a modifier that adds the weapon.

    Nothing is bought, so nothing is written — and the four things free
    kit is supposed to mean follow from that rather than having to be
    arranged. The gang is no richer or poorer for the claws, they are on
    no ledger, there is nothing to sell, and they last exactly as long as
    the beast.
    """

    @pytest.fixture
    def bought(self, gang, fighter, granting_helamite):
        return buy(fighter, thing=granting_helamite, paid=45)

    def test_the_claws_arrive_with_the_wargear(self, fighter, bought):
        assert [weapon.name for weapon in card_for(fighter).weapons] == [
            "Helamite claws"
        ]

    def test_the_claws_draw_their_firing_line(self, fighter, bought):
        """A weapon with no statline is a name, and a name is no use at
        the table. The granted claws print what they do: Strength 4,
        Armour Piercing -1, at engagement range."""
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
        """The fighter and the beast, and not a credit for the claws."""
        gang.refresh_from_db()

        assert gang.rating == 50 + 45
        assert_reconciled(gang)

    def test_the_claws_are_on_no_ledger(self, fighter, bought, claws):
        """There is no row for them at all, so there is nothing for an
        entry to be about."""
        assert not LedgerEntry.objects.filter(assignment__weapon=claws).exists()
        assert not any(
            assignment.weapon_id == claws.pk for assignment in fighter.assignments.all()
        )

    def test_the_claws_cannot_be_sold(self, fighter, bought):
        """The sale controls are drawn from what the model owns, and a
        granted weapon is not owned: nobody paid for it, so there is
        nothing to hand back for money."""
        held = owned_things(build_card(fighter), "/n26/fighters/x/equip/")
        offered = {thing.name for things in held.values() for thing in things}

        assert "Helamite claws" not in offered

    def test_removing_the_helamite_takes_the_claws(
        self, gang, fighter, bought, granting_helamite
    ):
        remove(beast_row(fighter, granting_helamite))
        gang.refresh_from_db()

        assert card_for(fighter).weapons == []
        assert gang.rating == 50  # the fighter, and nothing they were lent
        assert_reconciled(gang)


class TestTheWholeRuleAsTwoModifiers:
    """ "A Dustback Helamite is equipped with Helamite claws, which gain
    the Additional Attacks (1) trait" — the whole sentence, carried by
    the wargear, as two modifiers: one hands over the weapon, one arms it.

    They run in that order because of what each says, not because of how
    they were written. Handing over the claws asks nothing of anybody, so
    it settles first; naming a weapon is a condition, so it is asked
    afterwards, of a card the claws are already on.
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
        """The scope names the claws, so it reaches the claws — the
        weapon the beast never brought keeps its own printed traits."""
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
        """Which is the whole reason this works. Handing over the claws
        is unconditional, so it settles in the first round; naming a
        weapon is a condition, so it is asked in the second, of a card
        the claws are already on."""
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
        """Everything a granted weapon draws — its firing lines, their
        characteristics, the traits printed on them — is fetched before
        the computing starts, because the computing may not query. A card
        that reached back to the database here would do it once per
        granted weapon, on every model, on every page showing a gang."""
        card = build_card(fighter, with_statlines=True)
        index = build_modifier_index([node.assignable for node in card.all_nodes()])

        with django_assert_num_queries(0):
            build_model_card(fighter, card=card, computed=compute(card, index))


class TestAnUnfilteredArmingModifierMissesTheClaws:
    """The trap next door to the rule that works.

    Scopes are asked in rounds by how conditional they are, so that a
    narrow rule sees what a broad one did. A scope with no conditions is
    asked in the first round — at the same time as the grant, and
    therefore before it. So a wargear that hands over a weapon and, in
    the same breath, says "all my bearer's weapons gain this" arms every
    weapon except the one it just handed over.

    Naming the weapon is what fixes it, and naming the weapon is what the
    rule says anyway.
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
    """Built-in and granted claws look alike on the card and are not the
    same thing underneath.

    **All four properties of free kit hold on the grant route, and only
    three on the built-ins route** — because a built-in is a row and a
    grant is not. A row is what makes a thing sellable, so free kit
    brought as a built-in can be turned into money it was never worth
    (the strict xfail above), while free kit brought as a grant has
    nothing to sell. That is the argument for reaching for a grant when
    what you mean is "this comes with it and is not the owner's to trade".

    The price of a grant is the same fact read the other way: nothing can
    be done to it. It cannot be handed to another fighter, it takes no
    accessories, and it carries no bought ammunition. A weapon a player
    is meant to own — even one that arrives free — wants the row.
    """

    def test_a_built_in_is_a_row_and_a_grant_is_not(self, fighter, helamite, claws):
        """A built-in is materialised at purchase, so the fighter holds a
        real assignment for it — which is what makes it sellable, movable
        and countable, and what makes taking it away an operation."""
        buy(fighter, thing=helamite, paid=45)

        assert claws_row(fighter, claws).rating == 0

    def test_a_grant_leaves_nothing_to_move_or_sell(
        self, fighter, granting_helamite, claws
    ):
        """The same claws, granted, exist only while the card is being
        read. An owner cannot hand them to somebody else or sell them,
        because there is no row to re-home."""
        buy(fighter, thing=granting_helamite, paid=45)

        assert not any(
            assignment.weapon_id == claws.pk for assignment in fighter.assignments.all()
        )
        assert [weapon.name for weapon in card_for(fighter).weapons] == [
            "Helamite claws"
        ]

    def test_a_granted_weapon_offers_no_paid_ammo(self, fighter, granting_helamite):
        """A paid firing line is ammunition somebody bought, and nobody
        bought this: the card draws the lines that come with the gun and
        no others, and there is no assignment for an accessory or an ammo
        type to hang off."""
        buy(fighter, thing=granting_helamite, paid=45)
        weapon = next(
            w for w in card_for(fighter).weapons if w.name == "Helamite claws"
        )

        assert weapon.named_profiles == []
        assert weapon.id == ""
        assert weapon.total_rating == 0
