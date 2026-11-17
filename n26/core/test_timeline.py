"""Pure timeline authoring preserves identities, history and generated cursors."""

from dataclasses import replace
from datetime import UTC, date, datetime
from itertools import count

import pytest

from n26.core import schedule as s
from n26.core import timeline as t


@pytest.fixture
def ids():
    sequence = count()
    return lambda: f"new-{next(sequence)}"


def state(*, protected=(), current="cycle-1", repeating=False):
    phases = (
        s.Phase(
            "occupation",
            s.PhaseDetails(
                "Occupation",
                "Opening story",
                "Claim territory",
                s.RewardSettings(entry_credits=s.CreditAmount(100)),
            ),
        ),
        s.Phase("downtime", s.PhaseDetails("Downtime")),
        s.Phase("takeover", s.PhaseDetails("Takeover")),
    )
    occurrences = (
        s.PhaseOccurrence("block-1", "occupation", 1),
        s.PhaseOccurrence("block-2", "downtime", 2),
        s.PhaseOccurrence("block-3", "occupation", 3),
    )
    cycles = tuple(
        s.Cycle(
            f"cycle-{order}",
            order,
            s.CycleDetails(
                occurrence.phase_id,
                custom_name="Market week" if order == 3 else None,
                description="",
                effects="Local effect" if order == 3 else "",
            ),
            s.CycleSource(
                s.PlannedPosition("source-plan", order - 1), "source-step", 0, order - 1
            ),
            occurrence_id=occurrence.id,
            customized_fields=frozenset(
                {"custom_name", "starts_on", "ends_on", "description", "effects"}
            )
            if order == 3
            else frozenset(),
        )
        for order, occurrence in enumerate(
            (
                occurrences[0],
                occurrences[0],
                occurrences[1],
                occurrences[1],
                occurrences[2],
            ),
            start=1,
        )
    )
    plan = s.Plan(
        "tail",
        "repeating" if repeating else "fixed",
        (s.PlanStep("tail-step", "occupation", 3),) if repeating else (),
    )
    return s.Schedule(
        "campaign",
        phases,
        plan,
        5 if repeating else 0,
        cycles,
        current,
        status="in_progress",
        revision=4,
        occurrences=occurrences,
        protected_cycle_ids=frozenset(protected),
    )


def live(schedule):
    return tuple(c for c in schedule.cycles if not c.archived)


def blocks(schedule):
    return tuple(o for o in schedule.occurrences if not o.archived)


def test_inserting_an_authored_cycle_pushes_the_tail_without_consuming_its_cursor(ids):
    original = state(repeating=True)
    details = s.CycleDetails(
        "occupation", custom_name="Market day", description="", effects=""
    )
    change = t.insert_cycle(
        original, "block-3", after_cycle_id="cycle-5", details=details, new_id=ids
    )
    assert [c.order for c in live(change.schedule)] == [1, 2, 3, 4, 5, 6]
    assert change.created[0].source == s.CycleSource()
    assert change.created[0].details == details
    assert change.created[0].customized_fields == frozenset(
        s.CycleDetails.__dataclass_fields__
    )
    assert change.schedule.next_position == original.next_position
    assert change.schedule.plan == original.plan
    assert s.project(change.schedule, limit=1)[0].order == 7
    assert (
        s.project(change.schedule, limit=1)[0].source
        == s.project(original, limit=1)[0].source
    )
    assert change.schedule.current_cycle_id == original.current_cycle_id
    assert change.transition is None
    assert change.schedule.revision == original.revision + 1


def test_moving_a_cycle_keeps_its_identity_source_and_explicit_empty_customisations():
    original = state()
    selected = original.cycles[2]
    change = t.move_cycle(original, selected.id, "block-3", after_cycle_id="cycle-5")
    moved = live(change.schedule)[-1]
    assert [c.id for c in live(change.schedule)] == [
        "cycle-1",
        "cycle-2",
        "cycle-4",
        "cycle-5",
        "cycle-3",
    ]
    assert moved.id == selected.id and moved.source == selected.source
    assert moved.details == replace(selected.details, phase_id="occupation")
    assert selected.customized_fields <= moved.customized_fields
    assert {"phase_id", "occurrence_id"} <= moved.customized_fields
    assert [o.id for o in blocks(change.schedule)] == ["block-1", "block-2", "block-3"]
    assert selected.id in {c.id for c in change.updated}
    assert not change.created


