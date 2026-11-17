"""Saved reorder metadata describes stable, visible gaps without changing history."""

from dataclasses import asdict
from datetime import date
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import cycles, timeline
from n26.core import schedule as s
from n26.core.campaigns import campaign_operation
from n26.core.cycle_data import template_data
from n26.core.cycle_display import SAVED_PAGE_SIZE, build
from n26.core.models import CampaignCycle, CampaignPhaseOccurrence, CampaignSchedule
from n26.flags import CYCLE_TRACKING
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def schedule(campaign_type):
    owner = User.objects.create_user("drag-arbitrator")
    FeatureFlag.objects.create(
        slug=CYCLE_TRACKING, name="Campaign cycles", availability=Availability.EVERYONE
    )
    campaign = found_campaign("Drag timeline", campaign_type, owner=owner)

    def configure(*, template=s.DEFAULT_TEMPLATE, current=None, mode="fixed"):
        cycles.configure(
            campaign,
            actor=owner,
            template_id="",
            definition=template_data(template),
            current_position=current,
            mode=mode,
            request_key=uuid4(),
        )
        return campaign, cycles.load(campaign)

    return configure


def sources(display):
    return {item["id"]: item for item in display.reorder["sources"]}


def targets(display):
    return {item["id"]: item for item in display.reorder["targets"]}


def repeated_template(count=2):
    return s.ScheduleTemplate(
        "Repeated blocks",
        (
            s.Phase("a", s.PhaseDetails("Occupation")),
            s.Phase("b", s.PhaseDetails("Break")),
        ),
        (
            s.PlanStep("a1", "a", count),
            s.PlanStep("b", "b", 1),
            s.PlanStep("a2", "a", count),
        ),
    )


