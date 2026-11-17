"""An arbitrator edits the planned campaign, including persisted future cycles."""

from dataclasses import replace
from datetime import UTC, datetime
from itertools import count

from n26.core import schedule as s

NOW = datetime(2026, 11, 15, 22, tzinfo=UTC)


def configured():
    identities = count()
    return s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="editable-timeline",
        current_position=0,
        mode="fixed",
        status="in_progress",
        now=NOW,
        new_id=lambda: f"timeline-{next(identities)}",
    ).schedule


def test_fixed_setup_saves_the_whole_editable_plan_without_starting_future_cycles():
    state = configured()
    assert [cycle.order for cycle in state.cycles if not cycle.archived] == list(
        range(1, 8)
    )
    assert state.current.order == 1
    assert s.project(state) == ()


def test_removing_an_unused_future_cycle_closes_the_visible_sequence():
    state = configured()
    if len(state.cycles) == 1:
        state, _ = s._ensure_saved(state, s.project(state)[-1].ref)
        state = state.schedule
    victim = state.cycles[5]
    last = state.cycles[6]
    change = s.delete_cycle(state, s.SavedCycleRef(victim.id))
    kept = [cycle for cycle in change.schedule.cycles if not cycle.archived]
    assert [cycle.order for cycle in kept] == [1, 2, 3, 4, 5, 6]
    assert kept[-1].id == last.id
    assert change.schedule.current_cycle_id == state.current_cycle_id
    assert change.transition is None
    assert s.project(change.schedule) == ()


def test_editing_a_future_entry_keeps_the_other_planned_entries_editable():
    state = configured()
    if len(state.cycles) == 1:
        change, _ = s._ensure_saved(state, s.project(state)[-1].ref)
        state = change.schedule
    first, sixth = state.cycles[1], state.cycles[5]
    state = s.edit_cycle(
        state,
        s.SavedCycleRef(sixth.id),
        replace(sixth.details, custom_name="Market week"),
    ).schedule
    state = s.edit_cycle(
        state,
        s.SavedCycleRef(first.id),
        replace(first.details, description="Changed after the distant edit."),
    ).schedule
    by_id = {cycle.id: cycle for cycle in state.cycles}
    assert by_id[sixth.id].name == "Market week"
    assert by_id[first.id].details.description == "Changed after the distant edit."
    assert state.current.order == 1


def test_an_explicit_future_phase_edit_keeps_the_selected_phase():
    state = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="phase-correction",
        current_position=0,
        mode="repeating",
        status="in_progress",
        now=NOW,
    ).schedule
    next_cycle = s.project(state, limit=1)[0]
    downtime = state.phases[1]
    change = s.edit_cycle(state, next_cycle.ref, s.CycleDetails(downtime.id))
    selected = next(c for c in change.schedule.cycles if c.order == 2)
    occurrence = next(
        o for o in change.schedule.occurrences if o.id == selected.occurrence_id
    )
    assert selected.details.phase_id == occurrence.phase_id == downtime.id
    assert change.schedule.current_cycle_id == state.current_cycle_id


def repeating_fifteen():
    state = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="ending",
        current_position=0,
        mode="repeating",
        status="in_progress",
        now=NOW,
    ).schedule
    target = s.project(state, limit=14)[-1]
    return s.edit_cycle(
        state, target.ref, s.CycleDetails(target.phase_id, custom_name="Market week")
    ).schedule


def test_converting_after_cycle_fifteen_finishes_its_pass_at_twenty_one():
    before = repeating_fifteen()
    change = s.timeline_settings(before, mode="fixed", steps=s.fixed_steps(before))
    active = [c for c in change.schedule.cycles if not c.archived]
    assert len(active) == 21
    assert [c.id for c in active[:15]] == [c.id for c in before.cycles]
    assert active[14].name == "Market week"
    assert (
        active[14].occurrence_id == active[15].occurrence_id == active[16].occurrence_id
    )
    assert change.schedule.current_cycle_id == before.current_cycle_id
    assert change.transition is None
    assert s.project(change.schedule) == ()


def test_the_arbitrator_can_shorten_the_fixed_endpoint_back_to_fifteen():
    from n26.core import timeline as t

    before = repeating_fifteen()
    state = s.timeline_settings(
        before, mode="fixed", steps=s.fixed_steps(before)
    ).schedule
    for cycle in reversed(state.cycles[15:]):
        state = t.remove_cycle(state, cycle.id).schedule
    assert [c.id for c in state.cycles if not c.archived] == [
        c.id for c in before.cycles
    ]
    assert s.project(state) == ()
    assert state.current_cycle_id == before.current_cycle_id


