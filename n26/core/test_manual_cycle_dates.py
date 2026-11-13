"""Cycle transitions are explicit, with or without planning dates."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from n26.core import schedule as s

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def manual():
    return s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="manual",
        current_position=None,
        mode="repeating",
    ).schedule


def test_undated_cycles_can_be_saved_started_and_advanced():
    state = manual()
    saved, selected = s._ensure_saved(state, s.project(state)[3].ref)
    assert len(saved.created) == 4
    assert saved.transition is None
    assert saved.schedule.current is None
    started = s.start(saved.schedule, now=NOW)
    advanced = s.advance(started.schedule, now=NOW)
    assert advanced.schedule.current.order == 2
    assert advanced.schedule.cycles[-1].id == selected.id
    assert all(
        c.details.starts_on is c.details.ends_on is None
        for c in advanced.schedule.cycles
    )
    state = s.start(state, now=NOW).schedule
    advanced = s.advance(state, now=NOW)
    assert advanced.created[0].order == 2
    assert advanced.created[0].details.starts_on is None


def test_disabling_planning_dates_retains_saved_dates_and_only_clears_projections():
    state = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="dated",
        current_position=2,
        mode="repeating",
        calendar=s.CycleCalendar(date(2026, 11, 1)),
    ).schedule
    unchanged = s.replace_plan(state, steps=state.plan.steps, mode="repeating").schedule
    assert unchanged == state
    cleared = s.replace_plan(
        state, steps=state.plan.steps, mode="repeating", clear_calendar=True
    )
    assert cleared.schedule.cycles == state.cycles
    assert cleared.schedule.plan == state.plan
    assert cleared.schedule.calendar is None
    assert cleared.schedule.revision == state.revision + 1
    assert cleared.updated == ()
    assert s.project(cleared.schedule)[0].starts_on is None
    again = s.replace_plan(
        cleared.schedule, steps=state.plan.steps, mode="repeating", clear_calendar=True
    )
    assert again.schedule == cleared.schedule


def test_enabling_future_dates_keeps_saved_dated_and_undated_cycles():
    state = s.start(manual(), now=NOW).schedule
    state = s.advance(state, now=NOW).schedule
    first = state.cycles[0]
    state = s.edit_cycle(
        state,
        s.SavedCycleRef(first.id),
        replace(first.details, starts_on=date(2026, 11, 1), ends_on=date(2026, 11, 7)),
    ).schedule
    planned = s.replace_plan(
        state,
        steps=state.plan.steps,
        mode="repeating",
        calendar=s.CycleCalendar(date(2026, 12, 1), starts_after_order=2),
    )
    assert planned.schedule.cycles == state.cycles
    assert planned.updated == ()
    assert s.project(planned.schedule)[0].starts_on == date(2026, 12, 1)
    assert s.advance(
        planned.schedule, now=NOW
    ).schedule.current.details.starts_on == date(2026, 12, 1)


@pytest.mark.parametrize("projected", [False, True])
def test_manual_date_edits_reject_known_overlap_with_partial_or_complete_ranges(
    projected,
):
    state = s.start(manual(), now=NOW).schedule
    first = state.current
    state = s.edit_cycle(
        state,
        s.SavedCycleRef(first.id),
        replace(first.details, starts_on=date(2026, 11, 1), ends_on=date(2026, 11, 7)),
    ).schedule
    if projected:
        target = s.project(state)[0]
        ref, details = target.ref, s.CycleDetails(target.phase_id)
    else:
        state = s.advance(state, now=NOW).schedule
        ref, details = s.SavedCycleRef(state.current.id), state.current.details
    with pytest.raises(s.ScheduleError, match="overlap"):
        s.edit_cycle(state, ref, replace(details, starts_on=date(2026, 11, 2)))
    with pytest.raises(s.ScheduleError, match="overlap"):
        s.edit_cycle(
            state,
            ref,
            replace(details, starts_on=date(2026, 11, 2), ends_on=date(2026, 11, 8)),
        )


def test_clearing_dates_keeps_cycle_identity_without_inheriting_calendar_dates():
    state = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="dated",
        current_position=0,
        calendar=s.CycleCalendar(date(2026, 11, 1)),
    ).schedule
    first = state.current
    details = replace(first.details, starts_on=None, ends_on=None)
    cleared = s.edit_cycle(state, s.SavedCycleRef(first.id), details)
    assert cleared.schedule.current.id == first.id
    assert cleared.schedule.current.details.starts_on is None
    assert cleared.schedule.current.details.ends_on is None
    assert cleared.transition is None


@pytest.mark.parametrize("clear", [False, True])
def test_partial_ranges_can_be_edited_or_cleared_independently(clear):
    state = manual()
    state, _cycle = s._ensure_saved(state, s.project(state)[1].ref)
    state = state.schedule
    first, second = state.cycles
    first = replace(first, details=replace(first.details, starts_on=date(2026, 11, 1)))
    second = replace(
        second, details=replace(second.details, ends_on=date(2026, 11, 14))
    )
    state = replace(state, cycles=(first, second))
    details = (
        replace(first.details, starts_on=None, ends_on=None)
        if clear
        else replace(first.details, ends_on=date(2026, 11, 7))
    )
    repaired = s.edit_cycle(state, s.SavedCycleRef(first.id), details).schedule
    assert repaired.cycles[1] == second
    repaired = s.edit_cycle(
        repaired,
        s.SavedCycleRef(second.id),
        replace(second.details, starts_on=date(2026, 11, 8)),
    ).schedule
    assert repaired.cycles[1].details.starts_on == date(2026, 11, 8)
    planned = s.replace_plan(
        state,
        steps=state.plan.steps,
        mode="repeating",
        calendar=s.CycleCalendar(date(2026, 12, 1), starts_after_order=2),
    ).schedule
    assert planned.cycles == state.cycles
