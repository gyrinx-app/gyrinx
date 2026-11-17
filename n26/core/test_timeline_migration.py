"""The timeline backfill preserves frozen legacy records and their attribution."""

from datetime import UTC, date, datetime
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import override_settings

from n26.core.models import CampaignCycle, CampaignPhaseOccurrence
from n26.library.authoring import create_action
from n26.tests.sandbox.actions import found_campaign, found_gang, hire

pytestmark = pytest.mark.django_db

MIGRATION = "0090_editable_campaign_timeline"


@pytest.fixture
def historical_apps():
    with override_settings(MIGRATION_MODULES={}):
        return MigrationLoader(None).project_state([("n26", MIGRATION)]).apps


@pytest.fixture
def legacy(historical_apps, campaign_type, gang_type, owner, make_profile):
    campaign = found_campaign("Legacy timeline", campaign_type, owner=owner)
    gang = found_gang("Legacy gang", gang_type, owner=owner, budget=1000)
    fighter = hire(gang, make_profile("Legacy profile"), "Legacy fighter")
    action = create_action("Legacy action", "post_cycle")

    def model(name):
        return historical_apps.get_model("n26", name)

    Phase = model("CampaignPhase")
    first = Phase.objects.create(campaign_id=campaign.pk, name="Occupation")
    same_name = Phase.objects.create(campaign_id=campaign.pk, name="Occupation")
    removed = Phase.objects.create(
        campaign_id=campaign.pk,
        name="Removed",
        archived=True,
        archived_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    empty = Phase.objects.create(campaign_id=campaign.pk, name="Authored empty block")
    tail = Phase.objects.create(campaign_id=campaign.pk, name="Unsaved tail")
    archived_empty = Phase.objects.create(
        campaign_id=campaign.pk, name="Archived unused", archived=True
    )
    plan = model("CampaignPlan").objects.create(
        campaign_id=campaign.pk,
        mode="repeating",
        steps=[
            {"id": "a", "phase_id": str(first.pk), "count": 2},
            {"id": "b", "phase_id": str(first.pk), "count": 1},
            {"id": "c", "phase_id": str(same_name.pk), "count": 1},
        ],
    )
    continuation = model("CampaignPlan").objects.create(
        campaign_id=campaign.pk,
        mode="repeating",
        starts_after_order=8,
        steps=[{"id": "tail", "phase_id": str(tail.pk), "count": 3}],
    )
    shapes = [
        (first, "a", 0, False, date(2026, 11, 1), None),
        (first, "a", 0, True, None, date(2026, 11, 7)),
        (first, "b", 0, False, None, None),
        (same_name, "c", 0, False, date(2026, 11, 8), date(2026, 11, 14)),
        (first, "a", 1, False, None, date(2026, 11, 21)),
        (removed, "a", 1, True, None, None),
        (first, "b", 1, True, None, None),
        (first, "c", 1, False, date(2026, 11, 22), None),
    ]
    cycles = [
        model("CampaignCycle").objects.create(
            campaign_id=campaign.pk,
            phase_id=phase.pk,
            order=order,
            custom_name=f"Authored cycle {order}",
            starts_on=start,
            ends_on=end,
            description=f"Description {order}",
            effects=f"Effects {order}",
            archived=archived,
            source_plan_id=plan.pk,
            source_position=order - 1,
            source_step=step,
            repetition=repetition,
            step_position=1 if order in (2, 6) else 0,
        )
        for order, (phase, step, repetition, archived, start, end) in enumerate(
            shapes, 1
        )
    ]
    header = model("CampaignSchedule").objects.create(
        campaign_id=campaign.pk,
        active_plan_id=continuation.pk,
        current_cycle_id=cycles[3].pk,
        next_position=0,
        revision=17,
        date_settings={
            "starts_on": "2026-11-01",
            "interval": 1,
            "unit": "weeks",
            "starts_after_order": 0,
        },
    )
    command = model("CampaignCycleCommand").objects.create(
        campaign_id=campaign.pk,
        actor_id=owner.pk,
        kind="edit_cycle",
        request_key=uuid4(),
        inputs={"expected_revision": 16, "details": {"ends_on": None}},
        result={"revision": 17, "cycle_id": str(cycles[3].pk), "transition_id": None},
    )
    transition = model("CampaignCycleTransition").objects.create(
        campaign_id=campaign.pk,
        command_id=command.pk,
        kind="advanced",
        previous_cycle_id=cycles[0].pk,
        current_cycle_id=cycles[3].pk,
        previous_phase_id=first.pk,
        current_phase_id=same_name.pk,
        actor_id=owner.pk,
        occurred_at=datetime(2026, 11, 8, tzinfo=UTC),
        receipt={"current_cycle": "Original recorded name", "enters_phase": True},
    )
    battle = model("Battle").objects.create(
        campaign_id=campaign.pk, cycle_id=cycles[0].pk, date=date(2026, 11, 2)
    )
    record = model("ActionRecord").objects.create(
        gang_id=gang.pk,
        fighter_id=fighter.pk,
        action_id=action.pk,
        cycle_id=cycles[4].pk,
        request_key=uuid4(),
    )
    event = model("LedgerEvent").objects.create(
        gang_id=gang.pk,
        campaign_id=campaign.pk,
        cycle_id=cycles[4].pk,
        action_record_id=record.pk,
        kind="renamed",
        note="Frozen legacy event",
    )
    return SimpleNamespace(
        apps=historical_apps,
        campaign=campaign,
        phases=(first, same_name, removed, empty, tail, archived_empty),
        plan=plan,
        cycles=cycles,
        header=header,
        command=command,
        transition=transition,
        battle=battle,
        record=record,
        event=event,
    )


def snapshot(model, **filters):
    return list(model.objects.filter(**filters).order_by("pk").values())


def test_historical_backfill_preserves_identity_sources_unknowns_and_recorded_references(
    legacy,
):
    apps = legacy.apps
    Cycle = apps.get_model("n26", "CampaignCycle")
    Occurrence = apps.get_model("n26", "CampaignPhaseOccurrence")
    before_cycles = snapshot(Cycle, campaign_id=legacy.campaign.pk)
    unchanged = {
        name: snapshot(apps.get_model("n26", name))
        for name in (
            "CampaignPlan",
            "CampaignSchedule",
            "CampaignCycleCommand",
            "CampaignCycleTransition",
            "Battle",
            "ActionRecord",
            "LedgerEvent",
        )
    }
    migration = import_module(f"n26.core.migrations.{MIGRATION}")
    with connection.schema_editor(atomic=False) as schema_editor:
        migration.backfill_timeline(apps, schema_editor)

    after_cycles = snapshot(Cycle, campaign_id=legacy.campaign.pk)
    changing = {"phase_occurrence_id", "customized_fields"}
    assert [
        {key: value for key, value in row.items() if key not in changing}
        for row in after_cycles
    ] == [
        {key: value for key, value in row.items() if key not in changing}
        for row in before_cycles
    ]
    assert all(
        row["customized_fields"] == migration.CUSTOMIZED_FIELDS for row in after_cycles
    )
    assert all(row["phase_occurrence_id"] is not None for row in after_cycles)
    active = Cycle.objects.filter(
        campaign_id=legacy.campaign.pk, archived=False
    ).order_by("order")
    assert list(active.values_list("order", flat=True)) == [1, 3, 4, 5, 8]
    for name, before in unchanged.items():
        assert snapshot(apps.get_model("n26", name)) == before

    attached = {
        cycle.pk: Cycle.objects.get(pk=cycle.pk).phase_occurrence_id
        for cycle in legacy.cycles
    }
    assert attached[legacy.cycles[0].pk] == attached[legacy.cycles[1].pk]
    assert len(set(attached.values())) == 7
    assert attached[legacy.cycles[0].pk] != attached[legacy.cycles[2].pk]
    assert attached[legacy.cycles[2].pk] != attached[legacy.cycles[3].pk]
    active_occurrences = Occurrence.objects.filter(
        campaign_id=legacy.campaign.pk, archived=False
    ).order_by("position")
    assert list(active_occurrences.values_list("position", flat=True)) == list(
        range(1, 8)
    )
    assert Occurrence.objects.get(pk=attached[legacy.cycles[6].pk]).archived is False
    assert Occurrence.objects.get(pk=attached[legacy.cycles[5].pk]).archived is True
    assert Occurrence.objects.filter(phase_id=legacy.phases[3].pk).count() == 1
    assert not Occurrence.objects.filter(
        phase_id__in=[legacy.phases[4].pk, legacy.phases[5].pk]
    ).exists()
    first_result = snapshot(Occurrence, campaign_id=legacy.campaign.pk)
    with connection.schema_editor(atomic=False) as schema_editor:
        migration.backfill_timeline(apps, schema_editor)
    assert snapshot(Occurrence, campaign_id=legacy.campaign.pk) == first_result
    assert snapshot(Cycle, campaign_id=legacy.campaign.pk) == after_cycles


def test_authored_cycles_and_archives_do_not_reserve_active_positions(legacy):
    phase = legacy.phases[0]
    occurrence = CampaignPhaseOccurrence.objects.create(
        campaign=legacy.campaign, phase_id=phase.pk, position=1
    )
    CampaignPhaseOccurrence.objects.create(
        campaign=legacy.campaign, phase_id=phase.pk, position=1, archived=True
    )
    authored = CampaignCycle.objects.create(
        campaign=legacy.campaign,
        phase_id=phase.pk,
        phase_occurrence=occurrence,
        order=9,
    )
    assert authored.source_plan_id is authored.source_position is None
    assert authored.source_step == ""
    assert authored.customized_fields == []
    authored.full_clean()
    CampaignCycle.objects.create(
        campaign=legacy.campaign, phase_id=phase.pk, order=9, archived=True
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        CampaignCycle.objects.create(
            campaign=legacy.campaign, phase_id=phase.pk, order=9
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        CampaignPhaseOccurrence.objects.create(
            campaign=legacy.campaign, phase_id=phase.pk, position=1
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        CampaignPhaseOccurrence.objects.create(
            campaign=legacy.campaign, phase_id=phase.pk, position=0
        )


@pytest.mark.parametrize("missing", ["source_plan", "source_position"])
def test_a_generated_source_requires_both_plan_and_position(legacy, missing):
    values = {"source_plan_id": legacy.plan.pk, "source_position": 100}
    values["source_plan_id" if missing == "source_plan" else "source_position"] = None
    with pytest.raises(IntegrityError), transaction.atomic():
        CampaignCycle.objects.create(
            campaign=legacy.campaign, phase_id=legacy.phases[0].pk, order=9, **values
        )


def test_cycle_validation_rejects_an_occurrence_for_another_phase(legacy):
    occurrence = CampaignPhaseOccurrence.objects.create(
        campaign=legacy.campaign, phase_id=legacy.phases[1].pk, position=1
    )
    cycle = CampaignCycle(
        campaign=legacy.campaign,
        phase_id=legacy.phases[0].pk,
        phase_occurrence=occurrence,
        order=9,
    )
    with pytest.raises(ValidationError) as error:
        cycle.clean()
    assert "phase_occurrence" in error.value.message_dict


@pytest.fixture
def metadata_schedule(campaign_type, owner):
    from gyrinx.site.models import Availability, FeatureFlag
    from n26.core import cycles
    from n26.core import schedule as s
    from n26.core.cycle_data import template_data
    from n26.flags import CYCLE_TRACKING

    FeatureFlag.objects.create(
        slug=CYCLE_TRACKING, name="Campaign cycles", availability=Availability.EVERYONE
    )
    campaign = found_campaign("Metadata writer", campaign_type, owner=owner)
    cycles.configure(
        campaign,
        actor=owner,
        template_id="",
        definition=template_data(s.DEFAULT_TEMPLATE),
        current_position=0,
        mode="repeating",
        request_key=uuid4(),
        calendar=s.CycleCalendar(date(2026, 11, 1)),
    )
    return campaign, owner, cycles.load(campaign)


def test_existing_phase_edit_clears_a_block_link_for_the_previous_phase(
    metadata_schedule,
):
    from dataclasses import replace

    from n26.core import cycles
    from n26.core import schedule as s

    campaign, actor, state = metadata_schedule
    selected = state.cycles[0]
    block = CampaignPhaseOccurrence.objects.create(
        campaign=campaign, phase_id=selected.details.phase_id, position=1
    )
    CampaignCycle.objects.filter(pk=selected.id).update(phase_occurrence=block)
    source = (selected.source.position, selected.source.step_id)
    cycles.edit_cycle(
        campaign,
        actor=actor,
        target=s.SavedCycleRef(selected.id),
        details=replace(selected.details, phase_id=state.phases[1].id),
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    stored = CampaignCycle.objects.get(pk=selected.id)
    assert stored.phase_occurrence_id is None
    assert stored.customized_fields == ["phase_id"]
    assert (str(stored.source_plan_id), stored.source_position) == (
        source[0].plan_id,
        source[0].index,
    )
    stored.full_clean()
    block.refresh_from_db()
    assert str(block.phase_id) == selected.details.phase_id


def test_projected_edits_record_cleared_dates_without_marking_untouched_prefix(
    metadata_schedule,
):
    from n26.core import cycles
    from n26.core import schedule as s

    campaign, actor, state = metadata_schedule
    target = s.project(state, limit=2)[-1]
    cycles.edit_cycle(
        campaign,
        actor=actor,
        target=target.ref,
        details=s.CycleDetails(target.phase_id, custom_name="Market week"),
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    stored = list(CampaignCycle.objects.filter(campaign=campaign).order_by("order"))
    assert stored[1].customized_fields == []
    assert set(stored[2].customized_fields) == {"custom_name", "starts_on", "ends_on"}
    assert stored[2].starts_on is stored[2].ends_on is None
    assert stored[2].custom_name == "Market week"
    for cycle in stored:
        cycle.full_clean()
