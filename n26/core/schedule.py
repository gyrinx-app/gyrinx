"""Campaign planning calculations, independent of persistence and delivery.

Concrete cycles form an editable timeline. Stable identities preserve activity
while visible positions can change. A source cursor supplies the repeating tail
independently of authored insertions; dates never decide the next position.
Callers persist a change under the campaign lock and deliver any transition
only after commit. This module performs no database writes or reward execution.
"""

from calendar import monthrange
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from itertools import combinations
from typing import Literal
from uuid import uuid4

type NewId = Callable[[], str]
type Mode = Literal["fixed", "repeating"]
type Status = Literal["pre_campaign", "in_progress", "post_campaign"]


class ScheduleError(ValueError):
    """A schedule selection or edit cannot be applied."""


def _id():
    return str(uuid4())


def _positive(value, label):
    if type(value) is not int or value < 1:
        raise ScheduleError(f"{label} must be a positive whole number.")


def _nonnegative(value, label):
    if type(value) is not int or value < 0:
        raise ScheduleError(f"{label} must be zero or a positive whole number.")


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ScheduleError("Enter a name of up to 200 characters.")


def _unique(values, label):
    values = tuple(values)
    if len(set(values)) != len(values):
        raise ScheduleError(f"{label} must have distinct identities.")


@dataclass(frozen=True)
class DiceAmount:
    count: int = 1
    sides: int = 6
    multiplier: int = 1

    def __post_init__(self):
        _positive(self.count, "Dice count")
        if self.sides not in (3, 6):
            raise ScheduleError("Select D3 or D6 for the credit amount.")
        _positive(self.multiplier, "Dice multiplier")


@dataclass(frozen=True)
class CreditAmount:
    fixed: int = 0
    dice: DiceAmount | None = None

    def __post_init__(self):
        _nonnegative(self.fixed, "Credits")


@dataclass(frozen=True)
class Reward:
    credits: CreditAmount = CreditAmount()
    reputation: int = 0

    def __post_init__(self):
        if type(self.reputation) is not int:
            raise ScheduleError("Reputation must be a whole number.")


@dataclass(frozen=True)
class RewardSettings:
    win: Reward = Reward()
    draw: Reward = Reward()
    loss: Reward = Reward()
    entry_credits: CreditAmount = CreditAmount()


@dataclass(frozen=True)
class PhaseDetails:
    name: str
    description: str = ""
    effects: str = ""
    rewards: RewardSettings = RewardSettings()

    def __post_init__(self):
        _name(self.name)


@dataclass(frozen=True)
class Phase:
    id: str
    details: PhaseDetails
    archived: bool = False


@dataclass(frozen=True)
class PhaseOccurrence:
    """One ordered phase block in a campaign, independently of its rules."""

    id: str
    phase_id: str
    position: int
    archived: bool = False
    continues_pattern: bool = False

    def __post_init__(self):
        _positive(self.position, "Phase position")


@dataclass(frozen=True)
class PlanStep:
    id: str
    phase_id: str
    count: int

    def __post_init__(self):
        _positive(self.count, "Cycle count")


@dataclass(frozen=True)
class Plan:
    """An immutable continuation; a full-length start retains completed-pass credit."""

    id: str
    mode: Mode
    steps: tuple[PlanStep, ...]
    starts_after_order: int = 0
    start_position: int = 0

    def __post_init__(self):
        if self.mode not in ("fixed", "repeating"):
            raise ScheduleError("Select a fixed or repeating plan.")
        if not self.steps and self.mode == "repeating":
            raise ScheduleError("Add at least one step to the plan.")
        _unique((step.id for step in self.steps), "Plan steps")
        _nonnegative(self.starts_after_order, "Plan boundary")
        _nonnegative(self.start_position, "Initial plan position")
        if self.start_position and (
            self.mode != "repeating" or self.start_position > self.length
        ):
            raise ScheduleError("Select a position within the repeating pattern.")

    def order_for(self, position):
        return self.starts_after_order + position - self.start_position + 1

    def position_for(self, order):
        return order - self.starts_after_order + self.start_position - 1

    @property
    def length(self):
        return sum(step.count for step in self.steps)


@dataclass(frozen=True)
class PlannedPosition:
    plan_id: str
    index: int

    def __post_init__(self):
        _nonnegative(self.index, "Plan position")


@dataclass(frozen=True)
class PlanContinuation:
    plan: Plan
    next_position: int
    calendar: CycleCalendar | None = None
    saved_count: int | None = None

    def __post_init__(self):
        _nonnegative(self.next_position, "Next plan position")
        if self.saved_count is not None:
            _nonnegative(self.saved_count, "Saved cycle count")


@dataclass(frozen=True)
class CycleSource:
    position: PlannedPosition | None = None
    step_id: str = ""
    repetition: int = 0
    offset: int = 0

    def __post_init__(self):
        _nonnegative(self.repetition, "Pattern repetition")
        _nonnegative(self.offset, "Position within the step")
        if self.position is None and (self.step_id or self.repetition or self.offset):
            raise ScheduleError("An authored cycle cannot claim a generated position.")


@dataclass(frozen=True)
class SavedCycleRef:
    cycle_id: str


@dataclass(frozen=True)
class ProjectedCycleRef:
    position: PlannedPosition


type CycleRef = SavedCycleRef | ProjectedCycleRef


@dataclass(frozen=True)
class CycleDetails:
    phase_id: str
    custom_name: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    description: str = ""
    effects: str = ""

    def __post_init__(self):
        if self.custom_name is not None:
            _name(self.custom_name)
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ScheduleError("The end date cannot be before the start date.")


