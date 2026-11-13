"""Spyrer equipment tiers are authored as single-pick augmentation choices.

Each item builds in a slot whose picklist contains its tiers. Each tier
declares all effects of that level, including effects retained from lower
levels. Modifiers target the named weapon or its wearer; trait swaps combine
removal and addition. Replacing a pick replaces those computed effects.

Manual tier changes move no credits or rating in these fixtures. Paid action
flows record their costs separately. Choices appear under their equipment,
follow unaugmented equipment between hosts, and disappear with the item.
Earned augmentations prevent reassignment even after choosing no tier.
The paired bolt launchers are represented by one weapon definition.
"""

from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment
from n26.core.operations import Refusal, operation
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card, option_key
from n26.library.authoring import is_one_of, targets_weapons
from n26.library.models import Stat, StatlineType, StatlineTypeStat
from n26.tests.sandbox.actions import (
    add_built_in,
    add_picklist_member,
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


@pytest.fixture
def weapon_statline_type(default_pack, fighter_stats):
    """Reuse the fighter statline's Strength definition in the weapon statline."""
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
    """Create a non-repeating slot type for item augmentation tiers."""
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
    """Create the paired bolt launchers as one weapon with a shared profile."""
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
    """Declare cumulative tiers targeting the bolt launchers.

    Tier 2 repeats Tier 1's change. Tier 3 repeats both stat changes and swaps
    Rapid Fire (1) for Rapid Fire (2). Each modifier receives its own scope.
    """

    def launchers():
        return targets_weapons(is_one_of(bolt_launchers))

    def lethal():
        return (launchers(), changes_stat(lethality, mode="set", amount=2))

    def piercing():
        return (launchers(), changes_stat(armour_piercing, mode="set", amount=-2))

    tiers = {
        "Tier 1": create_pickable(
            "Tier 1",
            augmentation,
            qualifier="Bolt launchers",
            summary="The launchers have Lethality 2.",
            effects=[lethal()],
        ),
        "Tier 2": create_pickable(
            "Tier 2",
            augmentation,
            qualifier="Bolt launchers",
            summary="The launchers have Lethality 2 and Armour Piercing −2.",
            effects=[lethal(), piercing()],
        ),
        "Tier 3": create_pickable(
            "Tier 3",
            augmentation,
            qualifier="Bolt launchers",
            summary="The launchers have Rapid Fire (2), Lethality 2 and Armour Piercing −2.",
            effects=[
                lethal(),
                piercing(),
                (launchers(), adds(traits["Rapid Fire (2)"])),
                (launchers(), removes(traits["Rapid Fire (1)"])),
            ],
        ),
    }
    table = create_picklist("Bolt launchers augmentations", augmentation)
    for level, pick in enumerate(tiers.values(), start=1):
        add_picklist_member(table, pick, level=level)
    slot = create_slot(
        "Bolt launchers augmentation",
        augmentation,
        table,
        label="Augmentation",
        introduction="Pick a tier for the bolt launchers.",
        mode="tier_ladder",
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
            summary="Strength +1 while carrying the rig.",
            effects=[strength()],
        ),
        "Tier 2": create_pickable(
            "Tier 2",
            augmentation,
            qualifier="Jakara hunting rig",
            summary="Strength +1 and Attacks +1 while carrying the rig.",
            effects=[strength(), attacks()],
        ),
    }
    table = create_picklist("Jakara hunting rig augmentations", augmentation)
    for level, pick in enumerate(tiers.values(), start=1):
        add_picklist_member(table, pick, level=level)
    slot = create_slot(
        "Jakara hunting rig augmentation",
        augmentation,
        table,
        label="Augmentation",
        introduction="Pick a tier for the Jakara hunting rig.",
        mode="tier_ladder",
        min_picks=0,
        max_picks=1,
    )
    add_built_in(rig, slot)
    return rig, tiers


