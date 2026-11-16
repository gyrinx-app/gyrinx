"""Author the concrete campaign timeline without consuming its generated tail.

Active blocks and cycles have consecutive positions; archived records keep their
identities and audit data. Every candidate is checked before it can be persisted.
"""

from dataclasses import replace

from n26.core import schedule as s

_UNSET = object()


def _occurrence(schedule, occurrence_id):
    for occurrence in schedule.occurrences:
        if occurrence.id == occurrence_id and not occurrence.archived:
            s._phase(schedule, occurrence.phase_id)
            return occurrence
    raise s.ScheduleError("Select an active phase block from this campaign.")


def _cycle(schedule, cycle_id):
    for cycle in schedule.cycles:
        if cycle.id == cycle_id and not cycle.archived:
            return cycle
    raise s.ScheduleError("Select an active cycle from this campaign.")


def _blocks(schedule):
    return [
        occurrence for occurrence in schedule.occurrences if not occurrence.archived
    ]


def _children(schedule, occurrence_id):
    return [
        c
        for c in schedule.cycles
        if not c.archived and c.occurrence_id == occurrence_id
    ]


def _insert(items, item, after_id, *, label):
    items = list(items)
    if after_id is None:
        items.insert(0, item)
        return items
    for index, previous in enumerate(items):
        if previous.id == after_id:
            items.insert(index + 1, item)
            return items
    raise s.ScheduleError(f"Choose a preceding {label} from the destination block.")


def _protect(before, cycles, occurrences):
    protected = set(before.protected_cycle_ids)
    if before.current:
        protected.update(
            c.id
            for c in before.cycles
            if not c.archived and c.order <= before.current.order
        )
    by_id = {cycle.id: cycle for cycle in cycles}
    frozen_blocks = {
        cycle.occurrence_id
        for cycle in before.cycles
        if not cycle.archived and cycle.id in protected
    }
    if before.current:
        current_block = _occurrence(before, before.current.occurrence_id)
        frozen_blocks.update(
            o.id for o in _blocks(before) if o.position <= current_block.position
        )
    for original in before.cycles:
        if original.archived or original.id not in protected:
            continue
        candidate = by_id.get(original.id)
        if candidate is None or (
            candidate.archived
            or candidate.order != original.order
            or candidate.occurrence_id != original.occurrence_id
            or candidate.details.phase_id != original.details.phase_id
        ):
            raise s.ScheduleError(
                "Current cycles and cycles with recorded activity must keep their place and phase."
            )
    blocks = {o.id: o for o in occurrences}
    for original in before.occurrences:
        if original.archived or original.id not in frozen_blocks:
            continue
        if blocks.get(original.id) != original:
            raise s.ScheduleError(
                "Current phase blocks and blocks with recorded activity must keep their place and rules."
            )


def _change(
    schedule,
    *,
    blocks=None,
    children=None,
    phases=None,
    archived_cycles=(),
    archived_blocks=(),
    continuation_occurrence_id=_UNSET,
):
    active_blocks = _blocks(schedule) if blocks is None else blocks
    active_blocks = tuple(
        replace(o, position=index) for index, o in enumerate(active_blocks, start=1)
    )
    children = {} if children is None else children
    active_cycles = [
        cycle
        for occurrence in active_blocks
        for cycle in children.get(occurrence.id, _children(schedule, occurrence.id))
    ]
    active_cycles = tuple(
        replace(c, order=index) for index, c in enumerate(active_cycles, start=1)
    )
    cycles = (
        active_cycles
        + tuple(c for c in schedule.cycles if c.archived)
        + tuple(archived_cycles)
    )
    occurrences = (
        active_blocks
        + tuple(o for o in schedule.occurrences if o.archived)
        + tuple(archived_blocks)
    )
    retained = {cycle.id for cycle in cycles}
    if any(cycle.id not in retained for cycle in schedule.cycles):
        raise s.ScheduleError(
            "Assign each cycle to an active phase block before editing the timeline."
        )
    _protect(schedule, cycles, occurrences)
    changed = replace(
        schedule,
        cycles=cycles,
        occurrences=occurrences,
        phases=schedule.phases if phases is None else phases,
        calendar=s.reindexed_calendar(schedule, len(active_cycles)),
        **(
            {"continuation_occurrence_id": continuation_occurrence_id}
            if continuation_occurrence_id is not _UNSET
            else {}
        ),
    )
    if changed == schedule:
        return s.ScheduleChange(schedule)
    s.validate_cycle_dates(changed.cycles)
    s._validate_projection_dates(changed)
    changed = replace(changed, revision=schedule.revision + 1)
    originals = {c.id: c for c in schedule.cycles}
    return s.ScheduleChange(
        changed,
        created=tuple(c for c in changed.cycles if c.id not in originals),
        updated=tuple(
            c for c in changed.cycles if c.id in originals and c != originals[c.id]
        ),
    )


