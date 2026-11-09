"""A configured schedule can wait without activating or inventing any cycle."""

from datetime import UTC, date, datetime

import pytest

from n26.core import schedule as s

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def configured(status="pre_campaign"):
    return s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="waiting",
        current_position=None,
        status=status,
        calendar=s.CycleCalendar(date(2026, 11, 1)),
    ).schedule


@pytest.mark.parametrize("status", ["pre_campaign", "in_progress", "post_campaign"])
def test_no_current_cycle_has_only_previews_and_no_transition(status):
    result = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="waiting",
        current_position=None,
        status=status,
        calendar=s.CycleCalendar(date(2026, 11, 1)),
    )
    assert result.schedule.current is result.schedule.current_phase is None
    assert result.schedule.current_cycle_id is None
    assert result.schedule.cycles == result.created == ()
    assert result.transition is None
    assert [p.order for p in s.project(result.schedule, limit=3)] == [1, 2, 3]


@pytest.mark.parametrize("status", ["pre_campaign", "in_progress"])
def test_starting_materialises_and_activates_the_first_cycle_only(status):
    before = configured(status)
    result = s.start(before, now=NOW)
    assert result.schedule.status == "in_progress"
    assert len(result.created) == 1
    assert result.schedule.current.order == result.schedule.next_position == 1
    assert result.transition.kind == "started"
    assert result.transition.previous_cycle is None


def test_materialising_before_start_keeps_every_saved_cycle_in_the_future():
    before = configured()
    saved, _ = s._ensure_saved(before, s.project(before, limit=4)[-1].ref)
    assert len(saved.created) == 4
    assert saved.schedule.current is None
    assert saved.transition is None
    started = s.start(saved.schedule, now=NOW)
    assert started.created == ()
    assert started.schedule.next_position == saved.schedule.next_position
    assert started.schedule.current.id == saved.schedule.cycles[0].id
    assert started.schedule.cycles == saved.schedule.cycles


def test_waiting_schedule_supports_calendar_and_pattern_edits():
    before = configured()
    after = s.replace_plan(
        before,
        mode="repeating",
        steps=before.plan.steps,
        calendar=s.CycleCalendar(date(2027, 1, 31), unit="months"),
    ).schedule
    assert after.current is None
    assert s.project(after, limit=1)[0].starts_on == date(2027, 1, 31)


def test_finishing_without_starting_a_cycle_does_not_invent_a_transition():
    result = s.finish(configured("in_progress"), now=NOW)
    assert result.schedule.status == "post_campaign"
    assert result.transition is None
    assert result.schedule.current is None
