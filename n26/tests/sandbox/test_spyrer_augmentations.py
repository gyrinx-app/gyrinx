"""Spyrer suit augmentations: an item's level, built from a slot and picks.

Every item a Spyrer carries prints its own augmentation tiers — a bolt
launcher's Tier 1 raises its Lethality, Tier 2 its Armour Piercing, Tier 3
swaps Rapid Fire (1) for Rapid Fire (2); a Jakara hunting rig's tiers
raise the wearer's Strength and then Attacks. An item has one augmentation
level, which Suit Evolution raises by one and a glitch can lower by one,
and a higher level keeps what the lower ones brought online.

This file states that the ladder is content, not code. Per item: one
picklist of an **Augmentation** slot type holding that item's tiers as
pickables, and one slot of a single pick built into the item, so the
choice appears on whoever carries it and goes when the item goes. The
level is the pick; each tier carries the whole effect of being at that
level, so Tier 2's modifiers restate Tier 1's — as the book's own
wording of "additional functions online" wants, and as the earlier
edition's content is written. Each modifier names the item outright
(``targets_weapons(is_one_of(...))``) or reaches the wearer
(``targets_model()``); a trait swap is a removal and an addition.

Rungs are free. What raises the Spyrer's credit value is the Power Boost
result that unlocked the tier, which is a pick of its own on the model.
So climbing, stepping back and switching move no credits and no rating
here, which is what lets a player change their mind: the app informs,
it does not police.

The choice draws under the weapon it belongs to, as the book prints the
tier beside the item, and never as a row about the model.

The Orrus carries two bolt launchers, printed as one line ("x2"), and the
book's augmentation is of the pair. They are one weapon here for the same
reason: a scope naming a weapon reaches every copy the model carries.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card, option_key
from n26.library.authoring import is_one_of, targets_weapons
from n26.library.models import Stat, StatlineType, StatlineTypeStat
from n26.tests.sandbox.actions import (
    add_built_in,
    adds,
    attach,
    buy,
    changes_stat,
    choose,
    create_gang_type,
    create_pickable,
    create_picklist,
    create_profile,
    create_rule,
    create_slot,
    create_slot_type,
    create_stat,
    create_trait,
    create_wargear,
    create_weapon,
    create_weapon_accessory,
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
    """The slot type. One level per item, so a choice of it takes one pick."""
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
    """Three levels, each naming the launchers outright and each carrying
    the whole of being at that level: Tier 2 restates Tier 1's change,
    Tier 3 restates both and swaps the trait. A scope belongs to one
    modifier, so each gets its own."""

    def launchers():
        return targets_weapons(is_one_of(bolt_launchers))

    def lethal():
        return (launchers(), changes_stat(lethality, mode="set", amount=2))

    def piercing():
        return (launchers(), changes_stat(armour_piercing, mode="set", amount=-2))

    tiers = {
        "Tier 1": create_pickable(
            "Tier 1", augmentation, qualifier="Bolt launchers", effects=[lethal()]
        ),
        "Tier 2": create_pickable(
            "Tier 2",
            augmentation,
            qualifier="Bolt launchers",
            effects=[lethal(), piercing()],
        ),
        "Tier 3": create_pickable(
            "Tier 3",
            augmentation,
            qualifier="Bolt launchers",
            effects=[
                lethal(),
                piercing(),
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
        label="Augmentation",
        min_picks=0,
        max_picks=1,
    )
    add_built_in(bolt_launchers, slot)
    return tiers


@pytest.fixture
def jakara_rig(augmentation, fighter_stats):
    """Wargear whose tiers reach the wearer rather than a weapon."""
    rig = create_wargear("Jakara hunting rig", price=0)

    def strength():
        return (
            targets_model(),
            changes_stat(fighter_stats["S"], mode="improve", amount=1),
        )

    def attacks():
        return (
            targets_model(),
            changes_stat(fighter_stats["A"], mode="improve", amount=1),
        )

    tiers = {
        "Tier 1": create_pickable(
            "Tier 1",
            augmentation,
            qualifier="Jakara hunting rig",
            effects=[strength()],
        ),
        "Tier 2": create_pickable(
            "Tier 2",
            augmentation,
            qualifier="Jakara hunting rig",
            effects=[strength(), attacks()],
        ),
    }
    table = create_picklist(
        "Jakara hunting rig augmentations", augmentation, members=list(tiers.values())
    )
    slot = create_slot(
        "Jakara hunting rig augmentation",
        augmentation,
        table,
        label="Augmentation",
        min_picks=0,
        max_picks=1,
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


def choice_behind(miniature, item):
    """The computed choice an item carries: the one whose anchor the
    item's assignment caused."""
    _, computed = card_for(miniature)
    return next(
        line for line in computed.choices if line.anchor.caused_by_key == item.pk
    )


