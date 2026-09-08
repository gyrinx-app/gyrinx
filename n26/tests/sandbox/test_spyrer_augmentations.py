"""Spyrer suit augmentations: a tier ladder built from slots and picks.

Every item a Spyrer carries prints its own augmentation tiers — a bolt
launcher's Tier 1 raises its Lethality, Tier 2 its Armour Piercing, Tier 3
swaps Rapid Fire (1) for Rapid Fire (2); a Jakara hunting rig's tiers
raise the wearer's Strength and then Attacks. Tiers are gained one at a
time through Suit Evolution and stack: an item at Tier 2 has both its
first and second tier working.

This file states that the ladder is content, not code. Per item: one
picklist of an **Augmentation** slot type holding that item's tiers as
pickables, and one slot built into the item, so the choice appears on
whoever carries it and goes when the item goes. A level is one pick per
rung, and the level is the count of live picks — never stored. Each tier
carries its effect as ordinary modifiers that name the item outright
(``targets_weapons(is_one_of(...))``) or reach the wearer
(``targets_model()``); a trait swap is a removal and an addition.

Rungs are free. What raises the Spyrer's credit value is the Power Boost
result that unlocked the tier, which is a pick of its own on the model.
So climbing, stepping back and switching move no credits and no rating
here, which is what lets a player change their mind: the app informs,
it does not police.

The Orrus carries two bolt launchers, printed as one line ("x2"), and the
book's augmentation is of the pair. They are one weapon here for the same
reason: a scope naming a weapon reaches every copy the model carries.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.library.authoring import is_one_of, targets_weapons
from n26.library.models import Stat, StatlineType, StatlineTypeStat
from n26.tests.sandbox.actions import (
    add_built_in,
    adds,
    buy,
    changes_stat,
    choose,
    create_gang_type,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    create_stat,
    create_trait,
    create_wargear,
    create_weapon,
    found_gang,
    hire,
    move,
    remove,
    removes,
    set_statline,
    targets_model,
)

pytestmark = pytest.mark.django_db

#: The printed weapon profile, minus traits and pricing. AP is inverted:
#: improving it means a lower number, so -1 improved by one is -2.
WEAPON_STATS = [
    ("SR", "Short Range", {"is_inches": True}),
    ("LR", "Long Range", {"is_inches": True}),
    ("Str", "Strength", {}),
    ("AP", "Armour Piercing", {"is_inverted": True}),
    ("L", "Lethality", {}),
]


# --- The content: an Orrus's bolt launchers and a Jakara's rig ----------------


@pytest.fixture
def weapon_statline_type(default_pack, fighter_stats):
    """Strength is one definition shared with the fighter's statline, so
    the weapon shape reuses it rather than defining a second."""
    statline_type = StatlineType.objects.create(name="Weapon")
    for position, (short, full, flags) in enumerate(WEAPON_STATS):
        stat = Stat.objects.filter(full_name=full).first() or create_stat(
            short, full, **flags
        )
        StatlineTypeStat.objects.create(
            statline_type=statline_type,
            stat=stat,
            position=position,
            is_first_of_group=(position == 0),
        )
    return statline_type


@pytest.fixture
def gang_type(default_pack):
    return create_gang_type("Spyre Hunting Party", starting_credits=1000)


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def gang(owner, gang_type):
    return found_gang("The Descent", gang_type, owner=owner, budget=1000)


@pytest.fixture
def augmentation(default_pack):
    """The slot type. Each tier is its own pickable, so repeats are never
    wanted: Tier 1 is taken once."""
    return create_slot_type(
        "Augmentation", plural_name="Augmentations", allows_repeats=False
    )


@pytest.fixture
def lethality(weapon_statline_type):
    return weapon_statline_type.stats.get(stat__short_name="L").stat


@pytest.fixture
def armour_piercing(weapon_statline_type):
    return weapon_statline_type.stats.get(stat__short_name="AP").stat


@pytest.fixture
def traits(default_pack):
    return {
        "Rapid Fire (1)": create_trait("Rapid Fire", annotation="1"),
        "Rapid Fire (2)": create_trait("Rapid Fire", annotation="2"),
        "Sidearm": create_trait("Sidearm"),
    }


@pytest.fixture
def bolt_launchers(weapon_statline_type, traits):
    """The Orrus's paired bolt launchers, as the book prints them."""
    weapon = create_weapon(
        "Bolt launchers", profiles=(("", 0),), statline_type=weapon_statline_type
    )
    (profile,) = weapon.profiles.all()
    set_statline(
        profile,
        short_range=8,
        long_range=20,
        strength=4,
        armour_piercing=-1,
        lethality=1,
    )
    profile.traits.set([traits["Rapid Fire (1)"], traits["Sidearm"]])
    return weapon