@dataclass(frozen=True)
class CycleCalendar:
    starts_on: date
    interval: int = 1
    unit: Literal["weeks", "months"] = "weeks"
    starts_after_order: int = 0
    days_offset: int = 0
    position_offset: int = 0

    def __post_init__(self):
        if type(self.starts_on) is not date:
            raise ScheduleError("Enter the first cycle's start date.")
        _positive(self.interval, "Cycle interval")
        _nonnegative(self.starts_after_order, "Date boundary")
        if self.unit not in ("weeks", "months"):
            raise ScheduleError("Select weeks or calendar months.")
        if type(self.days_offset) is not int:
            raise ScheduleError("Enter a whole number of days to shift the calendar.")
        if type(self.position_offset) is not int:
            raise ScheduleError("Enter a whole calendar position offset.")

    def _boundary(self, index):
        try:
            if self.unit == "weeks":
                return self.starts_on + timedelta(
                    weeks=self.interval * index, days=self.days_offset
                )
            month = (
                self.starts_on.year * 12
                + self.starts_on.month
                - 1
                + self.interval * index
            )
            year, month = divmod(month, 12)
            month += 1
            return date(
                year, month, min(self.starts_on.day, monthrange(year, month)[1])
            ) + timedelta(days=self.days_offset)
        except ValueError, OverflowError:
            raise ScheduleError(
                "The cycle dates extend beyond the supported calendar."
            ) from None

    def dates_for(self, order):
        index = order + self.position_offset - self.starts_after_order - 1
        _nonnegative(index, "Cycle date position")
        return self._boundary(index), self._boundary(index + 1) - timedelta(days=1)


def _date_span(details):
    start, end = details.starts_on, details.ends_on
    if start is None:
        return (end, end) if end is not None else None
    return start, end if end is not None else start


def validate_cycle_dates(cycles, *, affected=None):
    """Check asserted days in cycle order for the dates a command changes."""
    dated = []
    for cycle in sorted(cycles, key=lambda cycle: cycle.order):
        if cycle.archived:
            continue
        if (span := _date_span(cycle.details)) is not None:
            dated.append((cycle, span))
    for (earlier, left), (later, right) in combinations(dated, 2):
        if affected is not None and not {earlier.id, later.id} & affected:
            continue
        if left[0] <= right[1] and right[0] <= left[1]:
            raise ScheduleError(
                f"The dates for {later.name} overlap {earlier.name}. Choose dates outside the other saved cycles."
            )
        if left[0] > right[1]:
            raise ScheduleError(
                f"The dates for {later.name} must follow {earlier.name}."
            )


@dataclass(frozen=True)
class Cycle:
    id: str
    order: int
    details: CycleDetails
    source: CycleSource
    archived: bool = False
    occurrence_id: str | None = None
    customized_fields: frozenset[str] = frozenset()

    @property
    def name(self):
        return self.details.custom_name or f"Cycle {self.order}"


@dataclass(frozen=True)
class ProjectedCycle:
    ref: ProjectedCycleRef
    order: int
    phase_id: str
    source: CycleSource
    starts_on: date | None = None
    ends_on: date | None = None

    @property
    def name(self):
        return f"Cycle {self.order}"


@dataclass(frozen=True)
class Schedule:
    campaign_id: str
    phases: tuple[Phase, ...]
    plan: Plan
    next_position: int
    cycles: tuple[Cycle, ...]
    current_cycle_id: str | None
    status: Status = "pre_campaign"
    revision: int = 0
    calendar: CycleCalendar | None = None
    occurrences: tuple[PhaseOccurrence, ...] = ()
    protected_cycle_ids: frozenset[str] = frozenset()
    continuation_occurrence_id: str | None = None

    def __post_init__(self):
        if self.status not in ("pre_campaign", "in_progress", "post_campaign"):
            raise ScheduleError("Select a campaign status.")
        _nonnegative(self.revision, "Schedule revision")
        _nonnegative(self.next_position, "Next plan position")
        _unique((phase.id for phase in self.phases), "Phases")
        _unique((cycle.id for cycle in self.cycles), "Cycles")
        _unique(
            (
                cycle.source.position
                for cycle in self.cycles
                if cycle.source.position is not None
            ),
            "Cycle sources",
        )
        if self.current_cycle_id is not None and self.current_cycle_id not in {
            cycle.id for cycle in self.cycles if not cycle.archived
        }:
            raise ScheduleError("Select a saved current cycle.")
        active = tuple(cycle for cycle in self.cycles if not cycle.archived)
        if tuple(cycle.order for cycle in active) != tuple(range(1, len(active) + 1)):
            raise ScheduleError("Active cycles must keep their consecutive order.")
        _unique((occurrence.id for occurrence in self.occurrences), "Phase occurrences")
        active_occurrences = tuple(o for o in self.occurrences if not o.archived)
        if tuple(o.position for o in active_occurrences) != tuple(
            range(1, len(active_occurrences) + 1)
        ):
            raise ScheduleError(
                "Active phase blocks must keep their consecutive order."
            )
        if self.occurrences:
            by_id = {o.id: o for o in self.occurrences}
            for cycle in active:
                occurrence = by_id.get(cycle.occurrence_id)
                if (
                    occurrence is None
                    or occurrence.archived
                    or occurrence.phase_id != cycle.details.phase_id
                ):
                    raise ScheduleError("Select an active phase block for each cycle.")
        phase_ids = {phase.id for phase in self.phases}
        active_phases = {phase.id for phase in self.phases if not phase.archived}
        if any(step.phase_id not in active_phases for step in self.plan.steps) or any(
            cycle.details.phase_id not in phase_ids for cycle in self.cycles
        ):
            raise ScheduleError("Select phases from this campaign.")
        if self.plan.mode == "fixed" and self.next_position > self.plan.length:
            raise ScheduleError("The next position is beyond the fixed plan.")
        if self.calendar is not None:
            self.calendar.dates_for(len(active) + 100)

    @property
    def current(self):
        return next((c for c in self.cycles if c.id == self.current_cycle_id), None)

    @property
    def current_phase(self):
        return _phase(self, self.current.details.phase_id) if self.current else None


@dataclass(frozen=True)
class ScheduleTemplate:
    name: str
    phases: tuple[Phase, ...]
    steps: tuple[PlanStep, ...]

    def __post_init__(self):
        _name(self.name)
        _unique((phase.id for phase in self.phases), "Template phases")
        if not self.steps:
            raise ScheduleError("Add at least one step to the template.")
        Plan("template", "fixed", self.steps)
        phase_ids = {phase.id for phase in self.phases}
        if any(step.phase_id not in phase_ids for step in self.steps):
            raise ScheduleError("Select phases from this template.")


DEFAULT_TEMPLATE = ScheduleTemplate(
    name="Occupation and Takeover",
    phases=(
        Phase("occupation", PhaseDetails("Occupation")),
        Phase("downtime", PhaseDetails("Downtime")),
        Phase("takeover", PhaseDetails("Takeover")),
    ),
    steps=(
        PlanStep("occupation", "occupation", 3),
        PlanStep("downtime", "downtime", 1),
        PlanStep("takeover", "takeover", 3),
    ),
)


