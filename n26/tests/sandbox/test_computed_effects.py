"""Computed effects: Mounted, Eye Injury, Backstab.

Modifiers are never stored player-side. A card is loaded, ``compute`` works
out what the modifiers say, and the card renders the result. Remove the
thing carrying the modifier and the effect simply stops appearing — there
is nothing to clean up.
"""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.render import build_model_card
from n26.core.render_text import render_model_card
from n26.library.models import Profile, ProfileType, StatlineType, StatlineTypeStat
from n26.tests.sandbox.actions import (
    adds,
    assign,
    changes_stat,
    create_skill,
    create_stat,
    create_subtype,
    create_trait,
    create_wargear,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    modifier,
    remove,
    removes,
    set_statline,
    targets_gang,
    targets_model,
    targets_weapons,
)
from n26.tests.sandbox.test_render import FIGHTER_STATS

pytestmark = pytest.mark.django_db


@pytest.fixture
def stats(db):
    return {
        full: create_stat(short, full, **flags)
        for short, full, flags, _, _ in FIGHTER_STATS
    }


@pytest.fixture
def fighter_type(stats):
    shape = StatlineType.objects.create(name="Fighter")
    for position, (_, full, _flags, first, highlighted) in enumerate(FIGHTER_STATS):
        StatlineTypeStat.objects.create(
            statline_type=shape,
            stat=stats[full],
            position=position,
            is_first_of_group=first,
            is_highlighted=highlighted,
        )
    return ProfileType.objects.create(name="Fighter", statline_type=shape)


@pytest.fixture
def ganger_profile(fighter_type, gang_type):
    profile = Profile.objects.create(
        name="Escher Ganger", profile_type=fighter_type, gang_type=gang_type, price=55
    )
    set_statline(
        profile,
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
        willpower=6,
        intelligence=6,
    )
    return profile


@pytest.fixture
def yolanda(ganger_profile, gang_type):
    player = User.objects.create_user("player")
    gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
    return hire(gang, ganger_profile, "Yolanda", paid=55)


def card_for(miniature, with_effects=True):
    card = build_card(miniature, with_statlines=True)
    if not with_effects:
        return build_model_card(miniature, card=card)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


class TestMounted:
    """A mount grants a subtype, which itself grants two skills."""

    @pytest.fixture
    def mount(self, db):
        mounted = create_subtype("Mounted")
        agile = create_subtype("Agile")
        for skill_name in ["Nerves of Steel", "Hit & Run"]:
            modifier(
                f"Mounted grants {skill_name}",
                targets_model(),
                adds(create_skill(skill_name)),
                carried_by=mounted,
            )
        cutter = create_wargear("Cutter")
        modifier(
            "Cutter grants Mounted", targets_model(), adds(mounted), carried_by=cutter
        )
        modifier("Cutter grants Agile", targets_model(), adds(agile), carried_by=cutter)
        return cutter

    def test_without_the_mount_the_fighter_is_plain(self, yolanda):
        card = card_for(yolanda)
        assert card.type_line == "Fighter"
        assert card.skills == []

    def test_buying_the_mount_grants_the_subtypes(self, yolanda, mount):
        assign(mount, miniature=yolanda, paid=75)
        card = card_for(yolanda)
        assert card.type_line == "Fighter (Agile, Mounted)"

    def test_the_chain_reaches_the_skills(self, yolanda, mount):
        """Cutter grants Mounted grants two skills — depth two."""
        assign(mount, miniature=yolanda, paid=75)
        card = card_for(yolanda)
        assert [s.name for s in card.skills] == ["Hit & Run", "Nerves of Steel"]

    def test_every_line_says_where_it_came_from(self, yolanda, mount):
        """Provenance is data on the line itself, never a display string."""
        assign(mount, miniature=yolanda, paid=75)
        card = card_for(yolanda)

        lines = {line.name: line.provenance for line in card.skills + card.subtypes}
        assert lines["Mounted"].source == "Cutter"
        assert lines["Mounted"].source_kind == "wargear"
        assert lines["Mounted"].computed is True
        assert lines["Agile"].source == "Cutter"
        assert lines["Hit & Run"].source == "Mounted"
        assert lines["Hit & Run"].source_kind == "subtype"
        assert lines["Nerves of Steel"].source == "Mounted"
        # Computed things were never paid for, so they carry no reason.
        assert lines["Mounted"].reason is None

    def test_a_stored_line_carries_its_ledger_reason(self, yolanda, mount):
        assign(mount, miniature=yolanda, paid=75)
        card = card_for(yolanda)
        (cutter,) = card.equipment
        assert cutter.provenance.reason == "bought"
        assert cutter.provenance.source is None  # taken directly
        assert cutter.provenance.computed is False

    def test_nothing_is_stored(self, yolanda, mount):
        from n26.core.models import Assignment

        assign(mount, miniature=yolanda, paid=75)
        card_for(yolanda)
        # The hire and the Cutter. Not the subtypes, not the skills.
        assert (
            Assignment.objects.filter(archived=False, gang_type__isnull=True).count()
            == 2
        )

    def test_selling_the_mount_takes_it_all_away(self, yolanda, mount):
        assignment = assign(mount, miniature=yolanda, paid=75)
        assert [s.name for s in card_for(yolanda).skills] == [
            "Hit & Run",
            "Nerves of Steel",
        ]

        remove(assignment)

        card = card_for(yolanda)
        assert card.type_line == "Fighter"
        assert card.skills == []


