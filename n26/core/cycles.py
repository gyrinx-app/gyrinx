"""Atomic campaign cycle commands and their durable retry receipts.

The schedule engine calculates changes without I/O. This boundary checks access
under the campaign lock, recognises exact retries and persists each change with
its transition and notification deliveries. Battle and action writers can resolve
a cycle inside their existing campaign transaction without advancing it.
"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from uuid import UUID

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from ulid import ULID

from n26 import flags
from n26.core import schedule as s
from n26.core.campaign_permissions import may_record_campaign
from n26.core.campaigns import campaign_operation
from n26.core.cycle_data import (
    calendar_data,
    calendar_from_data,
    cycle_details_data,
    ref_data,
    rewards_from_data,
    steps_from_data,
    template_data,
    template_from_data,
)
from n26.core.fields import to_ulid
from n26.core.models import (
    Battle,
    Campaign,
    CampaignCycle,
    CampaignCycleCommand,
    CampaignCycleTransition,
    CampaignEvent,
    CampaignPhase,
    CampaignPlan,
    CampaignSchedule,
    CampaignScheduleTemplate,
)
from n26.core.operations import Refusal
from n26.write_pause import guarded_write

DEFAULT_TEMPLATE_KEY = "occupation-and-takeover"
MAX_PREFIX = 1000


class CycleConflict(Refusal):
    """The submitted baseline no longer describes the campaign schedule."""


class CycleKeyConflict(CycleConflict):
    """A command key belongs to different input, rather than a stale baseline."""


@dataclass(frozen=True)
class CommandResult:
    revision: int
    cycle_id: str | None
    transition_id: str | None
    replayed: bool = False


def _new_id():
    return str(ULID())


def templates_for(user):
    return CampaignScheduleTemplate.objects.filter(
        Q(owner__isnull=True) | Q(owner=user)
    ).order_by("name", "id")


def _template_for(actor, identity):
    try:
        identity = to_ulid(identity)
    except ValueError:
        raise Refusal("Select one of your schedule templates.") from None
    template = templates_for(actor).filter(pk=identity).first()
    if template is None:
        raise Refusal("Select one of your schedule templates.")
    return template


def _access(act, *, manage=True):
    actor, campaign = act.actor, act.campaign
    if not flags.enabled(flags.CYCLE_TRACKING, actor):
        raise Refusal("Cycle tracking is not available to this account.")
    if campaign.archived or not may_record_campaign(campaign, actor):
        raise Refusal("You cannot change this campaign's cycles.")
    if manage and campaign.owner_id != actor.pk:
        raise Refusal("Only the arbitrator can change the campaign schedule.")


def load(campaign):
    """Read one consistent snapshot, serialised with campaign writers."""
    with transaction.atomic():
        fresh = Campaign.objects.select_for_update(no_key=True).get(pk=campaign.pk)
        return _load_locked(fresh)


def _load_locked(campaign):
    """Read a bounded-query snapshot while the caller holds the campaign lock."""
    header = (
        CampaignSchedule.objects.filter(campaign=campaign)
        .select_related("active_plan")
        .first()
    )
    if header is None:
        return None
    phases = tuple(
        s.Phase(
            str(p.pk),
            s.PhaseDetails(
                p.name, p.description, p.effects, rewards_from_data(p.rewards)
            ),
            archived=p.archived,
        )
        for p in CampaignPhase.objects.filter(campaign=campaign).order_by(
            "created", "id"
        )
    )
    plan = s.Plan(
        str(header.active_plan_id),
        header.active_plan.mode,
        steps_from_data(header.active_plan.steps),
        header.active_plan.starts_after_order,
        header.active_plan.start_position,
    )
    cycles = tuple(
        s.Cycle(
            str(c.pk),
            c.order,
            s.CycleDetails(
                str(c.phase_id),
                c.custom_name or None,
                c.starts_on,
                c.ends_on,
                c.description,
                c.effects,
            ),
            s.CycleSource(
                s.PlannedPosition(str(c.source_plan_id), c.source_position),
                c.source_step,
                c.repetition,
                c.step_position,
            ),
            archived=c.archived,
        )
        for c in CampaignCycle.objects.filter(campaign=campaign).order_by("order")
    )
    return s.Schedule(
        str(campaign.pk),
        phases,
        plan,
        header.next_position,
        cycles,
        str(header.current_cycle_id) if header.current_cycle_id else None,
        campaign.status,
        header.revision,
        calendar=calendar_from_data(header.date_settings),
    )


def _phase_record(campaign, phase):
    return CampaignPhase(
        id=phase.id,
        campaign=campaign,
        name=phase.details.name,
        description=phase.details.description,
        effects=phase.details.effects,
        rewards=asdict(phase.details.rewards),
        archived=phase.archived,
        archived_at=timezone.now() if phase.archived else None,
    )


def _cycle_record(campaign, cycle):
    return CampaignCycle(
        id=cycle.id,
        campaign=campaign,
        phase_id=cycle.details.phase_id,
        order=cycle.order,
        custom_name=cycle.details.custom_name or "",
        starts_on=cycle.details.starts_on,
        ends_on=cycle.details.ends_on,
        description=cycle.details.description,
        effects=cycle.details.effects,
        source_plan_id=cycle.source.position.plan_id,
        source_position=cycle.source.position.index,
        source_step=cycle.source.step_id,
        repetition=cycle.source.repetition,
        step_position=cycle.source.offset,
        archived=cycle.archived,
        archived_at=timezone.now() if cycle.archived else None,
    )


def _persist(act, before, change, *, command=None, transition_id=None):
    after = change.schedule
    campaign = act.campaign
    old_phases = {p.id: p for p in before.phases} if before else {}
    new_phases = {p.id: p for p in after.phases}
    CampaignPhase.objects.bulk_create(
        [_phase_record(campaign, p) for p in after.phases if p.id not in old_phases]
    )
    changed_phases = [
        _phase_record(campaign, p)
        for p in after.phases
        if p.id in old_phases and p != old_phases[p.id]
    ]
    if changed_phases:
        for phase in changed_phases:
            phase.modified = timezone.now()
        CampaignPhase.objects.bulk_update(
            changed_phases,
            [
                "name",
                "description",
                "effects",
                "rewards",
                "archived",
                "archived_at",
                "modified",
            ],
        )
    if before is None or before.plan.id != after.plan.id:
        CampaignPlan.objects.create(
            id=after.plan.id,
            campaign=campaign,
            mode=after.plan.mode,
            starts_after_order=after.plan.starts_after_order,
            start_position=after.plan.start_position,
            steps=[asdict(step) for step in after.plan.steps],
        )
    CampaignCycle.objects.bulk_create(
        [_cycle_record(campaign, c) for c in change.created]
    )
    if change.updated:
        updated = [_cycle_record(campaign, c) for c in change.updated]
        for cycle in updated:
            cycle.modified = timezone.now()
        CampaignCycle.objects.bulk_update(
            updated,
            [
                "phase",
                "custom_name",
                "starts_on",
                "ends_on",
                "description",
                "effects",
                "archived",
                "archived_at",
                "modified",
            ],
        )
    removed = [c.id for c in (*change.created, *change.updated) if c.archived]
    if removed:
        Battle.objects.filter(campaign=campaign, cycle_id__in=removed).update(
            cycle=None, revision=F("revision") + 1, modified=timezone.now()
        )
    header_values = {
        "current_cycle_id": after.current_cycle_id,
        "active_plan_id": after.plan.id,
        "next_position": after.next_position,
        "revision": after.revision,
        "date_settings": calendar_data(after.calendar),
        "modified": timezone.now(),
    }
    if before is None:
        CampaignSchedule.objects.create(campaign=campaign, **header_values)
    elif before != after:
        CampaignSchedule.objects.filter(campaign=campaign).update(**header_values)
    if campaign.status != after.status:
        was = campaign.get_status_display()
        campaign.status = after.status
        campaign.save(update_fields=["status", "modified"])
        act.event(
            CampaignEvent.Kind.STATUS_CHANGED,
            note=f"{was} → {campaign.get_status_display()}",
        )
    if change.transition is not None:
        transition = change.transition
        previous = transition.previous_cycle
        current = transition.current_cycle
        old_phase = (
            next(p for p in before.phases if p.id == previous.details.phase_id)
            if previous is not None and before is not None
            else None
        )
        phase = new_phases[current.details.phase_id]
        record = CampaignCycleTransition.objects.create(
            id=transition_id or _new_id(),
            campaign=campaign,
            command=command,
            actor=act.actor,
            kind=transition.kind,
            previous_cycle_id=previous.id if previous else None,
            current_cycle_id=current.id,
            previous_phase_id=old_phase.id if old_phase else None,
            current_phase_id=phase.id,
            occurred_at=transition.occurred_at,
            receipt={
                "campaign": campaign.name,
                "previous_cycle": previous.name if previous else None,
                "current_cycle": current.name,
                "previous_phase": asdict(old_phase.details) if old_phase else None,
                "current_phase": asdict(phase.details),
                "enters_phase": transition.enters_phase,
            },
        )
        from n26.notifications import record_cycle_deliveries

        record_cycle_deliveries(record)
        act.event(CampaignEvent.Kind.CYCLE_TRANSITION, note=current.name)
    elif before != after:
        act.event(CampaignEvent.Kind.SCHEDULE_EDITED)


def _key(value):
    try:
        return UUID(str(value))
    except TypeError, ValueError, AttributeError:
        raise Refusal("Reload the form before saving the schedule.") from None


def _previous(act, kind, inputs, request_key):
    previous = CampaignCycleCommand.objects.filter(
        campaign=act.campaign, request_key=request_key
    ).first()
    if previous is None:
        return None
    if (
        previous.actor_id != act.actor.pk
        or previous.kind != kind
        or previous.inputs != inputs
    ):
        raise CycleKeyConflict(
            "A different change was saved from this form. Reload the page."
        )
    return CommandResult(**previous.result, replayed=True)


def _command(campaign, actor, *, kind, inputs, request_key, expected_revision, apply):
    with campaign_operation(campaign, actor=actor) as act:
        _access(act)
        key = _key(request_key)
        inputs = {**inputs, "expected_revision": expected_revision}
        previous = _previous(act, kind, inputs, key)
        if previous is not None:
            return previous
        before = _load_locked(act.campaign)
        actual_revision = before.revision if before is not None else None
        if (
            type(expected_revision) is not type(actual_revision)
            or expected_revision != actual_revision
        ):
            raise CycleConflict(
                "The schedule changed. Review the current schedule before saving."
            )
        if before is None and kind != "configure":
            raise Refusal("Set up campaign cycles before changing the schedule.")
        try:
            change, selected_id = apply(act, before)
        except s.ScheduleError as exc:
            raise Refusal(str(exc)) from exc
        transition_id = _new_id() if change.transition else None
        result = CommandResult(change.schedule.revision, selected_id, transition_id)
        command = CampaignCycleCommand.objects.create(
            campaign=act.campaign,
            actor=actor,
            request_key=key,
            kind=kind,
            inputs=inputs,
            result={k: v for k, v in asdict(result).items() if k != "replayed"},
        )
        _persist(act, before, change, command=command, transition_id=transition_id)
        return result


def configure(
    campaign,
    *,
    actor,
    template_id,
    current_position,
    mode,
    request_key,
    calendar=None,
    definition=None,
):
    def apply(act, before):
        if before is not None:
            raise Refusal("This campaign already has a cycle schedule.")
        template = _template_for(actor, template_id) if template_id else None
        if template is None and definition is None:
            raise Refusal("Add a phase and a step to your custom schedule.")
        if current_position is not None and (
            type(current_position) is not int or not 0 <= current_position < MAX_PREFIX
        ):
            raise Refusal("Select an initial cycle within the first 1,000 cycles.")
        change = s.configure(
            template_from_data(
                template.name if template else "Custom",
                definition if definition is not None else template.definition,
            ),
            campaign_id=str(campaign.pk),
            current_position=current_position,
            mode=mode,
            status=act.campaign.status,
            now=timezone.now(),
            calendar=calendar,
            new_id=_new_id,
        )
        return change, change.schedule.current_cycle_id

    return _command(
        campaign,
        actor,
        kind="configure",
        inputs={
            "template": str(template_id),
            "current_position": current_position,
            "mode": mode,
            **({"calendar": calendar_data(calendar)} if calendar is not None else {}),
            **({"definition": definition} if definition is not None else {}),
        },
        request_key=request_key,
        expected_revision=None,
        apply=apply,
    )


def _bounded_target(before, target):
    if (
        isinstance(target, s.ProjectedCycleRef)
        and target.position.plan_id == before.plan.id
    ):
        if target.position.index - before.next_position >= MAX_PREFIX:
            raise Refusal("You can save up to 1,000 projected cycles at once.")


def edit_cycle(
    campaign,
    *,
    actor,
    target,
    details,
    expected_revision,
    request_key,
    shift_later=False,
):
    def apply(act, before):
        _bounded_target(before, target)
        change = s.edit_cycle(
            before,
            target,
            details,
            now=timezone.now(),
            new_id=_new_id,
            shift_later=shift_later,
        )
        selected = s._selected(change.schedule, target)
        return change, selected.id

    return _command(
        campaign,
        actor,
        kind="edit_cycle",
        inputs={
            "target": ref_data(target),
            "details": cycle_details_data(details),
            **({"shift_later": True} if shift_later else {}),
        },
        request_key=request_key,
        expected_revision=expected_revision,
        apply=apply,
    )


def edit_phase(campaign, *, actor, phase_id, details, expected_revision, request_key):
    return _command(
        campaign,
        actor,
        kind="edit_phase",
        inputs={"phase": str(phase_id), "details": asdict(details)},
        request_key=request_key,
        expected_revision=expected_revision,
        apply=lambda act, before: (s.edit_phase(before, str(phase_id), details), None),
    )


def add_phase(campaign, *, actor, details, expected_revision, request_key):
    return _command(
        campaign,
        actor,
        kind="add_phase",
        inputs={"details": asdict(details)},
        request_key=request_key,
        expected_revision=expected_revision,
        apply=lambda act, before: (s.add_phase(before, details, new_id=_new_id), None),
    )


def duplicate_phase(campaign, *, actor, phase_id, name, expected_revision, request_key):
    return _command(
        campaign,
        actor,
        kind="duplicate_phase",
        inputs={"phase": str(phase_id), "name": name},
        request_key=request_key,
        expected_revision=expected_revision,
        apply=lambda act, before: (
            s.duplicate_phase(before, str(phase_id), name=name, new_id=_new_id),
            None,
        ),
    )


def _deletion_inputs(replacement, no_current):
    return {
        **({"replacement": ref_data(replacement)} if replacement is not None else {}),
        **({"no_current": True} if no_current else {}),
    }


def delete_cycle(
    campaign,
    *,
    actor,
    target,
    expected_revision,
    request_key,
    replacement=None,
    no_current=False,
):
    def apply(act, before):
        _bounded_target(before, target)
        if replacement is not None:
            _bounded_target(before, replacement)
        return s.delete_cycle(
            before,
            target,
            replacement=replacement,
            no_current=no_current,
            new_id=_new_id,
        ), None

    return _command(
        campaign,
        actor,
        kind="delete_cycle",
        inputs={
            "target": ref_data(target),
            **_deletion_inputs(replacement, no_current),
        },
        request_key=request_key,
        expected_revision=expected_revision,
        apply=apply,
    )


def delete_phase(
    campaign,
    *,
    actor,
    phase_id,
    expected_revision,
    request_key,
    replacement=None,
    no_current=False,
):
    def apply(act, before):
        if replacement is not None:
            _bounded_target(before, replacement)
        return s.delete_phase(
            before,
            str(phase_id),
            replacement=replacement,
            no_current=no_current,
            new_id=_new_id,
        ), None

    return _command(
        campaign,
        actor,
        kind="delete_phase",
        inputs={"phase": str(phase_id), **_deletion_inputs(replacement, no_current)},
        request_key=request_key,
        expected_revision=expected_revision,
        apply=apply,
    )


def replace_plan(
    campaign,
    *,
    actor,
    steps,
    mode,
    expected_revision,
    request_key,
    calendar=None,
    clear_calendar=False,
):
    """Plan future dates while preserving every saved cycle bound."""
    raw_steps = [asdict(step) for step in steps]

    def apply(act, before):
        dates = calendar
        if dates is not None:
            dates = replace(
                dates,
                starts_after_order=len(before.cycles),
            )
            if before.calendar is not None and (
                dates.interval == before.calendar.interval
                and dates.unit == before.calendar.unit
                and dates.starts_on
                == before.calendar.dates_for(len(before.cycles) + 1)[0]
            ):
                dates = before.calendar
        return s.replace_plan(
            before,
            steps=steps_from_data(raw_steps),
            mode=mode,
            new_id=_new_id,
            calendar=dates,
            clear_calendar=clear_calendar,
        ), None

    return _command(
        campaign,
        actor,
        kind="replace_plan",
        inputs={
            "steps": raw_steps,
            "mode": mode,
            **({"clear_calendar": True} if clear_calendar else {}),
            **({"calendar": calendar_data(calendar)} if calendar is not None else {}),
        },
        request_key=request_key,
        expected_revision=expected_revision,
        apply=apply,
    )


def apply_template(
    campaign, *, actor, template_id, mode, expected_revision, request_key
):
    def apply(act, before):
        template = _template_for(actor, template_id)
        return s.apply_template(
            before,
            template_from_data(template.name, template.definition),
            mode=mode,
            new_id=_new_id,
        ), None

    return _command(
        campaign,
        actor,
        kind="apply_template",
        inputs={"template": str(template_id), "mode": mode},
        request_key=request_key,
        expected_revision=expected_revision,
        apply=apply,
    )


def advance(campaign, *, actor, expected_current, expected_revision, request_key):
    def apply(act, before):
        if before.current_cycle_id != (
            str(expected_current) if expected_current else None
        ):
            raise CycleConflict(
                "The current cycle changed. Review the transition before advancing."
            )
        change = s.advance(before, now=timezone.now(), new_id=_new_id)
        return change, change.schedule.current_cycle_id

    return _command(
        campaign,
        actor,
        kind="advance",
        inputs={"current": str(expected_current)},
        request_key=request_key,
        expected_revision=expected_revision,
        apply=apply,
    )


def start(
    campaign, *, actor, expected_current, expected_revision, request_key, target=None
):
    def apply(act, before):
        if before.current_cycle_id != (
            str(expected_current) if expected_current else None
        ):
            raise CycleConflict("The current cycle changed. Review it before starting.")
        if target is not None:
            _bounded_target(before, target)
        change = s.start(before, now=timezone.now(), new_id=_new_id, target=target)
        return change, change.schedule.current_cycle_id

    return _command(
        campaign,
        actor,
        kind="start",
        inputs={
            "current": str(expected_current),
            **({"target": ref_data(target)} if target is not None else {}),
        },
        request_key=request_key,
        expected_revision=expected_revision,
        apply=apply,
    )


def finish(campaign, *, actor, expected_current, expected_revision, request_key):
    def apply(act, before):
        if before.current_cycle_id != (
            str(expected_current) if expected_current else None
        ):
            raise CycleConflict(
                "The current cycle changed. Review it before finishing."
            )
        change = s.finish(before, now=timezone.now())
        return change, change.schedule.current_cycle_id

    return _command(
        campaign,
        actor,
        kind="finish",
        inputs={"current": str(expected_current)},
        request_key=request_key,
        expected_revision=expected_revision,
        apply=apply,
    )


def resolve_selection(act, target):
    """Resolve within the caller's campaign operation and atomic domain write."""
    _access(act, manage=False)
    before = _load_locked(act.campaign)
    if before is None:
        raise Refusal("Set up campaign cycles before selecting one.")
    _bounded_target(before, target)
    try:
        change, selected = s._ensure_saved(before, target, new_id=_new_id)
    except s.ScheduleError as exc:
        raise Refusal(str(exc)) from exc
    _persist(act, before, change)
    return CampaignCycle.objects.get(campaign=act.campaign, pk=selected.id)