@dataclass(frozen=True)
class Transition:
    kind: Literal["started", "advanced", "phase_changed", "finished"]
    previous_cycle: Cycle | None
    current_cycle: Cycle
    occurred_at: datetime

    def __post_init__(self):
        if (
            not isinstance(self.occurred_at, datetime)
            or self.occurred_at.utcoffset() is None
        ):
            raise ScheduleError("Supply a transition time with a time zone.")

    @property
    def enters_phase(self):
        return self.kind != "finished" and (
            self.previous_cycle is None
            or (
                self.previous_cycle.occurrence_id != self.current_cycle.occurrence_id
                if self.previous_cycle.occurrence_id
                and self.current_cycle.occurrence_id
                else self.previous_cycle.details.phase_id
                != self.current_cycle.details.phase_id
            )
        )


@dataclass(frozen=True)
class ScheduleChange:
    schedule: Schedule
    created: tuple[Cycle, ...] = ()
    updated: tuple[Cycle, ...] = ()
    transition: Transition | None = None


@dataclass(frozen=True)
class EditPreview:
    target: CycleRef
    details: CycleDetails
    creates: tuple[ProjectedCycle, ...]
    following_on: date | None = None


@dataclass(frozen=True)
class TransitionPreview:
    current: Cycle
    following: Cycle | ProjectedCycle | None

    @property
    def finishes(self):
        return self.following is None


@dataclass(frozen=True)
class CycleContext:
    campaign_id: str
    cycle_id: str


def _phase(schedule, phase_id):
    for phase in schedule.phases:
        if phase.id == phase_id and not phase.archived:
            return phase
    raise ScheduleError("Select a phase from this campaign.")


def _at(plan, index):
    _nonnegative(index, "Plan position")
    if index < plan.start_position:
        raise ScheduleError("That position is already covered by saved cycles.")
    if not plan.length:
        raise ScheduleError("There are no more cycles in this fixed plan.")
    repetition, offset = divmod(index, plan.length)
    if plan.mode == "fixed" and repetition:
        raise ScheduleError("There are no more cycles in this fixed plan.")
    for step in plan.steps:
        if offset < step.count:
            source = CycleSource(
                PlannedPosition(plan.id, index), step.id, repetition, offset
            )
            return ProjectedCycle(
                ProjectedCycleRef(source.position),
                plan.order_for(index),
                step.phase_id,
                source,
            )
        offset -= step.count
    raise AssertionError("A non-empty plan must resolve every position.")


def project(
    schedule: Schedule | PlanContinuation, *, limit: int = 12
) -> tuple[ProjectedCycle, ...]:
    """Read a bounded continuation without allocating saved identities."""
    _positive(limit, "Projection size")
    end = schedule.next_position + limit
    if schedule.plan.mode == "fixed":
        end = min(end, schedule.plan.length)
    count = (
        sum(not cycle.archived for cycle in schedule.cycles)
        if isinstance(schedule, Schedule)
        else schedule.saved_count
    )
    return tuple(
        _dated(
            _projected_details(schedule, _at(schedule.plan, i), count + offset + 1)
            if count is not None
            else _at(schedule.plan, i),
            schedule.calendar,
        )
        for offset, i in enumerate(range(schedule.next_position, end))
    )


def _can_continue_occurrence(
    *,
    plan,
    next_position,
    occurrence,
    continuation_occurrence_id,
    source_blocks,
    source,
):
    if not next_position or occurrence.archived or not occurrence.continues_pattern:
        return False
    previous = _at(replace(plan, start_position=0), next_position - 1)
    group = (source.position.plan_id, source.repetition, source.step_id)
    if (
        previous.source.position.plan_id,
        previous.source.repetition,
        previous.source.step_id,
    ) != group:
        return False
    if continuation_occurrence_id == occurrence.id or group in source_blocks:
        return True
    return (
        (plan.mode == "fixed" or next_position == plan.start_position)
        and occurrence.phase_id == previous.phase_id
        and any(block[2] == source.step_id for block in source_blocks)
    )


def _continuing_occurrence(schedule, source):
    """Keep the current generated step attached to its explicitly arranged block."""
    if not isinstance(schedule, Schedule):
        return None
    occurrence = next(
        (o for o in reversed(schedule.occurrences) if not o.archived), None
    )
    if occurrence is None:
        return None
    blocks = {
        _source_block(c)
        for c in schedule.cycles
        if c.occurrence_id == occurrence.id
        and c.source.position is not None
        and "occurrence_id" not in c.customized_fields
    }
    return (
        occurrence
        if _can_continue_occurrence(
            plan=schedule.plan,
            next_position=schedule.next_position,
            occurrence=occurrence,
            continuation_occurrence_id=schedule.continuation_occurrence_id,
            source_blocks=blocks,
            source=source,
        )
        else None
    )


def _projected_details(schedule, cycle, order):
    occurrence = _continuing_occurrence(schedule, cycle.source)
    return replace(
        cycle,
        order=order,
        phase_id=occurrence.phase_id if occurrence else cycle.phase_id,
    )


def _dated(cycle, calendar):
    if calendar is None:
        return cycle
    start, end = calendar.dates_for(cycle.order)
    return replace(cycle, starts_on=start, ends_on=end)


def _selected(schedule, target):
    for cycle in schedule.cycles:
        if cycle.archived:
            continue
        if (
            isinstance(target, SavedCycleRef)
            and cycle.id == target.cycle_id
            or isinstance(target, ProjectedCycleRef)
            and cycle.source.position == target.position
        ):
            return cycle
    if isinstance(target, SavedCycleRef):
        raise ScheduleError("Select a saved cycle from this campaign.")
    if not isinstance(target, ProjectedCycleRef):
        raise ScheduleError("Select a saved or projected cycle.")
    if target.position.plan_id != schedule.plan.id:
        raise ScheduleError(
            "The plan changed. Select a cycle from the current schedule."
        )
    if target.position.index < schedule.next_position:
        raise ScheduleError("That cycle has been deleted. Select another cycle.")
    return project(
        PlanContinuation(
            schedule.plan,
            target.position.index,
            schedule.calendar,
            sum(not c.archived for c in schedule.cycles)
            + target.position.index
            - schedule.next_position,
        ),
        limit=1,
    )[0]


def _prefix(schedule, selected):
    if isinstance(selected, Cycle):
        return ()
    return project(
        schedule, limit=selected.source.position.index - schedule.next_position + 1
    )


