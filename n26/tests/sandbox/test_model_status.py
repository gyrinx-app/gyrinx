"""A model's standing between battles: In Recovery, Critically Injured,
Captured, Dead — and how a result sets it.

The rules keep one tick box on the roster and write everything else on
the Lasting Injuries line. The app keeps one column, ``Miniature.status``,
written only through an operation and journaled every time. A result's
effect sets it when the pick lands, so rolling 33 and adding Grievous
Wound puts the fighter into Recovery in the same act; Clean House at the
end of the cycle clears every Recovery; a death keeps the model on the
roster, under its own heading, counting nothing towards the rating.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core import history
from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import LedgerEvent, Miniature
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_gang
from n26.core.status import Status
from n26.library.models import Modifier, Picklist, Slot
from n26.library.standard_content import STANDARD_CONTENT
from n26.tests.sandbox.actions import (
    create_profile,
    create_weapon,
    ef_adds,
    found_gang,
    give_weapon,
    hire,
    is_profile_type,
    modifier,
    targets_every_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def tables(default_pack):
    """The shipped lasting-effect tables, as Foundations creates them —
    status effects included."""
    STANDARD_CONTENT["lasting-effect-tables"].create()
    return {
        "injury": Picklist.objects.get(name="Lasting Injury Table"),
        "damage": Picklist.objects.get(name="Lasting Damage Table"),
        "injury_slot": Slot.objects.get(name="Lasting Injury"),
        "damage_slot": Slot.objects.get(name="Lasting Damage"),
    }


@pytest.fixture
def gang(gang_type, owner, fighter_type, vehicle_type, tables):
    modifier(
        "Fighters carry Lasting Injury",
        targets_every_model(is_profile_type(fighter_type)),
        ef_adds(tables["injury_slot"]),
        carried_by=gang_type,
    )
    modifier(
        "Vehicles carry Lasting Damage",
        targets_every_model(is_profile_type(vehicle_type)),
        ef_adds(tables["damage_slot"]),
        carried_by=gang_type,
    )
    return found_gang("The Scar Crossing", gang_type, owner=owner, budget=1000)


@pytest.fixture
def krago(gang, gang_type, fighter_type):
    profile = create_profile("Ganger", fighter_type, gang_type, price=50)
    return hire(gang, profile, "Krago", paid=50)


@pytest.fixture
def nix(gang, gang_type, fighter_type):
    profile = create_profile("Juve", fighter_type, gang_type, price=25)
    return hire(gang, profile, "Nix", paid=25)


@pytest.fixture
def rig(gang, gang_type, vehicle_type):
    profile = create_profile("Cargo Rig", vehicle_type, gang_type, price=100)
    return hire(gang, profile, "The Rig", paid=100)


def computed_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def choice_of(miniature, label):
    return next(s for s in computed_for(miniature).choices if s.kind_label == label)


def result_named(table, name):
    return next(m.pickable for m in table.members.all() if m.pickable.name == name)


def add_result(miniature, label, table, name):
    """Add a result to the model's choice, as the pick screen does."""
    slot = choice_of(miniature, label)
    gang = miniature.membership.gang
    with operation(gang, actor=gang.owner) as op:
        return op.choose(
            slot.anchor.assignment,
            result_named(table, name),
            slot=slot.slot,
            miniature=miniature,
        )


def fresh(miniature):
    return Miniature.objects.get(pk=miniature.pk)


def sentences(gang):
    return ["".join(span.text for span in act.spans) for act in history.build(gang)]


class TestTheSeedAttachesTheOutcomes:
    """Foundations attaches "marks the model …" to every result the
    book gives a consequence — once, and never again on a second run."""

    def test_every_consequential_result_carries_its_status(self, tables):
        from n26.library.standard_content import LASTING_EFFECT_STATUSES

        for table in (tables["injury"], tables["damage"]):
            for member in table.members.select_related("pickable"):
                expected = LASTING_EFFECT_STATUSES.get(member.pickable.name)
                carried = [
                    m.effect.status
                    for m in member.pickable.modifiers.all()
                    if m.op_sets_status_id is not None
                ]
                assert carried == ([expected] if expected else []), member.pickable

    def test_running_the_seed_again_attaches_nothing_twice(self, tables):
        before = Modifier.objects.filter(op_sets_status__isnull=False).count()
        STANDARD_CONTENT["lasting-effect-tables"].create()
        assert Modifier.objects.filter(op_sets_status__isnull=False).count() == before

    def test_the_delegation_table_sends_a_critical_injury_home(self, tables):
        table = Picklist.objects.get(name="Delegation Lasting Injury Table")
        critical = result_named(table, "Critical Injury")
        assert [m.effect.status for m in critical.modifiers.all()] == [Status.DEAD]