def ladder_of(miniature, weapon_name):
    weapon = Assignment.objects.get(
        miniature=miniature, weapon__name=weapon_name, archived=False
    )
    return choice_behind(miniature, weapon)


def set_level(ladder, tier):
    """Take a tier on a one-pick choice, as the picker does: the pick
    held is taken back and the new one written. The verb alone writes a
    pick; replacing the standing one is the page's act."""
    for pick in ladder.picks:
        remove(pick.assignment)
    return choose(ladder.anchor.assignment, tier)


def climb(miniature, weapon_name, tier):
    return set_level(ladder_of(miniature, weapon_name), tier)


class TestTheLadderArrivesWithTheItem:
    """Carrying an augmentable item opens its augmentation choice on the
    carrier's card, drawn under the item. Nothing is written for the
    level: the line is computed, empty, and asks for nothing."""

    def test_the_launchers_bring_an_open_choice_under_the_weapon(self, orrus, gang):
        drawn, _ = card_for(orrus)
        gun = next(w for w in drawn.weapons if w.name == "Bolt launchers")

        (choice,) = gun.choices
        assert choice.kind_label == "Augmentation"
        assert not choice.is_resolved
        assert not choice.takes_several
        assert [line.kind_label for line in drawn.choices] == []
        assert drawn.questions == gun.choices
        assert_reconciled(gang)

    def test_a_model_without_the_item_has_no_ladder(
        self, gang, spyrer, bolt_launcher_tiers
    ):
        unarmed = hire(gang, spyrer, "Kaustos", paid=200)

        drawn, _ = card_for(unarmed)
        assert drawn.questions == []
        assert_reconciled(gang)

    def test_an_empty_ladder_leaves_no_remark(self, orrus):
        """A minimum of none: leaving it alone is not a shortfall."""
        drawn, _ = card_for(orrus)
        assert drawn.remarks == []


