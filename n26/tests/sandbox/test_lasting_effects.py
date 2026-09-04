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

No profile carries either choice as a built-in. Each gang type carries
a standing grant instead — a modifier reaching every model whose Type
is Fighter and giving it the injury choice, and the vehicle twin — so
every fighter in every gang of the type has its row the moment the
modifier is attached, gangs founded long before included, and nothing
is written per model. Detaching the grant takes the row off every
card and leaves what was already picked where it is.
"""

import pytest

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import detach_modifier
from n26.library.standard_content import (
    LASTING_EFFECT_TABLES,
    STANDARD_CONTENT,
)
from n26.library.views import coverage
from n26.tests.sandbox.actions import (
    attach_modifiers_to,
    changes_stat,
    choose,
    create_profile,
    ef_adds,
    found_gang,
    hire,
    is_profile_type,
    modifier,
    targets_every_model,
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
        for name, _, _, _, _ in LASTING_EFFECT_TABLES
    }


@pytest.fixture
def gang(gang_type, db):
    from django.contrib.auth.models import User

    owner = User.objects.create_user("player")
    return found_gang("The Scar Crossing", gang_type, owner=owner, budget=1000)


@pytest.fixture
def standing(gang_type, fighter_type, vehicle_type, tables):
    """The two grants on the gang type: every fighter carries the
    injury choice, every vehicle the damage choice."""
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


def choice_of(miniature, label):
    return next(
        (s for s in computed_for(miniature).choices if s.kind_label == label), None
    )


def pick(miniature, label, pickable):
    """A pick on a granted slot, as the choose page makes it: the slot
    is named, because the anchor is the gang's founding line rather
    than a slot of its own, and the pick is hosted on the model whose
    card it was made from rather than on the gang."""
    slot = choice_of(miniature, label)
    return choose(slot.anchor.assignment, pickable, slot=slot.slot, miniature=miniature)


def result_named(table, name):
    return next(m.pickable for m in table.members.all() if m.pickable.name == name)


class TestTheTablesAsSeeded:
    """Both tables cover their die exactly, with nothing doubled and
    nothing unrollable — pinned so a band changes deliberately."""

    @pytest.mark.parametrize(
        ("name", "rolls"),
        [(n, {"d66": 36, "d6": 6}[dice]) for n, _, _, dice, _ in LASTING_EFFECT_TABLES],
    )
    def test_the_table_is_whole(self, tables, name, rolls):
        said = coverage(tables[name]["table"])
        assert said.covered == said.total == rolls
        assert said.unclaimed == []
        assert said.doubled == []
        assert said.bandless == []

    def test_running_the_seed_again_creates_nothing(self, tables):
        from n26.library.models import Pickable, PicklistMember, Slot, SlotType

        kinds = (SlotType, Pickable, PicklistMember, Slot)
        counts = {kind: kind.objects.count() for kind in kinds}
        STANDARD_CONTENT["lasting-effect-tables"].create()
        assert counts == {kind: kind.objects.count() for kind in kinds}

        present, total = STANDARD_CONTENT["lasting-effect-tables"].check()
        assert present == total

    def test_a_name_owned_by_another_slot_type_is_refused_in_words(self, default_pack):
        """A pack holds one pickable per name and qualifier, whichever
        slot type it belongs to — so a name already claimed elsewhere
        stops the seed with an explanation, never a bare constraint."""
        from n26.library.authoring import create_pickable, create_slot_type

        other = create_slot_type("Gang Legacy", plural_name="Gang Legacies")
        create_pickable("Captured", other)

        with pytest.raises(RuntimeError, match="Captured"):
            STANDARD_CONTENT["lasting-effect-tables"].create()

    def test_the_shared_names_are_separate_results_per_table(self, tables):
        """Lesson Learnt sits on three tables, Grievous Wound on three,
        Out Cold on two — as one pickable per table, because a pickable
        belongs to one slot type; the twins are told apart by qualifier."""
        from n26.library.models import Pickable
        from n26.library.standard_content import SHARED_LASTING_RESULTS

        assert SHARED_LASTING_RESULTS >= {"Lesson Learnt", "Grievous Wound", "Out Cold"}
        for name in SHARED_LASTING_RESULTS:
            on_tables = {
                table
                for table, _, rows, _, _ in LASTING_EFFECT_TABLES
                if any(result == name for _, _, result in rows)
            }
            types = {p.slot_type.name for p in Pickable.objects.filter(name=name)}
            assert types == on_tables, name

    def test_a_table_seeded_before_a_later_twin_gains_no_second_copy(
        self, default_pack
    ):
        """Production seeded the first two tables before the others
        existed, so the Lasting Damage table's Superficial Damage carries
        no qualifier. Seeding again must find that row, not make a twin
        beside it and double the band."""
        from n26.library.models import Pickable, PicklistMember

        STANDARD_CONTENT["lasting-effect-tables"].create()
        early = Pickable.objects.get(
            name="Superficial Damage", slot_type__name="Lasting Damage"
        )
        assert early.qualifier == ""
        STANDARD_CONTENT["lasting-effect-tables"].create()
        assert Pickable.objects.filter(name="Superficial Damage").count() == 2
        assert (
            PicklistMember.objects.filter(pickable__name="Superficial Damage").count()
            == 2
        )


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
        pick(yolanda, "Lasting Injuries", result_named(table, "Eye Injury"))

        changes = [
            c for c in computed_for(yolanda).stat_changes if c.source == "Eye Injury"
        ]
        assert len(changes) == 1
        assert_reconciled(gang)

    def test_a_result_that_changes_nothing_is_still_on_the_card(
        self, gang, yolanda, tables
    ):
        table = tables["Lasting Injury"]["table"]
        pick(yolanda, "Lasting Injuries", result_named(table, "Out Cold"))

        slot = choice_of(yolanda, "Lasting Injuries")
        assert [p.assignable.name for p in slot.picks] == ["Out Cold"]
        assert_reconciled(gang)

    def test_the_same_injury_twice_stands_and_stacks(self, gang, yolanda, tables):
        eye = result_named(tables["Lasting Injury"]["table"], "Eye Injury")
        for _ in range(2):
            pick(yolanda, "Lasting Injuries", eye)

        changes = [
            c for c in computed_for(yolanda).stat_changes if c.source == "Eye Injury"
        ]
        assert len(changes) == 2
        assert_reconciled(gang)

    def test_the_row_is_there_before_anyone_wrote_it(
        self, gang, gang_type, yolanda, standing
    ):
        """A gang founded before the grant existed has the row the
        moment the modifier is attached: nothing is written per model,
        so there is nothing to propagate to gangs that already exist."""
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
        """The row goes from every fighter's card at once; an injury
        already picked stays, its effect with it, as a plain line the
        player can remove — a grant detached by mistake must not eat
        a gang's history."""
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
        """The choice is the gang type's to give, but a pick is hosted
        on the model whose card it was made from — never on the gang,
        where it would ride every fighter's card."""
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


class TestAVehicleIsHit:
    def test_busted_sights_worsen_the_ballistic_skill(self, gang, rig, tables):
        table = tables["Lasting Damage"]["table"]
        pick(rig, "Lasting Damage", result_named(table, "Busted Sights"))

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
        with pytest.raises(Refusal):
            pick(yolanda, "Lasting Injuries", result_named(table, "Busted Sights"))
        assert_reconciled(gang)