def test_removing_an_unused_cycle_archives_only_it_and_renumbers_survivors():
    original = state()
    change = t.remove_cycle(original, "cycle-3")
    assert [c.id for c in live(change.schedule)] == [
        "cycle-1",
        "cycle-2",
        "cycle-4",
        "cycle-5",
    ]
    assert [c.order for c in live(change.schedule)] == [1, 2, 3, 4]
    removed = next(c for c in change.schedule.cycles if c.id == "cycle-3")
    assert removed == replace(original.cycles[2], archived=True)
    assert change.schedule.phases == original.phases
    assert change.schedule.occurrences == original.occurrences
    assert s.project(change.schedule) == ()


def test_last_child_removal_leaves_an_empty_addressable_block(ids):
    original = state()
    removed = t.remove_cycle(original, "cycle-5").schedule
    assert blocks(removed)[-1].id == "block-3"
    assert not [c for c in live(removed) if c.occurrence_id == "block-3"]
    restored = t.insert_cycle(removed, "block-3", new_id=ids)
    assert restored.created[0].occurrence_id == "block-3"
    assert next(c for c in restored.schedule.cycles if c.id == "cycle-5").archived


def test_cycle_copy_keeps_fields_but_gets_a_new_identity_and_no_generated_source(ids):
    original = state(repeating=True)
    change = t.duplicate_cycle(original, "cycle-3", new_id=ids)
    copied = change.created[0]
    assert copied.id != "cycle-3"
    assert copied.details == original.cycles[2].details
    assert copied.customized_fields == original.cycles[2].customized_fields
    assert copied.source == s.CycleSource()
    assert copied.order == 4
    assert change.schedule.next_position == original.next_position


def dated(original):
    return replace(
        original,
        cycles=tuple(
            replace(
                c,
                details=replace(
                    c.details,
                    starts_on=date(2026, 11, c.order),
                    ends_on=date(2026, 11, c.order),
                ),
            )
            for c in original.cycles
        ),
    )


def test_dated_copy_refuses_overlap_and_only_explicit_clear_dates_removes_bounds(ids):
    original = dated(state())
    with pytest.raises(s.ScheduleError, match="overlap"):
        t.duplicate_cycle(original, "cycle-3", new_id=ids)
    copied = t.duplicate_cycle(
        original, "cycle-3", clear_dates=True, new_id=ids
    ).created[0]
    assert copied.details == replace(
        original.cycles[2].details, starts_on=None, ends_on=None
    )
    assert {"starts_on", "ends_on"} <= copied.customized_fields
    assert original.cycles[2].details.starts_on == date(2026, 11, 3)


@pytest.mark.parametrize(
    "move",
    [
        lambda schedule: t.move_cycle(
            schedule, "cycle-3", "block-2", after_cycle_id="cycle-4"
        ),
        lambda schedule: t.move_occurrence(
            schedule, "block-2", after_occurrence_id="block-3"
        ),
    ],
)
def test_reordering_dated_entries_refuses_instead_of_clearing_dates(move):
    original = dated(state())
    with pytest.raises(s.ScheduleError, match="must follow"):
        move(original)
    assert [c.details.starts_on for c in original.cycles] == [
        date(2026, 11, n) for n in range(1, 6)
    ]


def test_complete_candidate_dates_are_validated_even_for_a_rules_edit(ids):
    original = dated(state())
    original = replace(
        original,
        cycles=tuple(
            replace(
                c,
                details=replace(
                    c.details, starts_on=date(2026, 11, 1), ends_on=date(2026, 11, 1)
                ),
            )
            if c.id == "cycle-4"
            else c
            for c in original.cycles
        ),
    )
    with pytest.raises(s.ScheduleError, match="overlap"):
        t.edit_occurrence(original, "block-3", s.PhaseDetails("Changed"), new_id=ids)


def test_insert_move_and_duplicate_empty_blocks_have_independent_positions(ids):
    original = state()
    change = t.insert_occurrence(
        original, "takeover", after_occurrence_id="block-1", new_id=ids
    )
    empty = blocks(change.schedule)[1]
    assert [c.id for c in live(change.schedule)] == [c.id for c in original.cycles]
    assert [o.position for o in blocks(change.schedule)] == [1, 2, 3, 4]
    moved = t.move_occurrence(
        change.schedule, empty.id, after_occurrence_id="block-3"
    ).schedule
    assert blocks(moved)[-1].id == empty.id
    copy = t.duplicate_occurrence(moved, empty.id, new_id=ids)
    assert len(blocks(copy.schedule)) == 5
    assert copy.created == ()
    assert blocks(copy.schedule)[-1].phase_id != empty.phase_id


