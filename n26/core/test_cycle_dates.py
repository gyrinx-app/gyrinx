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


def test_legacy_overlap_can_be_repaired_without_blocking_on_another_old_overlap():
    legacy = s.configure(
        s.DEFAULT_TEMPLATE, campaign_id="legacy", current_position=3
    ).schedule
    ranges = [(1, 10), (5, 14), (20, 25), (21, 28)]
    legacy = replace(
        legacy,
        cycles=tuple(
            replace(
                cycle,
                details=replace(
                    cycle.details,
                    starts_on=date(2026, 11, start),
                    ends_on=date(2026, 11, end),
                ),
            )
            for cycle, (start, end) in zip(legacy.cycles, ranges, strict=True)
        ),
    )
    selected = legacy.cycles[0]
    repaired = s.edit_cycle(
        legacy,
        s.SavedCycleRef(selected.id),
        replace(
            selected.details, starts_on=date(2026, 10, 1), ends_on=date(2026, 10, 7)
        ),
    )
    assert repaired.schedule.cycles[1:] == legacy.cycles[1:]
    with pytest.raises(s.ScheduleError, match="overlap"):
        s.edit_cycle(
            legacy,
            s.SavedCycleRef(selected.id),
            replace(
                selected.details, starts_on=date(2026, 11, 3), ends_on=date(2026, 11, 8)
            ),
        )


def test_projected_edit_validates_submitted_dates_before_temporary_defaults():
    state = configured()
    first = state.current
    state = replace(
        state,
        cycles=(
            replace(
                first,
                details=replace(
                    first.details,
                    starts_on=date(2026, 11, 8),
                    ends_on=date(2026, 11, 14),
                ),
            ),
        ),
    )
    projected = s.project(state)[0]
    changed = s.edit_cycle(
        state,
        projected.ref,
        s.CycleDetails(
            projected.phase_id, starts_on=date(2026, 11, 15), ends_on=date(2026, 11, 21)
        ),
        shift_later=True,
    )
    assert changed.created[-1].details.starts_on == date(2026, 11, 15)
    with pytest.raises(s.ScheduleError, match="overlap"):
        later = s.project(state)[1]
        s.edit_cycle(
            state,
            later.ref,
            s.CycleDetails(
                later.phase_id, starts_on=date(2026, 11, 22), ends_on=date(2026, 11, 28)
            ),
        )


def test_initial_calendar_checks_retained_dates_against_the_first_projection():
    legacy = s.configure(
        s.DEFAULT_TEMPLATE, campaign_id="legacy", current_position=0
    ).schedule
    first = legacy.current
    legacy = replace(
        legacy,
        cycles=(
            replace(
                first,
                details=replace(
                    first.details,
                    starts_on=date(2026, 11, 1),
                    ends_on=date(2026, 11, 20),
                ),
            ),
        ),
    )
    with pytest.raises(s.ScheduleError, match="future cycle"):
        s.set_calendar(legacy, s.CycleCalendar(date(2026, 11, 1)))


def test_initial_calendar_preserves_saved_missing_endpoints():
    legacy = s.configure(
        s.DEFAULT_TEMPLATE, campaign_id="legacy", current_position=1
    ).schedule
    legacy = replace(
        legacy,
        cycles=(
            replace(
                legacy.cycles[0],
                details=replace(legacy.cycles[0].details, starts_on=date(2026, 11, 2)),
            ),
            replace(
                legacy.cycles[1],
                details=replace(legacy.cycles[1].details, ends_on=date(2026, 11, 13)),
            ),
        ),
    )
    updated = s.set_calendar(legacy, s.CycleCalendar(date(2026, 11, 1))).schedule
    assert [
        (cycle.details.starts_on, cycle.details.ends_on) for cycle in updated.cycles
    ] == [
        (date(2026, 11, 2), None),
        (None, date(2026, 11, 13)),
    ]


def test_setup_does_not_derive_planning_dates_from_a_transition_timestamp():
    from datetime import UTC, datetime

    state = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="legacy",
        current_position=0,
        status="in_progress",
        now=datetime(2026, 11, 1, tzinfo=UTC),
    ).schedule
    assert state.calendar is None
    assert state.current.details.starts_on is state.current.details.ends_on is None


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


