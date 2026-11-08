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


@dataclass(frozen=True)
class PlanStep:
    id: str
    phase_id: str
    count: int

    def __post_init__(self):
        _positive(self.count, "Cycle count")


@dataclass(frozen=True)
class Plan:
    id: str
    mode: Mode
    steps: tuple[PlanStep, ...]
    starts_after_order: int = 0

    def __post_init__(self):
        if self.mode not in ("fixed", "repeating"):
            raise ScheduleError("Select a fixed or repeating plan.")
        if not self.steps and self.mode == "repeating":
            raise ScheduleError("Add at least one step to the plan.")
        _unique((step.id for step in self.steps), "Plan steps")
        _nonnegative(self.starts_after_order, "Plan boundary")

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

    def __post_init__(self):
        if type(self.starts_on) is not date:
            raise ScheduleError("Enter the first cycle's start date.")
        _positive(self.interval, "Cycle interval")
        _nonnegative(self.starts_after_order, "Date boundary")
        if self.unit not in ("weeks", "months"):
            raise ScheduleError("Select weeks or calendar months.")

    def _boundary(self, index):
        try:
            if self.unit == "weeks":
                return self.starts_on + timedelta(weeks=self.interval * index)
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
            )
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
    current_cycle_id: str
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
        if self.current_cycle_id not in {cycle.id for cycle in self.cycles}:
            raise ScheduleError("Select a saved current cycle.")
        if tuple(cycle.order for cycle in self.cycles) != tuple(
            range(1, len(self.cycles) + 1)
        ):
            raise ScheduleError("Saved cycles must keep their consecutive order.")
        phase_ids = {phase.id for phase in self.phases}
        if any(step.phase_id not in phase_ids for step in self.plan.steps) or any(
            cycle.details.phase_id not in phase_ids for cycle in self.cycles
        ):
            raise ScheduleError("Select phases from this campaign.")
        if len(self.cycles) != self.plan.starts_after_order + self.next_position:
            raise ScheduleError("The plan must continue after the saved cycles.")
        if self.plan.mode == "fixed" and self.next_position > self.plan.length:
            raise ScheduleError("The next position is beyond the fixed plan.")
        for index, cycle in enumerate(self.cycles[self.plan.starts_after_order :]):
            projected = _at(self.plan, index)
            if cycle.source != projected.source:
                raise ScheduleError("Saved cycles must retain their plan positions.")
        if self.calendar is not None:
            validate_cycle_dates(self.cycles)
            self.calendar.dates_for(len(self.cycles) + 100)

    @property
    def current(self):
        return next(c for c in self.cycles if c.id == self.current_cycle_id)

    @property
    def current_phase(self):
        return _phase(self, self.current.details.phase_id)


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
        Phase("occupation", PhaseDetails("Occupation Phase")),
        Phase("downtime", PhaseDetails("Downtime")),
        Phase("takeover", PhaseDetails("Takeover Phase")),
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
        if phase.id == phase_id:
            return phase
    raise ScheduleError("Select a phase from this campaign.")


