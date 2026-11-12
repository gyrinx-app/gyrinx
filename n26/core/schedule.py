"""Campaign planning calculations, independent of persistence and delivery.

Saved cycles form an ordered prefix. A plan describes only the continuation
after that prefix; editable dates never decide which position comes next.
Replacing a plan preserves saved cycles and their original source positions.
Callers persist a change under the campaign lock and deliver any transition
only after commit. This module performs no database writes or reward execution.
"""

from calendar import monthrange
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
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

    def __post_init__(self):
        _nonnegative(self.next_position, "Next plan position")


@dataclass(frozen=True)
class CycleSource:
    position: PlannedPosition
    step_id: str
    repetition: int
    offset: int

    def __post_init__(self):
        _nonnegative(self.repetition, "Pattern repetition")
        _nonnegative(self.offset, "Position within the step")


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

    def __post_init__(self):
        if type(self.starts_on) is not date:
            raise ScheduleError("Enter the first cycle's start date.")
        _positive(self.interval, "Cycle interval")
        _nonnegative(self.starts_after_order, "Date boundary")
        if self.unit not in ("weeks", "months"):
            raise ScheduleError("Select weeks or calendar months.")
        if type(self.days_offset) is not int:
            raise ScheduleError("Enter a whole number of days to shift the calendar.")

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
        index = order - self.starts_after_order - 1
        _nonnegative(index, "Cycle date position")
        return self._boundary(index), self._boundary(index + 1) - timedelta(days=1)


def validate_cycle_dates(cycles, *, required=True):
    dated = []
    for cycle in cycles:
        if cycle.archived:
            continue
        start, end = cycle.details.starts_on, cycle.details.ends_on
        if start is None or end is None:
            if required:
                raise ScheduleError(f"Enter both dates for {cycle.name}.")
            continue
        dated.append((start, end, cycle.name))
    dated.sort()
    for previous, following in zip(dated, dated[1:], strict=False):
        if previous[1] >= following[0]:
            raise ScheduleError(
                f"The dates for {following[2]} overlap {previous[2]}. Choose a range outside the other saved cycles."
            )