def _save(projected, new_id):
    return Cycle(
        new_id(),
        projected.order,
        CycleDetails(
            projected.phase_id, starts_on=projected.starts_on, ends_on=projected.ends_on
        ),
        projected.source,
    )


def _copy_template(template, *, mode, starts_after_order, new_id):
    phase_ids = {phase.id: new_id() for phase in template.phases}
    phases = tuple(replace(phase, id=phase_ids[phase.id]) for phase in template.phases)
    plan = Plan(
        new_id(),
        mode,
        tuple(
            replace(step, id=new_id(), phase_id=phase_ids[step.phase_id])
            for step in template.steps
        ),
        starts_after_order,
    )
    return phases, plan


def _source_block(cycle):
    source = cycle.source
    if source.position is None:
        return None
    return source.position.plan_id, source.repetition, source.step_id


def _attach_occurrences(schedule, created, new_id):
    """Keep one stable block for adjacent entries from the same pattern step."""
    occurrences = list(schedule.occurrences)
    by_id = {occurrence.id: occurrence for occurrence in occurrences}
    source_by_occurrence = {}
    tail = None
    for cycle in schedule.cycles:
        if not cycle.archived:
            tail = cycle
            if cycle.source.position is not None:
                source_by_occurrence[cycle.occurrence_id] = _source_block(cycle)
    next_position = sum(not occurrence.archived for occurrence in occurrences)
    attached = []
    last_occurrence = next(
        (o.id for o in reversed(occurrences) if not o.archived), None
    )
    for index, cycle in enumerate(created):
        occurrence = (
            _continuing_occurrence(schedule, cycle.source)
            if index == 0
            else by_id.get(tail.occurrence_id)
            if tail
            else None
        )
        if (
            occurrence is None
            or occurrence.archived
            or not occurrence.continues_pattern
            or occurrence.id != last_occurrence
            or occurrence.phase_id != cycle.details.phase_id
            or index > 0
            and source_by_occurrence.get(occurrence.id) != _source_block(cycle)
        ):
            next_position += 1
            occurrence = PhaseOccurrence(
                new_id(),
                cycle.details.phase_id,
                next_position,
                continues_pattern=cycle.source.position is not None
                and "phase_id" not in cycle.customized_fields,
            )
            occurrences.append(occurrence)
            by_id[occurrence.id] = occurrence
        last_occurrence = occurrence.id
        cycle = replace(cycle, occurrence_id=occurrence.id)
        attached.append(cycle)
        tail = cycle
        if cycle.source.position is not None:
            source_by_occurrence[occurrence.id] = _source_block(cycle)
    return tuple(occurrences), tuple(attached)


def _active_order(cycles):
    """Renumber active entries without changing their identities or audit source."""
    active = tuple(
        replace(cycle, order=index)
        for index, cycle in enumerate((c for c in cycles if not c.archived), start=1)
    )
    return active + tuple(c for c in cycles if c.archived)


def _with_cycle_blocks(schedule, cycles, new_id):
    """Keep phase blocks contiguous when an individual cycle changes phase."""
    by_id = {o.id: o for o in schedule.occurrences}
    ordered = []
    result = []
    previous = None
    for cycle in cycles:
        if cycle.archived:
            result.append(cycle)
            continue
        occurrence = by_id.get(cycle.occurrence_id)
        if occurrence is None or occurrence.phase_id != cycle.details.phase_id:
            occurrence = PhaseOccurrence(new_id(), cycle.details.phase_id, 1)
        if previous is None or previous.id != occurrence.id:
            if any(o.id == occurrence.id for o in ordered):
                occurrence = replace(occurrence, id=new_id())
            ordered.append(replace(occurrence, position=len(ordered) + 1))
        previous = occurrence
        result.append(replace(cycle, occurrence_id=occurrence.id))
    used = {o.id for o in ordered}
    empty = [
        o
        for o in schedule.occurrences
        if not o.archived
        and o.id not in used
        and not any(c.occurrence_id == o.id for c in schedule.cycles if not c.archived)
    ]
    for occurrence in empty:
        following = next(
            (
                o.id
                for o in schedule.occurrences
                if not o.archived and o.position > occurrence.position and o.id in used
            ),
            None,
        )
        index = next(
            (i for i, o in enumerate(ordered) if o.id == following), len(ordered)
        )
        ordered.insert(index, occurrence)
    ordered = [replace(o, position=i) for i, o in enumerate(ordered, start=1)]
    archived = tuple(
        replace(o, archived=True)
        for o in schedule.occurrences
        if o.id not in {v.id for v in ordered}
    )
    return replace(
        schedule, cycles=tuple(result), occurrences=tuple(ordered) + archived
    )


def reindexed_calendar(schedule, active_count):
    """Keep the next projected date when authoring changes visible positions."""
    if schedule.calendar is None:
        return None
    old_count = sum(not c.archived for c in schedule.cycles)
    return replace(
        schedule.calendar,
        position_offset=schedule.calendar.position_offset + old_count - active_count,
    )


def calendar_boundary(schedule):
    """First future position with dates that can still take schedule defaults."""
    frontier = max(
        (
            c.order
            for c in schedule.cycles
            if c.id in schedule.protected_cycle_ids or c.id == schedule.current_cycle_id
        ),
        default=0,
    )
    eligible = [
        c.order
        for c in schedule.cycles
        if not c.archived
        and c.order > frontier
        and not {"starts_on", "ends_on"}.issubset(c.customized_fields)
    ]
    return min(eligible, default=sum(not c.archived for c in schedule.cycles) + 1) - 1


def calendar_defaults_start(schedule):
    """Use an eligible saved start as evidence; projection offsets apply only to the tail."""
    boundary = calendar_boundary(schedule)
    selected = next(
        (c for c in schedule.cycles if not c.archived and c.order == boundary + 1), None
    )
    if (
        selected
        and "starts_on" not in selected.customized_fields
        and selected.details.starts_on is not None
    ):
        return selected.details.starts_on
    if schedule.calendar is None:
        return None
    try:
        return schedule.calendar.dates_for(boundary + 1)[0]
    except ScheduleError:
        try:
            return schedule.calendar.dates_for(
                sum(not c.archived for c in schedule.cycles) + 1
            )[0]
        except ScheduleError:
            return None


