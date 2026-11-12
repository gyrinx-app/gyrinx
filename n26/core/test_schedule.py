"""Executable campaign schedules distinguish planning, saving and activation."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
from itertools import count

import pytest

from n26.core import schedule as s

NOW = datetime(2026, 11, 7, 18, tzinfo=UTC)
LATER = datetime(2026, 11, 14, 18, tzinfo=UTC)


@pytest.fixture
def ids():
    sequence = count()
    return lambda: f"identity-{next(sequence)}"


def configured(ids, *, current=0, mode="fixed", status="in_progress"):
    return s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="campaign",
        current_position=current,
        mode=mode,
        status=status,
        now=NOW,
        calendar=s.CycleCalendar(NOW.date()),
        new_id=ids,
    ).schedule


def phase_names(schedule, cycles):
    names = {p.id: p.details.name for p in schedule.phases}
    return [
        names[c.details.phase_id if isinstance(c, s.Cycle) else c.phase_id]
        for c in cycles
    ]


class TestConfigure:
    def test_the_default_template_expands_to_three_one_three(self, ids):
        schedule = configured(ids)
        assert phase_names(schedule, schedule.cycles + s.project(schedule)) == [
            "Occupation",
            "Occupation",
            "Occupation",
            "Downtime",
            "Takeover",
            "Takeover",
            "Takeover",
        ]

    def test_the_initial_choice_saves_a_prefix_without_inventing_earlier_transitions(
        self, ids
    ):
        change = s.configure(
            s.DEFAULT_TEMPLATE,
            campaign_id="campaign",
            current_position=3,
            status="in_progress",
            now=NOW,
            new_id=ids,
        )
        assert [c.name for c in change.created] == [
            "Cycle 1",
            "Cycle 2",
            "Cycle 3",
            "Cycle 4",
        ]
        assert change.schedule.current == change.created[-1]
        assert change.transition.previous_cycle is None
        assert change.transition.current_cycle == change.created[-1]
        assert change.transition.occurred_at == NOW
        assert change.transition.enters_phase

    def test_pre_campaign_setup_waits_for_an_explicit_start(self, ids):
        change = s.configure(
            s.DEFAULT_TEMPLATE,
            campaign_id="campaign",
            current_position=0,
            new_id=ids,
        )
        assert change.schedule.status == "pre_campaign"
        assert change.transition is None
        started = s.start(change.schedule, now=LATER)
        assert started.schedule.current_cycle_id == change.schedule.current_cycle_id
        assert started.schedule.status == "in_progress"
        assert started.created == ()
        assert started.transition.occurred_at == LATER

    def test_campaigns_receive_independent_phase_and_step_identities(self, ids):
        first, second = configured(ids), configured(ids)
        assert {p.id for p in first.phases}.isdisjoint(p.id for p in second.phases)
        assert {p.id for p in first.plan.steps}.isdisjoint(
            p.id for p in second.plan.steps
        )
        changed = s.edit_phase(
            first, first.current_phase.id, s.PhaseDetails("Opening")
        ).schedule
        assert changed.current_phase.details.name == "Opening"
        assert second.current_phase.details.name == "Occupation"
        assert s.DEFAULT_TEMPLATE.phases[0].details.name == "Occupation"

    def test_an_initial_choice_beyond_a_fixed_plan_is_rejected(self, ids):
        with pytest.raises(s.ScheduleError, match="no more cycles"):
            configured(ids, current=7)


class TestProjectionAndSaving:
    def test_reading_a_projection_leaves_the_schedule_unchanged(self, ids):
        schedule = configured(ids)
        before = schedule
        first = s.project(schedule, limit=3)
        assert s.project(schedule, limit=3) == first
        assert [p.order for p in first] == [2, 3, 4]
        assert all(isinstance(p.ref, s.ProjectedCycleRef) for p in first)
        assert schedule == before
        assert len(schedule.cycles) == 1
        with pytest.raises(FrozenInstanceError):
            schedule.next_position = 99

    def test_editing_cycle_six_saves_four_through_six_without_advancing(self, ids):
        schedule = configured(ids, current=1)
        third = s.project(schedule, limit=1)[0]
        schedule = s.edit_cycle(
            schedule, third.ref, s.CycleDetails(third.phase_id), new_id=ids
        ).schedule
        sixth = s.project(schedule, limit=3)[-1]
        details = s.CycleDetails(sixth.phase_id, custom_name="The crossing")
        preview = s.preview_cycle_edit(schedule, sixth.ref, details)
        assert [c.order for c in preview.creates] == [4, 5, 6]
        change = s.edit_cycle(schedule, sixth.ref, details, new_id=ids)
        assert [c.order for c in change.created] == [4, 5, 6]
        assert change.schedule.current_cycle_id == schedule.current_cycle_id
        assert change.schedule.next_position == 6
        assert change.schedule.cycles[-1].name == "The crossing"
        assert change.transition is None
        assert change.schedule.cycles[:3] == schedule.cycles

    def test_the_same_projected_reference_resolves_to_its_saved_cycle(self, ids):
        schedule = configured(ids)
        target = s.project(schedule, limit=3)[-1]
        details = s.CycleDetails(target.phase_id, custom_name="A quiet cycle")
        first = s.edit_cycle(schedule, target.ref, details, new_id=ids)
        replay = s.edit_cycle(first.schedule, target.ref, details, new_id=ids)
        assert replay.schedule == first.schedule
        assert replay.created == replay.updated == ()
        assert replay.transition is None

    def test_saving_a_later_cycle_preserves_every_recorded_source_position(self, ids):
        schedule = configured(ids)
        projected = s.project(schedule, limit=5)
        change = s.edit_cycle(
            schedule,
            projected[-1].ref,
            s.CycleDetails(projected[-1].phase_id),
            new_id=ids,
        )
        assert [c.source for c in change.created] == [p.source for p in projected]
        assert s.project(change.schedule, limit=1)[0].order == 7

    def test_dates_do_not_reorder_cycles_or_move_the_cursor(self, ids):
        schedule = configured(ids, current=3)
        target = schedule.cycles[0]
        context = s.context(schedule, target.id)
        changed = s.edit_cycle(
            schedule,
            s.SavedCycleRef(target.id),
            replace(
                target.details,
                starts_on=date(2020, 1, 1),
                ends_on=date(2020, 1, 2),
            ),
        )
        assert [c.id for c in changed.schedule.cycles] == [
            c.id for c in schedule.cycles
        ]
        assert [c.source for c in changed.schedule.cycles] == [
            c.source for c in schedule.cycles
        ]
        assert changed.schedule.next_position == schedule.next_position
        assert s.project(changed.schedule) == s.project(schedule)
        assert s.context(changed.schedule, target.id) == context
        assert changed.transition is None

    def test_an_unknown_saved_cycle_cannot_be_attached(self, ids):
        schedule = configured(ids)
        with pytest.raises(s.ScheduleError, match="from this campaign"):
            s.preview_cycle_edit(
                schedule, s.SavedCycleRef("foreign"), schedule.current.details
            )

    def test_an_unknown_phase_cannot_be_used(self, ids):
        schedule = configured(ids)
        with pytest.raises(s.ScheduleError, match="phase from this campaign"):
            s.edit_cycle(
                schedule,
                s.SavedCycleRef(schedule.current_cycle_id),
                s.CycleDetails("x"),
            )


class TestRepeatingAndReplacement:
    @pytest.mark.parametrize(
        "saved,counts,end",
        [
            (0, [3, 1, 3], 7),
            (2, [1, 1, 3], 7),
            (6, [1], 7),
            (7, [], 7),
            (9, [1, 1, 3], 14),
            (14, [], 14),
        ],
    )
    def test_fixed_conversion_finishes_the_saved_tail_pass(
        self, ids, saved, counts, end
    ):
        schedule = configured(
            ids, current=saved - 1 if saved else None, mode="repeating"
        )
        steps = s.fixed_steps(schedule)
        assert [step.count for step in steps] == counts
        fixed = s.replace_plan(schedule, steps=steps, mode="fixed", new_id=ids).schedule
        assert fixed.cycles == schedule.cycles
        assert fixed.current_cycle_id == schedule.current_cycle_id
        assert fixed.calendar == schedule.calendar
        assert fixed.plan.order_for(fixed.plan.length) - 1 == end

    def test_fixed_conversion_uses_future_saved_tail_without_moving_current(self, ids):
        schedule = configured(ids, current=1, mode="repeating")
        future = next(cycle for cycle in s.project(schedule) if cycle.order == 9)
        change, _selected = s._ensure_saved(schedule, future.ref, new_id=ids)
        schedule = change.schedule
        fixed = s.replace_plan(
            schedule, steps=s.fixed_steps(schedule), mode="fixed", new_id=ids
        ).schedule
        assert fixed.cycles == schedule.cycles
        assert fixed.current.order == 2
        assert [cycle.order for cycle in s.project(fixed)] == [10, 11, 12, 13, 14]

    @pytest.mark.parametrize("saved", [2, 7])
    def test_fixed_conversion_respects_a_credited_repeat_start(self, ids, saved):
        schedule = configured(ids, current=saved - 1)
        repeating = s.replace_plan(
            schedule, steps=schedule.plan.steps, mode="repeating", new_id=ids
        ).schedule
        fixed = s.replace_plan(
            repeating, steps=s.fixed_steps(repeating), mode="fixed", new_id=ids
        ).schedule
        assert fixed.cycles == schedule.cycles
        assert fixed.plan.order_for(fixed.plan.length) - 1 == 7

    @pytest.mark.parametrize(
        "saved,counts,end", [(0, [2], 7), (1, [1], 7), (2, [], 7), (3, [1], 9)]
    )
    def test_fixed_conversion_retains_an_unstarted_replacement_pattern(
        self, ids, saved, counts, end
    ):
        schedule = configured(ids, current=4, mode="repeating")
        downtime = schedule.phases[1].id
        repeating = s.replace_plan(
            schedule,
            steps=(s.PlanStep("new-downtime", downtime, 2),),
            mode="repeating",
            new_id=ids,
        ).schedule
        if saved:
            target = s.project(repeating)[saved - 1]
            change, _selected = s._ensure_saved(repeating, target.ref, new_id=ids)
            repeating = change.schedule
        steps = s.fixed_steps(repeating)
        assert [step.count for step in steps] == counts
        fixed = s.replace_plan(
            repeating, steps=steps, mode="fixed", new_id=ids
        ).schedule
        assert fixed.cycles == repeating.cycles
        assert fixed.current_cycle_id == schedule.current_cycle_id
        assert fixed.plan.order_for(fixed.plan.length) - 1 == end

    @pytest.mark.parametrize("completed", [False, True])
    def test_fixed_conversion_keeps_installed_credit_after_a_saved_phase_correction(
        self, ids, completed
    ):
        schedule = configured(ids, current=6 if completed else 4)
        steps = (
            schedule.plan.steps
            if completed
            else (s.PlanStep("new-downtime", schedule.phases[1].id, 2),)
        )
        repeating = s.replace_plan(
            schedule, steps=steps, mode="repeating", new_id=ids
        ).schedule
        assert repeating.plan.start_position == (7 if completed else 0)
        tail = repeating.cycles[-1]
        corrected = s.edit_cycle(
            repeating,
            s.SavedCycleRef(tail.id),
            replace(tail.details, phase_id=schedule.phases[0 if completed else 1].id),
            now=LATER,
            new_id=ids,
        ).schedule
        resaved = s.replace_plan(
            corrected, steps=corrected.plan.steps, mode="repeating", new_id=ids
        ).schedule
        assert resaved is corrected
        proposed = s.fixed_steps(resaved)
        assert [step.count for step in proposed] == ([] if completed else [2])
        fixed = s.replace_plan(
            corrected, steps=proposed, mode="fixed", new_id=ids
        ).schedule
        assert fixed.cycles == corrected.cycles
        assert fixed.plan.order_for(fixed.plan.length) - 1 == 7

    @pytest.mark.parametrize("current,counts", [(0, [2, 1, 3]), (3, [3]), (6, [])])
    def test_a_fixed_plan_editor_contains_only_the_unsaved_remainder(
        self, ids, current, counts
    ):
        schedule = configured(ids, current=current)
        steps = s.editable_steps(schedule)
        assert [step.count for step in steps] == counts
        assert [step.phase_id for step in steps] == [
            cycle.phase_id
            for cycle in s.project(schedule)
            if cycle.source.offset == 0
            or cycle.source.position.index == schedule.next_position
        ]
        unchanged = s.replace_plan(schedule, steps=steps, mode="fixed", new_id=ids)
        assert unchanged.schedule is schedule
        assert unchanged.schedule.next_position == current + 1

    def test_a_repeating_editor_keeps_the_complete_pattern_at_any_position(self, ids):
        schedule = configured(ids, current=9, mode="repeating")
        assert s.editable_steps(schedule) == schedule.plan.steps
        assert s.project(
            s.PlanContinuation(schedule.plan, schedule.next_position, schedule.calendar)
        ) == s.project(schedule)
        assert (
            s.replace_plan(
                schedule, steps=s.editable_steps(schedule), mode="repeating", new_id=ids
            ).schedule
            is schedule
        )

    def test_separate_downtime_steps_keep_their_positions_across_repetitions(self, ids):
        schedule = configured(ids)
        occupation, downtime, takeover = [p.id for p in schedule.phases]
        changed = s.replace_plan(
            schedule,
            mode="repeating",
            steps=(
                s.PlanStep("occupation", occupation, 2),
                s.PlanStep("first-downtime", downtime, 1),
                s.PlanStep("takeover", takeover, 2),
                s.PlanStep("second-downtime", downtime, 1),
            ),
            new_id=ids,
        ).schedule
        projected = s.project(changed, limit=14)
        expected = [
            "occupation",
            "occupation",
            "first-downtime",
            "takeover",
            "takeover",
            "second-downtime",
        ] * 3
        assert [p.source.step_id for p in projected] == expected[1:15]
        assert [p.source.repetition for p in projected] == (
            [0] * 6 + [1] * 6 + [2] * 6
        )[1:15]
        assert [p.source.offset for p in projected] == ([0, 1, 0, 0, 1, 0] * 3)[1:15]
        saved = s.edit_cycle(
            changed,
            projected[7].ref,
            s.CycleDetails(occupation),
            new_id=ids,
        ).schedule
        assert s.project(saved, limit=1)[0].source == projected[8].source

    def test_replacing_a_plan_starts_after_the_saved_tail_not_the_current_cycle(
        self, ids
    ):
        schedule = configured(ids)
        future = s.project(schedule, limit=4)[-1]
        schedule = s.edit_cycle(
            schedule, future.ref, s.CycleDetails(future.phase_id), new_id=ids
        ).schedule
        changed = s.replace_plan(
            schedule,
            steps=(s.PlanStep("repeat", schedule.phases[1].id, 2),),
            mode="repeating",
            new_id=ids,
        ).schedule
        assert changed.cycles == schedule.cycles
        assert changed.current_cycle_id == schedule.current_cycle_id
        assert changed.next_position == 0
        assert changed.plan.starts_after_order == 5
        first = s.project(changed, limit=1)[0]
        assert first.order == 6
        assert first.source.position == s.PlannedPosition(changed.plan.id, 0)

    def test_an_unsaved_reference_to_a_replaced_plan_is_rejected(self, ids):
        schedule = configured(ids)
        stale = s.project(schedule, limit=3)[-1]
        changed = s.apply_template(schedule, s.DEFAULT_TEMPLATE, new_id=ids).schedule
        with pytest.raises(s.ScheduleError, match="plan changed"):
            s.edit_cycle(changed, stale.ref, s.CycleDetails(stale.phase_id), new_id=ids)

    def test_a_materialised_reference_survives_replacement(self, ids):
        schedule = configured(ids)
        target = s.project(schedule, limit=2)[-1]
        details = s.CycleDetails(target.phase_id)
        schedule = s.edit_cycle(schedule, target.ref, details, new_id=ids).schedule
        schedule = s.apply_template(schedule, s.DEFAULT_TEMPLATE, new_id=ids).schedule
        replay = s.edit_cycle(schedule, target.ref, details, new_id=ids)
        assert replay.schedule == schedule
        assert replay.created == ()

    def test_replacing_a_template_preserves_saved_phase_definitions(self, ids):
        schedule = configured(ids, current=3)
        old_phases, old_cycles = schedule.phases, schedule.cycles
        replacement = replace(
            s.DEFAULT_TEMPLATE,
            phases=(
                replace(
                    s.DEFAULT_TEMPLATE.phases[0],
                    details=s.PhaseDetails("A new opening"),
                ),
                *s.DEFAULT_TEMPLATE.phases[1:],
            ),
        )
        changed = s.apply_template(schedule, replacement, new_id=ids).schedule
        assert changed.phases[:3] == old_phases
        assert changed.cycles == old_cycles
        assert phase_names(changed, s.project(changed, limit=1)) == ["A new opening"]
        assert changed.current_phase.details.name == "Downtime"

    def test_a_fixed_replacement_can_follow_a_repeating_saved_prefix(self, ids):
        schedule = configured(ids, current=8, mode="repeating")
        changed = s.apply_template(schedule, s.DEFAULT_TEMPLATE, new_id=ids).schedule
        assert changed.plan.mode == "fixed"
        assert [p.order for p in s.project(changed)] == list(range(10, 17))
        assert changed.cycles == schedule.cycles

    def test_removing_all_future_fixed_entries_keeps_saved_cycles_and_allows_finishing(
        self, ids
    ):
        schedule = configured(ids, current=2)
        changed = s.replace_plan(schedule, steps=(), mode="fixed", new_id=ids).schedule
        assert changed.cycles == schedule.cycles
        assert s.project(changed) == ()
        assert s.preview_advance(changed).finishes
        assert s.finish(changed, now=LATER).schedule.current == schedule.current


class TestTransitions:
    def test_advancing_into_a_saved_cycle_consumes_no_plan_position(self, ids):
        schedule = configured(ids)
        third = s.project(schedule, limit=2)[-1]
        schedule = s.edit_cycle(
            schedule, third.ref, s.CycleDetails(third.phase_id), new_id=ids
        ).schedule
        preview = s.preview_advance(schedule)
        assert preview.following == schedule.cycles[1]
        changed = s.advance(schedule, now=LATER, new_id=ids)
        assert changed.schedule.current.order == 2
        assert changed.schedule.next_position == schedule.next_position
        assert changed.created == ()
        assert not changed.transition.enters_phase

    def test_advancing_into_a_projection_saves_and_activates_it_together(self, ids):
        schedule = configured(ids, current=2)
        preview = s.preview_advance(schedule)
        assert isinstance(preview.following, s.ProjectedCycle)
        changed = s.advance(schedule, now=LATER, new_id=ids)
        assert changed.created == (changed.schedule.current,)
        assert changed.schedule.current_phase.details.name == "Downtime"
        assert changed.transition.enters_phase
        assert changed.transition.previous_cycle == schedule.current
        assert changed.transition.occurred_at == LATER

    def test_current_phase_reassignment_records_phase_entry_without_ending_a_cycle(
        self, ids
    ):
        schedule = configured(ids)
        changed = s.edit_cycle(
            schedule,
            s.SavedCycleRef(schedule.current.id),
            replace(schedule.current.details, phase_id=schedule.phases[1].id),
            now=LATER,
        )
        assert changed.schedule.current.id == schedule.current.id
        assert changed.schedule.current_phase.details.name == "Downtime"
        assert changed.transition.kind == "phase_changed"
        assert changed.transition.enters_phase
        assert changed.schedule.next_position == schedule.next_position

    def test_historical_reassignment_and_phase_copy_edits_do_not_activate_anything(
        self, ids
    ):
        schedule = configured(ids, current=3)
        changed = s.edit_cycle(
            schedule,
            s.SavedCycleRef(schedule.cycles[0].id),
            replace(schedule.cycles[0].details, phase_id=schedule.phases[2].id),
        )
        assert changed.transition is None
        changed = s.edit_phase(
            changed.schedule,
            schedule.current_phase.id,
            s.PhaseDetails("Intermission", effects="An arbitrator's note."),
        )
        assert changed.transition is None

    def test_finishing_retains_the_final_cycle_and_its_context(self, ids):
        schedule = configured(ids, current=6)
        assert s.preview_advance(schedule).finishes
        with pytest.raises(s.ScheduleError, match="Finish the campaign"):
            s.advance(schedule, now=LATER)
        changed = s.finish(schedule, now=LATER)
        assert changed.schedule.current == schedule.current
        assert changed.schedule.status == "post_campaign"
        assert changed.transition.kind == "finished"
        assert not changed.transition.enters_phase
        assert changed.created == ()
        assert s.context(changed.schedule, schedule.current.id) == s.context(
            schedule, schedule.current.id
        )

    def test_an_occupation_context_stays_pinned_after_entry_into_takeover(self, ids):
        schedule = configured(ids)
        pinned = s.context(schedule, schedule.current.id)
        for _ in range(4):
            schedule = s.advance(schedule, now=LATER, new_id=ids).schedule
        assert schedule.current_phase.details.name == "Takeover"
        assert s.context(schedule, pinned.cycle_id) == pinned
        assert phase_names(schedule, [schedule.cycles[0]]) == ["Occupation"]

    def test_an_unstarted_campaign_cannot_advance(self, ids):
        schedule = configured(ids, status="pre_campaign")
        with pytest.raises(s.ScheduleError, match="Start the campaign"):
            s.advance(schedule, now=LATER)

    def test_a_finished_campaign_cannot_advance(self, ids):
        schedule = s.finish(configured(ids), now=LATER).schedule
        with pytest.raises(s.ScheduleError, match="campaign has finished"):
            s.advance(schedule, now=LATER)

    @pytest.mark.parametrize("now", [None, datetime(2026, 11, 7)])
    def test_actual_transition_times_require_a_time_zone(self, ids, now):
        schedule = configured(ids, status="pre_campaign")
        with pytest.raises(s.ScheduleError, match="time zone"):
            s.start(schedule, now=now)


class TestPhasesAndValidation:
    def test_duplicating_a_phase_preserves_settings_without_reassigning_cycles(
        self, ids
    ):
        schedule = configured(ids)
        settings = s.RewardSettings(
            win=s.Reward(s.CreditAmount(10, s.DiceAmount(2, 6, 10)), 2),
            entry_credits=s.CreditAmount(100),
        )
        schedule = s.edit_phase(
            schedule,
            schedule.current_phase.id,
            s.PhaseDetails("Opening", rewards=settings),
        ).schedule
        changed = s.duplicate_phase(
            schedule, schedule.current_phase.id, name="Extended opening", new_id=ids
        )
        assert changed.schedule.phases[-1].details.rewards == settings
        assert changed.schedule.phases[-1].id != schedule.current_phase.id
        assert changed.schedule.cycles == schedule.cycles
        assert changed.schedule.plan == schedule.plan
        assert changed.transition is None

    def test_current_phase_deletion_requires_explicit_current_selection(self, ids):
        state = configured(ids)
        with pytest.raises(s.ScheduleError, match="replacement current cycle"):
            s.delete_phase(state, state.current_phase.id)

    def test_phase_deletion_removes_all_future_occurrences(self, ids):
        state = configured(ids, mode="repeating")
        removed = s.delete_phase(state, state.phases[1].id, new_id=ids)
        assert all(
            c.phase_id != state.phases[1].id
            for c in s.project(removed.schedule, limit=20)
        )
        assert removed.schedule.current == state.current
        assert removed.transition is None

    def test_an_unused_phase_is_archived(self, ids):
        state = configured(ids)
        copied = s.duplicate_phase(
            state, state.current_phase.id, name="Unused", new_id=ids
        ).schedule
        after = s.delete_phase(copied, copied.phases[-1].id).schedule
        assert after.phases[:-1] == state.phases
        assert after.phases[-1].archived

    @pytest.mark.parametrize("count", [0, -1, 1.5, True])
    def test_a_step_requires_a_positive_whole_cycle_count(self, count):
        with pytest.raises(s.ScheduleError, match="positive whole"):
            s.PlanStep("step", "phase", count)

    @pytest.mark.parametrize("limit", [0, -1, 1.5, True])
    def test_projection_requires_a_positive_whole_limit(self, ids, limit):
        with pytest.raises(s.ScheduleError, match="positive whole"):
            s.project(configured(ids), limit=limit)

    def test_repeated_step_identities_are_rejected(self, ids):
        schedule = configured(ids)
        with pytest.raises(s.ScheduleError, match="distinct identities"):
            s.replace_plan(
                schedule,
                steps=(schedule.plan.steps[0], schedule.plan.steps[0]),
                mode="fixed",
                new_id=ids,
            )

    def test_an_empty_plan_is_rejected(self):
        with pytest.raises(s.ScheduleError, match="at least one step"):
            s.Plan("empty", "repeating", ())

    def test_a_cycle_cannot_end_before_its_own_start(self):
        with pytest.raises(s.ScheduleError, match="end date"):
            s.CycleDetails(
                "phase", starts_on=date(2026, 2, 2), ends_on=date(2026, 2, 1)
            )

    def test_foreign_phases_cannot_enter_a_replacement_plan(self, ids):
        schedule = configured(ids)
        with pytest.raises(s.ScheduleError, match="phases from this campaign"):
            s.replace_plan(
                schedule,
                steps=(s.PlanStep("foreign", "other-campaign-phase", 1),),
                mode="fixed",
                new_id=ids,
            )


class TestDeletion:
    def test_projected_cycle_deletion_saves_prefix_and_preserves_pattern(self, ids):
        state = configured(ids, mode="repeating")
        target = s.project(state)[4]
        change = s.delete_cycle(state, target.ref, new_id=ids)
        assert [c.order for c in change.created] == [2, 3, 4, 5, 6]
        assert [c.order for c in change.created if c.archived] == [6]
        assert change.schedule.plan == state.plan
        assert change.schedule.current == state.current
        assert s.project(change.schedule)[0].order == 7
        assert change.transition is None
        with pytest.raises(s.ScheduleError, match="deleted"):
            s._ensure_saved(change.schedule, target.ref, new_id=ids)

    @pytest.mark.parametrize("mode", ["fixed", "repeating"])
    def test_deleting_downtime_preserves_cursor_into_takeover(self, ids, mode):
        state = configured(ids, current=3, mode=mode)
        phase_id = state.current_phase.id
        change = s.delete_phase(state, phase_id, no_current=True, new_id=ids)
        assert change.schedule.current is None
        assert change.schedule.cycles[3].archived
        assert s.project(change.schedule)[0].phase_id == state.phases[2].id
        assert s.project(change.schedule)[0].order == 5
        assert change.transition is None

    def test_repeated_occurrences_map_the_old_cursor_into_the_filtered_pattern(
        self, ids
    ):
        template = s.ScheduleTemplate(
            "Repeated",
            (
                s.Phase("a", s.PhaseDetails("A")),
                s.Phase("b", s.PhaseDetails("B")),
                s.Phase("c", s.PhaseDetails("C")),
            ),
            (
                s.PlanStep("a1", "a", 2),
                s.PlanStep("b", "b", 1),
                s.PlanStep("a2", "a", 3),
                s.PlanStep("c", "c", 2),
            ),
        )
        state = s.configure(
            template,
            campaign_id="campaign",
            mode="repeating",
            current_position=4,
            new_id=ids,
        ).schedule
        change = s.delete_phase(state, state.phases[0].id, no_current=True, new_id=ids)
        assert [c.phase_id for c in s.project(change.schedule, limit=4)] == [
            state.phases[2].id,
            state.phases[2].id,
            state.phases[1].id,
            state.phases[2].id,
        ]
        assert [c.archived for c in change.schedule.cycles] == [
            True,
            True,
            False,
            True,
            True,
        ]

    def test_current_cycle_replacement_does_not_start_or_advance(self, ids):
        state = configured(ids, current=3)
        target = s.SavedCycleRef(state.current_cycle_id)
        with pytest.raises(s.ScheduleError, match="not being deleted"):
            s.delete_cycle(state, target, replacement=target)
        replacement = s.project(state)[1]
        change = s.delete_cycle(state, target, replacement=replacement.ref, new_id=ids)
        assert change.schedule.current.order == replacement.order
        assert change.schedule.status == state.status
        assert change.transition is None

    def test_start_and_advance_skip_archived_saved_cycles(self, ids):
        state = configured(ids, current=3)
        state = s.delete_cycle(state, s.SavedCycleRef(state.cycles[1].id)).schedule
        state = s.delete_cycle(
            state,
            s.SavedCycleRef(state.current_cycle_id),
            replacement=s.SavedCycleRef(state.cycles[0].id),
        ).schedule
        assert s.preview_advance(state).following.order == 3
        state = s.delete_cycle(
            state, s.SavedCycleRef(state.current_cycle_id), no_current=True
        ).schedule
        assert s.start(state, now=NOW).schedule.current.order == 3

    @pytest.mark.parametrize("mode", ["fixed", "repeating"])
    def test_last_phase_deletion_leaves_rebuildable_empty_fixed_schedule(
        self, ids, mode
    ):
        template = s.ScheduleTemplate(
            "Only", (s.Phase("a", s.PhaseDetails("A")),), (s.PlanStep("a", "a", 2),)
        )
        state = s.configure(
            template, campaign_id="campaign", mode=mode, current_position=0, new_id=ids
        ).schedule
        change = s.delete_phase(
            state, state.current_phase.id, no_current=True, new_id=ids
        )
        assert change.schedule.plan.mode == "fixed"
        assert not s.project(change.schedule)
        assert all(c.archived for c in change.schedule.cycles)
        assert all(p.archived for p in change.schedule.phases)
        with pytest.raises(s.ScheduleError, match="Add a cycle"):
            s.start(change.schedule, now=NOW)
        rebuilt = s.add_phase(
            change.schedule, s.PhaseDetails("Fresh"), new_id=ids
        ).schedule
        rebuilt = s.replace_plan(
            rebuilt,
            steps=(s.PlanStep("new", rebuilt.phases[-1].id, 1),),
            mode="fixed",
            new_id=ids,
        ).schedule
        assert s.start(rebuilt, now=NOW, new_id=ids).schedule.current.order == 2