def insert_cycle(
    schedule, occurrence_id, *, after_cycle_id=None, details=None, new_id=s._id
):
    """Insert an authored cycle at a block's start, or after its selected child."""
    occurrence = _occurrence(schedule, occurrence_id)
    supplied = details is not None
    details = s.CycleDetails(occurrence.phase_id) if details is None else details
    if details.phase_id != occurrence.phase_id:
        raise s.ScheduleError("Select the phase belonging to this block.")
    cycle = s.Cycle(
        new_id(),
        1,
        details,
        s.CycleSource(),
        occurrence_id=occurrence.id,
        customized_fields=frozenset(s.CycleDetails.__dataclass_fields__)
        if supplied
        else frozenset(),
    )
    children = _insert(
        _children(schedule, occurrence.id), cycle, after_cycle_id, label="cycle"
    )
    return _change(schedule, children={occurrence.id: children})


def move_cycle(schedule, cycle_id, occurrence_id, *, after_cycle_id=None):
    """Move a concrete cycle, preserving its identity, dates and customisations."""
    original = _cycle(schedule, cycle_id)
    occurrence = _occurrence(schedule, occurrence_id)
    if after_cycle_id == original.id:
        raise s.ScheduleError("Choose another cycle to place this cycle after.")
    moved = replace(
        original,
        occurrence_id=occurrence.id,
        details=replace(original.details, phase_id=occurrence.phase_id),
        customized_fields=original.customized_fields
        | ({"phase_id"} if original.details.phase_id != occurrence.phase_id else set())
        | ({"occurrence_id"} if original.occurrence_id != occurrence.id else set()),
    )
    children = {
        original.occurrence_id: [
            c
            for c in _children(schedule, original.occurrence_id)
            if c.id != original.id
        ]
    }
    destination = children.get(occurrence.id, _children(schedule, occurrence.id))
    children[occurrence.id] = _insert(destination, moved, after_cycle_id, label="cycle")
    return _change(schedule, children=children)


def _copy_cycle(original, *, identity, occurrence, clear_dates):
    details = replace(original.details, phase_id=occurrence.phase_id)
    fields = original.customized_fields
    if clear_dates:
        details = replace(details, starts_on=None, ends_on=None)
        fields = fields | {"starts_on", "ends_on"}
    return replace(
        original,
        id=identity,
        details=details,
        source=s.CycleSource(),
        archived=False,
        occurrence_id=occurrence.id,
        customized_fields=fields,
    )


def duplicate_cycle(
    schedule,
    cycle_id,
    *,
    occurrence_id=None,
    after_cycle_id=_UNSET,
    clear_dates=False,
    new_id=s._id,
):
    """Copy into the source block after the source, or into another block's start.

    Dates are retained unless the caller explicitly requests clearing both bounds.
    A retained date conflict is refused rather than silently changing the copy.
    """
    original = _cycle(schedule, cycle_id)
    occurrence = _occurrence(schedule, occurrence_id or original.occurrence_id)
    if after_cycle_id is _UNSET:
        after_cycle_id = (
            original.id if occurrence.id == original.occurrence_id else None
        )
    copied = _copy_cycle(
        original, identity=new_id(), occurrence=occurrence, clear_dates=clear_dates
    )
    children = _insert(
        _children(schedule, occurrence.id), copied, after_cycle_id, label="cycle"
    )
    return _change(schedule, children={occurrence.id: children})


def remove_cycle(schedule, cycle_id):
    """Archive one unused entry while keeping its block, including an empty block."""
    original = _cycle(schedule, cycle_id)
    return _change(
        schedule,
        children={
            original.occurrence_id: [
                c
                for c in _children(schedule, original.occurrence_id)
                if c.id != original.id
            ]
        },
        archived_cycles=(replace(original, archived=True),),
    )