@pytest.fixture
def spyrer(fighter_type, gang_type):
    """Create a Spyrer profile with characteristics modified by the hunting rig."""
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
    """Hire an Orrus and buy launchers, materialising their built-in tier slot."""
    model = hire(gang, spyrer, "Orrus", paid=200)
    buy(model, thing=bolt_launchers, paid=0)
    return model


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


@pytest.mark.parametrize("recruitment", [True, False])
def test_a_weapon_stat_names_its_tier_after_either_kind_of_augmentation(
    client,
    owner,
    gang,
    spyrer,
    bolt_launchers,
    bolt_launcher_tiers,
    augmentation,
    counter_tracking,
    recruitment,
):
    from uuid import uuid4

    from n26.core.operations import operation
    from n26.library import authoring as a

    kills = a.create_counter("Kill Count")
    outcome = a.create_outcome("Augment weapon", a.augment_carried_item(augmentation))
    action = a.create_action(
        "Recruitment augmentation" if recruitment else "Suit Evolution",
        "recruitment" if recruitment else "post_cycle",
        outcomes=[outcome],
        allowance_rule=a.recruitment_allowance_rule() if recruitment else None,
        use_price=[]
        if recruitment
        else [
            {"resource": "counter", "payer": "fighter", "counter": kills, "amount": 4}
        ],
    )
    a.add_built_in(spyrer, action)
    a.add_built_in(spyrer, kills)
    fighter = hire(gang, spyrer, "Hunt Master", paid=200)
    weapon = buy(fighter, thing=bolt_launchers, paid=0)
    with operation(gang, actor=owner) as op:
        balance = fighter.assignments.get(counter=kills, archived=False)
        op.tally(balance, 4)
        record = op.start_action(fighter, action, uuid4())
        record = op.review_action(
            record,
            outcome=outcome,
            terms={
                "item_assignment": str(weapon.pk),
                "intended_pick": str(bolt_launcher_tiers["Tier 1"].pk),
            },
        )
        op.complete_action(
            record, revision=record.revision, review=record.review, outcome=outcome
        )
    cell = gun_of(fighter, "Bolt launchers").profiles[0].statline.get("L")
    assert cell.value == "2"
    assert cell.modified
    assert "Tier 1" in cell.changed_by
    client.force_login(owner)
    html = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert "L changed by Tier 1" in html
    assert_reconciled(gang)


def choice_behind(miniature, item):
    """Find the computed choice anchored to a slot caused by this item assignment."""
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
    """Remove existing tier picks before choosing the replacement, as the picker does.

    The choose operation alone adds a pick without replacing the old selection.
    """
    for pick in ladder.picks:
        remove(pick.assignment)
    return choose(ladder.anchor.assignment, tier)


def climb(miniature, weapon_name, tier):
    return set_level(ladder_of(miniature, weapon_name), tier)


class TestTheLadderArrivesWithTheItem:
    """Show the built-in augmentation choice beneath its equipment without selecting a tier."""

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
        """An optional tier choice must not produce a missing-pick warning."""
        drawn, _ = card_for(orrus)
        assert drawn.remarks == []


class TestClimbingTheLadder:
    """Replace the single tier pick and apply its cumulative effects only to the named weapon."""

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
        assert gun.tier_mark == " (Tier 2)"
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
        assert (
            next(line for line in drawn.equipment if line.name == rig.name).tier_mark
            == " (Tier 2)"
        )
        assert stat_of(gun_of(orrus, "Bolt launchers"), "L") == "1"
        assert_reconciled(gang)

    def test_rungs_are_free(self, gang, orrus, bolt_launcher_tiers):
        """Manual changes between these zero-priced tiers move neither credits nor rating."""
        gang.refresh_from_db()
        credits_before, rating_before = gang.credits, gang.rating

        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 2"])

        gang.refresh_from_db()
        assert (gang.credits, gang.rating) == (credits_before, rating_before)
        assert_reconciled(gang)