@contextmanager
def action_operation(campaign, gang, *, actor, target):
    """Select a cycle and apply an action in one campaign-before-gang transaction."""
    from n26.core.cycle_context import CycleContext
    from n26.core.operations import operation

    with campaign_operation(campaign, actor=actor) as act:
        selected = resolve_selection(act, target)
        with operation(
            gang, actor=actor, cycle_context=CycleContext.from_cycle(selected)
        ) as op:
            yield op


def status_changed(act, status):
    """Keep an opted-in schedule consistent with existing campaign status actions."""
    if not flags.enabled(flags.CYCLE_TRACKING, act.actor):
        # Status is part of a cycle edit's baseline even while cycle controls are hidden.
        CampaignSchedule.objects.filter(campaign=act.campaign).update(
            revision=F("revision") + 1
        )
        return False
    before = _load_locked(act.campaign)
    if before is None:
        return False
    _access(act)
    if status == "in_progress":
        if before.status == "pre_campaign":
            if before.current is None and (
                any(c.archived for c in before.cycles)
                or any(p.archived for p in before.phases)
            ):
                raise Refusal("Choose the cycle to start in Phases & cycles.")
            change = s.start(before, now=timezone.now(), new_id=_new_id)
        else:
            change = s.ScheduleChange(
                replace(before, status=status, revision=before.revision + 1),
                transition=s.Transition("started", None, before.current, timezone.now())
                if before.current
                else None,
            )
    elif status == "post_campaign" and before.status == "in_progress":
        change = s.finish(before, now=timezone.now())
    else:
        change = s.ScheduleChange(
            replace(before, status=status, revision=before.revision + 1)
        )
    _persist(act, before, change)
    return True


