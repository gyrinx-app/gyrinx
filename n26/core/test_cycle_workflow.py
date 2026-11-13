"""Prepared cycle choices cover the same bounded prefix accepted by commands."""

import json
from dataclasses import replace
from datetime import date
from itertools import count
from uuid import uuid4

import pytest

from n26.core import cycles
from n26.core import schedule as s
from n26.core.cycle_data import ref_data, ref_from_data
from n26.core.cycle_workflow import _available_cycle_choices, perform
from n26.core.operations import Refusal


@pytest.mark.parametrize(
    "opening_count, available",
    [(20, True), (cycles.MAX_PREFIX, True), (cycles.MAX_PREFIX + 1, False)],
)
def test_phase_replacement_choices_reach_the_supported_projected_prefix(
    opening_count, available
):
    identities = count()
    state = s.configure(
        s.ScheduleTemplate(
            "Long opening",
            (
                s.Phase("opening", s.PhaseDetails("Opening")),
                s.Phase("next", s.PhaseDetails("Next phase")),
            ),
            (
                s.PlanStep("opening", "opening", opening_count),
                s.PlanStep("next", "next", 1),
            ),
        ),
        campaign_id="campaign",
        current_position=0,
        mode="repeating",
        new_id=lambda: f"identity-{next(identities)}",
    ).schedule
    choices = _available_cycle_choices(
        state, {state.current_cycle_id}, phase_id=state.current_phase.id
    )
    targets = [ref_from_data(json.loads(choice["value"])) for choice in choices]
    assert all(isinstance(target, s.ProjectedCycleRef) for target in targets)
    assert all(
        target.position.index - state.next_position < cycles.MAX_PREFIX
        for target in targets
    )
    assert (
        any(target.position.index == opening_count for target in targets) is available
    )
    target = s.ProjectedCycleRef(s.PlannedPosition(state.plan.id, opening_count))
    if available:
        cycles._bounded_target(state, target)
    else:
        with pytest.raises(Refusal, match="1,000 projected cycles"):
            cycles._bounded_target(state, target)


@pytest.mark.parametrize("exclude_phase", [False, True])
def test_choice_labels_do_not_project_calendar_dates_beyond_the_supported_year(
    exclude_phase,
):
    state = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="campaign",
        current_position=0,
        mode="repeating",
        calendar=s.CycleCalendar(date(2026, 11, 1), 520),
    ).schedule
    assert len(s.project(state)) == 12
    with pytest.raises(s.ScheduleError, match="beyond the supported calendar"):
        s.project(state, limit=cycles.MAX_PREFIX)
    saved_dates = [
        (cycle.details.starts_on, cycle.details.ends_on) for cycle in state.cycles
    ]
    excluded = {"phase_id": state.current_phase.id} if exclude_phase else {}
    choices = _available_cycle_choices(state, {state.current_cycle_id}, **excluded)
    assert choices == _available_cycle_choices(
        replace(state, calendar=None), {state.current_cycle_id}, **excluded
    )
    assert (
        ref_from_data(json.loads(choices[-1]["value"])).position.index
        == cycles.MAX_PREFIX
    )
    assert [
        (cycle.details.starts_on, cycle.details.ends_on) for cycle in state.cycles
    ] == saved_dates
    assert state.calendar == s.CycleCalendar(date(2026, 11, 1), 520)


def test_selecting_an_unrepresentable_replacement_still_returns_calendar_validation(
    monkeypatch,
):
    state = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="campaign",
        current_position=0,
        mode="repeating",
        calendar=s.CycleCalendar(date(2026, 11, 1), 520),
    ).schedule
    target = s.SavedCycleRef(state.current_cycle_id)
    replacement = s.ProjectedCycleRef(
        s.PlannedPosition(state.plan.id, cycles.MAX_PREFIX)
    )
    cycles._bounded_target(state, replacement)

    def delete_cycle(campaign, *, target, replacement, **kwargs):
        return s.delete_cycle(state, target, replacement=replacement)

    monkeypatch.setattr(cycles, "delete_cycle", delete_cycle)
    submitted = perform(
        object(),
        object(),
        "delete-cycle",
        {
            "request_key": str(uuid4()),
            "expected_revision": state.revision,
            "target": json.dumps(ref_data(target)),
            "current_choice": json.dumps(ref_data(replacement)),
        },
        {"cycle": state.current_cycle_id},
    )
    assert submitted.result is None
    assert list(submitted.form.non_field_errors()) == [
        "The cycle dates extend beyond the supported calendar."
    ]
    assert not state.current.archived
    assert len(state.cycles) == 1