class TestTheLadderIsTheModelsOwn:
    """Keep tier effects local to the carrying model and remove picks with their equipment."""

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
        """Move the built-in tier choice from stashed equipment onto its new carrier's card."""
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
        """Host an accessory's choice on its weapon's model and move it with the accessory."""
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
        # Display the accessory's tier choice under its weapon alongside the weapon's own choice.
        drawn, _ = card_for(other)
        gun = next(w for w in drawn.weapons if w.name == "Bolt launchers")
        assert sorted(c.chosen or "" for c in gun.choices) == ["", "Tier 1"]
        assert drawn.row_questions == []
        assert len(gun_of(orrus, "Bolt launchers").choices) == 1
        assert_reconciled(gang)

    def test_an_earned_tier_keeps_the_item_with_its_fighter(
        self, gang, orrus, bolt_launcher_tiers
    ):
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        launchers = orrus.assignments.get(weapon__isnull=False, archived=False)

        with pytest.raises(
            Refusal, match="earned augmentations that cannot be transferred"
        ):
            with operation(gang, actor=gang.owner) as op:
                op.reassign(launchers, gang.stash)
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
        """Replace the current tier with a lower tier without refunding credits."""
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
    """Each mirror shield tier declares its complete save and range effects.

    Replacing Tier 1 with Tier 3 removes the earlier 6+ save and applies the
    5+ save and longer range. No earlier tier remains selected.
    """

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


class TestAuthoredPickerCopy:
    """The picker shows the slot's introduction and each tier's summary."""

    def test_the_lead_and_tier_summary_come_from_the_author(
        self, client, owner, gang, orrus, bolt_launcher_tiers
    ):
        from n26.tests.fixtures import island_props

        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        ladder = ladder_of(orrus, "Bolt launchers")
        key = f"{orrus.pk}:{ladder.anchor.assignment.pk}:{ladder.identity.pk}"
        client.force_login(owner)

        response = client.get(reverse("n26-choose", args=[gang.pk, key]))
        page = response.content.decode()

        assert "Pick a tier for the bolt launchers." in page
        assert "The launchers have Lethality 2." in page
        assert "The carrier's" not in page
        tier = next(
            option
            for group in response.context["offer"].groups
            for option in group.options
            if option.name == "Tier 1"
        )
        assert tier.summary == "The launchers have Lethality 2."
        props = island_props(page, "choice-workflow")
        assert props["lead"] == "Pick a tier for the bolt launchers."
        option = next(
            option
            for group in props["offer"]["groups"]
            for option in group["options"]
            if option["key"] == tier.key
        )
        assert option["summary"] == tier.summary

    def test_an_empty_introduction_adds_no_generated_subhead(
        self, client, owner, gang, orrus, bolt_launcher_tiers
    ):
        from n26.library.models import Slot

        slot = Slot.objects.get(name="Bolt launchers augmentation")
        slot.introduction = ""
        slot.save(update_fields=["introduction"])
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        ladder = ladder_of(orrus, "Bolt launchers")
        key = f"{orrus.pk}:{ladder.anchor.assignment.pk}:{ladder.identity.pk}"
        client.force_login(owner)

        page = client.get(reverse("n26-choose", args=[gang.pk, key]))

        assert page.context["choice_props"]["lead"] == ""
        assert "Bolt launchers, for Orrus." not in page.content.decode()

    def test_the_unpicked_tier_does_not_add_a_line_to_the_roster(
        self, client, owner, gang, orrus, bolt_launcher_tiers
    ):
        from bs4 import BeautifulSoup

        client.force_login(owner)
        page = BeautifulSoup(
            client.get(reverse("n26-gang", args=[gang.pk])).content, "html.parser"
        )
        text = page.get_text(" ", strip=True)

        assert "Bolt launchers" in text
        assert "Augmentation: —" not in text

    def test_chosen_tiers_sit_beside_both_kinds_of_equipment(
        self, client, owner, gang, orrus, bolt_launcher_tiers, jakara_rig
    ):
        from bs4 import BeautifulSoup

        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 2"])
        rig, tiers = jakara_rig
        buy(orrus, thing=rig, paid=0)
        worn = Assignment.objects.get(miniature=orrus, wargear=rig, archived=False)
        set_level(choice_behind(orrus, worn), tiers["Tier 2"])
        client.force_login(owner)

        for url in (
            reverse("n26-gang", args=[gang.pk]),
            reverse("n26-edit-fighter", args=[orrus.pk]),
            reverse("n26-print", args=[gang.pk]),
        ):
            page = BeautifulSoup(client.get(url).content, "html.parser")
            text = page.get_text(" ", strip=True)
            assert "Bolt launchers (Tier 2)" in text
            assert "Jakara hunting rig (Tier 2)" in text
            assert "Augmentation: Tier 2" not in text
            assert "Jakara hunting rig augmentation: Tier 2" not in text
        edit = client.get(reverse("n26-edit-fighter", args=[orrus.pk])).content.decode()
        assert 'aria-label="More for Jakara hunting rig (Tier 2)"' in edit
        assert_reconciled(gang)


