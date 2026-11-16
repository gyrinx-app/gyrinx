"""Locked timeline commands preserve persisted identities, references and exact retries."""

from dataclasses import asdict, replace
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gyrinx.site.models import Availability, FeatureFlag, Notification
from n26.core import cycles
from n26.core import schedule as s
from n26.core.campaigns import campaign_operation
from n26.core.cycle_data import template_data
from n26.core.models import (
    Battle,
    BattleCommand,
    Campaign,
    CampaignCycle,
    CampaignCycleCommand,
    CampaignCycleDelivery,
    CampaignCycleTransition,
    CampaignEvent,
    CampaignPhase,
    CampaignPhaseOccurrence,
    CampaignPlan,
    CampaignSchedule,
)
from n26.core.operations import Refusal
from n26.flags import CYCLE_TRACKING
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def table(campaign_type):
    owner = User.objects.create_user("timeline-arbitrator")
    flag = FeatureFlag.objects.create(
        slug=CYCLE_TRACKING, name="Campaign cycles", availability=Availability.EVERYONE
    )
    campaign = found_campaign("Editable Ash Road", campaign_type, owner=owner)
    cycles.configure(
        campaign,
        actor=owner,
        template_id="",
        definition=template_data(s.DEFAULT_TEMPLATE),
        current_position=0,
        mode="fixed",
        request_key=uuid4(),
    )
    return SimpleNamespace(
        owner=owner, campaign=campaign, flag=flag, state=cycles.load(campaign)
    )


def command(
    table, action, *, expected_revision=None, request_key=None, actor=None, **kwargs
):
    return cycles.author_timeline(
        table.campaign,
        actor=actor or table.owner,
        action=action,
        expected_revision=cycles.load(table.campaign).revision
        if expected_revision is None
        else expected_revision,
        request_key=request_key or uuid4(),
        **kwargs,
    )


def rows(model, **filters):
    return list(model.objects.filter(**filters).order_by("pk").values())


def snapshot(table):
    campaign_models = (
        CampaignCycle,
        CampaignCycleCommand,
        CampaignCycleTransition,
        CampaignEvent,
        CampaignPhase,
        CampaignPhaseOccurrence,
        CampaignPlan,
        CampaignSchedule,
        Battle,
        BattleCommand,
    )
    return {
        model.__name__: rows(model, campaign=table.campaign)
        for model in campaign_models
    } | {
        "campaign": rows(Campaign, pk=table.campaign.pk),
        "deliveries": rows(CampaignCycleDelivery),
        "notifications": rows(Notification),
    }


def live(table):
    return list(
        CampaignCycle.objects.filter(campaign=table.campaign, archived=False).order_by(
            "order"
        )
    )