def test_repeated_definitions_and_empty_blocks_have_distinct_stable_destinations(
    schedule,
):
    campaign, state = schedule(template=repeated_template())
    cycles.author_timeline(
        campaign,
        actor=campaign.owner,
        action="insert_occurrence",
        details=s.PhaseDetails("Empty phase"),
        after_occurrence_id=state.occurrences[0].id,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    display = build(campaign, campaign.owner)
    destinations = targets(display)
    repeated = [phase for phase in display.phases if phase["name"] == "Occupation"]
    assert len({phase["phaseId"] for phase in repeated}) == 1
    assert len({phase["id"] for phase in repeated}) == 2
    for phase in repeated:
        assert destinations[f"cycle-start:{phase['id']}"]["occurrenceId"] == phase["id"]
    empty = next(phase for phase in display.phases if phase["name"] == "Empty phase")
    empty_start = f"cycle-start:{empty['id']}"
    assert destinations[empty_start]["afterId"] is None
    assert empty_start in sources(display)[f"cycle:{state.cycles[-1].id}"]["targets"]
    assert display.reorder["revision"] == state.revision

    for source in display.reorder["sources"]:
        assert source["origin"] in destinations
        assert source["origin"] not in source["targets"]
        kind, identity = source["id"].split(":", 1)
        assert all(destinations[key]["kind"] == kind for key in source["targets"])
        assert all(
            destinations[key]["afterId"] != identity for key in source["targets"]
        )


def test_every_offered_structural_move_preserves_protected_history(schedule):
    campaign, state = schedule(current=0)
    with campaign_operation(campaign, actor=campaign.owner) as act:
        act.record_battle(
            date=date(2026, 11, 1),
            scenario="Recorded future",
            cycle=s.SavedCycleRef(state.cycles[3].id),
        )
    state = cycles.load(campaign)
    display = build(campaign, campaign.owner)
    assert {
        item["id"]
        for item in display.reorder["sources"]
        if item["id"].startswith("cycle:")
    } == {f"cycle:{cycle.id}" for cycle in state.cycles if cycle.order > 4}
    destination = targets(display)
    for source in display.reorder["sources"]:
        kind, identity = source["id"].split(":", 1)
        for key in source["targets"]:
            gap = destination[key]
            if kind == "cycle":
                moved = timeline.move_cycle(
                    state, identity, gap["occurrenceId"], after_cycle_id=gap["afterId"]
                )
            else:
                moved = timeline.move_occurrence(
                    state, identity, after_occurrence_id=gap["afterId"]
                )
            assert moved.schedule.current == state.current
            assert (
                next(c for c in moved.schedule.cycles if c.id == state.cycles[3].id)
                == state.cycles[3]
            )
    assert "phase-start" not in destination
    assert all(
        not key.startswith("cycle-start:")
        or gap["occurrenceId"] != state.cycles[0].occurrence_id
        for key, gap in destination.items()
    )


def test_pagination_retains_hidden_origins_without_offering_a_false_block_start(
    schedule,
):
    campaign, state = schedule(template=repeated_template(SAVED_PAGE_SIZE + 2))
    display = build(campaign, campaign.owner, page=2)
    first = state.cycles[SAVED_PAGE_SIZE]
    hidden = state.cycles[SAVED_PAGE_SIZE - 1]
    source = sources(display)[f"cycle:{first.id}"]
    origin = f"cycle-after:{hidden.id}"
    assert source["origin"] == origin
    assert targets(display)[origin]["afterId"] == hidden.id
    assert f"cycle-start:{first.occurrence_id}" not in targets(display)
    assert all(origin not in item["targets"] for item in display.reorder["sources"])
    ordered = [item["id"] for item in display.reorder["targets"]]
    assert ordered.index(origin) < ordered.index(f"cycle-after:{first.id}")


def test_phase_boundary_before_first_visible_group_uses_hidden_preceding_occurrence(
    schedule,
):
    phases = tuple(
        s.Phase(str(index), s.PhaseDetails(f"Phase {index}")) for index in range(3)
    )
    template = s.ScheduleTemplate(
        "Paged phases",
        phases,
        tuple(
            s.PlanStep(str(index), phase.id, SAVED_PAGE_SIZE)
            for index, phase in enumerate(phases)
        ),
    )
    campaign, state = schedule(template=template)
    display = build(campaign, campaign.owner, page=2)
    first, second, third = state.occurrences
    gap = f"phase-after:{first.id}"
    assert gap in targets(display)
    assert "phase-start" not in targets(display)
    assert sources(display)[f"phase:{second.id}"]["origin"] == gap
    assert f"phase:{third.id}" not in sources(display)
    assert f"phase-after:{third.id}" not in targets(display)


def test_projected_cycles_and_blocks_are_not_drag_sources_or_destinations(schedule):
    campaign, state = schedule(current=0, mode="repeating")
    display = build(campaign, campaign.owner)
    assert any(row.state == "Projected" for row in display.rows)
    projected_ids = {row.key for row in display.rows if row.state == "Projected"}
    projected_blocks = {
        phase["id"] for phase in display.phases if phase.get("generated")
    }
    assert not projected_ids & {
        item["id"].split(":", 1)[-1] for item in display.reorder["sources"]
    }
    assert all(
        item["occurrenceId"] not in projected_blocks
        for item in display.reorder["targets"]
    )
    assert all(
        item["afterId"] not in projected_ids for item in display.reorder["targets"]
    )


def test_build_is_read_only_and_metadata_query_growth_is_bounded(schedule):
    campaign, _ = schedule(template=repeated_template(SAVED_PAGE_SIZE + 2))
    owner = campaign.owner
    before = {
        model: list(model.objects.filter(campaign=campaign).order_by("pk").values())
        for model in (CampaignCycle, CampaignPhaseOccurrence, CampaignSchedule)
    }
    captures = []
    for page in (1, 2, 3):
        with CaptureQueriesContext(connection) as capture:
            display = build(campaign, owner, page=page)
            asdict(display)
        captures.append(capture.captured_queries)
    assert len({len(capture) for capture in captures}) == 1
    assert all(
        not query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for capture in captures
        for query in capture
    )
    assert any("LAG(" in query["sql"].upper() for query in captures[0])
    for model, snapshot in before.items():
        assert (
            list(model.objects.filter(campaign=campaign).order_by("pk").values())
            == snapshot
        )


def test_readers_and_unconfigured_campaigns_have_no_reorder_metadata(
    schedule, campaign_type
):
    campaign, _ = schedule()
    reader = User.objects.create_user("drag-reader")
    assert build(campaign, reader).reorder is None
    other = found_campaign("Unconfigured", campaign_type, owner=campaign.owner)
    assert build(other, campaign.owner).reorder is None


def test_phase_move_returns_the_page_containing_its_children(schedule):
    from n26.core import cycle_workflow as workflow

    template = s.ScheduleTemplate(
        "Long timeline",
        tuple(
            s.Phase(key, s.PhaseDetails(key)) for key in ("first", "moving", "later")
        ),
        (
            s.PlanStep("first", "first", 1),
            s.PlanStep("moving", "moving", 49),
            s.PlanStep("later", "later", 100),
        ),
    )
    campaign, state = schedule(template=template, current=0)
    moving = state.occurrences[1]
    original_children = {
        cycle.id for cycle in state.cycles if cycle.occurrence_id == moving.id
    }
    cycles.author_timeline(
        campaign,
        actor=campaign.owner,
        action="insert_occurrence",
        details=s.PhaseDetails("Empty final phase"),
        after_occurrence_id=state.occurrences[-1].id,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    prepared = workflow.prepare(campaign, "move-phase", {"phase": moving.id})
    submitted = workflow.perform(
        campaign,
        campaign.owner,
        "move-phase",
        {**prepared.initial, "after_occurrence_id": state.occurrences[-1].id},
        prepared.query,
    )
    assert submitted.result is not None, submitted.form.errors
    assert (
        workflow.next_url(campaign, "move-phase", submitted)
        == f"{workflow.schedule_url(campaign)}?page=3#phase-{moving.id}"
    )
    display = build(campaign, campaign.owner, page=3)
    assert f"phase:{moving.id}" in sources(display)
    assert {
        row.key for row in display.rows if row.occurrenceId == moving.id
    } == original_children


def test_empty_phase_move_keeps_a_visible_phase_anchor(schedule):
    from n26.core import cycle_workflow as workflow

    campaign, state = schedule(current=0)
    cycles.author_timeline(
        campaign,
        actor=campaign.owner,
        action="insert_occurrence",
        details=s.PhaseDetails("Empty"),
        after_occurrence_id=state.occurrences[0].id,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    moving = next(
        block
        for block in state.occurrences
        if not any(c.occurrence_id == block.id for c in state.cycles)
    )
    prepared = workflow.prepare(campaign, "move-phase", {"phase": moving.id})
    submitted = workflow.perform(
        campaign,
        campaign.owner,
        "move-phase",
        {**prepared.initial, "after_occurrence_id": state.occurrences[-1].id},
        prepared.query,
    )
    assert submitted.result is not None, submitted.form.errors
    assert workflow.next_url(campaign, "move-phase", submitted).endswith(
        f"?page=1#phase-{moving.id}"
    )
    assert f"phase:{moving.id}" in sources(build(campaign, campaign.owner, page=1))