def _ensure_saved(
    schedule: Schedule,
    target: CycleRef,
    *,
    new_id: NewId = _id,
    selected_details: CycleDetails | None = None,
) -> tuple[ScheduleChange, Cycle]:
    """Resolve a selection and save its prefix without activating any cycle.

    Production callers persist this result with their battle or action in the
    same campaign transaction. No unrestricted materialisation endpoint is needed.
    """
    selected = _selected(schedule, target)
    if isinstance(selected, Cycle):
        return ScheduleChange(schedule), selected
    created = tuple(_save(p, new_id) for p in _prefix(schedule, selected))
    if selected_details is not None:
        original = created[-1]
        fields = frozenset(
            field
            for field in CycleDetails.__dataclass_fields__
            if getattr(original.details, field) != getattr(selected_details, field)
        )
        created = created[:-1] + (
            replace(original, details=selected_details, customized_fields=fields),
        )
    occurrences, created = _attach_occurrences(schedule, created, new_id)
    changed = replace(
        schedule,
        cycles=_active_order(schedule.cycles + created),
        occurrences=occurrences,
        next_position=selected.source.position.index + 1,
        continuation_occurrence_id=created[-1].occurrence_id,
        revision=schedule.revision + 1,
    )
    # Explicit edits validate after their optional suffix shift is assembled.
    if selected_details is None:
        validate_cycle_dates(changed.cycles, affected={c.id for c in created})
        _validate_projection_dates(changed)
    return ScheduleChange(changed, created=created), created[-1]


def configure(
    template: ScheduleTemplate,
    *,
    campaign_id: str,
    current_position: int | None,
    mode: Mode = "fixed",
    status: Status = "pre_campaign",
    now: datetime | None = None,
    calendar: CycleCalendar | None = None,
    new_id: NewId = _id,
) -> ScheduleChange:
    """Copy a template and explicitly select the initial current cycle.

    Earlier saved cycles have no invented completion times. Pre-campaign
    configuration does not start a cycle; start() records that separately.
    """
    if current_position is not None:
        _nonnegative(current_position, "Current cycle position")
    phases, plan = _copy_template(
        template, mode=mode, starts_after_order=0, new_id=new_id
    )
    _at(plan, current_position if current_position is not None else 0)
    initial_count = (
        plan.length
        if mode == "fixed"
        else (current_position + 1 if current_position is not None else 0)
    )
    cycles = tuple(
        _save(_dated(_at(plan, i), calendar), new_id) for i in range(initial_count)
    )
    empty = Schedule(campaign_id, phases, plan, 0, (), None, status, calendar=calendar)
    occurrences, cycles = _attach_occurrences(empty, cycles, new_id)
    schedule = replace(
        empty,
        next_position=len(cycles),
        cycles=cycles,
        occurrences=occurrences,
        continuation_occurrence_id=cycles[-1].occurrence_id if cycles else None,
        current_cycle_id=cycles[current_position].id
        if current_position is not None
        else None,
    )
    validate_cycle_dates(schedule.cycles)
    _validate_projection_dates(schedule)
    transition = None
    if status == "in_progress" and schedule.current is not None:
        if now is None:
            raise ScheduleError("Supply the time the initial cycle started.")
        transition = Transition("started", None, schedule.current, now)
    return ScheduleChange(schedule, created=cycles, transition=transition)


def preview_cycle_edit(
    schedule: Schedule, target: CycleRef, details: CycleDetails
) -> EditPreview:
    _phase(schedule, details.phase_id)
    selected = _selected(schedule, target)
    try:
        following_on = _following_on(schedule, selected)
    except ScheduleError:
        # An unavailable future date cannot supply a shift preview.
        following_on = None
    return EditPreview(target, details, _prefix(schedule, selected), following_on)


def _following_on(schedule, selected):
    """Earliest asserted day after the selection and its virtual saved prefix."""
    anchors = [
        span[0]
        for cycle in schedule.cycles
        if not cycle.archived
        and cycle.order > selected.order
        and (span := _date_span(cycle.details)) is not None
    ]
    next_position = (
        schedule.next_position
        if isinstance(selected, Cycle)
        else selected.source.position.index + 1
    )
    following = project(
        PlanContinuation(
            schedule.plan,
            next_position,
            schedule.calendar,
            sum(not c.archived for c in schedule.cycles)
            + next_position
            - schedule.next_position,
        ),
        limit=1,
    )
    if following and following[0].starts_on is not None:
        anchors.append(following[0].starts_on)
    return min(anchors, default=None)


def _shift_days(old_end, new_end, following_on):
    if new_end is None or following_on is None:
        return 0
    if old_end is not None:
        return (new_end - old_end).days
    return max(0, (new_end - following_on).days + 1)