class TestGrantedPower:
    """A power a modifier grants — the psyker entry whose sheet says it
    starts knowing one. A fact on the card while the granter stands,
    filed in the Powers row where a learned power would sit."""

    @pytest.fixture
    def haunted_mask(self, db):
        from n26.tests.sandbox.actions import create_category, create_power

        family = create_category("Powers", "Whispers")
        crush = create_power("Crush", category=family)
        mask = create_wargear("Haunted Mask")
        modifier(
            "The mask knows Crush",
            targets_model(),
            adds(crush),
            carried_by=mask,
        )
        return mask

    def test_the_power_lands_in_the_powers_row(self, yolanda, haunted_mask):
        assign(haunted_mask, miniature=yolanda, paid=0)
        card = card_for(yolanda)
        assert [p.name for p in card.powers] == ["Crush"]

    def test_the_line_says_where_it_came_from(self, yolanda, haunted_mask):
        assign(haunted_mask, miniature=yolanda, paid=0)
        (line,) = card_for(yolanda).powers
        assert line.provenance.source == "Haunted Mask"
        assert line.provenance.computed is True

    def test_removing_the_granter_takes_the_power(self, yolanda, haunted_mask):
        carried = assign(haunted_mask, miniature=yolanda, paid=0)
        remove(carried)
        assert card_for(yolanda).powers == []