def test_new_block_can_have_its_own_phase_rules(ids):
    original = state()
    details = s.PhaseDetails(
        "Festival",
        "A market opens",
        "Trade equipment",
        original.phases[0].details.rewards,
    )
    change = t.insert_occurrence(
        original, details=details, after_occurrence_id="block-3", new_id=ids
    )
    block = blocks(change.schedule)[-1]
    assert block.phase_id == change.schedule.phases[-1].id
    assert change.schedule.phases[-1].details == details
    assert change.schedule.phases[:-1] == original.phases
    assert not change.created


def test_moving_a_block_moves_all_children_without_recreating_them():
    original = state()
    change = t.move_occurrence(original, "block-2", after_occurrence_id="block-3")
    assert [c.id for c in live(change.schedule)] == [
        "cycle-1",
        "cycle-2",
        "cycle-5",
        "cycle-3",
        "cycle-4",
    ]
    assert {
        c.id: (c.details, c.source, c.customized_fields) for c in live(change.schedule)
    } == {c.id: (c.details, c.source, c.customized_fields) for c in original.cycles}
    assert [o.id for o in blocks(change.schedule)] == ["block-1", "block-3", "block-2"]
    assert change.created == () and change.transition is None


def test_duplicating_a_block_copies_rules_children_and_explicit_empty_fields(ids):
    original = state(repeating=True)
    change = t.duplicate_occurrence(original, "block-2", new_id=ids)
    copied_block = blocks(change.schedule)[2]
    copied_phase = next(
        p for p in change.schedule.phases if p.id == copied_block.phase_id
    )
    assert copied_phase.id != "downtime"
    assert copied_phase.details == original.phases[1].details
    assert len(change.created) == 2
    for copied, source in zip(change.created, original.cycles[2:4], strict=True):
        assert copied.details == replace(source.details, phase_id=copied_phase.id)
        assert copied.id != source.id and copied.occurrence_id == copied_block.id
        assert copied.source == s.CycleSource()
        assert copied.customized_fields == source.customized_fields
    assert change.schedule.next_position == original.next_position
    assert change.schedule.plan == original.plan


def test_dated_block_copy_needs_explicit_bound_clearing(ids):
    original = dated(state())
    with pytest.raises(s.ScheduleError, match="overlap"):
        t.duplicate_occurrence(original, "block-2", new_id=ids)
    change = t.duplicate_occurrence(original, "block-2", clear_dates=True, new_id=ids)
    assert all(
        c.details.starts_on is None and c.details.ends_on is None
        for c in change.created
    )
    assert all({"starts_on", "ends_on"} <= c.customized_fields for c in change.created)


def test_occurrence_edit_copies_rules_only_for_selected_repeated_block(ids):
    original = state(repeating=True)
    details = s.PhaseDetails(
        "Occupation finale",
        "New story",
        "Special rules",
        s.RewardSettings(entry_credits=s.CreditAmount(250)),
    )
    change = t.edit_occurrence(original, "block-3", details, new_id=ids)
    edited = blocks(change.schedule)[2]
    assert edited.id == "block-3" and edited.phase_id != "occupation"
    assert change.schedule.phases[-1].details == details
    assert change.schedule.phases[:-1] == original.phases
    assert blocks(change.schedule)[0] == original.occurrences[0]
    assert live(change.schedule)[:4] == original.cycles[:4]
    assert live(change.schedule)[-1].id == "cycle-5"
    assert live(change.schedule)[-1].details.phase_id == edited.phase_id
    assert live(change.schedule)[-1].source == original.cycles[-1].source
    assert change.schedule.plan == original.plan
    assert s.project(change.schedule, limit=1)[0].phase_id == "occupation"


def test_removing_one_block_does_not_remove_other_occurrences_or_phase_rules():
    original = state()
    change = t.remove_occurrence(original, "block-3")
    assert [o.id for o in blocks(change.schedule)] == ["block-1", "block-2"]
    assert change.schedule.phases == original.phases
    assert next(o for o in change.schedule.occurrences if o.id == "block-3").archived
    assert next(c for c in change.schedule.cycles if c.id == "cycle-5").archived
    assert change.schedule.plan == original.plan