class TestTimelinePersistence:
    """Concrete entries stay editable without changing their generated audit identity."""

    def test_an_authored_insert_has_no_generated_source_and_does_not_consume_the_cursor(
        self, table
    ):
        before = table.state
        destination = before.occurrences[-1]
        details = s.CycleDetails(
            destination.id,
            custom_name="Market week",
            description="",
            effects="Extra trade",
        )
        result = command(
            table,
            "insert_cycle",
            occurrence_id=destination.id,
            after_cycle_id=before.cycles[-1].id,
            details=details,
        )
        saved = CampaignCycle.objects.get(pk=result.cycle_id)
        assert saved.source_plan_id is saved.source_position is None
        assert saved.source_step == "" and saved.repetition == saved.step_position == 0
        assert str(saved.phase_occurrence_id) == destination.id
        assert str(saved.phase_id) == destination.phase_id
        assert (
            saved.custom_name == "Market week"
            and saved.description == ""
            and saved.effects == "Extra trade"
        )
        assert set(saved.customized_fields) == set(s.CycleDetails.__dataclass_fields__)
        assert saved.order == 8
        reloaded = cycles.load(table.campaign)
        assert (
            reloaded.next_position == before.next_position
            and reloaded.plan == before.plan
        )
        assert reloaded.current_cycle_id == before.current_cycle_id
        assert [c.order for c in reloaded.cycles if not c.archived] == list(range(1, 9))
        assert s.project(reloaded) == ()
        assert not CampaignCycleTransition.objects.exists()
        assert not CampaignCycleDelivery.objects.exists()

    def test_block_then_cycle_reordering_persists_stable_ids_and_immediate_unique_ordinals(
        self, table
    ):
        before = table.state
        first, middle, last = before.occurrences
        sources = {c.id: c.source for c in before.cycles}
        command(
            table,
            "move_occurrence",
            occurrence_id=last.id,
            after_occurrence_id=first.id,
        )
        expected = [
            c.id for c in before.cycles[:3] + before.cycles[4:] + before.cycles[3:4]
        ]
        assert [str(c.pk) for c in live(table)] == expected
        assert [c.order for c in live(table)] == list(range(1, 8))
        assert list(
            CampaignPhaseOccurrence.objects.filter(
                campaign=table.campaign, archived=False
            )
            .order_by("position")
            .values_list("position", flat=True)
        ) == [1, 2, 3]
        selected = before.cycles[5]
        command(
            table,
            "move_cycle",
            cycle_id=selected.id,
            occurrence_id=middle.id,
            after_cycle_id=before.cycles[3].id,
        )
        saved = CampaignCycle.objects.get(pk=selected.id)
        assert (
            str(saved.phase_occurrence_id) == middle.id
            and str(saved.phase_id) == middle.phase_id
        )
        assert "phase_id" in saved.customized_fields
        after = cycles.load(table.campaign)
        assert {c.id for c in after.cycles} == {c.id for c in before.cycles}
        assert {c.id: c.source for c in after.cycles} == sources
        assert [c.order for c in live(table)] == list(range(1, 8))
        assert after.current_cycle_id == before.current_cycle_id
        assert not CampaignCycleTransition.objects.exists()
        assert not CampaignCycleDelivery.objects.exists()

    def test_a_used_block_split_keeps_current_recorded_links_and_transition_receipts(
        self, table
    ):
        start_key = uuid4()
        cycles.start(
            table.campaign,
            actor=table.owner,
            expected_current=table.state.current_cycle_id,
            expected_revision=table.state.revision,
            request_key=start_key,
        )
        before = cycles.load(table.campaign)
        recorded = before.cycles[1]
        with campaign_operation(table.campaign, actor=table.owner) as act:
            battle = act.record_battle(
                date=date(2026, 11, 15),
                scenario="Recorded encounter",
                cycle=s.SavedCycleRef(recorded.id),
            )
        # Battle receipts have no separate public construction verb.
        BattleCommand.objects.create(
            campaign=table.campaign,
            actor=table.owner,
            battle=battle,
            request_key=uuid4(),
            kind="create",
            inputs={"cycle": recorded.id},
            revision=battle.revision,
        )
        history = {
            "battle": rows(Battle, pk=battle.pk),
            "battle_commands": rows(BattleCommand),
            "transitions": rows(CampaignCycleTransition),
            "deliveries": rows(CampaignCycleDelivery),
            "start_receipt": rows(CampaignCycleCommand, request_key=start_key),
        }
        original_phase = before.phases[0]
        details = s.PhaseDetails(
            "Later occupation",
            "Future story",
            "Future rules",
            s.RewardSettings(entry_credits=s.CreditAmount(250)),
        )
        command(
            table,
            "edit_occurrence",
            occurrence_id=before.occurrences[0].id,
            details=details,
        )
        after = cycles.load(table.campaign)
        assert after.current_cycle_id == before.current_cycle_id
        assert after.cycles[:2] == before.cycles[:2]
        future = after.cycles[2]
        assert (
            future.id == before.cycles[2].id
            and future.source == before.cycles[2].source
        )
        assert future.occurrence_id != before.occurrences[0].id
        assert future.details.phase_id != original_phase.id
        assert (
            next(p for p in after.phases if p.id == future.details.phase_id).details
            == details
        )
        assert (
            next(p for p in after.phases if p.id == original_phase.id) == original_phase
        )
        assert [c.order for c in live(table)] == list(range(1, 8))
        assert rows(Battle, pk=battle.pk) == history["battle"]
        assert rows(BattleCommand) == history["battle_commands"]
        assert rows(CampaignCycleTransition) == history["transitions"]
        assert rows(CampaignCycleDelivery) == history["deliveries"]
        assert (
            rows(CampaignCycleCommand, request_key=start_key)
            == history["start_receipt"]
        )
        assert str(Battle.objects.get(pk=battle.pk).cycle_id) == recorded.id