def edit_cycle(
    schedule: Schedule,
    target: CycleRef,
    details: CycleDetails,
    *,
    now: datetime | None = None,
    new_id: NewId = _id,
    shift_later: bool = False,
    customized_fields: frozenset[str] | None = None,
) -> ScheduleChange:
    _phase(schedule, details.phase_id)
    original = _selected(schedule, target)
    old_end = (
        original.details.ends_on if isinstance(original, Cycle) else original.ends_on
    )
    shift = (
        _shift_days(old_end, details.ends_on, _following_on(schedule, original))
        if shift_later and details.ends_on is not None
        else 0
    )
    change, selected = _ensure_saved(
        schedule,
        target,
        new_id=new_id,
        selected_details=details,
    )
    original_details = (
        original.details
        if isinstance(original, Cycle)
        else CycleDetails(
            original.phase_id, starts_on=original.starts_on, ends_on=original.ends_on
        )
    )
    touched = (
        customized_fields
        if customized_fields is not None
        else frozenset(
            field
            for field in CycleDetails.__dataclass_fields__
            if getattr(original_details, field) != getattr(details, field)
        )
    )
    amended = replace(
        selected,
        details=details,
        customized_fields=selected.customized_fields | touched,
    )
    if amended.details.phase_id != selected.details.phase_id:
        # Blocks are normalised with the changed entry before constructing Schedule.
        changed_cycles = tuple(
            amended if c.id == amended.id else c for c in change.schedule.cycles
        )
        change = replace(
            change, schedule=_with_cycle_blocks(change.schedule, changed_cycles, new_id)
        )
        amended = next(c for c in change.schedule.cycles if c.id == amended.id)
    dates_changed = (
        (original.details.starts_on, original.details.ends_on)
        if isinstance(original, Cycle)
        else (original.starts_on, original.ends_on)
    ) != (details.starts_on, details.ends_on)
    if selected == amended and not shift:
        if change.created or dates_changed:
            validate_cycle_dates(
                change.schedule.cycles,
                affected={c.id for c in change.created} | {selected.id},
            )
            _validate_projection_dates(change.schedule)
        return change
    transition = None
    if (
        selected.id == schedule.current_cycle_id
        and selected.details.phase_id != details.phase_id
        and schedule.status == "in_progress"
    ):
        if now is None:
            raise ScheduleError("Supply the time the current phase changed.")
        transition = Transition("phase_changed", selected, amended, now)
    later = []
    if shift:
        try:
            delta = timedelta(days=shift)
            later = [
                replace(
                    c,
                    details=replace(
                        c.details,
                        starts_on=c.details.starts_on + delta
                        if c.details.starts_on is not None
                        else None,
                        ends_on=c.details.ends_on + delta
                        if c.details.ends_on is not None
                        else None,
                    ),
                )
                for c in change.schedule.cycles
                if not c.archived
                and c.order > selected.order
                and _date_span(c.details) is not None
            ]
        except ValueError, OverflowError:
            raise ScheduleError(
                "The shifted dates extend beyond the supported calendar."
            ) from None
    replacements = {c.id: c for c in (*later, amended)}
    after = replace(
        change.schedule,
        cycles=tuple(replacements.get(c.id, c) for c in change.schedule.cycles),
        calendar=replace(
            schedule.calendar, days_offset=schedule.calendar.days_offset + shift
        )
        if shift and schedule.calendar is not None
        else schedule.calendar,
        revision=schedule.revision + 1,
    )
    if change.created or dates_changed or shift:
        affected = {c.id for c in (*change.created, *later)}
        if dates_changed:
            affected.add(selected.id)
        validate_cycle_dates(after.cycles, affected=affected)
        _validate_projection_dates(after)
    return ScheduleChange(
        after,
        created=tuple(amended if c.id == selected.id else c for c in change.created),
        updated=tuple(later) + (() if change.created else (amended,)),
        transition=transition,
    )


def _validate_projection_dates(schedule):
    following = project(schedule, limit=1)
    if (
        schedule.calendar
        and schedule.cycles
        and following
        and any(
            not c.archived
            and any(
                bound is not None and following[0].starts_on <= bound
                for bound in (c.details.starts_on, c.details.ends_on)
            )
            for c in schedule.cycles
        )
    ):
        raise ScheduleError(
            "The dates overlap a future cycle. Move later cycle dates too, or choose an earlier end date."
        )


def edit_phase(
    schedule: Schedule, phase_id: str, details: PhaseDetails
) -> ScheduleChange:
    phase = _phase(schedule, phase_id)
    if phase.details == details:
        return ScheduleChange(schedule)
    return ScheduleChange(
        replace(
            schedule,
            phases=tuple(
                replace(p, details=details) if p.id == phase_id else p
                for p in schedule.phases
            ),
            revision=schedule.revision + 1,
        )
    )


def add_phase(
    schedule: Schedule, details: PhaseDetails, *, new_id: NewId = _id
) -> ScheduleChange:
    return ScheduleChange(
        replace(
            schedule,
            phases=schedule.phases + (Phase(new_id(), details),),
            revision=schedule.revision + 1,
        )
    )


def duplicate_phase(
    schedule: Schedule, phase_id: str, *, name: str, new_id: NewId = _id
) -> ScheduleChange:
    original = _phase(schedule, phase_id)
    copied = Phase(new_id(), replace(original.details, name=name))
    return ScheduleChange(
        replace(
            schedule,
            phases=schedule.phases + (copied,),
            revision=schedule.revision + 1,
        )
    )


def _archive_cycles(
    schedule, victims, *, replacement=None, no_current=False, new_id=_id
):
    if victims & schedule.protected_cycle_ids:
        raise ScheduleError(
            "These cycles have recorded activity. Keep them in the campaign timeline."
        )
    current = schedule.current_cycle_id
    change = ScheduleChange(schedule)
    if current in victims:
        if (replacement is None) == (not no_current):
            raise ScheduleError(
                "Choose a replacement current cycle or No current cycle."
            )
        if replacement is not None:
            selected = _selected(schedule, replacement)
            if isinstance(selected, Cycle) and selected.id in victims:
                raise ScheduleError("Choose a current cycle that is not being deleted.")
            change, selected = _ensure_saved(schedule, replacement, new_id=new_id)
            current = selected.id
        else:
            current = None
    elif replacement is not None or no_current:
        raise ScheduleError(
            "The current cycle is not being deleted. Leave it unchanged."
        )
    archived = tuple(
        replace(c, archived=True) for c in change.schedule.cycles if c.id in victims
    )
    replacements = {c.id: c for c in archived}
    return ScheduleChange(
        replace(
            change.schedule,
            cycles=_active_order(
                tuple(replacements.get(c.id, c) for c in change.schedule.cycles)
            ),
            current_cycle_id=current,
            calendar=reindexed_calendar(
                change.schedule,
                sum(
                    not c.archived and c.id not in victims
                    for c in change.schedule.cycles
                ),
            ),
            revision=schedule.revision + 1,
        ),
        created=tuple(replacements.get(c.id, c) for c in change.created),
        updated=tuple(
            c
            for c in _active_order(
                tuple(replacements.get(c.id, c) for c in change.schedule.cycles)
            )
            if c.id not in {c.id for c in change.created}
            and c != next(old for old in schedule.cycles if old.id == c.id)
        ),
    )


def delete_cycle(schedule, target, *, replacement=None, no_current=False, new_id=_id):
    """Keep the original identity and source position without starting a cycle."""
    change, selected = _ensure_saved(schedule, target, new_id=new_id)
    removed = _archive_cycles(
        change.schedule,
        {selected.id},
        replacement=replacement,
        no_current=no_current,
        new_id=new_id,
    )
    archived = {c.id: c for c in removed.schedule.cycles}
    created = tuple(archived[c.id] for c in change.created) + removed.created
    return ScheduleChange(
        replace(removed.schedule, revision=schedule.revision + 1),
        created=created,
        updated=tuple(
            c for c in removed.updated if c.id not in {c.id for c in created}
        ),
    )