@pytest.mark.parametrize(
    "command",
    [
        lambda state, ids: t.remove_cycle(state, "cycle-1"),
        lambda state, ids: t.move_cycle(state, "cycle-1", "block-2"),
        lambda state, ids: t.insert_cycle(state, "block-1", new_id=ids),
        lambda state, ids: t.remove_occurrence(state, "block-1"),
        lambda state, ids: t.move_occurrence(
            state, "block-1", after_occurrence_id="block-3"
        ),
        lambda state, ids: t.insert_occurrence(state, "takeover", new_id=ids),
        lambda state, ids: t.edit_occurrence(
            state, "block-1", s.PhaseDetails("Changed"), new_id=ids
        ),
    ],
)
def test_current_and_earlier_history_cannot_be_changed_or_crossed(command, ids):
    original = state(current="cycle-2")
    with pytest.raises(s.ScheduleError, match="Current"):
        command(original, ids)


@pytest.mark.parametrize(
    "command",
    [
        lambda state, ids: t.remove_cycle(state, "cycle-4"),
        lambda state, ids: t.move_cycle(
            state, "cycle-3", "block-2", after_cycle_id="cycle-4"
        ),
        lambda state, ids: t.insert_cycle(state, "block-2", new_id=ids),
        lambda state, ids: t.move_occurrence(
            state, "block-2", after_occurrence_id="block-3"
        ),
        lambda state, ids: t.edit_occurrence(
            state, "block-2", s.PhaseDetails("Changed"), new_id=ids
        ),
    ],
)
def test_referenced_future_cycles_and_their_positions_are_protected(command, ids):
    with pytest.raises(s.ScheduleError, match="recorded activity"):
        command(state(protected={"cycle-4"}), ids)


def test_empty_blocks_before_current_are_protected_even_without_children(ids):
    original = state()
    empty = s.PhaseOccurrence("empty-history", "takeover", 1)
    original = replace(
        original,
        occurrences=(empty,)
        + tuple(replace(o, position=o.position + 1) for o in original.occurrences),
    )
    with pytest.raises(s.ScheduleError, match="Current phase blocks"):
        t.move_occurrence(original, empty.id, after_occurrence_id="block-3")


def test_existing_archives_are_retained_exactly_and_do_not_block_reusing_their_dates(
    ids,
):
    original = state()
    archived_cycle = replace(
        original.cycles[2],
        id="archived-cycle",
        order=40,
        archived=True,
        source=s.CycleSource(),
        details=replace(
            original.cycles[2].details,
            starts_on=date(2026, 11, 10),
            ends_on=date(2026, 11, 10),
        ),
    )
    archived_block = s.PhaseOccurrence("archived-block", "takeover", 90, archived=True)
    original = replace(
        original,
        cycles=original.cycles + (archived_cycle,),
        occurrences=original.occurrences + (archived_block,),
    )
    change = t.insert_cycle(
        original,
        "block-3",
        after_cycle_id="cycle-5",
        details=s.CycleDetails(
            "occupation", starts_on=date(2026, 11, 10), ends_on=date(2026, 11, 10)
        ),
        new_id=ids,
    )
    assert change.schedule.cycles[-1] == archived_cycle
    assert change.schedule.occurrences[-1] == archived_block
    assert archived_cycle not in change.updated


def test_all_unused_blocks_can_be_removed_without_recreating_a_fixed_tail():
    schedule = state(current=None)
    for occurrence in tuple(blocks(schedule)):
        schedule = t.remove_occurrence(schedule, occurrence.id).schedule
    assert live(schedule) == () and blocks(schedule) == ()
    assert len(schedule.cycles) == 5 and all(c.archived for c in schedule.cycles)
    assert s.project(schedule) == ()


def test_exact_noops_do_not_bump_revision_or_allocate_new_rules(ids):
    original = state()
    assert t.move_cycle(original, "cycle-3", "block-2").schedule is original
    assert (
        t.move_occurrence(original, "block-2", after_occurrence_id="block-1").schedule
        is original
    )
    assert (
        t.edit_occurrence(
            original, "block-3", original.phases[0].details, new_id=ids
        ).schedule
        is original
    )