@pytest.fixture
def bolt_launcher_tiers(
    bolt_launchers, augmentation, lethality, armour_piercing, traits
):
    """Three rungs, each naming the launchers outright. The third is a
    swap, so it is two modifiers: take Rapid Fire (1) off, put Rapid
    Fire (2) on. A scope belongs to one modifier, so each gets its own."""

    def launchers():
        return targets_weapons(is_one_of(bolt_launchers))

    tiers = {
        "Tier 1": create_pickable(
            "Tier 1",
            augmentation,
            qualifier="Bolt launchers",
            effects=[(launchers(), changes_stat(lethality, mode="set", amount=2))],
        ),
        "Tier 2": create_pickable(
            "Tier 2",
            augmentation,
            qualifier="Bolt launchers",
            effects=[
                (launchers(), changes_stat(armour_piercing, mode="set", amount=-2))
            ],
        ),
        "Tier 3": create_pickable(
            "Tier 3",
            augmentation,
            qualifier="Bolt launchers",
            effects=[
                (launchers(), adds(traits["Rapid Fire (2)"])),
                (launchers(), removes(traits["Rapid Fire (1)"])),
            ],
        ),
    }
    table = create_picklist(
        "Bolt launchers augmentations", augmentation, members=list(tiers.values())
    )
    slot = create_slot(
        "Bolt launchers augmentation",
        augmentation,
        table,
        label="Bolt launchers",
        min_picks=0,
        max_picks=3,
    )
    add_built_in(bolt_launchers, slot)
    return tiers


@pytest.fixture
def jakara_rig(augmentation, fighter_stats):
    """Wargear whose tiers reach the wearer rather than a weapon."""
    rig = create_wargear("Jakara hunting rig", price=0)
    tiers = {
        "Tier 1": create_pickable(
            "Tier 1",
            augmentation,
            qualifier="Jakara hunting rig",
            effects=[
                (
                    targets_model(),
                    changes_stat(fighter_stats["S"], mode="improve", amount=1),
                )
            ],
        ),
        "Tier 2": create_pickable(
            "Tier 2",
            augmentation,
            qualifier="Jakara hunting rig",
            effects=[
                (
                    targets_model(),
                    changes_stat(fighter_stats["A"], mode="improve", amount=1),
                )
            ],
        ),
    }
    table = create_picklist(
        "Jakara hunting rig augmentations", augmentation, members=list(tiers.values())
    )
    slot = create_slot(
        "Jakara hunting rig augmentation",
        augmentation,
        table,
        label="Jakara hunting rig",
        min_picks=0,
        max_picks=2,
    )
    add_built_in(rig, slot)
    return rig, tiers


@pytest.fixture
def spyrer(fighter_type, gang_type):
    """A Spyrer profile with the statline the rig's tiers move."""
    profile = create_profile("Spyrer", fighter_type, gang_type, price=200)
    set_statline(
        profile,
        movement=5,
        weapon_skill=3,
        ballistic_skill=3,
        strength=3,
        toughness=3,
        wounds=2,
        initiative=3,
        attacks=1,
        save=4,
        leadership=6,
        cool=6,
        willpower=6,
        intelligence=6,
    )
    return profile