class TestManualTierChoices:
    """Owners can set any authored tier without running a paid action."""

    def picker(self, gang, orrus):
        ladder = ladder_of(orrus, "Bolt launchers")
        key = f"{orrus.pk}:{ladder.anchor.assignment.pk}:{ladder.identity.pk}"
        return reverse("n26-choose", args=[gang.pk, key])

    def test_an_empty_ladder_has_a_chooser_beside_dismiss(
        self, client, owner, gang, orrus, bolt_launcher_tiers
    ):
        client.force_login(owner)
        edit = reverse("n26-edit-fighter", args=[orrus.pk])

        page = client.get(edit).content.decode()

        assert self.picker(gang, orrus) in page
        assert "Choose tier" in page

    @pytest.mark.parametrize("starting_tier", [None, "Tier 1"])
    def test_every_tier_is_available_as_a_manual_choice(
        self, client, owner, gang, orrus, bolt_launcher_tiers, starting_tier
    ):
        from n26.core.models import ActionRecord, LedgerEvent

        if starting_tier:
            climb(orrus, "Bolt launchers", bolt_launcher_tiers[starting_tier])
        client.force_login(owner)
        picker = self.picker(gang, orrus)
        page = client.get(picker)
        assert page.status_code == 200
        for tier in bolt_launcher_tiers.values():
            assert option_key(tier) in page.content.decode()
        gang.refresh_from_db()
        before = (gang.rating, gang.credits)
        events_before = LedgerEvent.objects.filter(gang=gang).count()

        for tier_name in ("Tier 3", "Tier 1", "Tier 2"):
            assert (
                client.post(
                    picker,
                    {
                        "request_key": str(uuid4()),
                        "thing": option_key(bolt_launcher_tiers[tier_name]),
                    },
                ).status_code
                == 302
            )
            assert [c.chosen for c in gun_of(orrus, "Bolt launchers").choices] == [
                tier_name
            ]
            assert stat_of(gun_of(orrus, "Bolt launchers"), "L") == "2"
            assert stat_of(gun_of(orrus, "Bolt launchers"), "AP") == (
                "-1" if tier_name == "Tier 1" else "-2"
            )
            assert ("Rapid Fire (2)" in traits_of(gun_of(orrus, "Bolt launchers"))) == (
                tier_name == "Tier 3"
            )
        assert (
            client.post(
                picker, {"request_key": str(uuid4()), "thing": "none"}
            ).status_code
            == 302
        )
        assert stat_of(gun_of(orrus, "Bolt launchers"), "L") == "1"
        assert [c.chosen for c in gun_of(orrus, "Bolt launchers").choices] == [None]
        gang.refresh_from_db()
        assert (gang.rating, gang.credits) == before
        assert not ActionRecord.objects.filter(gang=gang).exists()
        assert LedgerEvent.objects.filter(gang=gang).count() > events_before
        assert_reconciled(gang)

    def test_a_rig_can_be_set_straight_to_its_highest_tier(
        self, client, owner, gang, orrus, jakara_rig
    ):
        rig, tiers = jakara_rig
        worn = buy(orrus, thing=rig, paid=0)
        ladder = choice_behind(orrus, worn)
        key = f"{orrus.pk}:{ladder.anchor.assignment.pk}:{ladder.identity.pk}"
        client.force_login(owner)
        picker = reverse("n26-choose", args=[gang.pk, key])
        assert (
            picker
            in client.get(reverse("n26-edit-fighter", args=[orrus.pk])).content.decode()
        )
        assert (
            client.post(
                picker,
                {"request_key": str(uuid4()), "thing": option_key(tiers["Tier 2"])},
            ).status_code
            == 302
        )
        drawn, _ = card_for(orrus)
        assert drawn.statline.get("S").value == "4"
        assert drawn.statline.get("A").value == "2"
        assert_reconciled(gang)

    def test_switching_to_an_unearned_tier_keeps_action_history(
        self, client, owner, gang, spyrer, orrus, bolt_launcher_tiers
    ):
        from uuid import uuid4

        from n26.core.models import ActionRecord, SlotSelection
        from n26.library.authoring import create_action

        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 2"])
        ladder = ladder_of(orrus, "Bolt launchers")
        action = create_action("Suit Evolution", "post_cycle")
        record = ActionRecord.objects.create(
            gang=gang,
            fighter=orrus,
            action=action,
            request_key=uuid4(),
            state=ActionRecord.State.COMPLETED,
        )
        SlotSelection.objects.create(
            action_record=record,
            item_assignment=ladder.anchor.assignment.caused_by,
            slot_assignment=ladder.anchor.assignment,
            intended_pick=bolt_launcher_tiers["Tier 2"],
            new_pick=ladder.picks[0].assignment,
        )
        client.force_login(owner)
        picker = self.picker(gang, orrus)
        assert (
            client.post(
                picker,
                {
                    "request_key": str(uuid4()),
                    "thing": option_key(bolt_launcher_tiers["Tier 3"]),
                },
            ).status_code
            == 302
        )
        assert [c.chosen for c in gun_of(orrus, "Bolt launchers").choices] == ["Tier 3"]

        assert (
            client.post(
                picker,
                {
                    "request_key": str(uuid4()),
                    "thing": option_key(bolt_launcher_tiers["Tier 1"]),
                },
            ).status_code
            == 302
        )
        assert stat_of(gun_of(orrus, "Bolt launchers"), "AP") == "-1"
        assert (
            client.post(
                picker,
                {
                    "request_key": str(uuid4()),
                    "thing": option_key(bolt_launcher_tiers["Tier 2"]),
                },
            ).status_code
            == 302
        )
        assert [c.chosen for c in gun_of(orrus, "Bolt launchers").choices] == ["Tier 2"]
        assert (
            ActionRecord.objects.get(pk=record.pk).state == ActionRecord.State.COMPLETED
        )
        assert (
            SlotSelection.objects.get(action_record=record).intended_pick
            == (bolt_launcher_tiers["Tier 2"])
        )
        other = hire(gang, spyrer, "Kaustos", paid=200)
        launchers = orrus.assignments.get(weapon__isnull=False, archived=False)
        assert (
            client.post(
                picker, {"request_key": str(uuid4()), "thing": "none"}
            ).status_code
            == 302
        )
        with pytest.raises(
            Refusal, match="earned augmentations that cannot be transferred"
        ):
            with operation(gang, actor=gang.owner) as op:
                op.reassign(launchers, other)
        assert (
            client.post(
                picker,
                {
                    "request_key": str(uuid4()),
                    "thing": option_key(bolt_launcher_tiers["Tier 2"]),
                },
            ).status_code
            == 302
        )
        assert [c.chosen for c in gun_of(orrus, "Bolt launchers").choices] == ["Tier 2"]
        assert_reconciled(gang)

    def test_a_tier_selected_before_actions_remains_available_after_choosing_none(
        self, client, owner, gang, orrus, bolt_launcher_tiers
    ):
        climb(orrus, "Bolt launchers", bolt_launcher_tiers["Tier 1"])
        client.force_login(owner)
        picker = self.picker(gang, orrus)

        assert (
            client.post(
                picker, {"request_key": str(uuid4()), "thing": "none"}
            ).status_code
            == 302
        )
        assert [c.chosen for c in gun_of(orrus, "Bolt launchers").choices] == [None]
        assert (
            picker
            in client.get(reverse("n26-edit-fighter", args=[orrus.pk])).content.decode()
        )
        assert (
            client.post(
                picker,
                {
                    "request_key": str(uuid4()),
                    "thing": option_key(bolt_launcher_tiers["Tier 1"]),
                },
            ).status_code
            == 302
        )
        assert [c.chosen for c in gun_of(orrus, "Bolt launchers").choices] == ["Tier 1"]
        assert_reconciled(gang)