@pytest.mark.parametrize(
    "command",
    [
        lambda state, ids: t.insert_cycle(state, "foreign", new_id=ids),
        lambda state, ids: t.move_cycle(state, "foreign", "block-2"),
        lambda state, ids: t.insert_cycle(
            state, "block-2", after_cycle_id="cycle-5", new_id=ids
        ),
        lambda state, ids: t.insert_cycle(
            state, "block-2", details=s.CycleDetails("occupation"), new_id=ids
        ),
        lambda state, ids: t.move_occurrence(state, "foreign"),
        lambda state, ids: t.move_occurrence(
            state, "block-2", after_occurrence_id="block-2"
        ),
        lambda state, ids: t.move_cycle(
            state, "cycle-3", "block-2", after_cycle_id="cycle-3"
        ),
        lambda state, ids: t.insert_occurrence(
            state, "occupation", details=s.PhaseDetails("Both"), new_id=ids
        ),
    ],
)
def test_foreign_or_ambiguous_targets_are_refused(command, ids):
    with pytest.raises(s.ScheduleError):
        command(state(), ids)


def test_unattached_legacy_cycles_are_refused_instead_of_silently_dropped(ids):
    original = state(current=None)
    original = replace(
        original,
        occurrences=(),
        cycles=tuple(replace(c, occurrence_id=None) for c in original.cycles),
    )
    with pytest.raises(s.ScheduleError, match="Assign each cycle"):
        t.insert_occurrence(original, "occupation", new_id=ids)
    assert len(original.cycles) == 5


def test_unresolved_external_protection_ids_do_not_prevent_editing_unused_future(ids):
    original = state(protected={"not-loaded-reference"})
    change = t.insert_cycle(original, "block-3", after_cycle_id="cycle-5", new_id=ids)
    assert len(live(change.schedule)) == 6
    assert change.schedule.protected_cycle_ids == original.protected_cycle_ids


def test_partly_used_occurrence_edits_only_its_future_suffix(ids):
    original = state(repeating=True)
    changed_rules = s.PhaseDetails(
        "Later occupation",
        "Future story",
        "Future effects",
        s.RewardSettings(entry_credits=s.CreditAmount(200)),
    )
    change = t.edit_occurrence(original, "block-1", changed_rules, new_id=ids)
    assert blocks(change.schedule)[0] == original.occurrences[0]
    assert blocks(change.schedule)[1].id != original.occurrences[0].id
    assert blocks(change.schedule)[1].phase_id == change.schedule.phases[-1].id
    assert change.schedule.phases[-1].details == changed_rules
    assert live(change.schedule)[0] == original.cycles[0]
    assert live(change.schedule)[1].id == "cycle-2"
    assert live(change.schedule)[1].occurrence_id == blocks(change.schedule)[1].id
    assert live(change.schedule)[1].source == original.cycles[1].source
    assert live(change.schedule)[2:] == original.cycles[2:]
    assert [c.order for c in live(change.schedule)] == [1, 2, 3, 4, 5]
    assert change.schedule.phases[:-1] == original.phases
    assert change.schedule.plan == original.plan
    assert change.transition is None


def test_split_cannot_shift_the_position_of_a_later_recorded_block(ids):
    with pytest.raises(s.ScheduleError, match="recorded activity"):
        t.edit_occurrence(
            state(protected={"cycle-5"}),
            "block-1",
            s.PhaseDetails("Future"),
            new_id=ids,
        )


def test_cycle_copy_distinguishes_default_after_source_from_explicit_block_start(ids):
    original = state()
    default = t.duplicate_cycle(original, "cycle-4", new_id=ids)
    beginning = t.duplicate_cycle(original, "cycle-4", after_cycle_id=None, new_id=ids)
    assert default.created[0].order == 5
    assert beginning.created[0].order == 3
    assert [c.id for c in live(beginning.schedule)][2] == beginning.created[0].id


def test_block_copy_distinguishes_default_after_source_from_explicit_timeline_start(
    ids,
):
    original = state(current=None)
    default = t.duplicate_occurrence(original, "block-2", new_id=ids)
    beginning = t.duplicate_occurrence(
        original, "block-2", after_occurrence_id=None, new_id=ids
    )
    assert blocks(default.schedule)[2].phase_id == default.schedule.phases[-1].id
    assert blocks(beginning.schedule)[0].phase_id == beginning.schedule.phases[-1].id
    assert beginning.created[0].order == 1