class TestTimelineRetriesAndRefusals:
    """Receipts settle earlier commands before removed targets or stale baselines matter."""

    def test_copy_retry_after_source_removal_keeps_the_same_copy_and_rejects_changed_input(
        self, table
    ):
        before = table.state
        source = before.cycles[-1]
        key = uuid4()
        arguments = {
            "cycle_id": source.id,
            "occurrence_id": source.occurrence_id,
            "clear_dates": True,
        }
        result = command(
            table,
            "duplicate_cycle",
            expected_revision=before.revision,
            request_key=key,
            **arguments,
        )
        command(table, "remove_cycle", cycle_id=source.id)
        assert CampaignCycle.objects.get(pk=source.id).archived
        after_removal = snapshot(table)
        replay = command(
            table,
            "duplicate_cycle",
            expected_revision=before.revision,
            request_key=key,
            **arguments,
        )
        assert (
            replay.replayed
            and replay.cycle_id == result.cycle_id
            and replay.revision == result.revision
        )
        assert snapshot(table) == after_removal
        changed = {**arguments, "clear_dates": False}
        with pytest.raises(cycles.CycleKeyConflict):
            command(
                table,
                "duplicate_cycle",
                expected_revision=before.revision,
                request_key=key,
                **changed,
            )
        assert snapshot(table) == after_removal
        assert (
            CampaignCycle.objects.filter(pk=result.cycle_id, archived=False).count()
            == 1
        )

    def test_legacy_phase_receipt_replays_after_its_occurrence_is_removed(self, table):
        before = table.state
        block = before.occurrences[1]
        details = s.PhaseDetails("Edited downtime", "Story", "Rules")
        key = uuid4()
        receipt = {"phase": block.phase_id, "details": asdict(details)}
        arguments = {
            "occurrence_id": block.id,
            "details": details,
            "receipt_inputs": receipt,
        }
        result = command(
            table,
            "edit_occurrence",
            expected_revision=before.revision,
            request_key=key,
            **arguments,
        )
        stored = CampaignCycleCommand.objects.get(
            campaign=table.campaign, request_key=key
        )
        assert stored.kind == "edit_phase"
        assert stored.inputs == {**receipt, "expected_revision": before.revision}
        command(table, "remove_occurrence", occurrence_id=block.id)
        assert CampaignPhaseOccurrence.objects.get(pk=block.id).archived
        current = snapshot(table)
        arguments["occurrence_id"] = block.phase_id
        replay = command(
            table,
            "edit_occurrence",
            expected_revision=before.revision,
            request_key=key,
            **arguments,
        )
        assert replay.replayed and replay.revision == result.revision
        assert snapshot(table) == current

    @pytest.mark.parametrize("refusal", ["player", "flag", "stale"])
    def test_unauthorised_closed_flag_and_stale_requests_write_nothing(
        self, table, refusal
    ):
        actor = table.owner
        if refusal == "player":
            actor = User.objects.create_user("timeline-player")
            with campaign_operation(table.campaign, actor=table.owner) as act:
                act.invite(actor)
            with campaign_operation(table.campaign, actor=actor) as act:
                act.answer_invitation(actor, True)
        if refusal == "flag":
            table.flag.availability = Availability.OFF
            table.flag.save()
        before = snapshot(table)
        with pytest.raises(Refusal):
            command(
                table,
                "insert_cycle",
                actor=actor,
                occurrence_id=table.state.occurrences[-1].id,
                after_cycle_id=table.state.cycles[-1].id,
                expected_revision=table.state.revision - 1
                if refusal == "stale"
                else table.state.revision,
            )
        assert snapshot(table) == before

    def test_used_cycle_removal_refuses_without_changing_history_or_any_other_rows(
        self, table
    ):
        with campaign_operation(table.campaign, actor=table.owner) as act:
            battle = act.record_battle(
                date=date(2026, 11, 15),
                scenario="Future recorded encounter",
                cycle=s.SavedCycleRef(table.state.cycles[4].id),
            )
        before = snapshot(table)
        with pytest.raises(Refusal, match="recorded activity"):
            command(table, "remove_cycle", cycle_id=str(battle.cycle_id))
        assert snapshot(table) == before