class TestEyeInjury:
    """A stat change, direction-aware, and a bionic that undoes it."""

    @pytest.fixture
    def eye_injury(self, stats):
        injury = create_wargear("Eye Injury")
        modifier(
            "Eye Injury worsens BS",
            targets_model(),
            changes_stat(stats["Ballistic Skill"], mode="worsen", amount=1),
            carried_by=injury,
        )
        return injury

    @pytest.fixture
    def bionic_eye(self, stats):
        bionic = create_wargear("Bionic Eye")
        modifier(
            "Bionic Eye improves BS",
            targets_model(),
            changes_stat(stats["Ballistic Skill"], mode="improve", amount=1),
            carried_by=bionic,
        )
        return bionic

    def test_worsening_a_roll_target_raises_it(self, yolanda, eye_injury):
        assert card_for(yolanda).statline.get("BS").value == "4+"
        assign(eye_injury, miniature=yolanda)
        assert card_for(yolanda).statline.get("BS").value == "5+"

    def test_the_cell_records_what_changed_it(self, yolanda, eye_injury):
        assign(eye_injury, miniature=yolanda)
        cell = card_for(yolanda).statline.get("BS")
        assert cell.modified is True
        (change,) = cell.modified_by
        assert change.source == "Eye Injury"
        assert change.source_kind == "wargear"
        assert change.computed is True

    def test_other_stats_are_untouched(self, yolanda, eye_injury):
        assign(eye_injury, miniature=yolanda)
        statline = card_for(yolanda).statline
        assert statline.get("WS").value == "4+"
        assert statline.get("WS").modified is False

    def test_a_bionic_cancels_it_out(self, yolanda, eye_injury, bionic_eye):
        """Permanent by persistence: nothing was ever edited, so they sum."""
        assign(eye_injury, miniature=yolanda)
        assign(bionic_eye, miniature=yolanda, paid=45)
        cell = card_for(yolanda).statline.get("BS")
        assert cell.value == "4+"
        assert sorted(p.source for p in cell.modified_by) == [
            "Bionic Eye",
            "Eye Injury",
        ]

    def test_worsening_a_plain_number_lowers_it(self, yolanda, stats):
        crippling = create_wargear("Old Wound")
        modifier(
            "Old Wound worsens Movement",
            targets_model(),
            changes_stat(stats["Movement"], mode="worsen", amount=1),
            carried_by=crippling,
        )
        assert card_for(yolanda).statline.get("M").value == '5"'
        assign(crippling, miniature=yolanda)
        assert card_for(yolanda).statline.get("M").value == '4"'


class TestBackstab:
    """A skill that adds a trait to every weapon matching a trait filter."""

    @pytest.fixture
    def weapons(self, db):
        melee = create_trait("Melee")
        self.melee = melee
        knife = create_weapon("Stiletto knife", profiles=[("Blade", 0, [melee])])
        gun = create_weapon("Lasgun", profiles=[("Las bolt", 0)])
        return knife, gun

    @pytest.fixture
    def backstab(self, weapons):
        skill = create_skill("Backstab")
        modifier(
            "Backstab arms Melee weapons",
            targets_weapons(with_trait=self.melee),
            adds(create_trait("Backstab")),
            carried_by=skill,
        )
        return skill

    def test_only_the_melee_weapon_gains_it(self, yolanda, weapons, backstab):
        knife, gun = weapons
        give_weapon(yolanda, knife, paid=20)
        give_weapon(yolanda, gun, paid=15)
        assign(backstab, miniature=yolanda)

        by_weapon = {w.name: w.profiles[0] for w in card_for(yolanda).weapons}
        knife_traits = [t.name for t in by_weapon["Stiletto knife"].traits]
        assert knife_traits == ["Backstab", "Melee"]
        assert by_weapon["Lasgun"].traits == []

    def test_the_added_trait_carries_computed_provenance(
        self, yolanda, weapons, backstab
    ):
        knife, _ = weapons
        give_weapon(yolanda, knife, paid=20)
        assign(backstab, miniature=yolanda)

        traits = {t.name: t for t in card_for(yolanda).weapons[0].profiles[0].traits}
        assert traits["Backstab"].provenance.computed is True
        assert traits["Backstab"].provenance.source == "Backstab"
        assert traits["Backstab"].provenance.source_kind == "skill"
        # The printed trait came with the weapon: empty provenance.
        assert traits["Melee"].provenance.computed is False
        assert traits["Melee"].provenance.source is None

    def test_without_the_skill_nothing_is_added(self, yolanda, weapons):
        knife, _ = weapons
        give_weapon(yolanda, knife, paid=20)
        traits = card_for(yolanda).weapons[0].profiles[0].traits
        assert [t.name for t in traits] == ["Melee"]

    def test_an_unfiltered_scope_reaches_every_weapon(self, yolanda, weapons):
        knife, gun = weapons
        give_weapon(yolanda, knife, paid=20)
        give_weapon(yolanda, gun, paid=15)
        blessed = create_skill("Blessed Arms")
        modifier(
            "Blessed Arms blesses everything",
            targets_weapons(),
            adds(create_trait("Blessed")),
            carried_by=blessed,
        )
        assign(blessed, miniature=yolanda)

        for weapon in card_for(yolanda).weapons:
            assert "Blessed" in [t.name for t in weapon.profiles[0].traits]