def test_editing_authored_empty_rules_archives_only_the_unreferenced_old_definition(
    ids,
):
    original = t.insert_occurrence(
        state(), "takeover", after_occurrence_id="block-3", new_id=ids
    ).schedule
    selected = blocks(original)[-1]
    change = t.edit_occurrence(
        original, selected.id, s.PhaseDetails("New takeover"), new_id=ids
    )
    assert next(p for p in change.schedule.phases if p.id == "takeover").archived
    assert (
        next(p for p in change.schedule.phases if p.id == "takeover").details
        == original.phases[2].details
    )
    assert len(blocks(change.schedule)) == len(blocks(original))
    assert blocks(change.schedule)[-1].id == selected.id


@pytest.mark.parametrize("reference", ["archived_occurrence", "active_plan"])
def test_editing_an_empty_block_keeps_definitions_referenced_by_history_or_the_plan(
    ids, reference
):
    original = t.insert_occurrence(
        state(), "takeover", after_occurrence_id="block-3", new_id=ids
    ).schedule
    selected = blocks(original)[-1]
    if reference == "archived_occurrence":
        original = replace(
            original,
            occurrences=original.occurrences
            + (s.PhaseOccurrence("historic-takeover", "takeover", 90, archived=True),),
        )
    else:
        original = replace(
            original,
            plan=s.Plan(
                "takeover-tail",
                "repeating",
                (s.PlanStep("takeover-step", "takeover", 1),),
            ),
            next_position=0,
        )
    change = t.edit_occurrence(
        original, selected.id, s.PhaseDetails("New takeover"), new_id=ids
    )
    assert not next(p for p in change.schedule.phases if p.id == "takeover").archived


def test_cow_keeps_archived_cycle_rules_on_the_original_archived_occurrence(ids):
    original = t.insert_occurrence(
        state(), "takeover", after_occurrence_id="block-3", new_id=ids
    ).schedule
    selected = blocks(original)[-1]
    historical = s.Cycle(
        "historic-takeover",
        90,
        s.CycleDetails("takeover", description="Kept history"),
        s.CycleSource(),
        archived=True,
        occurrence_id=selected.id,
    )
    original = replace(original, cycles=original.cycles + (historical,))
    change = t.edit_occurrence(
        original, selected.id, s.PhaseDetails("New takeover"), new_id=ids
    )
    assert not next(p for p in change.schedule.phases if p.id == "takeover").archived
    original_block = next(o for o in change.schedule.occurrences if o.id == selected.id)
    assert original_block.archived and original_block.phase_id == "takeover"
    assert blocks(change.schedule)[-1].id != selected.id
    assert (
        next(c for c in change.schedule.cycles if c.id == historical.id) == historical
    )


def test_split_preserves_pattern_continuation_despite_explicit_legacy_cycle_fields(ids):
    original = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="legacy-pattern",
        current_position=0,
        mode="repeating",
        new_id=ids,
    ).schedule
    saved, _ = s._ensure_saved(
        original, s.project(original, limit=1)[0].ref, new_id=ids
    )
    original = replace(
        saved.schedule,
        cycles=tuple(
            replace(c, customized_fields=frozenset(s.CycleDetails.__dataclass_fields__))
            for c in saved.schedule.cycles
        ),
    )
    occurrence = blocks(original)[0]
    assert occurrence.continues_pattern
    change = t.edit_occurrence(
        original, occurrence.id, s.PhaseDetails("Future occupation"), new_id=ids
    )
    future_block = blocks(change.schedule)[1]
    assert future_block.continues_pattern
    assert live(change.schedule)[0] == original.cycles[0]
    projected = s.project(change.schedule, limit=2)
    assert projected[0].phase_id == future_block.phase_id
    assert projected[1].phase_id == original.phases[1].id
    assert (
        next(
            p for p in change.schedule.phases if p.id == projected[0].phase_id
        ).details.name
        == "Future occupation"
    )