class TestTimelineCopyDates:
    """A copied date conflict is validated; clearing copied dates is an explicit choice."""

    def test_dated_cycle_copy_rolls_back_then_explicit_blank_dates_persist(self, table):
        source = table.state.cycles[4]
        details = replace(
            source.details, starts_on=date(2026, 12, 1), ends_on=date(2026, 12, 7)
        )
        cycles.edit_cycle(
            table.campaign,
            actor=table.owner,
            target=s.SavedCycleRef(source.id),
            details=details,
            expected_revision=table.state.revision,
            request_key=uuid4(),
        )
        before = snapshot(table)
        with pytest.raises(Refusal, match="overlap"):
            command(
                table,
                "duplicate_cycle",
                cycle_id=source.id,
                occurrence_id=source.occurrence_id,
                clear_dates=False,
            )
        assert snapshot(table) == before
        copied = command(
            table,
            "duplicate_cycle",
            cycle_id=source.id,
            occurrence_id=source.occurrence_id,
            clear_dates=True,
        )
        saved = CampaignCycle.objects.get(pk=copied.cycle_id)
        assert saved.starts_on is saved.ends_on is None
        assert {"starts_on", "ends_on"} <= set(saved.customized_fields)
        original = CampaignCycle.objects.get(pk=source.id)
        assert (original.starts_on, original.ends_on) == (
            date(2026, 12, 1),
            date(2026, 12, 7),
        )
        assert saved.source_plan_id is saved.source_position is None