class TestDismissingTheLadderFromTheSheet:
    """Dismiss an empty tier from Edit; restore it there without adding a roster line."""

    def key(self, orrus):
        ladder = ladder_of(orrus, "Bolt launchers")
        return f"{orrus.pk}:{ladder.anchor.assignment.pk}:{ladder.identity.pk}"

    def test_edit_offers_the_x_and_the_edit_grid_offers_restore(
        self, client, owner, gang, orrus, bolt_launcher_tiers
    ):
        client.force_login(owner)
        sheet = reverse("n26-gang", args=[gang.pk])
        edit = reverse("n26-edit-fighter", args=[orrus.pk])
        dismiss = reverse("n26-dismiss-offer", args=[gang.pk, self.key(orrus)])
        restore = reverse("n26-restore-offer", args=[gang.pk, self.key(orrus)])

        page = client.get(sheet).content.decode()
        assert "Augmentation: &mdash;" not in page
        assert dismiss not in page
        assert dismiss in client.get(edit).content.decode()

        reply = client.post(dismiss, {"request_key": str(uuid4())})
        assert reply.status_code == 302
        page = client.get(sheet).content.decode()
        assert "Augmentation:" not in page
        assert dismiss not in page

        page = client.get(f"{sheet}?dismissed=show").content.decode()
        assert "Augmentation:" not in page
        assert restore not in page
        assert restore in client.get(edit).content.decode()
        client.post(restore, {"request_key": str(uuid4()), "back": edit})
        assert dismiss in client.get(edit).content.decode()
        assert "Augmentation: &mdash;" not in client.get(sheet).content.decode()

    def test_choosing_a_tier_restores_a_dismissed_ladder(
        self, client, owner, gang, orrus, bolt_launcher_tiers
    ):
        from n26.core.models import DismissedOffer

        client.force_login(owner)
        key = self.key(orrus)
        client.post(
            reverse("n26-dismiss-offer", args=[gang.pk, key]),
            {"request_key": str(uuid4())},
        )
        assert DismissedOffer.objects.filter(gang=gang, slot_key=key).exists()

        reply = client.post(
            reverse("n26-choose", args=[gang.pk, key]),
            {
                "request_key": str(uuid4()),
                "thing": option_key(bolt_launcher_tiers["Tier 1"]),
            },
        )

        assert reply.status_code == 302
        assert [c.chosen for c in gun_of(orrus, "Bolt launchers").choices] == ["Tier 1"]
        assert not DismissedOffer.objects.filter(gang=gang, slot_key=key).exists()
        assert_reconciled(gang)
