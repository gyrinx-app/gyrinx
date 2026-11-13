"""Prepared cycle choices cover the same bounded prefix accepted by commands."""

import json
from itertools import count

import pytest

from n26.core import cycles
from n26.core import schedule as s
from n26.core.cycle_data import ref_from_data
from n26.core.cycle_workflow import _available_cycle_choices
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