def test_manual_phase_override_does_not_continue_after_cow_without_cycle_field_markers(
    ids,
):
    original = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="manual-pattern",
        current_position=0,
        mode="repeating",
        new_id=ids,
    ).schedule
    saved, selected = s._ensure_saved(
        original, s.project(original, limit=1)[0].ref, new_id=ids
    )
    manual = s.edit_cycle(
        saved.schedule,
        s.SavedCycleRef(selected.id),
        replace(selected.details, phase_id=original.phases[1].id),
        new_id=ids,
    ).schedule
    manual = replace(
        manual,
        cycles=tuple(replace(c, customized_fields=frozenset()) for c in manual.cycles),
    )
    selected = next(c for c in manual.cycles if c.id == selected.id)
    occurrence = next(o for o in manual.occurrences if o.id == selected.occurrence_id)
    assert not occurrence.continues_pattern
    change = t.edit_occurrence(
        manual, occurrence.id, s.PhaseDetails("Manual downtime"), new_id=ids
    )
    assert not next(
        o for o in change.schedule.occurrences if o.id == occurrence.id
    ).continues_pattern
    assert s.project(change.schedule, limit=1)[0].phase_id == original.phases[0].id


@pytest.mark.parametrize("current_position", [None, 0])
def test_cow_keeps_the_continuation_pointer_on_its_future_rules_across_plan_revisions(
    ids, current_position
):
    now = datetime(2026, 11, 15, tzinfo=UTC)
    original = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="revised-cow",
        current_position=current_position,
        mode="repeating",
        status="in_progress",
        now=now,
        new_id=ids,
    ).schedule
    target = s.ProjectedCycleRef(s.PlannedPosition(original.plan.id, 1))
    saved, _ = s._ensure_saved(original, target, new_id=ids)
    original = saved.schedule
    steps = (replace(original.plan.steps[0], count=4),) + original.plan.steps[1:]
    revised = s.replace_plan(
        original, steps=steps, mode="repeating", new_id=ids
    ).schedule
    selected = blocks(revised)[0]
    assert revised.continuation_occurrence_id == selected.id
    assert revised.plan.id != original.plan.id
    change = t.edit_occurrence(
        revised, selected.id, s.PhaseDetails("Future revised occupation"), new_id=ids
    )
    future = next(c for c in change.schedule.cycles if c.id == original.cycles[1].id)
    assert change.schedule.continuation_occurrence_id == future.occurrence_id
    assert (future.occurrence_id == selected.id) is (current_position is None)
    assert future.source == original.cycles[1].source
    projected = s.project(change.schedule, limit=1)[0]
    assert projected.phase_id == future.details.phase_id
    materialized, following = s._ensure_saved(
        change.schedule, projected.ref, new_id=ids
    )
    assert following.occurrence_id == future.occurrence_id
    assert materialized.schedule.next_position == change.schedule.next_position + 1
    if current_position is not None:
        entered = s.advance(materialized.schedule, now=now, new_id=ids)
        assert entered.transition.enters_phase
        continued = s.advance(entered.schedule, now=now, new_id=ids)
        assert not continued.transition.enters_phase


def test_same_rules_cycle_move_cannot_supply_another_blocks_pattern_continuation(ids):
    original = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="moved-source",
        current_position=0,
        mode="repeating",
        new_id=ids,
    ).schedule
    saved, _ = s._ensure_saved(
        original, s.project(original, limit=1)[0].ref, new_id=ids
    )
    original = saved.schedule
    destination = s.PhaseOccurrence(
        "empty-generated-block", original.phases[0].id, 2, continues_pattern=True
    )
    revised = replace(
        original,
        plan=replace(
            original.plan, id="replacement-plan", starts_after_order=2, start_position=2
        ),
        next_position=2,
        occurrences=original.occurrences + (destination,),
        continuation_occurrence_id=None,
    )
    moved = t.move_cycle(revised, original.cycles[1].id, destination.id).schedule
    selected = next(c for c in moved.cycles if c.id == original.cycles[1].id)
    assert selected.source == original.cycles[1].source
    assert selected.details.phase_id == original.cycles[1].details.phase_id
    assert "occurrence_id" in selected.customized_fields
    assert "phase_id" not in selected.customized_fields
    assert moved.next_position == revised.next_position
    assert s._continuing_occurrence(moved, s.project(moved, limit=1)[0].source) is None
    planned, following = s._ensure_saved(
        moved, s.project(moved, limit=1)[0].ref, new_id=ids
    )
    assert following.occurrence_id != destination.id
    assert planned.schedule.next_position == moved.next_position + 1


def interleaved_history():
    original = state(protected={"cycle-3"})
    return replace(
        original,
        cycles=tuple(
            replace(
                c,
                occurrence_id="block-1",
                details=replace(c.details, phase_id="occupation"),
            )
            if c.order <= 4
            else c
            for c in original.cycles
        ),
    )


