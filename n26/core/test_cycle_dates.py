"""Inclusive calendar ranges are projected, then retained with saved identities."""

from dataclasses import replace
from datetime import date

import pytest

from n26.core import schedule as s
from n26.core.cycle_data import calendar_data, calendar_from_data


def configured(*, current=0, calendar=None):
    return s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="campaign",
        current_position=current,
        mode="repeating",
        calendar=calendar or s.CycleCalendar(date(2026, 11, 1)),
    ).schedule


@pytest.mark.parametrize(
    ("anchor", "index", "start", "end"),
    [
        (date(2026, 1, 31), 1, date(2026, 1, 31), date(2026, 2, 27)),
        (date(2026, 1, 31), 2, date(2026, 2, 28), date(2026, 3, 30)),
        (date(2026, 1, 31), 3, date(2026, 3, 31), date(2026, 4, 29)),
        (date(2028, 1, 31), 2, date(2028, 2, 29), date(2028, 3, 30)),
    ],
)
def test_monthly_boundaries_keep_the_original_day_across_short_and_leap_months(
    anchor, index, start, end
):
    calendar = s.CycleCalendar(anchor, unit="months")
    assert calendar.dates_for(index) == (start, end)
    assert calendar.dates_for(index + 1)[0] > end


def test_weekly_projection_has_dates_without_creating_saved_cycles():
    state = configured()
    projected = s.project(state, limit=2)
    assert (projected[0].starts_on, projected[0].ends_on) == (
        date(2026, 11, 8),
        date(2026, 11, 14),
    )
    assert (projected[1].starts_on, projected[1].ends_on) == (
        date(2026, 11, 15),
        date(2026, 11, 21),
    )
    assert len(state.cycles) == 1


def test_saving_a_projected_cycle_persists_its_prefix_dates_without_advancing():
    state = configured()
    target = s.project(state)[3]
    change, selected = s._ensure_saved(state, target.ref)
    assert selected.order == 5
    assert [
        (cycle.details.starts_on, cycle.details.ends_on) for cycle in change.created
    ] == [state.calendar.dates_for(order) for order in range(2, 6)]
    assert change.schedule.current_cycle_id == state.current_cycle_id
    assert change.transition is None
    assert s._ensure_saved(change.schedule, target.ref)[0].created == ()


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2026, 11, 7), date(2026, 11, 10)),
        (date(2026, 11, 1), date(2026, 11, 7)),
        (date(2026, 10, 30), date(2026, 11, 30)),
    ],
)
def test_overlapping_or_shared_end_dates_are_refused_across_saved_cycles(start, end):
    state = configured(current=2)
    selected = state.cycles[1]
    with pytest.raises(s.ScheduleError, match="overlap"):
        s.edit_cycle(
            state,
            s.SavedCycleRef(selected.id),
            replace(selected.details, starts_on=start, ends_on=end),
        )


def test_adjacent_inclusive_ranges_are_valid_but_missing_an_end_date_is_not():
    state = configured(current=2)
    assert state.cycles[0].details.ends_on < state.cycles[1].details.starts_on
    selected = state.cycles[1]
    with pytest.raises(s.ScheduleError, match="both dates"):
        s.edit_cycle(
            state, s.SavedCycleRef(selected.id), replace(selected.details, ends_on=None)
        )


def test_future_calendar_changes_preserve_saved_dates_ids_and_plan_sources():
    state = configured(current=3)
    calendar = s.CycleCalendar(date(2027, 1, 31), unit="months", starts_after_order=4)
    change = s.replace_plan(
        state, steps=state.plan.steps, mode="repeating", calendar=calendar
    )
    assert change.schedule.cycles == state.cycles
    assert change.updated == ()
    projected = s.project(change.schedule)
    assert (projected[0].starts_on, projected[0].ends_on) == (
        date(2027, 1, 31),
        date(2027, 2, 27),
    )
    assert projected[1].starts_on == date(2027, 2, 28)
    assert change.schedule.revision == state.revision + 1


def test_new_timing_cannot_project_over_saved_history():
    state = configured(current=3)
    with pytest.raises(s.ScheduleError, match="after all saved"):
        s.set_calendar(state, s.CycleCalendar(date(2026, 11, 2), starts_after_order=4))


def test_explicit_date_settings_fill_an_undated_saved_prefix_without_inventing_transitions():
    state = s.configure(
        s.DEFAULT_TEMPLATE, campaign_id="legacy", current_position=2
    ).schedule
    change = s.set_calendar(state, s.CycleCalendar(date(2026, 10, 1)))
    assert [cycle.id for cycle in change.schedule.cycles] == [
        cycle.id for cycle in state.cycles
    ]
    assert len(change.updated) == 3
    assert change.schedule.cycles[-1].details.ends_on == date(2026, 10, 21)
    assert change.transition is None


def test_calendar_storage_round_trips_dates_and_rejects_unsupported_fields():
    calendar = s.CycleCalendar(date(2026, 11, 1), 2, "months", 6)
    assert calendar_from_data(calendar_data(calendar)) == calendar
    assert calendar_from_data({}) is None
    with pytest.raises(s.ScheduleError):
        calendar_from_data({**calendar_data(calendar), "automatic": True})
