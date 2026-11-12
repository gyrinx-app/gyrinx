"""A replacement pattern credits saved positions without changing their provenance."""

from dataclasses import replace
from datetime import date

from n26.core import schedule as s


def configured():
    return s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="campaign",
        current_position=1,
        mode="repeating",
        calendar=s.CycleCalendar(date(2026, 11, 1)),
    ).schedule


def test_replacement_finishes_the_saved_phase_instead_of_adding_a_full_occurrence():
    state = configured()
    steps = state.plan.steps[:2]
    after = s.replace_plan(state, mode="repeating", steps=steps).schedule
    assert after.cycles == state.cycles
    assert after.plan.start_position == after.next_position == 2
    projection = s.project(after, limit=5)
    assert [p.phase_id for p in projection] == [
        steps[0].phase_id,
        steps[1].phase_id,
        steps[0].phase_id,
        steps[0].phase_id,
        steps[0].phase_id,
    ]
    assert [p.order for p in projection] == [3, 4, 5, 6, 7]
    materialised, _ = s._ensure_saved(after, projection[3].ref)
    assert materialised.schedule.cycles[:2] == state.cycles
    assert s.project(materialised.schedule, limit=1)[0].source == projection[4].source


def test_completed_or_shortened_phase_continues_with_the_next_step():
    state = configured()
    steps = (replace(state.plan.steps[0], count=1), state.plan.steps[1])
    after = s.replace_plan(state, mode="repeating", steps=steps).schedule
    assert s.project(after, limit=1)[0].phase_id == steps[1].phase_id
    assert after.cycles == state.cycles


def test_matching_step_identity_distinguishes_two_occurrences_of_the_same_phase():
    state = configured()
    a, b = state.plan.steps[:2]
    steps = (a, b, s.PlanStep("second", a.phase_id, 4))
    after = s.replace_plan(state, mode="repeating", steps=steps).schedule
    assert s.project(after, limit=1)[0].source.step_id == a.id
    assert s.project(after, limit=2)[1].source.step_id == b.id


def test_resaving_an_unstarted_revision_preserves_its_explicit_continuation():
    state = configured()
    plan = s.Plan("reset", "repeating", state.plan.steps[:2], len(state.cycles))
    reset = replace(state, plan=plan, next_position=0)
    unchanged = s.replace_plan(reset, mode="repeating", steps=plan.steps).schedule
    assert unchanged is reset
    assert unchanged.next_position == 0
    assert unchanged.cycles == state.cycles
