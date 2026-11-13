"""Executable date-policy proposal; the application retains its paired-date rule."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from itertools import product

import pytest

from n26.core import schedule as s
from scripts.experiments.cycle_date_policy import (
    Bounds,
    Entry,
    ShiftProposal,
    propose_shift,
    shift_later,
    validate,
)


def d(day):
    return date(2026, 11, day)


def entry(key, order, start=None, end=None, *, archived=False):
    return Entry(key, order, Bounds(start, end), archived)


def codes(entries, **options):
    return {issue.code for issue in validate(entries, **options)}


STATES = ("undated", "start-only", "end-only", "complete")


def shape(state, first, last):
    return Bounds(
        first if state in ("start-only", "complete") else None,
        last if state in ("end-only", "complete") else None,
    )


@pytest.mark.parametrize("left,right", product(STATES, repeat=2))
def test_all_sixteen_separated_date_shapes_are_permitted(left, right):
    entries = (
        Entry("a", 1, shape(left, d(1), d(7))),
        Entry("b", 2, shape(right, d(8), d(14))),
    )
    assert validate(entries) == ()


@pytest.mark.parametrize("left,right", product(STATES, repeat=2))
def test_all_sixteen_same_day_shapes_expose_every_known_collision(left, right):
    entries = (
        Entry("a", 1, shape(left, d(13), d(13))),
        Entry("b", 2, shape(right, d(13), d(13))),
    )
    expected = set() if "undated" in (left, right) else {"overlap"}
    assert codes(entries) == expected


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (Bounds(d(13), None), Bounds(d(20), d(27)), set()),
        (Bounds(d(13), d(19)), Bounds(d(20), d(27)), set()),
        (Bounds(d(13), d(20)), Bounds(d(20), d(27)), {"overlap"}),
        (Bounds(d(13), d(21)), Bounds(d(20), d(27)), {"overlap"}),
        (Bounds(d(13), d(20)), Bounds(d(17), None), {"overlap"}),
        (Bounds(d(13), d(20)), Bounds(None, d(17)), {"overlap"}),
        (Bounds(None, d(13)), Bounds(d(20), None), set()),
        (Bounds(d(13), d(13)), Bounds(d(14), d(14)), set()),
        (Bounds(d(20), d(13)), Bounds(), {"reversed"}),
        (Bounds(d(20), None), Bounds(d(13), None), {"date_order"}),
        (Bounds(None, d(20)), Bounds(d(13), None), {"date_order"}),
    ],
)
def test_boundary_cases(a, b, expected):
    assert codes((Entry("a", 1, a), Entry("b", 2, b))) == expected


def test_chronology_is_an_explicit_choice_and_never_reorders_cycles():
    entries = (entry("a", 1, d(20), d(27)), entry("b", 2, d(1), d(7)))
    assert codes(entries) == {"date_order"}
    assert validate(entries, chronological=False) == ()
    assert [e.key for e in entries] == ["a", "b"]


def test_undated_cycles_reserve_no_implicit_days_and_archived_dates_are_ignored():
    entries = (
        entry("a", 1, d(13), d(13)),
        entry("b", 2),
        entry("old", 3, d(20), d(1), archived=True),
        entry("c", 4, d(14), d(14)),
    )
    assert validate(entries) == ()


DOMAIN = tuple(d(day) for day in range(10, 17))
ANCHORS = (None, *DOMAIN[1:-1])
ALL_BOUNDS = tuple(Bounds(a, b) for a, b in product(ANCHORS, repeat=2))


def completions(bounds):
    # Undated entries assert no interval; known bounds may be completed independently.
    if bounds.start is bounds.end is None:
        return (None,)
    return tuple(
        (start, end)
        for start, end in product(DOMAIN, repeat=2)
        if start <= end
        and (bounds.start is None or start == bounds.start)
        and (bounds.end is None or end == bounds.end)
    )


def possible(a, b, chronological):
    for left, right in product(completions(a), completions(b)):
        if left is None or right is None:
            return True
        if left[1] < right[0] or (not chronological and right[1] < left[0]):
            return True
    return False


@pytest.mark.parametrize("chronological", [False, True])
def test_validator_matches_independent_exhaustive_completions(chronological):
    # 1,296 input pairs per policy, including reversed and partially known bounds.
    for a, b in product(ALL_BOUNDS, repeat=2):
        accepted = not validate(
            (Entry("a", 1, a), Entry("b", 2, b)), chronological=chronological
        )
        assert accepted == possible(a, b, chronological), (a, b, chronological)


def test_projection_boundary_matches_all_252_bounded_completion_cases():
    for bounds, start in product(ALL_BOUNDS, DOMAIN):
        result = not validate((Entry("saved", 1, bounds),), future_start=start)
        assert result == possible(bounds, Bounds(start, DOMAIN[-1]), True), (
            bounds,
            start,
        )


@pytest.mark.parametrize("chronological", [False, True])
def test_clearing_dates_can_relax_but_never_introduce_a_conflict(chronological):
    for a, b in product(ALL_BOUNDS, repeat=2):
        entries = (Entry("a", 1, a), Entry("b", 2, b))
        if validate(entries, chronological=chronological):
            continue
        for index in (0, 1):
            for bound in ("start", "end"):
                amended = list(entries)
                amended[index] = replace(
                    entries[index],
                    bounds=replace(entries[index].bounds, **{bound: None}),
                )
                assert validate(amended, chronological=chronological) == ()


def test_shift_moves_each_known_bound_preserving_unknowns_identity_and_archives():
    entries = (
        entry("a", 1, d(1), d(7)),
        entry("b", 2, d(8), None),
        entry("c", 3, None, d(21)),
        entry("d", 4),
        entry("old", 5, d(22), d(28), archived=True),
    )
    shifted = shift_later(entries, after_order=1, days=3)
    assert shifted[0] == entries[0]
    assert shifted[1].bounds == Bounds(d(11), None)
    assert shifted[2].bounds == Bounds(None, d(24))
    assert shifted[3:] == entries[3:]
    assert [(e.key, e.order, e.archived) for e in shifted] == [
        (e.key, e.order, e.archived) for e in entries
    ]
    assert entries[1].bounds == Bounds(d(8), None)
    assert validate(shifted) == ()
    assert shift_later(entries, after_order=1, days=0) == entries
    assert "overlap" in codes(shift_later(entries, after_order=1, days=-1))


def test_date_overflow_rejects_the_whole_candidate_without_mutation():
    entries = (entry("a", 1), entry("b", 2, date.max, None))
    with pytest.raises(ValueError):
        shift_later(entries, after_order=1, days=1)
    assert entries[1].bounds == Bounds(date.max, None)


def model_entries(schedule):
    return tuple(
        Entry(
            str(c.id),
            c.order,
            Bounds(c.details.starts_on, c.details.ends_on),
            c.archived,
        )
        for c in schedule.cycles
    )


@pytest.mark.parametrize("calendar", [None, s.CycleCalendar(d(1))])
def test_actual_prefix_model_can_preserve_a_partial_override_and_full_projections(
    calendar,
):
    state = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="model",
        current_position=None,
        mode="repeating",
        calendar=calendar,
    ).schedule
    target = s.project(state)[2]
    details = s.CycleDetails(target.phase_id, starts_on=target.starts_on or d(15))
    change, saved = s._ensure_saved(
        state, target.ref, selected_details=details, clear_dates=True
    )
    assert saved.details.starts_on == (target.starts_on or d(15))
    assert saved.details.ends_on is None
    assert saved.source == target.source
    assert change.schedule.current_cycle_id is None
    assert change.transition is None
    future = s.project(change.schedule)
    assert (
        validate(model_entries(change.schedule), future_start=future[0].starts_on) == ()
    )
    if calendar:
        assert all(c.starts_on is not None and c.ends_on is not None for c in future)
    else:
        assert all(c.starts_on is c.ends_on is None for c in future)


def test_start_advance_and_finish_preserve_partial_dates_without_guessing_boundaries():
    state = s.configure(
        s.DEFAULT_TEMPLATE, campaign_id="model", current_position=0, mode="repeating"
    ).schedule
    first = replace(
        state.current, details=replace(state.current.details, starts_on=d(1))
    )
    state = replace(state, cycles=(first,))
    now = datetime(2026, 11, 13, tzinfo=UTC)
    started = s.start(state, now=now).schedule
    advanced = s.advance(started, now=now).schedule
    finished = s.finish(advanced, now=now).schedule
    assert finished.cycles[0] == first
    assert finished.cycles[1].details.starts_on is None
    assert finished.cycles[1].details.ends_on is None


def test_future_calendar_settings_can_preserve_unknown_saved_bounds():
    state = s.configure(
        s.DEFAULT_TEMPLATE, campaign_id="model", current_position=0, mode="repeating"
    ).schedule
    first = replace(
        state.current, details=replace(state.current.details, starts_on=d(1))
    )
    state = replace(state, cycles=(first,))
    changed = s.replace_plan(
        state,
        steps=state.plan.steps,
        mode="repeating",
        calendar=s.CycleCalendar(d(15), starts_after_order=1),
        preserve_saved_dates=True,
    ).schedule
    assert changed.cycles == state.cycles
    assert changed.current_cycle_id == state.current_cycle_id
    assert s.project(changed)[0].starts_on == d(15)
    assert validate(model_entries(changed), future_start=d(15)) == ()
    assert codes(model_entries(changed), future_start=d(1)) == {"projection_boundary"}


def test_application_edit_rule_has_not_been_changed_by_the_experiment():
    state = s.configure(
        s.DEFAULT_TEMPLATE, campaign_id="model", current_position=0, mode="repeating"
    ).schedule
    with pytest.raises(s.ScheduleError, match="both dates"):
        s.edit_cycle(
            state,
            s.SavedCycleRef(state.current_cycle_id),
            replace(state.current.details, starts_on=d(1)),
        )


@pytest.mark.parametrize(
    "old_end,new_end,expected",
    [
        (d(7), d(10), ShiftProposal("delta", 3)),
        (d(7), d(5), ShiftProposal("delta", -2)),
        (d(7), d(7), None),
        (d(7), None, None),
        (None, None, None),
        (None, d(7), None),
        (None, d(8), ShiftProposal("align", 1)),
        (None, d(10), ShiftProposal("align", 3)),
    ],
)
def test_end_edits_offer_explicit_delta_or_alignment(old_end, new_end, expected):
    entries = (entry("a", 1, d(1), old_end), entry("b", 2, d(8), None))
    assert propose_shift(entries, order=1, old_end=old_end, new_end=new_end) == expected
    assert entries[1].bounds == Bounds(d(8), None)


@pytest.mark.parametrize("old_end", [None, d(7)])
def test_no_shift_without_a_later_known_date(old_end):
    entries = (
        entry("a", 1, d(1), old_end),
        entry("blank", 2),
        entry("old", 3, d(8), d(14), archived=True),
    )
    assert propose_shift(entries, order=1, old_end=old_end, new_end=d(10)) is None
    assert propose_shift(
        entries, order=1, old_end=old_end, new_end=d(10), future_start=d(8)
    ) == ShiftProposal("align" if old_end is None else "delta", 3)


def test_end_only_anchor_can_be_shifted_without_guessing_a_start():
    entries = (entry("a", 1, d(1)), entry("blank", 2), entry("b", 3, None, d(10)))
    proposal = propose_shift(entries, order=1, old_end=None, new_end=d(10))
    assert proposal == ShiftProposal("align", 1)
    candidate = (replace(entries[0], bounds=Bounds(d(1), d(10))), *entries[1:])
    assert codes(candidate) == {"overlap"}
    shifted = shift_later(candidate, after_order=1, days=proposal.days)
    assert validate(shifted) == ()
    assert shifted[1].bounds == Bounds()
    assert shifted[2].bounds == Bounds(None, d(11))


def test_clearing_end_preserves_following_dates_and_restoring_it_revalidates():
    original = (entry("a", 1, d(1), d(7)), entry("b", 2, d(8), d(14)))
    cleared = (replace(original[0], bounds=Bounds(d(1), None)), original[1])
    assert validate(cleared) == ()
    assert propose_shift(cleared, order=1, old_end=d(7), new_end=None) is None
    restored = (replace(cleared[0], bounds=Bounds(d(1), d(10))), cleared[1])
    assert codes(restored) == {"overlap"}
    proposal = propose_shift(cleared, order=1, old_end=None, new_end=d(10))
    assert proposal == ShiftProposal("align", 3)
    shifted = shift_later(restored, after_order=1, days=proposal.days)
    assert shifted[1].bounds == Bounds(d(11), d(17))
    assert validate(shifted) == ()
    assert original[1].bounds == Bounds(d(8), d(14))


def test_calendar_offset_moves_projections_together_without_changing_saved_identity():
    state = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="model",
        current_position=0,
        mode="repeating",
        calendar=s.CycleCalendar(d(1)),
    ).schedule
    first = replace(state.current, details=replace(state.current.details, ends_on=None))
    state = replace(state, cycles=(first,))
    before = s.project(state)
    proposal = propose_shift(
        model_entries(state),
        order=1,
        old_end=None,
        new_end=d(10),
        future_start=before[0].starts_on,
    )
    assert proposal == ShiftProposal("align", 3)
    shifted = replace(
        state,
        calendar=replace(
            state.calendar, days_offset=state.calendar.days_offset + proposal.days
        ),
    )
    after = s.project(shifted)
    assert shifted.cycles == state.cycles
    assert shifted.current_cycle_id == state.current_cycle_id
    assert [(c.ref, c.source) for c in after] == [(c.ref, c.source) for c in before]
    assert [(c.starts_on, c.ends_on) for c in after] == [
        (c.starts_on + timedelta(days=3), c.ends_on + timedelta(days=3)) for c in before
    ]
    candidate = (replace(model_entries(state)[0], bounds=Bounds(d(1), d(10))),)
    assert validate(candidate, future_start=after[0].starts_on) == ()


def test_shift_proposal_at_date_limit_is_safe_but_application_still_rejects_overflow():
    entries = (entry("a", 1, date.min), entry("b", 2, date.max))
    proposal = propose_shift(entries, order=1, old_end=None, new_end=date.max)
    assert proposal == ShiftProposal("align", 1)
    with pytest.raises(ValueError):
        shift_later(entries, after_order=1, days=proposal.days)


@pytest.mark.parametrize("future_start,expected_days", [(None, 6), (d(8), 8)])
def test_new_end_alignment_checks_every_later_bound_even_without_chronology(
    future_start, expected_days
):
    entries = (entry("a", 1, d(1)), entry("b", 2, d(20)), entry("c", 3, d(10)))
    proposal = propose_shift(
        entries, order=1, old_end=None, new_end=d(15), future_start=future_start
    )
    assert proposal == ShiftProposal("align", expected_days)
    amended = (replace(entries[0], bounds=Bounds(d(1), d(15))), *entries[1:])
    shifted = shift_later(amended, after_order=1, days=proposal.days)
    shifted_future = (
        future_start + timedelta(days=proposal.days) if future_start else None
    )
    # A projection boundary already before later saved dates remains invalid:
    # moving both by the same amount cannot repair that existing contradiction.
    expected = {"projection_boundary"} if future_start else set()
    assert codes(shifted, chronological=False, future_start=shifted_future) == expected