def test_an_authored_insertion_pushes_the_fixed_endpoint_without_consuming_a_pattern_slot():
    from n26.core import timeline as t

    before = repeating_fifteen()
    tail = before.cycles[-1]
    inserted = t.insert_cycle(
        before,
        tail.occurrence_id,
        after_cycle_id=tail.id,
        details=s.CycleDetails(tail.details.phase_id, custom_name="Festival"),
    ).schedule
    assert inserted.next_position == before.next_position == 15
    assert s.project(inserted, limit=1)[0].order == 17
    assert (
        s.project(inserted, limit=1)[0].source == s.project(before, limit=1)[0].source
    )
    fixed = s.timeline_settings(
        inserted, mode="fixed", steps=s.fixed_steps(inserted)
    ).schedule
    assert len([c for c in fixed.cycles if not c.archived]) == 22
    assert fixed.cycles[15].name == "Festival"


def test_editing_partial_phase_rules_applies_to_its_remaining_preview_only():
    from n26.core import timeline as t

    before = repeating_fifteen()
    occurrence = before.occurrences[-1]
    original = next(p for p in before.phases if p.id == occurrence.phase_id)
    edited = t.edit_occurrence(
        before,
        occurrence.id,
        replace(original.details, name="Final occupation", effects="Local adjustment"),
    ).schedule
    projected = s.project(edited, limit=3)
    assert (
        projected[0].phase_id
        == projected[1].phase_id
        == edited.occurrences[-1].phase_id
    )
    assert projected[2].phase_id == before.plan.steps[1].phase_id
    fixed = s.timeline_settings(
        edited, mode="fixed", steps=s.fixed_steps(edited)
    ).schedule
    assert (
        fixed.cycles[14].occurrence_id
        == fixed.cycles[15].occurrence_id
        == fixed.cycles[16].occurrence_id
    )
    assert before.plan == edited.plan
    assert before.current == edited.current


def test_an_empty_authored_phase_stays_before_the_generated_continuation():
    from n26.core import timeline as t

    before = repeating_fifteen()
    state = t.insert_occurrence(
        before,
        details=s.PhaseDetails("Planned event"),
        after_occurrence_id=before.occurrences[-1].id,
    ).schedule
    empty = state.occurrences[-1]
    preview = s.project(state, limit=1)[0]
    change, selected = s._ensure_saved(state, preview.ref)
    positions = {
        o.id: o.position for o in change.schedule.occurrences if not o.archived
    }
    assert positions[empty.id] < positions[selected.occurrence_id]
    assert selected.occurrence_id != before.cycles[-1].occurrence_id
    assert preview.source == s.project(before, limit=1)[0].source
    assert change.schedule.current_cycle_id == before.current_cycle_id


def test_removing_a_dated_future_cycle_preserves_later_saved_and_projected_dates():
    from datetime import date

    from n26.core import timeline as t

    state = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="dated",
        current_position=0,
        mode="repeating",
        status="in_progress",
        now=NOW,
        calendar=s.CycleCalendar(date(2026, 1, 31), unit="months"),
    ).schedule
    change, _ = s._ensure_saved(state, s.project(state, limit=6)[-1].ref)
    state = change.schedule
    next_cycle = s.project(state, limit=1)[0]
    saved_dates = {c.id: (c.details.starts_on, c.details.ends_on) for c in state.cycles}
    changed = t.remove_cycle(state, state.cycles[5].id).schedule
    assert (
        s.project(changed, limit=1)[0].starts_on
        == next_cycle.starts_on
        == date(2026, 8, 31)
    )
    assert s.project(changed, limit=1)[0].source == next_cycle.source
    assert {
        c.id: (c.details.starts_on, c.details.ends_on) for c in changed.cycles
    } == saved_dates


def test_projected_selection_uses_the_edited_continuing_block():
    from n26.core import timeline as t

    state = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="edited-projection",
        current_position=0,
        mode="repeating",
    ).schedule
    state = s._ensure_saved(state, s.project(state, limit=1)[0].ref)[0].schedule
    original = state.occurrences[0]
    phase = next(p for p in state.phases if p.id == original.phase_id)
    state = t.edit_occurrence(
        state, original.id, replace(phase.details, name="Revised occupation")
    ).schedule
    projected = s.project(state, limit=1)[0]
    selected = s._selected(state, projected.ref)
    assert selected == projected