class TestRemoval:
    def test_a_removes_modifier_beats_an_adds(self, yolanda):
        """Death of a Leader's subtype losses: removes always win."""
        ganger = create_subtype("Ganger")
        source = create_wargear("Promotion papers")
        modifier("Grants Ganger", targets_model(), adds(ganger), carried_by=source)
        assign(source, miniature=yolanda)
        assert card_for(yolanda).type_line == "Fighter (Ganger)"

        stripper = create_wargear("Leader's mantle")
        modifier("Strips Ganger", targets_model(), removes(ganger), carried_by=stripper)
        assign(stripper, miniature=yolanda)
        assert card_for(yolanda).type_line == "Fighter"

    def test_a_removes_modifier_takes_back_a_granted_weapon(self, yolanda):
        claws = create_weapon("Claws", profiles=[("", 0)])
        beast = create_wargear("Beast")
        modifier("Grants claws", targets_model(), adds(claws), carried_by=beast)
        assign(beast, miniature=yolanda)
        assert [weapon.name for weapon in card_for(yolanda).weapons] == ["Claws"]

        muzzle = create_wargear("Muzzle")
        modifier("Strips claws", targets_model(), removes(claws), carried_by=muzzle)
        assign(muzzle, miniature=yolanda)
        assert card_for(yolanda).weapons == []

    def test_a_removes_modifier_leaves_a_weapon_the_gang_bought(self, yolanda):
        """It reaches grants and nothing else. A bought weapon is a row
        somebody paid for, and parting with one is an operation — never
        something a card works out while being read."""
        claws = create_weapon("Claws", profiles=[("", 0)])
        give_weapon(yolanda, claws, paid=10)

        muzzle = create_wargear("Muzzle")
        modifier("Strips claws", targets_model(), removes(claws), carried_by=muzzle)
        assign(muzzle, miniature=yolanda)

        assert [weapon.name for weapon in card_for(yolanda).weapons] == ["Claws"]


class TestValidation:
    def test_a_trait_cannot_be_added_to_a_model(self, db):
        from n26.library.models import Modifier

        bad = Modifier(
            name="Nonsense",
            targets_miniature=targets_model(),
            adds_assignable=adds(create_trait("Melee")),
        )
        with pytest.raises(ValidationError, match="cannot apply"):
            bad.clean()

    def test_a_subtype_cannot_be_added_to_a_weapon(self, db):
        from n26.library.models import Modifier

        bad = Modifier(
            name="Nonsense",
            targets_weapons=targets_weapons(),
            adds_assignable=adds(create_subtype("Mounted")),
        )
        with pytest.raises(ValidationError, match="cannot apply"):
            bad.clean()

    def test_a_subtype_cannot_be_given_to_the_gang(self, db):
        """The gang's card has no type line: a rule or a standing list
        may land on the gang, and nothing else may."""
        from n26.library.models import Modifier

        bad = Modifier(
            name="Nonsense",
            targets_gang=targets_gang(),
            adds_assignable=adds(create_subtype("Chosen")),
        )
        with pytest.raises(ValidationError, match="cannot apply"):
            bad.clean()

    def test_a_weapon_cannot_be_given_to_the_gang(self, db):
        """A gang holds no weapons: a gun is carried by whoever carries
        it. A rule or a standing list may land on the gang's card; a
        thing that has to be held may not."""
        from n26.library.models import Modifier

        bad = Modifier(
            name="Nonsense",
            targets_gang=targets_gang(),
            adds_assignable=adds(create_weapon("Claws", profiles=[("", 0)])),
        )
        with pytest.raises(ValidationError, match="cannot apply"):
            bad.clean()

    def test_a_modifier_needs_a_scope_and_an_effect(self, db):
        from n26.library.models import Modifier

        with pytest.raises(ValidationError, match="exactly one scope"):
            Modifier(name="Empty").clean()