def test_phase_edit_keeps_the_entire_prefix_through_recorded_activity(ids):
    original = interleaved_history()
    change = t.edit_occurrence(
        original, "block-1", s.PhaseDetails("Future occupation"), new_id=ids
    )
    assert live(change.schedule)[:3] == original.cycles[:3]
    suffix = live(change.schedule)[3]
    assert suffix.id == original.cycles[3].id
    assert suffix.order == original.cycles[3].order
    assert suffix.source == original.cycles[3].source
    assert suffix.occurrence_id != "block-1"
    assert suffix.details.phase_id != "occupation"
    assert live(change.schedule)[4] == original.cycles[4]
    assert change.schedule.current_cycle_id == original.current_cycle_id
    assert change.transition is None


def test_unused_cycles_before_the_last_recorded_child_do_not_form_an_editable_suffix(
    ids,
):
    original = replace(
        interleaved_history(), protected_cycle_ids=frozenset({"cycle-4"})
    )
    with pytest.raises(s.ScheduleError, match="unused future cycles"):
        t.edit_occurrence(
            original, "block-1", s.PhaseDetails("No future suffix"), new_id=ids
        )


def test_editing_a_future_block_after_removal_keeps_archived_cycles_and_rules_exact(
    ids,
):
    original = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="archived-child-cow",
        current_position=0,
        mode="fixed",
        new_id=ids,
    ).schedule
    selected = blocks(original)[-1]
    removed = t.remove_cycle(original, original.cycles[-1].id).schedule
    historical = next(c for c in removed.cycles if c.archived)
    assert removed.continuation_occurrence_id == selected.id
    change = t.edit_occurrence(
        removed, selected.id, s.PhaseDetails("Future takeover"), new_id=ids
    )
    active = blocks(change.schedule)
    old_block = next(o for o in change.schedule.occurrences if o.id == selected.id)
    assert old_block == replace(selected, archived=True)
    assert active[-1].id != selected.id
    assert active[-1].position == selected.position
    assert change.schedule.continuation_occurrence_id == active[-1].id
    assert (
        next(c for c in change.schedule.cycles if c.id == historical.id) == historical
    )
    assert live(change.schedule)[:4] == live(removed)[:4]
    for current, before in zip(
        live(change.schedule)[4:], live(removed)[4:], strict=True
    ):
        assert current.id == before.id and current.order == before.order
        assert (
            current.source == before.source
            and current.customized_fields == before.customized_fields
        )
        assert current.occurrence_id == active[-1].id
        assert current.details == replace(before.details, phase_id=active[-1].phase_id)
    occurrence_phases = {o.id: o.phase_id for o in change.schedule.occurrences}
    assert all(
        c.details.phase_id == occurrence_phases[c.occurrence_id]
        for c in change.schedule.cycles
    )
    assert next(p for p in change.schedule.phases if p.id == selected.phase_id) == next(
        p for p in removed.phases if p.id == selected.phase_id
    )
    assert change.schedule.current_cycle_id == original.current_cycle_id
    assert change.schedule.next_position == original.next_position
    assert change.transition is None


def test_cow_replaces_a_block_with_archived_children_and_continues_its_generated_suffix(
    ids,
):
    original = s.configure(
        s.DEFAULT_TEMPLATE,
        campaign_id="archived-repeating-child",
        current_position=0,
        mode="repeating",
        new_id=ids,
    ).schedule
    saved, selected = s._ensure_saved(
        original,
        s.ProjectedCycleRef(s.PlannedPosition(original.plan.id, 5)),
        new_id=ids,
    )
    removed = t.remove_cycle(saved.schedule, selected.id).schedule
    old_block = blocks(removed)[-1]
    historical = next(c for c in removed.cycles if c.id == selected.id)
    change = t.edit_occurrence(
        removed, old_block.id, s.PhaseDetails("Future repeating takeover"), new_id=ids
    )
    active = blocks(change.schedule)[-1]
    assert active.id != old_block.id
    assert change.schedule.continuation_occurrence_id == active.id
    projected = s.project(change.schedule, limit=1)[0]
    assert projected.phase_id == active.phase_id
    planned, following = s._ensure_saved(change.schedule, projected.ref, new_id=ids)
    assert following.occurrence_id == active.id
    assert (
        next(c for c in planned.schedule.cycles if c.id == historical.id) == historical
    )
    assert len(blocks(planned.schedule)) == len(blocks(removed))