def _at(plan, index):
    _nonnegative(index, "Plan position")
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
                plan.starts_after_order + index + 1,
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
) -> tuple[ScheduleChange, Cycle]:
    """Resolve a selection and save its prefix without activating any cycle.

    Production callers persist this result with their battle or action in the
    same campaign transaction. No unrestricted materialisation endpoint is needed.
    """
    selected = _selected(schedule, target)
    if isinstance(selected, Cycle):
        return ScheduleChange(schedule), selected
    if schedule.calendar is None:
        raise ScheduleError("Set cycle date settings before saving a projected cycle.")
    created = tuple(_save(p, new_id) for p in _prefix(schedule, selected))
    if selected_details is not None:
        if selected_details.starts_on is None and selected_details.ends_on is None:
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
    current_position: int,
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
    _nonnegative(current_position, "Current cycle position")
    phases, plan = _copy_template(
        template, mode=mode, starts_after_order=0, new_id=new_id
    )
    _at(plan, current_position)
    cycles = tuple(
        _save(_dated(_at(plan, i), calendar), new_id)
        for i in range(current_position + 1)
    )
    schedule = Schedule(
        campaign_id,
        phases,
        plan,
        len(cycles),
        cycles,
        cycles[-1].id,
        status,
        calendar=calendar,
    )
    transition = None
    if status == "in_progress":
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
) -> ScheduleChange:
    _phase(schedule, details.phase_id)
    change, selected = _ensure_saved(
        schedule, target, new_id=new_id, selected_details=details
    )
    if details.starts_on is None and details.ends_on is None:
        details = replace(
            details,
            starts_on=selected.details.starts_on,
            ends_on=selected.details.ends_on,
        )
    if selected.details == details:
        return change
    amended = replace(selected, details=details)
    if schedule.calendar is None and (
        details.starts_on != selected.details.starts_on
        or details.ends_on != selected.details.ends_on
    ):
        validate_cycle_dates((amended,))
        for other in change.schedule.cycles:
            if other.id != amended.id:
                validate_cycle_dates((amended, other), required=False)
    transition = None
    if (
        selected.id == schedule.current_cycle_id
        and selected.details.phase_id != details.phase_id
        and schedule.status == "in_progress"
    ):
        if now is None:
            raise ScheduleError("Supply the time the current phase changed.")
        transition = Transition("phase_changed", selected, amended, now)
    after = replace(
        change.schedule,
        cycles=tuple(
            amended if c.id == selected.id else c for c in change.schedule.cycles
        ),
        revision=schedule.revision + 1,
    )
    return ScheduleChange(
        after,
        created=tuple(amended if c.id == selected.id else c for c in change.created),
        updated=() if change.created else (amended,),
        transition=transition,
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


def delete_phase(schedule: Schedule, phase_id: str) -> ScheduleChange:
    _phase(schedule, phase_id)
    if any(c.details.phase_id == phase_id for c in schedule.cycles):
        raise ScheduleError("You cannot delete a phase used by a saved cycle.")
    if any(step.phase_id == phase_id for step in schedule.plan.steps):
        raise ScheduleError("Remove the phase from the future plan before deleting it.")
    return ScheduleChange(
        replace(
            schedule,
            phases=tuple(p for p in schedule.phases if p.id != phase_id),
            revision=schedule.revision + 1,
        )
    )


def replace_plan(
    schedule: Schedule,
    *,
    steps: tuple[PlanStep, ...],
    mode: Mode,
    new_id: NewId = _id,
    calendar: CycleCalendar | None = None,
) -> ScheduleChange:
    revision = schedule.revision + 1
    dated = (
        set_calendar(schedule, calendar)
        if calendar is not None
        else ScheduleChange(schedule)
    )
    schedule = dated.schedule
    if mode == schedule.plan.mode and tuple(steps) == editable_steps(schedule):
        return dated
    plan = Plan(new_id(), mode, tuple(steps), len(schedule.cycles))
    if plan.id == schedule.plan.id:
        raise ScheduleError("A replacement plan must have a new identity.")
    return ScheduleChange(
        replace(schedule, plan=plan, next_position=0, revision=revision),
        updated=dated.updated,
    )


def set_calendar(schedule: Schedule, calendar: CycleCalendar) -> ScheduleChange:
    updated = []
    for cycle in schedule.cycles:
        if cycle.details.starts_on is None or cycle.details.ends_on is None:
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
    validate_cycle_dates(saved)
    start, _end = calendar.dates_for(len(saved) + 1)
    if start <= max(cycle.details.ends_on for cycle in saved):
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
    consumed = schedule.next_position
    remaining = []
    for step in schedule.plan.steps:
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
    if current.order < len(schedule.cycles):
        return TransitionPreview(current, schedule.cycles[current.order])
    following = project(schedule, limit=1)
    return TransitionPreview(current, following[0] if following else None)


def start(schedule: Schedule, *, now: datetime) -> ScheduleChange:
    if schedule.status != "pre_campaign":
        raise ScheduleError("Only a pre-campaign schedule can be started.")
    return ScheduleChange(
        replace(schedule, status="in_progress", revision=schedule.revision + 1),
        transition=Transition("started", None, schedule.current, now),
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
        transition=Transition("finished", schedule.current, schedule.current, now),
    )


def context(schedule: Schedule, cycle_id: str) -> CycleContext:
    """Pin a saved cycle without consulting the campaign's current phase later."""
    selected = _selected(schedule, SavedCycleRef(cycle_id))
    return CycleContext(schedule.campaign_id, selected.id)