class TestClimbingTheLadder:
    """The level is one pick. Picking the next tier replaces the one held,
    and a tier carries everything below it, so the card at Tier 2 shows
    both changes. Every tier's effect lands on the launchers and on
    nothing else the Spyrer carries."""

    def test_tier_one_raises_lethality_and_nothing_else(
        self, gang, orrus, bolt_launcher_tiers
    ):
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])

        gun = gun_of(orrus, "Bolt launchers")
        assert stat_of(gun, "L") == "2"
        assert stat_of(gun, "AP") == "-1"
        assert traits_of(gun) == ["Rapid Fire (1)", "Sidearm"]
        assert [choice.chosen for choice in gun.choices] == ["Tier 1"]
        assert_reconciled(gang)

    def test_tier_two_replaces_tier_one_and_keeps_its_change(
        self, gang, orrus, bolt_launcher_tiers
    ):
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 2"])

        gun = gun_of(orrus, "Bolt launchers")
        assert stat_of(gun, "L") == "2"
        assert stat_of(gun, "AP") == "-2"
        assert [choice.chosen for choice in gun.choices] == ["Tier 2"]
        assert not Assignment.objects.filter(
            pickable=bolt_launcher_tiers["Tier 1"], archived=False
        ).exists()
        assert_reconciled(gang)

    def test_tier_three_swaps_the_trait(self, gang, orrus, bolt_launcher_tiers):
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 3"])

        gun = gun_of(orrus, "Bolt launchers")
        assert stat_of(gun, "L") == "2"
        assert stat_of(gun, "AP") == "-2"
        assert traits_of(gun) == ["Rapid Fire (2)", "Sidearm"]
        assert gun.choices[0].is_full
        assert_reconciled(gang)

    def test_the_rigs_tiers_reach_the_wearer(self, gang, orrus, jakara_rig):
        rig, tiers = jakara_rig
        buy(orrus, thing=rig, paid=0)
        drawn, _ = card_for(orrus)
        assert drawn.statline.get("S").value == "3"

        worn = Assignment.objects.get(miniature=orrus, wargear=rig, archived=False)
        set_level(choice_behind(orrus, worn), tiers["Tier 2"])

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
    Spyrer's launchers are untouched, the pick goes with the item, and a
    step back is an ordinary change that owes nobody anything."""

    def test_another_spyrers_launchers_are_untouched(
        self, gang, spyrer, orrus, bolt_launchers, bolt_launcher_tiers
    ):
        other = hire(gang, spyrer, "Kaustos", paid=200)
        buy(other, thing=bolt_launchers, paid=0)

        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])

        assert stat_of(gun_of(orrus, "Bolt launchers"), "L") == "2"
        assert stat_of(gun_of(other, "Bolt launchers"), "L") == "1"
        assert not gun_of(other, "Bolt launchers").choices[0].is_resolved
        assert_reconciled(gang)

    def test_a_ladder_bought_into_the_stash_follows_the_item_to_its_carrier(
        self, gang, spyrer, bolt_launchers, bolt_launcher_tiers
    ):
        """Kit may be bought unassigned. Its augmentation choice waits in
        the stash beside it, where nobody can climb it, and comes along
        when a model takes the item up."""
        model = hire(gang, spyrer, "Orrus", paid=200)
        stashed = buy(gang.stash, thing=bolt_launchers, paid=0)
        drawn, _ = card_for(model)
        assert drawn.questions == []

        move(stashed, model)

        assert not gun_of(model, "Bolt launchers").choices[0].is_resolved
        climb(model, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        assert stat_of(gun_of(model, "Bolt launchers"), "L") == "2"
        assert_reconciled(gang)

    def test_a_ladder_on_a_bolted_on_part_follows_it_between_guns(
        self, gang, spyrer, orrus, bolt_launchers, augmentation, lethality
    ):
        """A part bolted onto a gun has no host of its own — it hangs off
        the gun — so what it brings is hosted on the gun's model. Moving
        the part to another model's gun takes its ladder to that model."""
        sight = create_weapon_accessory("Targeting rig", price=0)
        tier = create_pickable(
            "Tier 1",
            augmentation,
            qualifier="Targeting rig",
            effects=[
                (
                    targets_weapons(is_one_of(bolt_launchers)),
                    changes_stat(lethality, mode="set", amount=3),
                )
            ],
        )
        table = create_picklist(
            "Targeting rig augmentations", augmentation, members=[tier]
        )
        add_built_in(
            sight,
            create_slot(
                "Targeting rig augmentation",
                augmentation,
                table,
                label="Augmentation",
                min_picks=0,
                max_picks=1,
            ),
        )
        other = hire(gang, spyrer, "Kaustos", paid=200)
        other_launchers = buy(other, thing=bolt_launchers, paid=0)
        launchers = orrus.assignments.get(weapon__isnull=False, archived=False)
        bolted = attach(launchers, sight, paid=0)
        assert choice_behind(orrus, bolted) is not None

        move(bolted, other_launchers)

        _, computed = card_for(orrus)
        assert not any(
            line.anchor.caused_by_key == bolted.pk for line in computed.choices
        )
        set_level(choice_behind(other, bolted), tier)
        assert stat_of(gun_of(other, "Bolt launchers"), "L") == "3"
        assert stat_of(gun_of(orrus, "Bolt launchers"), "L") == "1"
        # The part hangs off the gun, so its choice draws under the gun
        # beside the gun's own — and nowhere else on the card.
        drawn, _ = card_for(other)
        gun = next(w for w in drawn.weapons if w.name == "Bolt launchers")
        assert sorted(c.chosen or "" for c in gun.choices) == ["", "Tier 1"]
        assert drawn.row_questions == []
        assert len(gun_of(orrus, "Bolt launchers").choices) == 1
        assert_reconciled(gang)

    def test_a_climbed_ladder_goes_back_to_the_stash_with_the_item(
        self, gang, orrus, bolt_launcher_tiers
    ):
        """The other way: stashing the gun takes its level out of play and
        off the model's card, and it returns when the gun is taken up."""
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        launchers = orrus.assignments.get(weapon__isnull=False, archived=False)

        move(launchers, gang.stash)
        drawn, _ = card_for(orrus)
        assert drawn.questions == []

        move(launchers, orrus)
        assert stat_of(gun_of(orrus, "Bolt launchers"), "L") == "2"
        assert [c.chosen for c in gun_of(orrus, "Bolt launchers").choices] == ["Tier 1"]
        assert_reconciled(gang)

    def test_losing_the_item_takes_the_ladder_and_its_level(
        self, gang, orrus, bolt_launcher_tiers
    ):
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        launchers = orrus.assignments.get(weapon__isnull=False, archived=False)

        remove(launchers)

        drawn, _ = card_for(orrus)
        assert drawn.questions == []
        assert not Assignment.objects.filter(
            pickable=bolt_launcher_tiers["Tier 1"], archived=False
        ).exists()
        assert_reconciled(gang)

    def test_stepping_back_a_level_is_a_change_that_refunds_nothing(
        self, gang, orrus, bolt_launcher_tiers
    ):
        """A glitch can lower an item's level. The player picks the tier
        below, which replaces the one held; nothing was paid for either,
        so nothing comes back."""
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 2"])
        gang.refresh_from_db()
        credits_before = gang.credits

        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])

        gun = gun_of(orrus, "Bolt launchers")
        assert stat_of(gun, "AP") == "-1"
        assert stat_of(gun, "L") == "2"
        assert [c.chosen for c in gun.choices] == ["Tier 1"]
        gang.refresh_from_db()
        assert gang.credits == credits_before
        assert_reconciled(gang)