@pytest.fixture
def orrus(gang, spyrer, bolt_launchers, bolt_launcher_tiers):
    """An Orrus hired and armed. The launchers bring their ladder: a
    purchase materialises what the weapon has built in, and a slot is
    one of those things."""
    model = hire(gang, spyrer, "Orrus", paid=200)
    buy(model, thing=bolt_launchers, paid=0)
    return model


# --- Reading the card -----------------------------------------------------------


def card_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    computed = compute(card, index)
    return build_model_card(miniature, card=card, computed=computed), computed


def gun_of(miniature, name):
    drawn, _ = card_for(miniature)
    return next(weapon for weapon in drawn.weapons if weapon.name == name)


def stat_of(weapon, short_name):
    return weapon.profiles[0].statline.get(short_name).value


def traits_of(weapon):
    return [trait.name for trait in weapon.profiles[0].traits]


def ladder_of(miniature, label):
    """The computed choice for one item's augmentations."""
    _, computed = card_for(miniature)
    return next(line for line in computed.choices if line.kind_label == label)


def climb(miniature, label, tier):
    return choose(ladder_of(miniature, label).anchor.assignment, tier)


class TestTheLadderArrivesWithTheItem:
    """Carrying an augmentable item opens its augmentation choice on the
    carrier's card. Nothing is written for the rungs: the line is
    computed, empty, and asks for nothing."""

    def test_the_launchers_bring_an_open_choice(self, orrus, gang):
        ladder = ladder_of(orrus, "Bolt launchers")

        assert not ladder.is_resolved
        assert (ladder.min_picks, ladder.max_picks) == (0, 3)
        assert_reconciled(gang)

    def test_a_model_without_the_item_has_no_ladder(
        self, gang, spyrer, bolt_launcher_tiers
    ):
        unarmed = hire(gang, spyrer, "Kaustos", paid=200)

        _, computed = card_for(unarmed)
        assert [line.kind_label for line in computed.choices] == []
        assert_reconciled(gang)

    def test_an_empty_ladder_leaves_no_remark(self, orrus):
        """A minimum of none: leaving it alone is not a shortfall."""
        drawn, _ = card_for(orrus)
        assert drawn.remarks == []


class TestClimbingTheLadder:
    """Each rung is a pick, and the picks stack: the level is how many
    the model holds. Every tier's effect lands on the launchers and on
    nothing else the Spyrer carries."""

    def test_tier_one_raises_lethality_and_nothing_else(
        self, orrus, bolt_launcher_tiers
    ):
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])

        gun = gun_of(orrus, "Bolt launchers")
        assert stat_of(gun, "L") == "2"
        assert stat_of(gun, "AP") == "-1"
        assert traits_of(gun) == ["Rapid Fire (1)", "Sidearm"]

    def test_tier_two_stacks_on_tier_one(self, orrus, bolt_launcher_tiers):
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 2"])

        gun = gun_of(orrus, "Bolt launchers")
        assert stat_of(gun, "L") == "2"
        assert stat_of(gun, "AP") == "-2"
        ladder = ladder_of(orrus, "Bolt launchers")
        assert len(ladder.picks) == 2
        assert ladder.chosen_name == "Tier 1, Tier 2"

    def test_tier_three_swaps_the_trait(self, orrus, bolt_launcher_tiers):
        for tier in ("Tier 1", "Tier 2", "Tier 3"):
            climb(orrus, "Bolt launchers", bolt_launcher_tiers[tier])

        gun = gun_of(orrus, "Bolt launchers")
        assert traits_of(gun) == ["Rapid Fire (2)", "Sidearm"]
        assert ladder_of(orrus, "Bolt launchers").is_full

    def test_the_rigs_tiers_reach_the_wearer(self, gang, orrus, jakara_rig):
        rig, tiers = jakara_rig
        buy(orrus, thing=rig, paid=0)
        drawn, _ = card_for(orrus)
        assert drawn.statline.get("S").value == "3"

        climb(orrus, "Jakara hunting rig", tiers["Tier 1"])
        climb(orrus, "Jakara hunting rig", tiers["Tier 2"])

        drawn, _ = card_for(orrus)
        assert drawn.statline.get("S").value == "4"
        assert drawn.statline.get("A").value == "2"
        assert stat_of(gun_of(orrus, "Bolt launchers"), "L") == "1"
        assert_reconciled(gang)

    def test_rungs_are_free(self, gang, orrus, bolt_launcher_tiers):
        """The credit value of an augmentation rides the Power Boost that
        unlocked it, not the rung, so climbing moves neither credits nor
        rating."""
        gang.refresh_from_db()
        credits_before, rating_before = gang.credits, gang.rating

        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 2"])

        gang.refresh_from_db()
        assert (gang.credits, gang.rating) == (credits_before, rating_before)
        assert_reconciled(gang)