@dataclass(frozen=True)
class Cycle:
    id: str
    order: int
    details: CycleDetails
    source: CycleSource
    archived: bool = False

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

    def __post_init__(self):
        if self.status not in ("pre_campaign", "in_progress", "post_campaign"):
            raise ScheduleError("Select a campaign status.")
        _nonnegative(self.revision, "Schedule revision")
        _nonnegative(self.next_position, "Next plan position")
        _unique((phase.id for phase in self.phases), "Phases")
        _unique((cycle.id for cycle in self.cycles), "Cycles")
        _unique((cycle.source.position for cycle in self.cycles), "Cycle sources")
        if self.current_cycle_id is not None and self.current_cycle_id not in {
            cycle.id for cycle in self.cycles if not cycle.archived
        }:
            raise ScheduleError("Select a saved current cycle.")
        if tuple(cycle.order for cycle in self.cycles) != tuple(
            range(1, len(self.cycles) + 1)
        ):
            raise ScheduleError("Saved cycles must keep their consecutive order.")
        phase_ids = {phase.id for phase in self.phases}
        active_phases = {phase.id for phase in self.phases if not phase.archived}
        if any(step.phase_id not in active_phases for step in self.plan.steps) or any(
            cycle.details.phase_id not in phase_ids for cycle in self.cycles
        ):
            raise ScheduleError("Select phases from this campaign.")
        if len(self.cycles) != self.plan.order_for(self.next_position) - 1:
            raise ScheduleError("The plan must continue after the saved cycles.")
        if self.plan.mode == "fixed" and self.next_position > self.plan.length:
            raise ScheduleError("The next position is beyond the fixed plan.")
        for index, cycle in enumerate(
            self.cycles[self.plan.starts_after_order :], start=self.plan.start_position
        ):
            projected = _at(self.plan, index)
            if cycle.source != projected.source:
                raise ScheduleError("Saved cycles must retain their plan positions.")
        if self.calendar is not None:
            validate_cycle_dates(self.cycles, required=False)
            self.calendar.dates_for(len(self.cycles) + 100)

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
            or self.previous_cycle.details.phase_id
            != self.current_cycle.details.phase_id
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
    return tuple(
        _dated(_at(schedule.plan, i), schedule.calendar)
        for i in range(schedule.next_position, end)
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
    return _dated(_at(schedule.plan, target.position.index), schedule.calendar)


def _prefix(schedule, selected):
    if isinstance(selected, Cycle):
        return ()
    return tuple(
        _dated(_at(schedule.plan, i), schedule.calendar)
        for i in range(schedule.next_position, selected.source.position.index + 1)
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


def _ensure_saved(
    schedule: Schedule,
    target: CycleRef,
    *,
    new_id: NewId = _id,
    selected_details: CycleDetails | None = None,
    clear_dates: bool = False,
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
        if (
            not clear_dates
            and selected_details.starts_on is None
            and selected_details.ends_on is None
        ):
            selected_details = replace(
                selected_details, starts_on=selected.starts_on, ends_on=selected.ends_on
            )
        created = created[:-1] + (replace(created[-1], details=selected_details),)
    changed = replace(
        schedule,
        cycles=schedule.cycles + created,
        next_position=selected.source.position.index + 1,
        revision=schedule.revision + 1,
    )
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
    cycles = tuple(
        _save(_dated(_at(plan, i), calendar), new_id)
        for i in range(current_position + 1 if current_position is not None else 0)
    )
    schedule = Schedule(
        campaign_id,
        phases,
        plan,
        len(cycles),
        cycles,
        cycles[-1].id if cycles else None,
        status,
        calendar=calendar,
    )
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
    return EditPreview(target, details, _prefix(schedule, selected))


def edit_cycle(
    schedule: Schedule,
    target: CycleRef,
    details: CycleDetails,
    *,
    now: datetime | None = None,
    new_id: NewId = _id,
    shift_later: bool = False,
    clear_dates: bool = False,
) -> ScheduleChange:
    _phase(schedule, details.phase_id)
    original = _selected(schedule, target)
    old_end = (
        original.details.ends_on if isinstance(original, Cycle) else original.ends_on
    )
    shift = 0
    if shift_later:
        if schedule.calendar is None or old_end is None or details.ends_on is None:
            raise ScheduleError("Set cycle dates before moving later cycle dates.")
        shift = (details.ends_on - old_end).days
    change, selected = _ensure_saved(
        schedule,
        target,
        new_id=new_id,
        selected_details=details,
        clear_dates=clear_dates,
    )
    if not clear_dates and details.starts_on is None and details.ends_on is None:
        details = replace(
            details,
            starts_on=selected.details.starts_on,
            ends_on=selected.details.ends_on,
        )
    amended = replace(selected, details=details)
    if (details.starts_on is None) != (details.ends_on is None):
        raise ScheduleError(f"Enter both dates for {amended.name}.")
    if schedule.calendar is None:
        validate_cycle_dates((amended,), required=False)
        for other in change.schedule.cycles:
            if other.id != amended.id:
                validate_cycle_dates((amended, other), required=False)
    if selected.details == details and not shift:
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
        delta = timedelta(days=shift)
        try:
            later = [
                replace(
                    c,
                    details=replace(
                        c.details,
                        starts_on=c.details.starts_on + delta,
                        ends_on=c.details.ends_on + delta,
                    ),
                )
                for c in change.schedule.cycles
                if not c.archived
                and c.order > selected.order
                and c.details.starts_on
                and c.details.ends_on
            ]
        except OverflowError:
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
        if shift
        else schedule.calendar,
        revision=schedule.revision + 1,
    )
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
            and c.details.ends_on
            and following[0].starts_on <= c.details.ends_on
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
            cycles=tuple(replacements.get(c.id, c) for c in change.schedule.cycles),
            current_cycle_id=current,
            revision=schedule.revision + 1,
        ),
        created=tuple(replacements.get(c.id, c) for c in change.created),
        updated=tuple(
            c for c in archived if c.id not in {c.id for c in change.created}
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
            # Map the old next offset into the filtered pattern, including repeated phases.
            offset = state.next_position % plan.length
            position = 0
            for step in plan.steps:
                consumed = min(offset, step.count)
                if step.phase_id != phase_id:
                    position += consumed
                offset -= consumed
            position = position % sum(step.count for step in steps) if steps else 0
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
    preserve_saved_dates: bool = False,
) -> ScheduleChange:
    """Replace future steps, preserving omitted timing unless explicitly cleared."""
    revision = schedule.revision + 1
    dated = (
        set_calendar(schedule, calendar, fill_saved_dates=not preserve_saved_dates)
        if calendar is not None
        else ScheduleChange(
            replace(schedule, calendar=None, revision=revision)
            if clear_calendar and schedule.calendar is not None
            else schedule
        )
    )
    schedule = dated.schedule
    if mode == schedule.plan.mode and tuple(steps) == editable_steps(schedule):
        return dated
    position = _repeat_continuation(schedule, steps) if mode == "repeating" else 0
    plan = Plan(new_id(), mode, tuple(steps), len(schedule.cycles), position)
    if plan.id == schedule.plan.id:
        raise ScheduleError("A replacement plan must have a new identity.")
    return ScheduleChange(
        replace(schedule, plan=plan, next_position=position, revision=revision),
        updated=dated.updated,
    )


def _repeat_continuation(schedule, steps):
    return _saved_tail_credit(schedule, steps)


def _saved_tail_credit(schedule, steps):
    """Credit the saved tail against its matching occurrence in the new pattern."""
    if not schedule.cycles:
        return 0
    tail = schedule.cycles[-1]
    phase_id, source = tail.details.phase_id, tail.source
    if (
        tail.archived
        and schedule.plan.mode == "repeating"
        and len(schedule.cycles) == schedule.plan.starts_after_order
    ):
        # Deletion maps the active continuation independently of the archived tail.
        if schedule.plan.start_position:
            previous = _at(
                replace(schedule.plan, start_position=0), schedule.plan.start_position - 1
            )
            phase_id, source = previous.phase_id, previous.source
        else:
            retained_steps = {step.id: step for step in schedule.plan.steps}
            previous = next((c for c in reversed(schedule.cycles) if c.source.step_id in retained_steps), None)
            if previous is None:
                return 0
            phase_id, source = retained_steps[previous.source.step_id].phase_id, previous.source
    matching = next(
        (
            step
            for step in steps
            if step.id == source.step_id and step.phase_id == phase_id
        ),
        None,
    )
    if matching is None:
        candidates = [step for step in steps if step.phase_id == phase_id]
        matching = candidates[0] if len(candidates) == 1 else None
    if matching is None:
        return 0
    before = sum(step.count for step in steps[: steps.index(matching)])
    return before + min(source.offset + 1, matching.count)


def set_calendar(
    schedule: Schedule, calendar: CycleCalendar, *, fill_saved_dates=True
) -> ScheduleChange:
    updated = []
    for cycle in schedule.cycles:
        if (
            not cycle.archived
            and fill_saved_dates
            and (cycle.details.starts_on is None or cycle.details.ends_on is None)
        ):
            start, end = calendar.dates_for(cycle.order)
            updated.append(
                replace(
                    cycle,
                    details=replace(
                        cycle.details,
                        starts_on=cycle.details.starts_on or start,
                        ends_on=cycle.details.ends_on or end,
                    ),
                )
            )
    replacements = {cycle.id: cycle for cycle in updated}
    saved = tuple(replacements.get(cycle.id, cycle) for cycle in schedule.cycles)
    validate_cycle_dates(saved, required=False)
    start, _end = calendar.dates_for(len(saved) + 1)
    latest_end = max(
        (
            cycle.details.ends_on
            for cycle in saved
            if not cycle.archived and cycle.details.ends_on
        ),
        default=None,
    )
    if latest_end and start <= latest_end:
        raise ScheduleError(
            "The first projected cycle must start after all saved cycle dates."
        )
    if calendar == schedule.calendar and not updated:
        return ScheduleChange(schedule)
    return ScheduleChange(
        replace(
            schedule,
            calendar=calendar,
            cycles=saved,
            revision=schedule.revision + 1,
        ),
        updated=tuple(updated),
    )


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
    return ScheduleChange(
        replace(
            schedule,
            phases=schedule.phases + phases,
            plan=plan,
            next_position=0,
            revision=schedule.revision + 1,
        )
    )


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