def test_adjacent_inclusive_ranges_allow_clearing_an_end_date():
    state = configured(current=2)
    selected = state.cycles[1]
    changed = s.edit_cycle(
        state, s.SavedCycleRef(selected.id), replace(selected.details, ends_on=None)
    ).schedule
    assert changed.cycles[1].details.starts_on == selected.details.starts_on
    assert changed.cycles[1].details.ends_on is None
    assert changed.cycles[0] == state.cycles[0]


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
    with pytest.raises(s.ScheduleError, match="future cycle"):
        s.set_calendar(state, s.CycleCalendar(date(2026, 11, 2), starts_after_order=4))


def test_date_settings_leave_saved_undated_cycles_unchanged():
    state = s.configure(
        s.DEFAULT_TEMPLATE, campaign_id="legacy", current_position=2
    ).schedule
    change = s.set_calendar(state, s.CycleCalendar(date(2026, 10, 1)))
    assert [cycle.id for cycle in change.schedule.cycles] == [
        cycle.id for cycle in state.cycles
    ]
    assert change.updated == ()
    assert change.schedule.cycles == state.cycles
    assert s.project(change.schedule)[0].starts_on == date(2026, 10, 22)
    assert change.transition is None


def test_calendar_storage_round_trips_dates_and_rejects_unsupported_fields():
    calendar = s.CycleCalendar(date(2026, 11, 1), 2, "months", 6)
    assert calendar_from_data(calendar_data(calendar)) == calendar
    assert calendar_from_data({}) is None
    with pytest.raises(s.ScheduleError):
        calendar_from_data({**calendar_data(calendar), "automatic": True})


@pytest.mark.parametrize("days", [-2, 3])
def test_end_date_shift_moves_saved_suffix_and_previews_once_with_stable_identities(
    days,
):
    from datetime import timedelta

    state = configured(current=4)
    selected = state.cycles[2]
    delta = timedelta(days=days)
    before_preview = s.project(state, limit=3)
    change = s.edit_cycle(
        state,
        s.SavedCycleRef(selected.id),
        replace(selected.details, ends_on=selected.details.ends_on + delta),
        shift_later=True,
    )
    assert change.schedule.cycles[:2] == state.cycles[:2]
    for before, after in zip(state.cycles[3:], change.schedule.cycles[3:], strict=True):
        assert after.id == before.id and after.source == before.source
        assert after.details.starts_on == before.details.starts_on + delta
        assert after.details.ends_on == before.details.ends_on + delta
    assert [c.starts_on for c in s.project(change.schedule, limit=3)] == [
        c.starts_on + delta for c in before_preview
    ]
    assert change.schedule.current_cycle_id == state.current_cycle_id
    assert change.transition is None
    assert (
        calendar_from_data(calendar_data(change.schedule.calendar))
        == change.schedule.calendar
    )


def test_projected_end_date_shift_moves_only_following_dates_and_keeps_prefix_once():
    from datetime import timedelta

    state = configured()
    target, following = s.project(state, limit=2)
    change = s.edit_cycle(
        state,
        target.ref,
        s.CycleDetails(
            target.phase_id,
            starts_on=target.starts_on,
            ends_on=target.ends_on - timedelta(days=2),
        ),
        shift_later=True,
    )
    assert len(change.created) == 1
    assert s.project(change.schedule, limit=1)[
        0
    ].starts_on == following.starts_on - timedelta(days=2)
    assert change.schedule.cycles[0] == state.cycles[0]


def test_shifted_monthly_calendar_preserves_month_end_boundaries_and_cycle_lengths():
    from datetime import timedelta

    calendar = s.CycleCalendar(date(2026, 1, 31), unit="months")
    shifted = replace(calendar, days_offset=-2)
    for index in range(1, 15):
        assert shifted.dates_for(index) == tuple(
            day - timedelta(days=2) for day in calendar.dates_for(index)
        )
    assert "days_offset" not in calendar_data(calendar)


def test_extending_a_cycle_into_a_preview_requires_the_shift_option():
    from datetime import timedelta

    state = configured()
    target = s.project(state, limit=1)[0]
    with pytest.raises(s.ScheduleError, match="future cycle"):
        s.edit_cycle(
            state,
            target.ref,
            s.CycleDetails(
                target.phase_id,
                starts_on=target.starts_on,
                ends_on=target.ends_on + timedelta(days=1),
            ),
        )
