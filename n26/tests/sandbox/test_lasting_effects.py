"""Seed lasting-effect tables and apply their results to fighters and vehicles.

The seed creates slot types, roll bands, choices and result names. Fixtures add
characteristic modifiers separately. Shared names use distinct pickables for
each slot type, with qualifiers where needed.

Gang-type modifiers grant the matching choice without per-model assignments.
Removing a grant hides its choice while preserving existing injury picks.
A delegation can replace the ordinary injury choice with its own table.
"""

import pytest

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.library.authoring import detach_modifier
from n26.library.standard_content import (
    LASTING_EFFECT_TABLES,
    STANDARD_CONTENT,
)
from n26.library.views import coverage
from n26.tests.sandbox.actions import (
    add_built_in,
    assign,
    attach_modifiers_to,
    changes_stat,
    choose,
    create_hidden,
    create_profile,
    create_wargear,
    ef_adds,
    ef_removes,
    found_gang,
    hire,
    is_profile_type,
    modifier,
    set_statline,
    targets_every_model,
    targets_model,
)

pytestmark = pytest.mark.django_db

#: Characteristic results and the stats they worsen by one. Fixtures add these
#: modifiers after the standard-content seed creates the named results.
WORSENS = {
    "Eye Injury": "BS",
    "Hand Injury": "WS",
    "Hobbled": "M",
    "Spinal Injury": "S",
    "Enfeebled": "T",
    "Head Injury": "Ld",
    "Busted Sights": "BS",
    "Drive System Fault": "M",
    "Buckled Frame": "T",
    "Engine Fracture": "W",
}


@pytest.fixture
def seeded_tables(default_pack):
    """The shipped tables, before an author adds characteristic modifiers."""
    from n26.library.models import Picklist, Slot

    STANDARD_CONTENT["lasting-effect-tables"].create()
    return {
        name: {
            "table": Picklist.objects.get(name=f"{name} Table"),
            "slot": Slot.objects.get(name=name),
        }
        for name, _, _, _, _ in LASTING_EFFECT_TABLES
    }


@pytest.fixture
def tables(seeded_tables, fighter_stats):
    """Hand-finish the seeded characteristic results for player-effect tests."""
    from n26.library.models import Pickable

    for result, short in WORSENS.items():
        modifier(
            f"{result}: worsens {short}",
            targets_model(),
            changes_stat(fighter_stats[short], "worsen", 1),
            carried_by=Pickable.objects.get(name=result),
        )
    return seeded_tables


@pytest.fixture
def gang(gang_type, db):
    from django.contrib.auth.models import User

    owner = User.objects.create_user("player")
    return found_gang("The Scar Crossing", gang_type, owner=owner, budget=1000)


@pytest.fixture
def standing(gang_type, fighter_type, vehicle_type, tables):
    """Grant Lasting Injury to fighters and Lasting Damage to vehicles."""
    return {
        name: modifier(
            f"{kind.name}s carry {name}",
            targets_every_model(is_profile_type(kind)),
            ef_adds(tables[name]["slot"]),
            carried_by=gang_type,
        )
        for name, kind in (
            ("Lasting Injury", fighter_type),
            ("Lasting Damage", vehicle_type),
        )
    }


@pytest.fixture
def yolanda(gang, gang_type, fighter_type, standing):
    profile = create_profile("Ganger", fighter_type, gang_type, price=50)
    return hire(gang, profile, "Yolanda", paid=50)


@pytest.fixture
def rig(gang, gang_type, vehicle_type, standing):
    profile = create_profile("Cargo Rig", vehicle_type, gang_type, price=100)
    return hire(gang, profile, "The Rig", paid=100)


def computed_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def card_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


def choice_of(miniature, label):
    return next(
        (s for s in computed_for(miniature).choices if s.kind_label == label), None
    )


def pick(miniature, label, pickable):
    """Choose for a model using the granted slot and its founding-assignment anchor."""
    slot = choice_of(miniature, label)
    return choose(slot.anchor.assignment, pickable, slot=slot.slot, miniature=miniature)


def result_named(table, name):
    return next(m.pickable for m in table.members.all() if m.pickable.name == name)