def insert_occurrence(
    schedule, phase_id=None, *, after_occurrence_id=None, details=None, new_id=s._id
):
    """Insert an empty block using existing rules or a new campaign-owned definition."""
    phases = schedule.phases
    if details is not None:
        if phase_id is not None:
            raise s.ScheduleError(
                "Choose existing phase rules or supply new rules, not both."
            )
        phase = s.Phase(new_id(), details)
        phases = phases + (phase,)
    else:
        phase = s._phase(schedule, phase_id)
    occurrence = s.PhaseOccurrence(new_id(), phase.id, 1)
    blocks = _insert(
        _blocks(schedule), occurrence, after_occurrence_id, label="phase block"
    )
    return _change(schedule, blocks=blocks, phases=phases)


def move_occurrence(schedule, occurrence_id, *, after_occurrence_id=None):
    """Move a complete block with its children and stable identities."""
    original = _occurrence(schedule, occurrence_id)
    if after_occurrence_id == original.id:
        raise s.ScheduleError("Choose another phase block to place this block after.")
    blocks = _insert(
        [o for o in _blocks(schedule) if o.id != original.id],
        original,
        after_occurrence_id,
        label="phase block",
    )
    return _change(schedule, blocks=blocks)


def duplicate_occurrence(
    schedule,
    occurrence_id,
    *,
    after_occurrence_id=_UNSET,
    clear_dates=False,
    new_id=s._id,
):
    """Copy rules and every active child into a new, independently editable block."""
    original = _occurrence(schedule, occurrence_id)
    phase = s.Phase(new_id(), s._phase(schedule, original.phase_id).details)
    occurrence = s.PhaseOccurrence(new_id(), phase.id, 1)
    copied = [
        _copy_cycle(
            c, identity=new_id(), occurrence=occurrence, clear_dates=clear_dates
        )
        for c in _children(schedule, original.id)
    ]
    blocks = _insert(
        _blocks(schedule),
        occurrence,
        original.id if after_occurrence_id is _UNSET else after_occurrence_id,
        label="phase block",
    )
    return _change(
        schedule,
        blocks=blocks,
        children={occurrence.id: copied},
        phases=schedule.phases + (phase,),
    )


def remove_occurrence(schedule, occurrence_id):
    """Archive only the selected block and its children; retain its phase definition."""
    original = _occurrence(schedule, occurrence_id)
    return _change(
        schedule,
        blocks=[o for o in _blocks(schedule) if o.id != original.id],
        archived_cycles=tuple(
            replace(c, archived=True) for c in _children(schedule, original.id)
        ),
        archived_blocks=(replace(original, archived=True),),
    )


def edit_occurrence(schedule, occurrence_id, details, *, new_id=s._id):
    """Copy future rules, splitting an already used block without changing its history."""
    original = _occurrence(schedule, occurrence_id)
    if s._phase(schedule, original.phase_id).details == details:
        return s.ScheduleChange(schedule)
    children = _children(schedule, original.id)
    protected = set(schedule.protected_cycle_ids)
    if schedule.current:
        protected.update(
            c.id
            for c in schedule.cycles
            if not c.archived and c.order <= schedule.current.order
        )
    frontier = max((c.order for c in children if c.id in protected), default=0)
    used = [c for c in children if c.order <= frontier]
    future = [c for c in children if c.order > frontier]
    if used and not future:
        raise s.ScheduleError(
            "Current cycles and cycles with recorded activity keep their phase rules. "
            "Add unused future cycles to edit this phase."
        )
    phase = s.Phase(new_id(), details)
    if used:
        occurrence = replace(original, id=new_id(), phase_id=phase.id, position=1)
        ordered = _insert(
            _blocks(schedule), occurrence, original.id, label="phase block"
        )
        replacements = {original.id: used}
    else:
        occurrence = replace(original, phase_id=phase.id)
        ordered = [occurrence if o.id == original.id else o for o in _blocks(schedule)]
        replacements = {}
    replacements[occurrence.id] = [
        replace(
            c,
            occurrence_id=occurrence.id,
            details=replace(c.details, phase_id=phase.id),
        )
        for c in future
    ]
    referenced = (
        any(o.phase_id == original.phase_id for o in ordered)
        or any(
            o.archived and o.phase_id == original.phase_id for o in schedule.occurrences
        )
        or any(step.phase_id == original.phase_id for step in schedule.plan.steps)
    )
    phases = tuple(
        replace(p, archived=True) if p.id == original.phase_id and not referenced else p
        for p in schedule.phases
    ) + (phase,)
    return _change(
        schedule,
        blocks=ordered,
        children=replacements,
        phases=phases,
        continuation_occurrence_id=occurrence.id
        if used and schedule.continuation_occurrence_id == original.id
        else _UNSET,
    )