class TestAdoptingEarlierWriterRows:
    """Rolling deployment metadata is deterministic on reads and persists on an explicit command."""

    def test_reads_adopt_old_writer_cycles_and_empty_phases_without_database_writes(
        self, table
    ):
        # These nullable metadata rows reproduce a preceding deployment's writer.
        phase = CampaignPhase.objects.create(
            campaign=table.campaign, name="Older authored phase", rewards={}
        )
        legacy = CampaignCycle.objects.create(
            campaign=table.campaign,
            phase=phase,
            order=8,
            custom_name="Older authored cycle",
            description="Keep this story",
        )
        empty = CampaignPhase.objects.create(
            campaign=table.campaign, name="Older empty phase", rewards={}
        )
        before = snapshot(table)
        legacy_before = rows(CampaignCycle, pk=legacy.pk)[0]
        with CaptureQueriesContext(connection) as queries:
            first = cycles.load(table.campaign)
            second = cycles.load(table.campaign)
        assert first == second
        assert not [
            q["sql"]
            for q in queries
            if q["sql"].lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}
        ]
        assert snapshot(table) == before
        adopted = next(c for c in first.cycles if c.id == str(legacy.pk))
        block = next(o for o in first.occurrences if o.phase_id == str(phase.pk))
        empty_block = next(o for o in first.occurrences if o.phase_id == str(empty.pk))
        assert adopted.occurrence_id == block.id
        assert adopted.customized_fields == frozenset(
            s.CycleDetails.__dataclass_fields__
        )
        assert not CampaignPhaseOccurrence.objects.filter(
            pk__in=[block.id, empty_block.id]
        ).exists()
        result = command(
            table, "insert_cycle", occurrence_id=empty_block.id, after_cycle_id=None
        )
        assert (
            CampaignPhaseOccurrence.objects.filter(
                pk__in=[block.id, empty_block.id]
            ).count()
            == 2
        )
        legacy.refresh_from_db()
        assert str(legacy.phase_occurrence_id) == block.id
        assert set(legacy.customized_fields) == set(s.CycleDetails.__dataclass_fields__)
        stored = rows(CampaignCycle, pk=legacy.pk)[0]
        changing = {"phase_occurrence_id", "customized_fields", "modified"}
        assert {k: v for k, v in stored.items() if k not in changing} == {
            k: v for k, v in legacy_before.items() if k not in changing
        }
        assert (
            str(CampaignCycle.objects.get(pk=result.cycle_id).phase_occurrence_id)
            == empty_block.id
        )
        reloaded = cycles.load(table.campaign)
        assert len(reloaded.occurrences) == len(first.occurrences)
        assert (
            next(c for c in reloaded.cycles if c.id == str(legacy.pk)).occurrence_id
            == block.id
        )

    def test_editing_an_authored_empty_block_does_not_resurrect_its_old_definition(
        self, table
    ):
        command(table, "insert_occurrence", details=s.PhaseDetails("Festival"))
        before = cycles.load(table.campaign)
        selected = before.occurrences[-1]
        command(
            table,
            "edit_occurrence",
            occurrence_id=selected.id,
            details=s.PhaseDetails("Market festival"),
        )
        old = CampaignPhase.objects.get(pk=selected.phase_id)
        assert old.archived
        first = cycles.load(table.campaign)
        second = cycles.load(table.campaign)
        assert first == second
        assert len(first.occurrences) == len(before.occurrences)
        assert [o.id for o in first.occurrences] == [o.id for o in before.occurrences]
        assert not any(
            o.phase_id == selected.phase_id and not o.archived
            for o in first.occurrences
        )
        assert first.phases[-1].details.name == "Market festival"

    def test_old_phase_bulk_updates_repair_stale_and_reused_blocks_without_changing_facts(
        self, table
    ):
        selected = table.state.cycles[1]
        cycles.edit_cycle(
            table.campaign,
            actor=table.owner,
            target=s.SavedCycleRef(selected.id),
            details=replace(
                selected.details, starts_on=date(2026, 12, 2), ends_on=date(2026, 12, 3)
            ),
            expected_revision=table.state.revision,
            request_key=uuid4(),
        )
        # An earlier writer changed the phase without updating occurrence metadata.
        CampaignCycle.objects.filter(pk=selected.id).update(
            phase_id=table.state.phases[1].id
        )
        before = snapshot(table)
        raw_before = rows(CampaignCycle, campaign=table.campaign)
        with CaptureQueriesContext(connection) as queries:
            first = cycles.load(table.campaign)
            second = cycles.load(table.campaign)
        assert first == second
        assert not [
            q["sql"]
            for q in queries
            if q["sql"].lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}
        ]
        assert snapshot(table) == before
        occurrences = {o.id: o for o in first.occurrences if not o.archived}
        runs = []
        for cycle in first.cycles:
            if cycle.archived:
                continue
            assert occurrences[cycle.occurrence_id].phase_id == cycle.details.phase_id
            if not runs or runs[-1] != cycle.occurrence_id:
                runs.append(cycle.occurrence_id)
        assert len(runs) == len(set(runs))
        assert runs == [o.id for o in first.occurrences if not o.archived]
        assert first.cycles[0].occurrence_id == table.state.cycles[0].occurrence_id
        assert first.cycles[0].occurrence_id != first.cycles[2].occurrence_id
        assert first.cycles[1].details.phase_id == table.state.phases[1].id
        assert first.cycles[1].details.starts_on == date(2026, 12, 2)
        assert first.cycles[1].details.ends_on == date(2026, 12, 3)
        assert first.cycles[1].customized_fields == frozenset(
            s.CycleDetails.__dataclass_fields__
        )
        command(
            table,
            "insert_occurrence",
            details=s.PhaseDetails("After the repaired blocks"),
        )
        raw_after = rows(CampaignCycle, campaign=table.campaign)
        changing = {"phase_occurrence_id", "customized_fields", "modified"}
        assert [
            {k: v for k, v in row.items() if k not in changing} for row in raw_after
        ] == [{k: v for k, v in row.items() if k not in changing} for row in raw_before]
        stored = {
            str(c.pk): c for c in CampaignCycle.objects.filter(campaign=table.campaign)
        }
        for cycle in first.cycles:
            assert str(stored[cycle.id].phase_occurrence_id) == cycle.occurrence_id
            stored[cycle.id].full_clean()
        assert cycles.load(table.campaign).cycles == first.cycles