class TestALaterTierWinsOverAnEarlierOne:
    """The mirror shield's tiers: a 6+ field save at Tier 1, a longer range
    at Tier 2, a 5+ field save at Tier 3. Tier 3 changes what Tier 1
    changed. Because an item holds one level and each tier carries the
    whole of being at that level, Tier 3's author writes the 5+ save
    and the range and nothing about the 6+; when Tier 3 replaces the
    earlier level there is nothing left to arbitrate."""

    @pytest.fixture
    def mirror_shield(self, weapon_statline_type, augmentation, fighter_stats):
        shield = create_weapon(
            "Mirror shield", profiles=(("", 0),), statline_type=weapon_statline_type
        )
        (profile,) = shield.profiles.all()
        set_statline(
            profile,
            short_range=4,
            long_range=8,
            strength=3,
            armour_piercing=0,
            lethality=1,
        )
        long_range = weapon_statline_type.stats.get(stat__short_name="LR").stat
        save_6 = create_rule("Field armour save", annotation="6+")
        save_5 = create_rule("Field armour save", annotation="5+")

        def reach():
            return (
                targets_weapons(is_one_of(shield)),
                changes_stat(long_range, mode="set", amount=12),
            )

        tiers = {
            "Tier 1": create_pickable(
                "Tier 1",
                augmentation,
                qualifier="Mirror shield",
                effects=[(targets_model(), adds(save_6))],
            ),
            "Tier 2": create_pickable(
                "Tier 2",
                augmentation,
                qualifier="Mirror shield",
                effects=[(targets_model(), adds(save_6)), reach()],
            ),
            "Tier 3": create_pickable(
                "Tier 3",
                augmentation,
                qualifier="Mirror shield",
                effects=[(targets_model(), adds(save_5)), reach()],
            ),
        }
        table = create_picklist(
            "Mirror shield augmentations", augmentation, members=list(tiers.values())
        )
        add_built_in(
            shield,
            create_slot(
                "Mirror shield augmentation",
                augmentation,
                table,
                label="Augmentation",
                min_picks=0,
                max_picks=1,
            ),
        )
        return shield, tiers

    def rules_of(self, miniature):
        drawn, _ = card_for(miniature)
        return [line.name for line in drawn.rules]

    def test_tier_three_carries_the_better_save_and_not_the_earlier_one(
        self, gang, spyrer, mirror_shield
    ):
        shield, tiers = mirror_shield
        jakara = hire(gang, spyrer, "Jakara", paid=200)
        buy(jakara, thing=shield, paid=0)

        climb(jakara, "Mirror shield", tiers["Tier 1"])
        assert self.rules_of(jakara) == ["Field armour save (6+)"]
        assert stat_of(gun_of(jakara, "Mirror shield"), "LR") == '8"'

        climb(jakara, "Mirror shield", tiers["Tier 3"])
        assert self.rules_of(jakara) == ["Field armour save (5+)"]
        assert stat_of(gun_of(jakara, "Mirror shield"), "LR") == '12"'
        assert [c.chosen for c in gun_of(jakara, "Mirror shield").choices] == ["Tier 3"]
        assert_reconciled(gang)

    def test_stepping_back_to_tier_one_restores_the_earlier_save(
        self, gang, spyrer, mirror_shield
    ):
        shield, tiers = mirror_shield
        jakara = hire(gang, spyrer, "Jakara", paid=200)
        buy(jakara, thing=shield, paid=0)
        climb(jakara, "Mirror shield", tiers["Tier 3"])

        climb(jakara, "Mirror shield", tiers["Tier 1"])

        assert self.rules_of(jakara) == ["Field armour save (6+)"]
        assert stat_of(gun_of(jakara, "Mirror shield"), "LR") == '8"'
        assert_reconciled(gang)


