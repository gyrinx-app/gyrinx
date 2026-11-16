"""Timeline edits keep calendar defaults separate from visible cycle positions."""

from dataclasses import replace
from datetime import date

from n26.core import schedule as s
from n26.core import timeline as t
from n26.core.cycle_data import (
    calendar_data,
    calendar_storage_data,
    timeline_calendar_from_data,
)


def monthly_prefix():
    state = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="monthly",
        current_position=0,
        mode="repeating",
        calendar=s.CycleCalendar(date(2026, 1, 31), unit="months"),
    ).schedule
    return s._ensure_saved(state, s.project(state, limit=6)[-1].ref)[0].schedule


def append_manual(state):
    tail = next(c for c in reversed(state.cycles) if not c.archived)
    return t.insert_cycle(
        state,
        tail.occurrence_id,
        after_cycle_id=tail.id,
        details=s.CycleDetails(tail.details.phase_id, custom_name="Market week"),
    ).schedule


def test_two_manual_appends_keep_the_first_saved_default_and_generated_tail():
    original = monthly_prefix()
    following = s.project(original, limit=1)[0]
    state = append_manual(append_manual(original))
    assert state.calendar.position_offset == -2
    assert s.calendar_boundary(state) == 1
    assert s.calendar_defaults_start(state) == date(2026, 2, 28)
    assert state.calendar.starts_on == date(2026, 1, 31)
    assert state.cycles[:7] == original.cycles
    assert all(
        c.details.starts_on is c.details.ends_on is None for c in state.cycles[7:]
    )
    assert state.next_position == original.next_position == 7
    projected = s.project(state, limit=1)[0]
    assert projected.source == following.source
    assert projected.starts_on == following.starts_on == date(2026, 8, 31)
    assert projected.ends_on == following.ends_on == date(2026, 9, 29)


def test_deleting_a_month_end_cycle_keeps_sources_and_later_calendar_days():
    original = monthly_prefix()
    before = s.project(original, limit=2)
    removed = original.cycles[5]
    state = t.remove_cycle(original, removed.id).schedule
    assert state.calendar.position_offset == 1
    assert state.next_position == original.next_position
    by_id = {c.id: c for c in state.cycles}
    assert by_id[removed.id].archived
    for cycle in original.cycles:
        assert by_id[cycle.id].source == cycle.source
        assert by_id[cycle.id].details == cycle.details
    after = s.project(state, limit=2)
    assert [c.source for c in after] == [c.source for c in before]
    assert [(c.starts_on, c.ends_on) for c in after] == [
        (date(2026, 8, 31), date(2026, 9, 29)),
        (date(2026, 9, 30), date(2026, 10, 30)),
    ]
    assert s.calendar_defaults_start(state) == date(2026, 2, 28)


def test_legacy_archived_slots_are_counted_once_and_storage_keeps_the_marker():
    original = s.CycleCalendar(date(2026, 1, 31), unit="months")
    canonical = calendar_data(original)
    assert canonical == {
        "starts_on": "2026-01-31",
        "interval": 1,
        "unit": "months",
        "starts_after_order": 0,
    }
    decoded = timeline_calendar_from_data(canonical, saved_count=5, recorded_count=7)
    assert decoded.position_offset == 2
    assert decoded.dates_for(6) == original.dates_for(8)
    stored = calendar_storage_data(decoded)
    assert stored["position_offset"] == 2
    assert (
        timeline_calendar_from_data(stored, saved_count=5, recorded_count=7) == decoded
    )
    assert calendar_data(decoded) == canonical
    zero = calendar_storage_data(original)
    assert zero["position_offset"] == 0
    assert (
        timeline_calendar_from_data(zero, saved_count=5, recorded_count=7) == original
    )


def test_fully_custom_future_bounds_do_not_supply_or_block_default_calendar_dates():
    state = append_manual(append_manual(monthly_prefix()))
    cycles = tuple(
        replace(c, customized_fields=c.customized_fields | {"starts_on", "ends_on"})
        for c in state.cycles
    )
    state = replace(state, cycles=cycles)
    assert s.calendar_boundary(state) == 9
    assert s.calendar_defaults_start(state) == date(2026, 8, 31)