class TestPerformance:
    def test_computing_is_query_free(self, yolanda, ganger_profile):
        """Everything compute needs is loaded first; it touches nothing."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        mounted = create_subtype("Mounted")
        modifier(
            "Mounted grants a skill",
            targets_model(),
            adds(create_skill("Nerves of Steel")),
            carried_by=mounted,
        )
        cutter = create_wargear("Cutter")
        modifier(
            "Cutter grants Mounted", targets_model(), adds(mounted), carried_by=cutter
        )
        assign(cutter, miniature=yolanda, paid=75)

        card = build_card(yolanda, with_statlines=True)
        index = build_modifier_index([n.assignable for n in card.all_nodes()])

        with CaptureQueriesContext(connection) as captured:
            computed = compute(card, index)
            rendered = build_model_card(yolanda, card=card, computed=computed)
            assert [s.name for s in rendered.skills] == ["Nerves of Steel"]
        assert captured.captured_queries == []

    def test_a_content_cycle_terminates(self, yolanda):
        """Two subtypes granting each other must not spin forever."""
        first = create_subtype("Yin")
        second = create_subtype("Yang")
        modifier("Yin grants Yang", targets_model(), adds(second), carried_by=first)
        modifier("Yang grants Yin", targets_model(), adds(first), carried_by=second)
        seed = create_wargear("Talisman")
        modifier("Talisman grants Yin", targets_model(), adds(first), carried_by=seed)
        assign(seed, miniature=yolanda)

        assert card_for(yolanda).type_line == "Fighter (Yang, Yin)"


class TestOnTheCard:
    def test_the_text_renderer_shows_it_all(self, yolanda, stats):
        mounted = create_subtype("Mounted")
        modifier(
            "Mounted grants Nerves of Steel",
            targets_model(),
            adds(create_skill("Nerves of Steel")),
            carried_by=mounted,
        )
        cutter = create_wargear("Cutter")
        modifier(
            "Cutter grants Mounted", targets_model(), adds(mounted), carried_by=cutter
        )
        injury = create_wargear("Eye Injury")
        modifier(
            "Eye Injury worsens BS",
            targets_model(),
            changes_stat(stats["Ballistic Skill"], "worsen", 1),
            carried_by=injury,
        )

        assign(cutter, miniature=yolanda, paid=75)
        assign(injury, miniature=yolanda)

        card = card_for(yolanda)
        text = "\n".join(render_model_card(card))
        print("\n" + text)

        assert "Fighter (Mounted)" in text
        assert "Skills: Nerves of Steel" in text
        assert card.statline.get("BS").value == "5+"


class TestAHiddenCarrierStaysHidden:
    """A hidden item's name is authored to be read; its kind is the
    library's plumbing and never reaches a player's tooltip."""

    def test_a_stat_shifted_by_a_hidden_names_it_without_its_kind(self, yolanda):
        from n26.library.models import Stat
        from n26.tests.sandbox.actions import create_hidden, ef_changes_stat

        strength = Stat.objects.get(short_name="S")
        setter = create_hidden(
            "Strength rolled 6",
            effects=[
                (targets_model(), ef_changes_stat(strength, mode="set", amount=5))
            ],
        )
        assign(setter, miniature=yolanda, paid=0)

        card = build_card(yolanda, with_statlines=True)
        computed = compute(
            card, build_modifier_index([n.assignable for n in card.all_nodes()])
        )
        (change,) = computed.stat_changes
        assert change.source == "Strength rolled 6"
        assert change.source_kind == ""