class TestThePickerNamesTheItem:
    """Opened from the weapon's sub-row, the pick screen says which item
    the level is on as well as whose card it is."""

    def test_the_lead_names_the_launchers_and_the_bearer(
        self, client, owner, gang, orrus, bolt_launcher_tiers
    ):
        ladder = ladder_of(orrus, "Bolt launchers")
        key = f"{orrus.pk}:{ladder.anchor.assignment.pk}:{ladder.identity.pk}"
        client.force_login(owner)

        page = client.get(reverse("n26-choose", args=[gang.pk, key])).content.decode()

        assert "Bolt launchers, for Orrus." in page
        assert 'aria-label="Add Tier 1"' in page or "Tier 1" in page


class TestThePickerReturnsWhereItWasOpened:
    """A link from the model's own page carries that page's address, and
    settling the choice lands the reader back there. An address that is
    not this site's own falls back to the gang."""

    def picker(self, gang, orrus):
        ladder = ladder_of(orrus, "Bolt launchers")
        key = f"{orrus.pk}:{ladder.anchor.assignment.pk}:{ladder.identity.pk}"
        return reverse("n26-choose", args=[gang.pk, key])

    def test_the_edit_page_links_its_choice_with_its_own_address(
        self, client, owner, gang, orrus, bolt_launcher_tiers
    ):
        client.force_login(owner)
        edit = reverse("n26-edit-fighter", args=[orrus.pk])

        page = client.get(edit).content.decode()

        assert f"return={edit}" in page.replace("%2F", "/")

    def test_saving_from_the_edit_page_lands_back_on_it(
        self, client, owner, gang, orrus, bolt_launcher_tiers
    ):
        client.force_login(owner)
        edit = reverse("n26-edit-fighter", args=[orrus.pk])
        picker = self.picker(gang, orrus)

        page = client.get(f"{picker}?return={edit}").content.decode()
        assert f'name="return" value="{edit}"' in page

        reply = client.post(
            picker,
            {"thing": option_key(bolt_launcher_tiers["Tier 2"]), "return": edit},
        )

        assert reply.status_code == 302
        assert reply.url == edit
        assert [c.chosen for c in gun_of(orrus, "Bolt launchers").choices] == ["Tier 2"]

    def test_an_address_that_is_not_ours_falls_back_to_the_gang(
        self, client, owner, gang, orrus, bolt_launcher_tiers
    ):
        client.force_login(owner)
        picker = self.picker(gang, orrus)

        reply = client.post(
            picker,
            {
                "thing": option_key(bolt_launcher_tiers["Tier 1"]),
                "return": "https://elsewhere.example/steal",
            },
        )

        assert reply.status_code == 302
        assert reply.url == reverse("n26-gang", args=[gang.pk])