class TestAResultSetsTheStatus:
    def test_a_fighter_starts_active(self, krago):
        assert krago.status == Status.ACTIVE

    def test_grievous_wound_puts_the_fighter_into_recovery(self, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Grievous Wound")
        assert fresh(krago).status == Status.RECOVERY
        assert_reconciled(gang)

    def test_the_pick_and_the_status_are_one_act_in_the_history(
        self, gang, krago, tables
    ):
        add_result(krago, "Lasting Injuries", tables["injury"], "Grievous Wound")
        events = list(LedgerEvent.objects.filter(gang=gang).order_by("created", "id"))[
            -2:
        ]
        assert [e.kind for e in events] == [
            LedgerEvent.Kind.GRANTED,
            LedgerEvent.Kind.STATUS_SET,
        ]
        assert events[0].batch == events[1].batch
        assert events[1].note == "active → recovery: Grievous Wound"

    def test_out_cold_leaves_the_status_alone(self, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Out Cold")
        assert fresh(krago).status == Status.ACTIVE

    def test_a_critical_injury_is_critical(self, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Critical Injury")
        assert fresh(krago).status == Status.CRITICAL

    def test_memorable_death_kills(self, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Memorable Death")
        assert fresh(krago).status == Status.DEAD

    def test_captured_marks_the_fighter_captured(self, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        assert fresh(krago).status == Status.CAPTURED

    def test_a_vehicle_takes_the_same_statuses(self, gang, rig, tables):
        add_result(rig, "Lasting Damage", tables["damage"], "Major Damage")
        assert fresh(rig).status == Status.RECOVERY

    def test_removing_the_pick_does_not_undo_the_status(self, gang, krago, tables):
        """Recovery is cleared by Clean House, not by taking the wound
        off the card."""
        from n26.tests.sandbox.actions import remove

        pick = add_result(krago, "Lasting Injuries", tables["injury"], "Grievous Wound")
        remove(pick)
        assert fresh(krago).status == Status.RECOVERY


class TestSettingItByHand:
    def test_the_owner_may_set_any_status(self, gang, krago):
        with operation(gang, actor=gang.owner) as op:
            op.set_status(krago, Status.CAPTURED)
        assert fresh(krago).status == Status.CAPTURED
        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.STATUS_SET)
        assert event.miniature == krago
        assert event.note == "active → captured"
        assert event.credits_delta == 0

    def test_the_same_status_again_writes_nothing(self, gang, krago):
        with operation(gang, actor=gang.owner) as op:
            op.set_status(krago, Status.ACTIVE)
        assert not LedgerEvent.objects.filter(kind=LedgerEvent.Kind.STATUS_SET).exists()


class TestTheDead:
    def test_a_dead_model_counts_nothing_towards_the_rating(self, gang, krago, nix):
        gang.refresh_from_db()
        before = gang.rating
        with operation(gang, actor=gang.owner) as op:
            op.set_status(krago, Status.DEAD)
        gang.refresh_from_db()
        assert gang.rating == before - 50
        assert fresh(krago).rating == 0
        assert_reconciled(gang)

    def test_a_dead_model_stays_on_the_roster_under_its_own_heading(
        self, gang, krago, nix
    ):
        with operation(gang, actor=gang.owner) as op:
            op.set_status(krago, Status.DEAD)
        sheet = render_gang(gang)
        assert [card.name for card in sheet.models] == ["Nix"]
        assert [card.name for card in sheet.dead] == ["Krago"]
        assert sheet.dead[0].status_label == "Dead"
        assert sheet.summary.count == 1

    def test_a_destroyed_vehicle_says_so(self, gang, rig):
        with operation(gang, actor=gang.owner) as op:
            op.set_status(rig, Status.DEAD)
        sheet = render_gang(gang)
        assert sheet.dead[0].status_label == "Destroyed"

    def test_the_card_says_where_the_model_stands(self, gang, krago):
        with operation(gang, actor=gang.owner) as op:
            op.set_status(krago, Status.RECOVERY)
        card = next(c for c in render_gang(gang).models if c.name == "Krago")
        assert card.status == Status.RECOVERY
        assert card.status_label == "In Recovery"
        assert "Misses the rest of the cycle" in card.status_note

    def test_a_vehicle_is_damaged_not_injured(self, gang, rig):
        with operation(gang, actor=gang.owner) as op:
            op.set_status(rig, Status.CRITICAL)
        card = next(c for c in render_gang(gang).models if c.name == "The Rig")
        assert card.status_label == "Critically Damaged"


class TestCleanHouse:
    def test_every_recovery_is_cleared_and_nothing_else_moves(
        self, gang, krago, nix, rig
    ):
        with operation(gang, actor=gang.owner) as op:
            op.set_status(krago, Status.RECOVERY)
            op.set_status(nix, Status.CRITICAL)
            op.set_status(rig, Status.RECOVERY)
        with operation(gang, actor=gang.owner) as op:
            cleared = op.clean_house()
        assert sorted(m.name for m in cleared) == ["Krago", "The Rig"]
        assert fresh(krago).status == Status.ACTIVE
        assert fresh(rig).status == Status.ACTIVE
        assert fresh(nix).status == Status.CRITICAL

    def test_it_reads_as_one_act(self, gang, krago, rig):
        with operation(gang, actor=gang.owner) as op:
            op.set_status(krago, Status.RECOVERY)
            op.set_status(rig, Status.RECOVERY)
        with operation(gang, actor=gang.owner) as op:
            op.clean_house()
        act = next(
            a
            for a in history.build(gang)
            if "cleaned house" in "".join(s.text for s in a.spans)
        )
        assert sorted(sub.name for sub in act.subs) == ["Krago", "The Rig"]


class TestTheHistoryTellsIt:
    def test_the_sentences(self, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Grievous Wound")
        with operation(gang, actor=gang.owner) as op:
            op.set_status(krago, Status.CAPTURED)
            op.set_status(krago, Status.DEAD)
        told = sentences(gang)
        assert "put Krago into Recovery — Grievous Wound" in told
        assert "marked Krago as captured" in told
        assert "marked Krago as dead" in told


class TestThePage:
    @pytest.fixture
    def sheet(self, gang):
        return reverse("n26-gang", args=[gang.pk])

    def test_the_card_wears_its_status(self, client, owner, gang, krago, sheet):
        with operation(gang, actor=owner) as op:
            op.set_status(krago, Status.RECOVERY)
        client.force_login(owner)
        page = client.get(sheet).content.decode()
        assert "In Recovery" in page
        assert "Misses the rest of the cycle" in page

    def test_the_owner_marks_a_model_from_the_dialog(
        self, client, owner, gang, krago, sheet
    ):
        client.force_login(owner)
        page = client.get(f"{sheet}?status={krago.pk}").content.decode()
        assert f"Mark {krago.name} as" in page
        reply = client.post(
            reverse("n26-mark-fighter", args=[krago.pk]), {"status": "recovery"}
        )
        assert reply.status_code == 302
        assert fresh(krago).status == Status.RECOVERY

    def test_a_death_may_stash_the_kit(self, client, owner, gang, krago, sheet):
        gun = create_weapon("Stub gun", price=30)
        give_weapon(krago, gun, paid=30)
        client.force_login(owner)
        client.post(
            reverse("n26-mark-fighter", args=[krago.pk]),
            {"status": "dead", "kit": "stash"},
        )
        gang.refresh_from_db()
        assert fresh(krago).status == Status.DEAD
        assert gang.stash.rating == 30
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_a_death_may_lose_the_kit(self, client, owner, gang, krago, sheet):
        gun = create_weapon("Stub gun", price=30)
        give_weapon(krago, gun, paid=30)
        client.force_login(owner)
        client.post(
            reverse("n26-mark-fighter", args=[krago.pk]),
            {"status": "dead", "kit": "lost"},
        )
        gang.refresh_from_db()
        assert gang.stash.rating == 0
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_the_dead_are_drawn_under_their_heading(
        self, client, owner, gang, krago, nix, sheet
    ):
        with operation(gang, actor=owner) as op:
            op.set_status(krago, Status.DEAD)
        client.force_login(owner)
        page = client.get(sheet).content.decode()
        assert page.index("Nix") < page.index(">Dead<") < page.index("Krago")

    def test_clean_house_from_the_sheet(self, client, owner, gang, krago, sheet):
        with operation(gang, actor=owner) as op:
            op.set_status(krago, Status.RECOVERY)
        client.force_login(owner)
        reply = client.post(reverse("n26-clean-house", args=[gang.pk]), follow=True)
        assert "back from Recovery" in reply.content.decode()
        assert fresh(krago).status == Status.ACTIVE

    def test_a_stranger_cannot_mark_a_model(self, client, gang, krago):
        other = User.objects.create_user("stranger")
        client.force_login(other)
        reply = client.post(
            reverse("n26-mark-fighter", args=[krago.pk]), {"status": "dead"}
        )
        assert reply.status_code == 404
        assert fresh(krago).status == Status.ACTIVE