class TestTheLadderIsTheModelsOwn:
    """A tier is a pick on one model, about that model's item. Another
    Spyrer's launchers are untouched, the picks go with the item, and a
    step back is an ordinary removal that owes nobody anything."""

    def test_another_spyrers_launchers_are_untouched(
        self, gang, spyrer, orrus, bolt_launchers, bolt_launcher_tiers
    ):
        other = hire(gang, spyrer, "Kaustos", paid=200)
        buy(other, thing=bolt_launchers, paid=0)

        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])

        assert stat_of(gun_of(orrus, "Bolt launchers"), "L") == "2"
        assert stat_of(gun_of(other, "Bolt launchers"), "L") == "1"
        assert not ladder_of(other, "Bolt launchers").is_resolved
        assert_reconciled(gang)

    def test_a_ladder_bought_into_the_stash_follows_the_item_to_its_carrier(
        self, gang, spyrer, bolt_launchers, bolt_launcher_tiers
    ):
        """Kit may be bought unassigned. Its augmentation choice waits in
        the stash beside it, where nobody can climb it, and comes along
        when a model takes the item up."""
        model = hire(gang, spyrer, "Orrus", paid=200)
        stashed = buy(gang.stash, thing=bolt_launchers, paid=0)
        _, computed = card_for(model)
        assert [line.kind_label for line in computed.choices] == []

        move(stashed, model)

        assert not ladder_of(model, "Bolt launchers").is_resolved
        climb(model, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        assert stat_of(gun_of(model, "Bolt launchers"), "L") == "2"
        assert_reconciled(gang)

    def test_a_climbed_ladder_goes_back_to_the_stash_with_the_item(
        self, gang, orrus, bolt_launcher_tiers
    ):
        """The other way: stashing the gun takes its rungs out of play
        and off the model's card, and they return when it is taken up."""
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        launchers = orrus.assignments.get(weapon__isnull=False, archived=False)

        move(launchers, gang.stash)
        _, computed = card_for(orrus)
        assert [line.kind_label for line in computed.choices] == []

        move(launchers, orrus)
        assert stat_of(gun_of(orrus, "Bolt launchers"), "L") == "2"
        assert len(ladder_of(orrus, "Bolt launchers").picks) == 1
        assert_reconciled(gang)

    def test_losing_the_item_takes_the_ladder_and_its_rungs(
        self, gang, orrus, bolt_launcher_tiers
    ):
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        launchers = orrus.assignments.get(weapon__isnull=False, archived=False)

        remove(launchers)

        _, computed = card_for(orrus)
        assert [line.kind_label for line in computed.choices] == []
        assert not Assignment.objects.filter(
            pickable=bolt_launcher_tiers["Tier 1"], archived=False
        ).exists()
        assert_reconciled(gang)

    def test_stepping_back_a_rung_is_a_removal_that_refunds_nothing(
        self, gang, orrus, bolt_launcher_tiers
    ):
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        second = climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 2"])
        gang.refresh_from_db()
        credits_before = gang.credits

        remove(second)

        gun = gun_of(orrus, "Bolt launchers")
        assert stat_of(gun, "AP") == "-1"
        assert stat_of(gun, "L") == "2"
        assert len(ladder_of(orrus, "Bolt launchers").picks) == 1
        gang.refresh_from_db()
        assert gang.credits == credits_before
        assert_reconciled(gang)
