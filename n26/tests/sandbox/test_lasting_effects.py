"""The Lasting Injury and Lasting Damage tables, built as they ship.

The executable spec for the rulebook's two lasting-effect tables (core
rules: resolving hits and injuries): each is a slot type, a roll table
of pickables with their bands, and a standing choice built into a
profile. Names and bands only, never the book's wording; the six
results that change a characteristic carry an ordinary modifier.

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
from n26.library.views import coverage
from n26.tests.sandbox.actions import (
    add_built_in,
    add_picklist_member,
    changes_stat,
    choose,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    found_gang,
    hire,
    modifier,
    remove,
    targets_model,
)

pytestmark = pytest.mark.django_db

# (band low, band high, result, characteristic worsened or None).
# A result with no characteristic is a name and a band: what it does is
# played at the table, and the card only has to say the model has it.
LASTING_INJURY_TABLE = [
    (11, 11, "Lesson Learnt", None),
    (12, 12, "Eternal Enmity", None),
    (13, 13, "Bitter Enmity", None),
    (14, 14, "Personal Enmity", None),
    (15, 15, "Horrid Scars", None),
    (16, 16, "Impressive Scars", None),
    (21, 26, "Out Cold", None),
    (31, 46, "Grievous Wound", None),
    (51, 51, "Eye Injury", "BS"),
    (52, 52, "Hand Injury", "WS"),
    (53, 53, "Hobbled", "M"),
    (54, 54, "Spinal Injury", "S"),
    (55, 55, "Enfeebled", "T"),
    (56, 56, "Head Injury", "Ld"),
    (61, 62, "Captured", None),
    (63, 65, "Critical Injury", None),
    (66, 66, "Memorable Death", None),
]

LASTING_DAMAGE_TABLE = [
    (11, 11, "Lesson Learnt", None),
    (12, 12, "Eternal Enmity", None),
    (13, 13, "Bitter Enmity", None),
    (14, 14, "Personal Enmity", None),
    (15, 16, "Percussive Repair", None),
    (21, 26, "Superficial Damage", None),
    (31, 46, "Major Damage", None),
    (51, 52, "Busted Sights", "BS"),
    (53, 53, "Drive System Fault", "M"),
    (54, 54, "Buckled Frame", "T"),
    (55, 56, "Engine Fracture", "W"),
    (61, 62, "Captured", None),
    (63, 65, "Critical Damage", None),
    (66, 66, "Catastrophic Explosion!", None),
]


#: On both tables at the same rolls. One pickable per name per pack, so
#: the damage twin of each carries a qualifier.
SHARED_RESULTS = {
    "Lesson Learnt",
    "Eternal Enmity",
    "Bitter Enmity",
    "Personal Enmity",
    "Captured",
}


def build_table(name, plural, rows, stats, twin_qualifier=""):
    """One lasting-effect table, whole, through the authoring verbs."""
    slot_type = create_slot_type(name, plural_name=plural, allows_repeats=True)
    table = create_picklist(f"{name} Table", slot_type, dice="d66", roll_selects="band")
    for low, high, result, worsens in rows:
        qualifier = twin_qualifier if result in SHARED_RESULTS else ""
        pickable = create_pickable(result, slot_type, qualifier=qualifier)
        add_picklist_member(table, pickable, roll_low=low, roll_high=high)
        if worsens:
            modifier(
                f"{result}: worsens {worsens}",
                targets_model(),
                changes_stat(stats[worsens], "worsen", 1),
                carried_by=pickable,
            )
    slot = create_slot(name, slot_type, table, label=plural, min_picks=0, max_picks=20)
    return slot_type, table, slot


@pytest.fixture
def injuries(default_pack, fighter_stats):
    return build_table(
        "Lasting Injury", "Lasting Injuries", LASTING_INJURY_TABLE, fighter_stats
    )


@pytest.fixture
def damage(default_pack, fighter_stats):
    return build_table(
        "Lasting Damage",
        "Lasting Damage",
        LASTING_DAMAGE_TABLE,
        fighter_stats,
        twin_qualifier="vehicle",
    )


@pytest.fixture
def gang(gang_type, db):
    from django.contrib.auth.models import User

    owner = User.objects.create_user("player")
    return found_gang("The Scar Crossing", gang_type, owner=owner, budget=1000)


@pytest.fixture
def yolanda(gang, gang_type, fighter_type, injuries):
    _, _, slot = injuries
    profile = create_profile("Ganger", fighter_type, gang_type, price=50)
    add_built_in(profile, slot)
    return hire(gang, profile, "Yolanda", paid=50)


@pytest.fixture
def rig(gang, gang_type, vehicle_type, damage):
    _, _, slot = damage
    profile = create_profile("Cargo Rig", vehicle_type, gang_type, price=100)
    add_built_in(profile, slot)
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


class TestTheTablesAsAuthored:
    """Both tables cover their die exactly, with nothing doubled and
    nothing unrollable — pinned so a band changes deliberately."""

    def test_the_injury_table_is_whole(self, injuries):
        _, table, _ = injuries
        said = coverage(table)
        assert said.covered == said.total == 36
        assert said.unclaimed == []
        assert said.doubled == []
        assert said.bandless == []

    def test_the_damage_table_is_whole(self, damage):
        _, table, _ = damage
        said = coverage(table)
        assert said.covered == said.total == 36
        assert said.unclaimed == []
        assert said.doubled == []
        assert said.bandless == []

    def test_the_shared_names_are_separate_results_per_table(self, injuries, damage):
        """Lesson Learnt, the three Enmities and Captured sit on both
        tables at the same rolls — as two pickables each, because a
        pickable belongs to one slot type."""
        from n26.library.models import Pickable

        for name in (
            "Lesson Learnt",
            "Eternal Enmity",
            "Bitter Enmity",
            "Personal Enmity",
            "Captured",
        ):
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

    def test_an_eye_injury_worsens_the_ballistic_skill(self, gang, yolanda, injuries):
        _, table, _ = injuries
        slot = choice_of(yolanda, "Lasting Injuries")
        choose(slot.anchor.assignment, result_named(table, "Eye Injury"))

        changes = [
            c for c in computed_for(yolanda).stat_changes if c.source == "Eye Injury"
        ]
        assert len(changes) == 1
        assert_reconciled(gang)

    def test_a_result_that_changes_nothing_is_still_on_the_card(
        self, gang, yolanda, injuries
    ):
        _, table, _ = injuries
        slot = choice_of(yolanda, "Lasting Injuries")
        choose(slot.anchor.assignment, result_named(table, "Out Cold"))

        slot = choice_of(yolanda, "Lasting Injuries")
        assert [p.assignable.name for p in slot.picks] == ["Out Cold"]
        assert_reconciled(gang)

    def test_the_same_injury_twice_stands_and_stacks(self, gang, yolanda, injuries):
        _, table, _ = injuries
        eye = result_named(table, "Eye Injury")
        for _ in range(2):
            slot = choice_of(yolanda, "Lasting Injuries")
            choose(slot.anchor.assignment, eye)

        changes = [
            c for c in computed_for(yolanda).stat_changes if c.source == "Eye Injury"
        ]
        assert len(changes) == 2
        assert_reconciled(gang)

    def test_removing_the_slot_takes_the_injuries_and_their_effects(
        self, gang, yolanda, injuries
    ):
        _, table, _ = injuries
        slot = choice_of(yolanda, "Lasting Injuries")
        choose(slot.anchor.assignment, result_named(table, "Eye Injury"))

        remove(choice_of(yolanda, "Lasting Injuries").anchor.assignment)

        computed = computed_for(yolanda)
        assert not any(s.kind_label == "Lasting Injuries" for s in computed.choices)
        assert not any(c.source == "Eye Injury" for c in computed.stat_changes)
        assert_reconciled(gang)


class TestAVehicleIsHit:
    def test_busted_sights_worsen_the_ballistic_skill(self, gang, rig, damage):
        _, table, _ = damage
        slot = choice_of(rig, "Lasting Damage")
        choose(slot.anchor.assignment, result_named(table, "Busted Sights"))

        changes = [
            c for c in computed_for(rig).stat_changes if c.source == "Busted Sights"
        ]
        assert len(changes) == 1
        assert_reconciled(gang)

    def test_a_fighter_cannot_be_handed_vehicle_damage(
        self, gang, yolanda, rig, damage
    ):
        """The two tables share a card row's shape, never their results:
        the choice's own type check is what stands between a fighter and
        a Busted Sights."""
        from n26.core.operations import Refusal

        _, table, _ = damage
        slot = choice_of(yolanda, "Lasting Injuries")
        with pytest.raises(Refusal):
            choose(slot.anchor.assignment, result_named(table, "Busted Sights"))
        assert_reconciled(gang)