class TestTheTablesAsSeeded:
    """Seeded tables cover every roll exactly once and remain unchanged on reseeding."""

    def test_the_complete_tables_keep_their_results_when_seeded_again(
        self, seeded_tables
    ):
        from n26.library.models import Pickable, PicklistMember, Slot, SlotType
        from n26.library.standard_content import SHARED_LASTING_RESULTS

        tables = seeded_tables
        for name, _, _, dice, _ in LASTING_EFFECT_TABLES:
            rolls = {"d66": 36, "d6": 6}[dice]
            said = coverage(tables[name]["table"])
            assert said.covered == said.total == rolls
            assert said.unclaimed == []
            assert said.doubled == []
            assert said.bandless == []

        early = Pickable.objects.get(
            name="Superficial Damage", slot_type__name="Lasting Damage"
        )
        assert early.qualifier == ""

        assert SHARED_LASTING_RESULTS >= {"Lesson Learnt", "Grievous Wound", "Out Cold"}
        for name in SHARED_LASTING_RESULTS:
            on_tables = {
                table
                for table, _, rows, _, _ in LASTING_EFFECT_TABLES
                if any(result == name for _, _, result in rows)
            }
            types = {p.slot_type.name for p in Pickable.objects.filter(name=name)}
            assert types == on_tables, name

        kinds = (SlotType, Pickable, PicklistMember, Slot)
        counts = {kind: kind.objects.count() for kind in kinds}
        STANDARD_CONTENT["lasting-effect-tables"].create()
        assert counts == {kind: kind.objects.count() for kind in kinds}

        present, total = STANDARD_CONTENT["lasting-effect-tables"].check()
        assert present == total

        assert Pickable.objects.filter(name="Superficial Damage").count() == 2
        assert (
            PicklistMember.objects.filter(pickable__name="Superficial Damage").count()
            == 2
        )

    def test_a_name_owned_by_another_slot_type_is_refused_in_words(self, default_pack):
        """Report a conflicting name and qualifier before a database constraint fails."""
        from n26.library.authoring import create_pickable, create_slot_type

        other = create_slot_type("Gang Legacy", plural_name="Gang Legacies")
        create_pickable("Captured", other)

        with pytest.raises(RuntimeError, match="Captured"):
            STANDARD_CONTENT["lasting-effect-tables"].create()


class TestAFighterIsHurt:
    def test_the_card_asks_under_the_tables_own_word(self, yolanda, rig):
        assert choice_of(yolanda, "Lasting Injuries") is not None
        assert choice_of(rig, "Lasting Damage") is not None
        assert not any(
            slot.kind_label == "Lasting Damage"
            for slot in computed_for(yolanda).choices
        )

    def test_an_eye_injury_worsens_ballistic_skill_and_repeated_injuries_stack(
        self, gang, yolanda, tables
    ):
        table = tables["Lasting Injury"]["table"]
        pick(yolanda, "Lasting Injuries", result_named(table, "Eye Injury"))

        changes = [
            c for c in computed_for(yolanda).stat_changes if c.source == "Eye Injury"
        ]
        assert len(changes) == 1
        assert_reconciled(gang)

        eye = result_named(tables["Lasting Injury"]["table"], "Eye Injury")
        pick(yolanda, "Lasting Injuries", eye)

        changes = [
            c for c in computed_for(yolanda).stat_changes if c.source == "Eye Injury"
        ]
        assert len(changes) == 2
        assert_reconciled(gang)

    def test_a_result_that_changes_nothing_is_still_on_the_card(
        self, gang, yolanda, tables
    ):
        table = tables["Lasting Injury"]["table"]
        pick(yolanda, "Lasting Injuries", result_named(table, "Out Cold"))

        slot = choice_of(yolanda, "Lasting Injuries")
        assert [p.assignable.name for p in slot.picks] == ["Out Cold"]
        assert_reconciled(gang)

    @pytest.fixture
    def brute(self, gang, gang_type, fighter_type, standing):
        profile = create_profile("Brute", fighter_type, gang_type, price=50)
        set_statline(profile, strength=3)
        return hire(gang, profile, "Ox", paid=50)

    def test_stacked_injuries_reach_the_floor_and_a_later_bionic_lifts_them(
        self, client, gang, brute, tables, fighter_stats
    ):
        spinal = result_named(tables["Lasting Injury"]["table"], "Spinal Injury")
        for _ in range(3):
            pick(brute, "Lasting Injuries", spinal)

        cell = card_for(brute).statline.get("S")
        assert cell.value == "1"
        assert cell.held_at == "minimum"
        assert cell.held_note == "Cannot get any worse."
        assert [p.source for p in cell.modified_by] == ["Spinal Injury"] * 3
        assert cell.changed_by == "Spinal Injury (x3)"
        assert_reconciled(gang)

        client.force_login(gang.owner)
        from django.urls import reverse

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "S changed by Spinal Injury (x3)" in body
        assert "S changed by Spinal Injury, Spinal Injury" not in body
        assert "Cannot get any worse." in body

        spinal = result_named(tables["Lasting Injury"]["table"], "Spinal Injury")
        for _ in range(2):
            pick(brute, "Lasting Injuries", spinal)
        bionic = create_wargear("Bionic Arm")
        modifier(
            "Bionic Arm improves S",
            targets_model(),
            changes_stat(fighter_stats["S"], "improve", 1),
            carried_by=bionic,
        )
        assign(bionic, miniature=brute, paid=30)

        cell = card_for(brute).statline.get("S")
        assert (cell.value, cell.held_at) == ("2", "")
        assert_reconciled(gang)

    def test_the_row_is_there_before_anyone_wrote_it(
        self, gang, gang_type, yolanda, standing
    ):
        """Attaching a grant exposes its choice on existing models without writing assignments."""
        from n26.core.models import Assignment

        for grant in standing.values():
            detach_modifier(gang_type, grant)
        assert choice_of(yolanda, "Lasting Injuries") is None

        before = Assignment.objects.count()
        attach_modifiers_to(gang_type, [standing["Lasting Injury"]])
        assert Assignment.objects.count() == before
        assert choice_of(yolanda, "Lasting Injuries") is not None
        assert_reconciled(gang)

    def test_detaching_the_grant_takes_the_row_off_but_keeps_the_injuries(
        self, gang, gang_type, yolanda, tables, standing
    ):
        """Removing a choice grant preserves existing injury picks and their effects."""
        table = tables["Lasting Injury"]["table"]
        pick(yolanda, "Lasting Injuries", result_named(table, "Eye Injury"))

        detach_modifier(gang_type, standing["Lasting Injury"])

        computed = computed_for(yolanda)
        assert not any(s.kind_label == "Lasting Injuries" for s in computed.choices)
        assert any(c.source == "Eye Injury" for c in computed.stat_changes)
        assert_reconciled(gang)

    def test_an_injury_is_the_hurt_fighters_alone(
        self, gang, gang_type, fighter_type, yolanda, tables
    ):
        """Host injury picks on the selected model so they cannot affect other fighters."""
        profile = create_profile("Juve", fighter_type, gang_type, price=25)
        other = hire(gang, profile, "Wren", paid=25)
        pick(
            yolanda,
            "Lasting Injuries",
            result_named(tables["Lasting Injury"]["table"], "Eye Injury"),
        )

        assert [
            p.assignable.name for p in choice_of(other, "Lasting Injuries").picks
        ] == []
        assert not any(
            c.source == "Eye Injury" for c in computed_for(other).stat_changes
        )
        assert_reconciled(gang)


