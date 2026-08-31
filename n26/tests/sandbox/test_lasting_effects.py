"""The Lasting Injury and Lasting Damage tables, built as they ship.

The executable spec for the rulebook's two lasting-effect tables (core
rules: resolving hits and injuries). The tables themselves — two slot
types, a D66 roll table of results at their bands, a standing choice
each — are a Foundations seed, created here exactly as the button
creates them. Seeds write names and numbers only, so what the ten
characteristic results *do* is attached afterwards as ordinary
modifiers, the way an author finishes the tables by hand.

Two slot types rather than one, so a fighter can never be handed
vehicle damage — the choice's own type check refuses it. Five names
appear on both tables at the same rolls; they are separate pickables,
because a pickable belongs to one slot type — and the damage twins
carry the qualifier "vehicle", because a pack holds one pickable per
name and the qualifier is the author-facing way to tell twins apart.
"""

import pytest

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.reconcile import assert_reconciled
from n26.library.standard_content import (
    LASTING_EFFECT_TABLES,
    STANDARD_CONTENT,
)
from n26.library.views import coverage
from n26.tests.sandbox.actions import (
    add_built_in,
    changes_stat,
    choose,
    create_profile,
    found_gang,
    hire,
    modifier,
    remove,
    targets_model,
)

pytestmark = pytest.mark.django_db

#: What the ten characteristic results worsen, by one. The seed cannot
#: write these — a modifier is behaviour, not a name — so they are the
#: hand-authored half of the tables.
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
def tables(default_pack, fighter_stats):
    """The seed, then the hand-finishing: the shipped path, whole."""
    from n26.library.models import Pickable, Picklist, Slot

    STANDARD_CONTENT["lasting-effect-tables"].create()
    for result, short in WORSENS.items():
        modifier(
            f"{result}: worsens {short}",
            targets_model(),
            changes_stat(fighter_stats[short], "worsen", 1),
            carried_by=Pickable.objects.get(name=result),
        )
    return {
        name: {
            "table": Picklist.objects.get(name=f"{name} Table"),
            "slot": Slot.objects.get(name=name),
        }
        for name, _, _, _ in LASTING_EFFECT_TABLES
    }


@pytest.fixture
def gang(gang_type, db):
    from django.contrib.auth.models import User

    owner = User.objects.create_user("player")
    return found_gang("The Scar Crossing", gang_type, owner=owner, budget=1000)


@pytest.fixture
def yolanda(gang, gang_type, fighter_type, tables):
    profile = create_profile("Ganger", fighter_type, gang_type, price=50)
    add_built_in(profile, tables["Lasting Injury"]["slot"])
    return hire(gang, profile, "Yolanda", paid=50)


@pytest.fixture
def rig(gang, gang_type, vehicle_type, tables):
    profile = create_profile("Cargo Rig", vehicle_type, gang_type, price=100)
    add_built_in(profile, tables["Lasting Damage"]["slot"])
    return hire(gang, profile, "The Rig", paid=100)


def computed_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def choice_of(miniature, label):
    return next(
        slot for slot in computed_for(miniature).choices if slot.kind_label == label
    )


def result_named(table, name):
    return next(m.pickable for m in table.members.all() if m.pickable.name == name)


class TestTheTablesAsSeeded:
    """Both tables cover their die exactly, with nothing doubled and
    nothing unrollable — pinned so a band changes deliberately."""

    @pytest.mark.parametrize("name", [n for n, _, _, _ in LASTING_EFFECT_TABLES])
    def test_the_table_is_whole(self, tables, name):
        said = coverage(tables[name]["table"])
        assert said.covered == said.total == 36
        assert said.unclaimed == []
        assert said.doubled == []
        assert said.bandless == []

    def test_the_shared_names_are_separate_results_per_table(self, tables):
        """Lesson Learnt, the three Enmities and Captured sit on both
        tables at the same rolls — as two pickables each, because a
        pickable belongs to one slot type."""
        from n26.library.models import Pickable
        from n26.library.standard_content import SHARED_LASTING_RESULTS

        for name in SHARED_LASTING_RESULTS:
            types = {p.slot_type.name for p in Pickable.objects.filter(name=name)}
            assert types == {"Lasting Injury", "Lasting Damage"}, name


class TestAFighterIsHurt:
    def test_the_card_asks_under_the_tables_own_word(self, yolanda, rig):
        assert choice_of(yolanda, "Lasting Injuries") is not None
        assert choice_of(rig, "Lasting Damage") is not None
        assert not any(
            slot.kind_label == "Lasting Damage"
            for slot in computed_for(yolanda).choices
        )

    def test_an_eye_injury_worsens_the_ballistic_skill(self, gang, yolanda, tables):
        table = tables["Lasting Injury"]["table"]
        slot = choice_of(yolanda, "Lasting Injuries")
        choose(slot.anchor.assignment, result_named(table, "Eye Injury"))

        changes = [
            c for c in computed_for(yolanda).stat_changes if c.source == "Eye Injury"
        ]
        assert len(changes) == 1
        assert_reconciled(gang)

    def test_a_result_that_changes_nothing_is_still_on_the_card(
        self, gang, yolanda, tables
    ):
        table = tables["Lasting Injury"]["table"]
        slot = choice_of(yolanda, "Lasting Injuries")
        choose(slot.anchor.assignment, result_named(table, "Out Cold"))

        slot = choice_of(yolanda, "Lasting Injuries")
        assert [p.assignable.name for p in slot.picks] == ["Out Cold"]
        assert_reconciled(gang)

    def test_the_same_injury_twice_stands_and_stacks(self, gang, yolanda, tables):
        eye = result_named(tables["Lasting Injury"]["table"], "Eye Injury")
        for _ in range(2):
            slot = choice_of(yolanda, "Lasting Injuries")
            choose(slot.anchor.assignment, eye)

        changes = [
            c for c in computed_for(yolanda).stat_changes if c.source == "Eye Injury"
        ]
        assert len(changes) == 2
        assert_reconciled(gang)

    def test_removing_the_slot_takes_the_injuries_and_their_effects(
        self, gang, yolanda, tables
    ):
        table = tables["Lasting Injury"]["table"]
        slot = choice_of(yolanda, "Lasting Injuries")
        choose(slot.anchor.assignment, result_named(table, "Eye Injury"))

        remove(choice_of(yolanda, "Lasting Injuries").anchor.assignment)

        computed = computed_for(yolanda)
        assert not any(s.kind_label == "Lasting Injuries" for s in computed.choices)
        assert not any(c.source == "Eye Injury" for c in computed.stat_changes)
        assert_reconciled(gang)


class TestAVehicleIsHit:
    def test_busted_sights_worsen_the_ballistic_skill(self, gang, rig, tables):
        table = tables["Lasting Damage"]["table"]
        slot = choice_of(rig, "Lasting Damage")
        choose(slot.anchor.assignment, result_named(table, "Busted Sights"))

        changes = [
            c for c in computed_for(rig).stat_changes if c.source == "Busted Sights"
        ]
        assert len(changes) == 1
        assert_reconciled(gang)

    def test_a_fighter_cannot_be_handed_vehicle_damage(
        self, gang, yolanda, rig, tables
    ):
        """The two tables share a card row's shape, never their results:
        the choice's own type check is what stands between a fighter and
        a Busted Sights."""
        from n26.core.operations import Refusal

        table = tables["Lasting Damage"]["table"]
        slot = choice_of(yolanda, "Lasting Injuries")
        with pytest.raises(Refusal):
            choose(slot.anchor.assignment, result_named(table, "Busted Sights"))
        assert_reconciled(gang)