@guarded_write
def create_template(*, actor, name, definition):
    """Create a private reusable definition without changing any campaign."""
    if not flags.enabled(flags.CYCLE_TRACKING, actor):
        raise Refusal("Cycle tracking is not available to this account.")
    if not actor.is_staff:
        raise Refusal("Only content authors can create schedule templates.")
    try:
        template = template_from_data(name, definition)
    except s.ScheduleError as exc:
        raise Refusal(str(exc)) from exc
    return CampaignScheduleTemplate.objects.create(
        owner=actor, name=template.name, definition=template_data(template)
    )


def replay_template_command(
    campaign, *, actor, kind, inputs, expected_revision, request_key
):
    def refuse_new(act, before):
        raise Refusal(
            "This template action is no longer available. Review the current schedule."
        )

    return _command(
        campaign,
        actor,
        kind=kind,
        inputs=inputs,
        expected_revision=expected_revision,
        request_key=request_key,
        apply=refuse_new,
    )


def save_template(campaign, *, actor, name, expected_revision, request_key):
    def apply(act, before):
        if not actor.is_staff:
            raise Refusal("Only content authors can create schedule templates.")
        used = {step.phase_id for step in before.plan.steps}
        template = s.ScheduleTemplate(
            name,
            tuple(phase for phase in before.phases if phase.id in used),
            before.plan.steps,
        )
        create_template(actor=actor, name=name, definition=template_data(template))
        return s.ScheduleChange(before), None

    return _command(
        campaign,
        actor,
        kind="save_template",
        inputs={"name": name},
        request_key=request_key,
        expected_revision=expected_revision,
        apply=apply,
    )
