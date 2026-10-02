"""A captured model and the Escape table.

The rules resolve a capture straight after the battle: the captured model
rolls a D6 on the Escape table and is executed, ransomed, or escapes into
Recovery (core rules, the Wrap-up). The app makes that one more roll
table on the machinery the injury tables use: the Captured result carries
a modifier that gives the model an Escape choice, so the card grows an
Escape row with Roll the moment Captured is added; each Escape result
sets the status when its pick lands.
"""

import re

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import LedgerEvent, Miniature
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card, option_key
from n26.core.status import Status
from n26.library.models import Picklist, Slot
from n26.library.standard_content import STANDARD_CONTENT
from n26.tests.fixtures import admit_to_founding
from n26.tests.sandbox.actions import (
    create_profile,
    ef_adds,
    found_gang,
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
    STANDARD_CONTENT["lasting-effect-tables"].create()
    return {
        "injury": Picklist.objects.get(name="Lasting Injury Table"),
        "damage": Picklist.objects.get(name="Lasting Damage Table"),
        "escape": Picklist.objects.get(name="Escape Table"),
        "injury_slot": Slot.objects.get(name="Lasting Injury"),
        "damage_slot": Slot.objects.get(name="Lasting Damage"),
        "escape_slot": Slot.objects.get(name="Escape"),
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
def rig(gang, gang_type, vehicle_type):
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


def result_named(table, name):
    return next(m.pickable for m in table.members.all() if m.pickable.name == name)


def add_result(miniature, label, table, name, roll=None):
    slot = choice_of(miniature, label)
    gang = miniature.membership.gang
    with operation(gang, actor=gang.owner) as op:
        return op.choose(
            slot.anchor.assignment,
            result_named(table, name),
            slot=slot.slot,
            miniature=miniature,
            roll=roll,
        )


def fresh(miniature):
    return Miniature.objects.get(pk=miniature.pk)


class TestTheTableAsSeeded:
    def test_the_escape_table_is_a_d6_band_table_of_three_results(self, tables):
        table = tables["escape"]
        assert table.dice == "d6"
        assert [
            (m.roll_low, m.roll_high, m.pickable.name)
            for m in table.members.order_by("position")
        ] == [(1, 1, "Executed"), (2, 4, "Ransomed"), (5, 6, "Daring Escape")]

    def test_the_choice_takes_one_pick(self, tables):
        assert (tables["escape_slot"].min_picks, tables["escape_slot"].max_picks) == (
            0,
            1,
        )

    def test_each_result_sets_a_status(self, tables):
        from n26.library.standard_content import ESCAPE_STATUSES

        for member in tables["escape"].members.select_related("pickable"):
            carried = [
                m.effect.status
                for m in member.pickable.modifiers.all()
                if m.op_sets_status_id is not None
            ]
            assert carried == [ESCAPE_STATUSES[member.pickable.name]]

    def test_captured_on_both_tables_grants_the_escape_choice(self, tables):
        for table in (tables["injury"], tables["damage"]):
            captured = result_named(table, "Captured")
            grants = [
                m.effect.slot
                for m in captured.modifiers.all()
                if m.adds_assignable_id is not None
            ]
            assert grants == [tables["escape_slot"]]

    def test_the_seed_runs_again_without_doubling(self, tables):
        from n26.library.models import Modifier

        before = Modifier.objects.count()
        STANDARD_CONTENT["lasting-effect-tables"].create()
        assert Modifier.objects.count() == before
        present, total = STANDARD_CONTENT["lasting-effect-tables"].check()
        assert present == total


class TestACapturedModel:
    def test_captured_puts_an_escape_row_on_the_card(self, gang, krago, tables):
        assert choice_of(krago, "Escape") is None
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        assert fresh(krago).status == Status.CAPTURED
        escape = choice_of(krago, "Escape")
        assert escape is not None
        assert escape.slot.picklist.dice == "d6"
        assert_reconciled(gang)

    def test_nobody_else_grows_an_escape_row(self, gang, krago, rig, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        assert choice_of(rig, "Escape") is None

    def test_a_captured_vehicle_rolls_too(self, gang, rig, tables):
        add_result(rig, "Lasting Damage", tables["damage"], "Captured")
        assert choice_of(rig, "Escape") is not None

    def test_executed_kills(self, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        add_result(krago, "Escape", tables["escape"], "Executed")
        assert fresh(krago).status == Status.DEAD
        assert_reconciled(gang)

    def test_a_daring_escape_is_recovery(self, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        add_result(krago, "Escape", tables["escape"], "Daring Escape")
        assert fresh(krago).status == Status.RECOVERY

    def test_ransomed_waits_on_the_payment(self, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        add_result(krago, "Escape", tables["escape"], "Ransomed")
        assert fresh(krago).status == Status.RANSOMED

    def test_the_roll_the_pick_and_the_status_are_one_story(self, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        escape = choice_of(krago, "Escape")
        with operation(gang, actor=gang.owner) as op:
            rolled = op.roll(escape.slot, miniature=krago, rolled=1)
        add_result(krago, "Escape", tables["escape"], "Executed", roll=rolled)
        kinds = list(
            LedgerEvent.objects.filter(gang=gang)
            .order_by("created", "id")
            .values_list("kind", flat=True)
        )[-3:]
        assert kinds == [
            LedgerEvent.Kind.ROLLED,
            LedgerEvent.Kind.GRANTED,
            LedgerEvent.Kind.STATUS_SET,
        ]


class TestThePage:
    @pytest.fixture(autouse=True)
    def admitted(self, owner):
        """The status controls reach the owners the founding flag admits."""
        admit_to_founding(owner)

    def test_the_escape_row_offers_to_roll_a_d6(
        self, client, owner, gang, krago, tables
    ):
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        escape = choice_of(krago, "Escape")
        address = reverse(
            "n26-choose",
            args=[
                gang.pk,
                f"{krago.pk}:{escape.anchor.assignment.pk}:{escape.identity.pk}",
            ],
        )
        client.force_login(owner)
        page = client.get(address).content.decode()
        assert "Roll a D6" in page
        assert "Executed" in page and "Daring Escape" in page

        client.post(address, {"act": "enter", "rolled": "6"})
        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.ROLLED)
        page = client.get(f"{address}?roll={event.pk}").content.decode()
        # One pick, so the page is radios with the landed row lifted and
        # already checked — Save is the Add — rather than a several-pick
        # list with an Add of its own.
        assert "Landed on" in page
        assert page.index("Landed on") < page.index("Daring Escape")
        checked = re.search(r'<input[^>]*name="thing"[^>]*checked[^>]*>', page)
        assert checked and "Daring Escape" not in checked.group(0)  # value is a key
        key = re.search(r'value="([^"]+)"', checked.group(0)).group(1)
        assert key == option_key(result_named(tables["escape"], "Daring Escape"))

    def test_the_captured_card_says_what_to_do(
        self, client, owner, gang, krago, tables
    ):
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        client.force_login(owner)
        page = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Captured" in page
        assert ">Escape<" in page


def lasting_rows(card):
    return [line for line in card.row_questions if line.is_lasting_effect]


class TestLastingEffectRowsOnTheCard:
    """Every model carries a lasting-effect choice. A card away from the
    model's own screens draws it only once something has been chosen."""

    def test_an_unaffected_card_has_no_lasting_effect_row(self, gang, krago, tables):
        card = build_model_card(krago, computed=computed_for(krago))
        assert lasting_rows(card) == []

    def test_the_models_own_screens_keep_the_open_choice(self, gang, krago, tables):
        card = build_model_card(
            krago, computed=computed_for(krago), open_lasting_effects=True
        )
        assert [line.kind_label for line in lasting_rows(card)] == ["Lasting Injuries"]

    def test_an_injury_the_model_has_stays_on_the_card(self, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Eye Injury")
        card = build_model_card(krago, computed=computed_for(krago))
        assert [line.chosen for line in lasting_rows(card)] == ["Eye Injury"]

    def test_the_escape_row_is_not_a_lasting_effect(self, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        card = build_model_card(krago, computed=computed_for(krago))
        assert "Escape" in [line.kind_label for line in card.row_questions]

    def test_the_sheet_leaves_it_off_and_edit_offers_it(
        self, client, owner, gang, krago, tables
    ):
        admit_to_founding(owner)
        client.force_login(owner)
        sheet = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Lasting Injuries" not in sheet
        edit = client.get(reverse("n26-edit-fighter", args=[krago.pk]))
        assert "Lasting Injuries" in edit.content.decode()


def held_names(miniature):
    from n26.core.models import Assignment

    return sorted(
        Assignment.objects.filter(
            miniature=miniature, archived=False, pickable__isnull=False
        ).values_list("pickable__name", flat=True)
    )


class TestLeavingCapturedByHand:
    """Captured only sets up the Escape roll. A model the owner takes out
    of Captured before that roll is no longer captured, so the result and
    its Escape choice go; once the roll is recorded, both stay."""

    @pytest.fixture(autouse=True)
    def admitted(self, owner):
        admit_to_founding(owner)

    def mark(self, client, owner, miniature, status):
        client.force_login(owner)
        return client.post(
            reverse("n26-mark-fighter", args=[miniature.pk]), {"status": status}
        )

    def test_the_unrolled_capture_goes_with_its_escape_row(
        self, client, owner, gang, krago, tables
    ):
        add_result(krago, "Lasting Injuries", tables["injury"], "Eye Injury")
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        self.mark(client, owner, krago, "active")
        assert fresh(krago).status == Status.ACTIVE
        assert held_names(krago) == ["Eye Injury"]
        assert choice_of(krago, "Escape") is None
        assert_reconciled(gang)

    def test_the_history_keeps_the_capture_and_its_removal(
        self, client, owner, gang, krago, tables
    ):
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        self.mark(client, owner, krago, "recovery")
        kinds = list(
            LedgerEvent.objects.filter(gang=gang)
            .order_by("created", "id")
            .values_list("kind", flat=True)
        )
        assert LedgerEvent.Kind.GRANTED in kinds
        assert kinds[-2:] == [LedgerEvent.Kind.REMOVED, LedgerEvent.Kind.STATUS_SET]

    def test_a_rolled_capture_stays(self, client, owner, gang, krago, tables):
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        add_result(krago, "Escape", tables["escape"], "Ransomed")
        self.mark(client, owner, krago, "active")
        assert fresh(krago).status == Status.ACTIVE
        assert held_names(krago) == ["Captured", "Ransomed"]

    def test_only_a_captured_model_is_released(
        self, client, owner, gang, krago, tables
    ):
        add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
        with operation(gang, actor=owner) as op:
            op.set_status(krago, Status.RECOVERY)
        self.mark(client, owner, krago, "active")
        assert held_names(krago) == ["Captured"]

    def test_a_vehicle_is_released_too(self, client, owner, gang, rig, tables):
        add_result(rig, "Lasting Damage", tables["damage"], "Captured")
        self.mark(client, owner, rig, "active")
        assert held_names(rig) == []
        assert choice_of(rig, "Escape") is None