class TestADelegationIsHurt:
    """A built-in hidden marker replaces the ordinary injury choice with the delegation table."""

    @pytest.fixture
    def bailiff(self, gang, gang_type, fighter_type, tables, standing):
        marker = create_hidden("Delegation")
        modifier(
            "Delegation: no Lasting Injuries",
            targets_model(),
            ef_removes(tables["Lasting Injury"]["slot"]),
            carried_by=marker,
        )
        modifier(
            "Delegation: its own table",
            targets_model(),
            ef_adds(tables["Delegation Lasting Injury"]["slot"]),
            carried_by=marker,
        )
        profile = create_profile("Bailiff", fighter_type, gang_type, price=60)
        add_built_in(profile, marker)
        return hire(gang, profile, "The Bailiff", paid=60)

    def test_the_delegation_uses_only_its_table_and_records_a_grievous_wound(
        self, gang, bailiff, yolanda, tables
    ):
        assert choice_of(bailiff, "Delegation Lasting Injuries") is not None
        assert choice_of(bailiff, "Lasting Injuries") is None
        assert choice_of(yolanda, "Lasting Injuries") is not None
        assert choice_of(yolanda, "Delegation Lasting Injuries") is None

        table = tables["Delegation Lasting Injury"]["table"]
        pick(
            bailiff,
            "Delegation Lasting Injuries",
            result_named(table, "Grievous Wound"),
        )

        slot = choice_of(bailiff, "Delegation Lasting Injuries")
        assert [p.assignable.name for p in slot.picks] == ["Grievous Wound"]
        assert_reconciled(gang)


class TestAVehicleIsHit:
    def test_vehicle_damage_refuses_a_fighter_and_worsens_the_vehicle(
        self, gang, yolanda, rig, tables
    ):
        from n26.core.operations import Refusal

        table = tables["Lasting Damage"]["table"]
        with pytest.raises(Refusal):
            pick(yolanda, "Lasting Injuries", result_named(table, "Busted Sights"))
        assert_reconciled(gang)

        table = tables["Lasting Damage"]["table"]
        pick(rig, "Lasting Damage", result_named(table, "Busted Sights"))

        changes = [
            c for c in computed_for(rig).stat_changes if c.source == "Busted Sights"
        ]
        assert len(changes) == 1
        assert_reconciled(gang)