def delete_phase(schedule, phase_id, *, replacement=None, no_current=False, new_id=_id):
    """Remove every occurrence while retaining saved identities for audit history."""
    _phase(schedule, phase_id)
    if replacement is not None:
        selected = _selected(schedule, replacement)
        selected_phase = (
            selected.details.phase_id
            if isinstance(selected, Cycle)
            else selected.phase_id
        )
        if selected_phase == phase_id:
            raise ScheduleError(
                "Choose a current cycle outside the phase being deleted."
            )
    victims = {
        c.id
        for c in schedule.cycles
        if not c.archived and c.details.phase_id == phase_id
    }
    change = _archive_cycles(
        schedule, victims, replacement=replacement, no_current=no_current, new_id=new_id
    )
    # A replacement can save a prefix containing more occurrences of this phase.
    extra = tuple(
        replace(c, archived=True) if c.details.phase_id == phase_id else c
        for c in change.created
    )
    replacements = {c.id: c for c in extra}
    state = replace(
        change.schedule,
        cycles=tuple(replacements.get(c.id, c) for c in change.schedule.cycles),
    )
    plan = state.plan
    if any(step.phase_id == phase_id for step in plan.steps):
        if plan.mode == "fixed":
            steps = tuple(
                step for step in editable_steps(state) if step.phase_id != phase_id
            )
            position = 0
        else:
            steps = tuple(step for step in plan.steps if step.phase_id != phase_id)
            # Keep a completed pass distinct from an unstarted filtered pattern.
            offset = state.next_position % plan.length
            if not offset and state.next_position > 0:
                offset = plan.length
            position = 0
            for step in plan.steps:
                consumed = min(offset, step.count)
                if step.phase_id != phase_id:
                    position += consumed
                offset -= consumed
        plan = Plan(
            new_id(),
            plan.mode if steps else "fixed",
            steps,
            len(state.cycles),
            position,
        )
        next_position = position
    else:
        next_position = state.next_position
    return ScheduleChange(
        replace(
            state,
            phases=tuple(
                replace(p, archived=True) if p.id == phase_id else p
                for p in state.phases
            ),
            plan=plan,
            next_position=next_position,
            revision=schedule.revision + 1,
        ),
        created=extra,
        updated=change.updated,
    )


def replace_plan(
    schedule: Schedule,
    *,
    steps: tuple[PlanStep, ...],
    mode: Mode,
    new_id: NewId = _id,
    calendar: CycleCalendar | None = None,
    clear_calendar: bool = False,
) -> ScheduleChange:
    """Replace future steps, preserving omitted timing unless explicitly cleared."""
    revision = schedule.revision + 1
    timing = calendar if calendar is not None else schedule.calendar
    if clear_calendar:
        timing = None
    if mode == schedule.plan.mode and tuple(steps) == editable_steps(schedule):
        if timing == schedule.calendar:
            return ScheduleChange(schedule)
        after = replace(schedule, calendar=timing, revision=revision)
    else:
        position = _repeat_continuation(schedule, steps) if mode == "repeating" else 0
        plan = Plan(new_id(), mode, tuple(steps), len(schedule.cycles), position)
        if plan.id == schedule.plan.id:
            raise ScheduleError("A replacement plan must have a new identity.")
        continuation = None
        if mode == "repeating" and position and schedule.next_position:
            previous = _at(
                replace(schedule.plan, start_position=0), schedule.next_position - 1
            )
            mapped = _at(replace(plan, start_position=0), position - 1)
            if mapped.phase_id == previous.phase_id:
                occurrence = _continuing_occurrence(schedule, previous.source)
                continuation = occurrence.id if occurrence else None
        used = (
            {step.phase_id for step in plan.steps}
            | {o.phase_id for o in schedule.occurrences}
            | {c.details.phase_id for c in schedule.cycles if not c.archived}
        )
        retired = {step.phase_id for step in schedule.plan.steps} - used
        after = replace(
            schedule,
            plan=plan,
            next_position=position,
            continuation_occurrence_id=continuation,
            phases=tuple(
                replace(p, archived=True) if p.id in retired else p
                for p in schedule.phases
            ),
            calendar=timing,
            revision=revision,
        )
    _validate_projection_dates(after)
    return ScheduleChange(after)


def _repeat_continuation(schedule, steps):
    """Map the consumed source cursor into a replacement pattern."""
    if not schedule.plan.length or not schedule.next_position:
        return 0
    previous = _at(replace(schedule.plan, start_position=0), schedule.next_position - 1)
    matching = next(
        (
            step
            for step in steps
            if step.id == previous.source.step_id and step.phase_id == previous.phase_id
        ),
        None,
    )
    if matching is None:
        candidates = [step for step in steps if step.phase_id == previous.phase_id]
        matching = candidates[0] if len(candidates) == 1 else None
    if matching is None:
        return 0
    before = sum(step.count for step in steps[: steps.index(matching)])
    return before + min(previous.source.offset + 1, matching.count)


def timeline_settings(
    schedule: Schedule,
    *,
    mode: Mode,
    steps: tuple[PlanStep, ...],
    calendar: CycleCalendar | None = None,
    clear_calendar=False,
    new_id: NewId = _id,
) -> ScheduleChange:
    """Set defaults, materialising a finite endpoint without rewriting authored entries."""
    state = schedule
    if mode == "fixed":
        remaining = (
            (state.plan.length - state.next_position % state.plan.length)
            % state.plan.length
            if state.plan.mode == "repeating" and state.next_position
            else state.plan.length - state.next_position
        )
        if remaining:
            change, _ = _ensure_saved(
                state, project(state, limit=remaining)[-1].ref, new_id=new_id
            )
            state = change.schedule
        if state.plan.mode != "fixed":
            plan = Plan(
                new_id(),
                "fixed",
                state.plan.steps,
                sum(not c.archived for c in state.cycles),
            )
            state = replace(state, plan=plan, next_position=plan.length)
    elif mode != state.plan.mode or steps != state.plan.steps:
        state = replace_plan(state, mode=mode, steps=steps, new_id=new_id).schedule
    timing = (
        None if clear_calendar else calendar if calendar is not None else state.calendar
    )
    if timing != schedule.calendar:
        frontier = max(
            (
                c.order
                for c in state.cycles
                if c.id in state.protected_cycle_ids or c.id == state.current_cycle_id
            ),
            default=0,
        )
        amended = []
        for cycle in state.cycles:
            if cycle.archived or cycle.order <= frontier:
                amended.append(cycle)
                continue
            if {"starts_on", "ends_on"}.issubset(cycle.customized_fields):
                amended.append(cycle)
                continue
            start, end = timing.dates_for(cycle.order) if timing else (None, None)
            values = {
                field: value
                for field, value in (("starts_on", start), ("ends_on", end))
                if field not in cycle.customized_fields
            }
            amended.append(replace(cycle, details=replace(cycle.details, **values)))
        state = replace(state, cycles=tuple(amended), calendar=timing)
        validate_cycle_dates(
            state.cycles,
            affected={
                c.id
                for c in state.cycles
                if c.order > frontier and c.id not in state.protected_cycle_ids
            },
        )
    if state == schedule:
        return ScheduleChange(schedule)
    state = replace(state, revision=schedule.revision + 1)
    _validate_projection_dates(state)
    original = {c.id: c for c in schedule.cycles}
    return ScheduleChange(
        state,
        created=tuple(c for c in state.cycles if c.id not in original),
        updated=tuple(
            c for c in state.cycles if c.id in original and c != original[c.id]
        ),
    )