class TestAddPhaseBoundary:
    """The visible boundary and its hidden placement describe the same insertion."""

    @pytest.mark.parametrize("native", [False, True])
    def test_add_phase_after_the_first_block_inserts_second_without_changing_cycles(
        self, table, client, native
    ):
        from n26.core.cycle_display import editor_url, schedule_url

        client.force_login(table.owner)
        selected = table.state.occurrences[0]
        response = client.get(
            editor_url(table.campaign, "add-phase", after=selected.id)
        )
        assert response.status_code == 200
        page = BeautifulSoup(response.content, "html.parser")
        host = page.select_one('[data-react-name="campaign-schedule"]')
        import json

        editor = json.loads(page.find(id=host["data-react-props"]).string)["editor"]
        assert editor["values"]["after_occurrence_id"] == selected.id
        assert "after=" + selected.id in editor["action"]
        assert "after=" + selected.id in editor["commandHref"]
        before_cycles = rows(CampaignCycle, campaign=table.campaign)
        saved = client.post(
            editor["action"] if native else editor["commandHref"],
            {**editor["values"], "name": "Between phases"},
        )
        assert saved.status_code == (302 if native else 200), saved.content
        assert (saved.url if native else saved.json()["nextUrl"]) == schedule_url(
            table.campaign
        )
        state = cycles.load(table.campaign)
        active = [o for o in state.occurrences if not o.archived]
        assert [
            o.id for o in active if o.id in {v.id for v in table.state.occurrences}
        ] == [o.id for o in table.state.occurrences]
        assert [o.position for o in active] == [1, 2, 3, 4]
        assert active[0].id == selected.id
        assert (
            next(p for p in state.phases if p.id == active[1].phase_id).details.name
            == "Between phases"
        )
        assert not any(c.occurrence_id == active[1].id for c in state.cycles)
        assert rows(CampaignCycle, campaign=table.campaign) == before_cycles
        assert state.current_cycle_id == table.state.current_cycle_id
        current = snapshot(table)
        forged = client.post(
            editor["commandHref"],
            {
                **editor["values"],
                "request_key": str(uuid4()),
                "name": "Forged placement",
                "after_occurrence_id": table.state.occurrences[-1].id,
            },
        )
        assert forged.status_code == 422
        assert "insertion point changed" in str(forged.json()["errors"])
        assert snapshot(table) == current


def test_cycle_selector_uses_the_edited_continuing_phase_block(table):
    from n26.core.cycle_data import ref_data
    from n26.core.cycle_selection import options

    state = table.state
    cycles.replace_plan(
        table.campaign,
        actor=table.owner,
        mode="repeating",
        steps=state.plan.steps,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    state = cycles.load(table.campaign)
    cycles.plan_cycles(
        table.campaign,
        actor=table.owner,
        count=1,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    state = cycles.load(table.campaign)
    tail = next(o for o in reversed(state.occurrences) if not o.archived)
    phase = next(p for p in state.phases if p.id == tail.phase_id)
    command(
        table,
        "edit_occurrence",
        occurrence_id=tail.id,
        details=replace(phase.details, name="Edited opening"),
    )
    state = cycles.load(table.campaign)
    projected = s.project(state, limit=1)[0]
    selected = ref_data(projected.ref)
    choice = next(
        c
        for c in options(table.campaign, selected=selected)["choices"]
        if c["value"] == selected
    )
    assert choice["phase"] == "Edited opening"
    assert choice["order"] == projected.order