def set_calendar(schedule: Schedule, calendar: CycleCalendar) -> ScheduleChange:
    """Change projected dates without filling or replacing saved bounds."""
    if calendar == schedule.calendar:
        return ScheduleChange(schedule)
    after = replace(schedule, calendar=calendar, revision=schedule.revision + 1)
    _validate_projection_dates(after)
    return ScheduleChange(after)


def editable_steps(schedule: Schedule | PlanContinuation) -> tuple[PlanStep, ...]:
    """A repeating pattern, or only the unsaved remainder of a fixed plan."""
    if schedule.plan.mode == "repeating":
        return schedule.plan.steps
    return _remaining_steps(schedule.plan.steps, schedule.next_position)


def fixed_steps(schedule: Schedule) -> tuple[PlanStep, ...]:
    """Finish the repeating pass containing the last saved cycle."""
    if schedule.plan.mode == "fixed":
        return editable_steps(schedule)
    consumed = schedule.next_position % schedule.plan.length
    completed = schedule.next_position > 0
    if not consumed and completed:
        return ()
    return _remaining_steps(schedule.plan.steps, consumed)


def _remaining_steps(
    steps: tuple[PlanStep, ...], consumed: int
) -> tuple[PlanStep, ...]:
    remaining = []
    for step in steps:
        if consumed >= step.count:
            consumed -= step.count
        else:
            remaining.append(replace(step, count=step.count - consumed))
            consumed = 0
    return tuple(remaining)


def apply_template(
    schedule: Schedule,
    template: ScheduleTemplate,
    *,
    mode: Mode = "fixed",
    new_id: NewId = _id,
) -> ScheduleChange:
    phases, plan = _copy_template(
        template,
        mode=mode,
        starts_after_order=len(schedule.cycles),
        new_id=new_id,
    )
    after = replace(
        schedule,
        phases=schedule.phases + phases,
        plan=plan,
        next_position=0,
        revision=schedule.revision + 1,
    )
    _validate_projection_dates(after)
    return ScheduleChange(after)


def preview_advance(schedule: Schedule) -> TransitionPreview:
    if schedule.status == "post_campaign":
        raise ScheduleError("This campaign has finished. Its cycle cannot advance.")
    if schedule.status != "in_progress":
        raise ScheduleError("Start the campaign before advancing its cycle.")
    current = schedule.current
    if current is None:
        raise ScheduleError("Start a cycle before advancing.")
    following_saved = next(
        (c for c in schedule.cycles if not c.archived and c.order > current.order), None
    )
    if following_saved is not None:
        return TransitionPreview(current, following_saved)
    following = project(schedule, limit=1)
    return TransitionPreview(current, following[0] if following else None)


def start(
    schedule: Schedule,
    *,
    now: datetime,
    new_id: NewId = _id,
    target: CycleRef | None = None,
) -> ScheduleChange:
    if schedule.status == "post_campaign":
        raise ScheduleError("Reopen the campaign before starting a cycle.")
    if schedule.status == "in_progress" and schedule.current is not None:
        raise ScheduleError(
            "A cycle is already current. Advance it to start the next cycle."
        )
    change = ScheduleChange(schedule)
    selected = schedule.current
    if target is not None:
        if selected is not None:
            raise ScheduleError("The current cycle is already selected.")
        change, selected = _ensure_saved(schedule, target, new_id=new_id)
    elif selected is None and (
        any(c.archived for c in schedule.cycles)
        or any(p.archived for p in schedule.phases)
    ):
        raise ScheduleError(
            "Choose the cycle to start after deleting a cycle or phase."
        )
    if selected is None:
        selected = next((c for c in schedule.cycles if not c.archived), None)
        if selected is None:
            following = project(schedule, limit=1)
            if not following:
                raise ScheduleError("Add a cycle before starting.")
            change, selected = _ensure_saved(schedule, following[0].ref, new_id=new_id)
    return ScheduleChange(
        replace(
            change.schedule,
            status="in_progress",
            current_cycle_id=selected.id,
            revision=schedule.revision + 1,
        ),
        created=change.created,
        transition=Transition("started", None, selected, now),
    )


def advance(
    schedule: Schedule, *, now: datetime, new_id: NewId = _id
) -> ScheduleChange:
    preview = preview_advance(schedule)
    if preview.finishes:
        raise ScheduleError("The final cycle has been reached. Finish the campaign.")
    target = (
        SavedCycleRef(preview.following.id)
        if isinstance(preview.following, Cycle)
        else preview.following.ref
    )
    change, selected = _ensure_saved(schedule, target, new_id=new_id)
    return ScheduleChange(
        replace(
            change.schedule,
            current_cycle_id=selected.id,
            revision=schedule.revision + 1,
        ),
        created=change.created,
        transition=Transition("advanced", schedule.current, selected, now),
    )


def finish(schedule: Schedule, *, now: datetime) -> ScheduleChange:
    if schedule.status != "in_progress":
        raise ScheduleError("Only an in-progress campaign can be finished.")
    return ScheduleChange(
        replace(schedule, status="post_campaign", revision=schedule.revision + 1),
        transition=Transition("finished", schedule.current, schedule.current, now)
        if schedule.current
        else None,
    )


def context(schedule: Schedule, cycle_id: str) -> CycleContext:
    """Pin a saved cycle without consulting the campaign's current phase later."""
    selected = _selected(schedule, SavedCycleRef(cycle_id))
    return CycleContext(schedule.campaign_id, selected.id)
