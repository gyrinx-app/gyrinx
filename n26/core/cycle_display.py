"""Bounded schedule reads and the display contract for campaign planning."""

from dataclasses import asdict, dataclass
from datetime import date
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, OuterRef, Q, Subquery
from django.urls import reverse

from n26.core import schedule as s
from n26.core.cycle_data import calendar_from_data, steps_from_data
from n26.core.models import (
    Campaign,
    CampaignCycle,
    CampaignPhase,
    CampaignSchedule,
)

SAVED_PAGE_SIZE = 50


def schedule_url(campaign):
    return reverse("n26-campaign-schedule", args=[campaign.pk])


def editor_url(campaign, action, **query):
    url = reverse("n26-cycle-editor", args=[campaign.pk, action])
    return url + ("?" + urlencode(query) if query else "")


@dataclass(frozen=True)
class DashboardCycles:
    name: str
    phase: str
    cycle_href: str
    schedule_href: str
    setup_href: str
    phase_description: str = ""
    cycle_description: str = ""
    order: int | None = None
    cycle_limit: int | None = None
    phase_position: int = 0
    phase_count: int | None = None
    next_phase: str = ""
    cycles_until_phase: int | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    mode: str = ""
    complete: bool = False
    action_href: str = ""
    action_label: str = ""


def _phase_end(plan, next_position, phase_id):
    """Find the next phase boundary in O(steps), including an endless same-phase pattern."""
    projected = s.project(s.PlanContinuation(plan, next_position), limit=1)
    if not projected:
        return plan.order_for(plan.length), None
    first = projected[0]
    if first.phase_id != phase_id:
        return first.order, first.phase_id
    index = next(
        i for i, step in enumerate(plan.steps) if step.id == first.source.step_id
    )
    boundary = first.order + plan.steps[index].count - first.source.offset
    following = plan.steps[index + 1 :]
    if plan.mode == "repeating":
        following += plan.steps[: index + 1]
    for step in following:
        if step.phase_id != phase_id:
            return boundary, step.phase_id
        boundary += step.count
    return (None, None) if plan.mode == "repeating" else (boundary, None)


def dashboard_summary(campaign, user):
    from n26 import flags

    if not flags.enabled(flags.CYCLE_TRACKING, user):
        return None
    different_phase = CampaignCycle.objects.filter(
        campaign_id=OuterRef("campaign_id"), archived=False
    ).exclude(phase_id=OuterRef("current_cycle__phase_id"))
    before = different_phase.filter(
        order__lt=OuterRef("current_cycle__order")
    ).order_by("-order")
    after = different_phase.filter(order__gt=OuterRef("current_cycle__order")).order_by(
        "order"
    )
    header = (
        CampaignSchedule.objects.filter(campaign=campaign)
        .select_related("active_plan", "current_cycle__phase")
        .annotate(
            previous_phase_order=Subquery(before.values("order")[:1]),
            following_phase_order=Subquery(after.values("order")[:1]),
            following_phase_name=Subquery(after.values("phase__name")[:1]),
        )
        .first()
    )
    manage = campaign.owner_id == user.pk
    if header is None:
        if not manage:
            return None
        return DashboardCycles(
            "", "", "", schedule_url(campaign), editor_url(campaign, "setup")
        )
    revision = header.active_plan
    plan = s.Plan(
        str(revision.pk),
        revision.mode,
        steps_from_data(revision.steps),
        revision.starts_after_order,
        revision.start_position,
    )
    saved_count = CampaignCycle.objects.filter(
        campaign=campaign, archived=False
    ).count()
    projected = s.project(s.PlanContinuation(plan, header.next_position), limit=1)
    current = header.current_cycle
    complete = campaign.status == Campaign.Status.POST_CAMPAIGN
    summary = dict(
        name=current.name if current else "No current cycle",
        phase=current.phase.name if current else "",
        cycle_href=schedule_url(campaign),
        schedule_href=schedule_url(campaign),
        setup_href="",
        mode=plan.mode,
        cycle_limit=plan.order_for(plan.length) - 1 if plan.mode == "fixed" else None,
        complete=complete,
    )
    if manage and not complete:
        if (campaign.status == Campaign.Status.PRE_CAMPAIGN or current is None) and (
            saved_count or projected
        ):
            summary.update(
                action_href=editor_url(campaign, "start"),
                action_label="Start campaign"
                if campaign.status == Campaign.Status.PRE_CAMPAIGN
                else "Start cycle"
                if plan.order_for(header.next_position) > 1
                else "Start first cycle",
            )
        elif current:
            following = CampaignCycle.objects.filter(
                campaign=campaign, archived=False, order__gt=current.order
            ).exists() or bool(projected)
            summary.update(
                action_href=editor_url(campaign, "advance" if following else "finish"),
                action_label="End cycle" if following else "Finish campaign",
            )
    if current:
        previous = header.previous_phase_order or 0
        boundary = header.following_phase_order
        next_phase = header.following_phase_name or ""
        if boundary is None:
            boundary, next_id = _phase_end(
                plan, header.next_position, str(current.phase_id)
            )
            if next_id:
                next_phase = (
                    CampaignPhase.objects.filter(campaign=campaign, pk=next_id)
                    .values_list("name", flat=True)
                    .get()
                )
        summary.update(
            phase_description=current.phase.description,
            cycle_description=current.description,
            order=current.order,
            phase_position=current.order - previous,
            phase_count=boundary - previous - 1 if boundary is not None else None,
            next_phase=next_phase if not complete else "",
            cycles_until_phase=boundary - current.order
            if next_phase and not complete
            else None,
            starts_on=current.starts_on,
            ends_on=current.ends_on,
        )
    if current:
        removed = CampaignCycle.objects.filter(campaign=campaign, archived=True)
        summary["phase_position"] -= removed.filter(
            order__gt=previous, order__lte=current.order
        ).count()
        if summary["phase_count"] is not None:
            summary["phase_count"] -= removed.filter(
                order__gt=previous, order__lt=boundary
            ).count()
        if summary["cycles_until_phase"] is not None:
            summary["cycles_until_phase"] -= removed.filter(
                order__gt=current.order, order__lt=boundary
            ).count()
    return DashboardCycles(**summary)


@dataclass(frozen=True)
class CycleLine:
    key: str
    name: str
    order: int
    phaseId: str
    phaseName: str
    state: str
    startsOn: str
    endsOn: str
    description: str
    effects: str
    editHref: str
    href: str
    startedAt: str = ""
    endedAt: str = ""
    deleteHref: str = ""


@dataclass(frozen=True)
class ScheduleDisplay:
    campaignName: str
    campaignHref: str
    scheduleHref: str
    canManage: bool
    configured: bool
    status: str
    currentName: str
    currentPhase: str
    currentPhaseId: str
    rows: tuple[CycleLine, ...]
    phases: tuple[dict, ...]
    plan: dict | None
    actions: dict
    previousHref: str
    nextHref: str
    moreHref: str
    focusId: str


def build(campaign, user, *, page=None, preview=12, focus=None):
    with transaction.atomic():
        fresh = Campaign.objects.select_for_update(no_key=True).get(pk=campaign.pk)
        return _build_locked(fresh, user, page=page, preview=preview, focus=focus)


def _build_locked(campaign, user, *, page, preview, focus):
    base = schedule_url(campaign)
    manage = campaign.owner_id == user.pk
    header = (
        CampaignSchedule.objects.filter(campaign=campaign)
        .select_related("active_plan", "current_cycle__phase")
        .first()
    )
    common = dict(
        campaignName=campaign.name,
        campaignHref=reverse("n26-campaign", args=[campaign.pk]),
        scheduleHref=base,
        canManage=manage,
        status=campaign.get_status_display(),
        focusId=str(focus.pk) if focus else "",
    )
    if header is None:
        return ScheduleDisplay(
            **common,
            configured=False,
            currentName="",
            currentPhase="",
            currentPhaseId="",
            rows=(),
            phases=(),
            plan=None,
            actions={"setup": editor_url(campaign, "setup")} if manage else {},
            previousHref="",
            nextHref="",
            moreHref="",
        )
    current = header.current_cycle
    current_order = current.order if current else 0
    phases = list(
        CampaignPhase.objects.filter(campaign=campaign, archived=False)
        .annotate(saved_count=Count("cycles", filter=Q(cycles__archived=False)))
        .order_by("created", "id")
    )
    phase_names = {str(phase.pk): phase.name for phase in phases}
    saved = Paginator(
        CampaignCycle.objects.filter(campaign=campaign, archived=False)
        .annotate(
            actual_start=Max(
                "starting_transitions__occurred_at",
                filter=Q(starting_transitions__kind__in=("started", "advanced")),
            ),
            actual_end=Max(
                "ending_transitions__occurred_at",
                filter=Q(ending_transitions__kind__in=("advanced", "finished")),
            ),
        )
        .order_by("order"),
        SAVED_PAGE_SIZE,
    )
    anchor = focus.order if focus else current_order or 1
    ordinal = CampaignCycle.objects.filter(
        campaign=campaign, archived=False, order__lte=anchor
    ).count()
    number = page or (max(ordinal, 1) - 1) // SAVED_PAGE_SIZE + 1
    selected = saved.get_page(number)
    rows = []
    for cycle in selected:
        key = str(cycle.pk)
        state = (
            "Current"
            if current and cycle.pk == current.pk
            else "Past"
            if cycle.order < current_order
            else "Saved future"
        )
        rows.append(
            CycleLine(
                key,
                cycle.name,
                cycle.order,
                str(cycle.phase_id),
                phase_names[str(cycle.phase_id)],
                state,
                cycle.starts_on.isoformat() if cycle.starts_on else "",
                cycle.ends_on.isoformat() if cycle.ends_on else "",
                cycle.description,
                cycle.effects,
                editor_url(campaign, "cycle", cycle=key) if manage else "",
                reverse("n26-campaign-cycle", args=[campaign.pk, cycle.pk]),
                cycle.actual_start.isoformat() if cycle.actual_start else "",
                cycle.actual_end.isoformat() if cycle.actual_end else "",
                deleteHref=editor_url(campaign, "delete-cycle", cycle=key)
                if manage
                else "",
            )
        )
    plan = s.Plan(
        str(header.active_plan_id),
        header.active_plan.mode,
        steps_from_data(header.active_plan.steps),
        header.active_plan.starts_after_order,
        header.active_plan.start_position,
    )
    projected = s.project(
        s.PlanContinuation(
            plan, header.next_position, calendar_from_data(header.date_settings)
        ),
        limit=preview,
    )
    if not selected.has_next():
        for cycle in projected:
            rows.append(
                CycleLine(
                    f"projected-{cycle.source.position.index}",
                    cycle.name,
                    cycle.order,
                    cycle.phase_id,
                    phase_names[cycle.phase_id],
                    "Projected",
                    cycle.starts_on.isoformat() if cycle.starts_on else "",
                    cycle.ends_on.isoformat() if cycle.ends_on else "",
                    "",
                    "",
                    editor_url(
                        campaign,
                        "cycle",
                        plan=plan.id,
                        position=cycle.source.position.index,
                    )
                    if manage
                    else "",
                    "",
                    deleteHref=editor_url(
                        campaign,
                        "delete-cycle",
                        plan=plan.id,
                        position=cycle.source.position.index,
                    )
                    if manage
                    else "",
                )
            )
    phase_display = tuple(
        {
            "id": str(phase.pk),
            "number": number,
            "name": phase.name,
            "description": phase.description,
            "effects": phase.effects,
            "rewards": phase.rewards,
            "count": phase.saved_count,
            "editHref": editor_url(campaign, "phase", phase=str(phase.pk))
            if manage
            else "",
            "duplicateHref": editor_url(
                campaign, "duplicate-phase", phase=str(phase.pk)
            )
            if manage
            else "",
            "deleteHref": editor_url(campaign, "delete-phase", phase=str(phase.pk))
            if manage
            else "",
        }
        for number, phase in enumerate(phases, start=1)
    )
    actions = {
        "plan": editor_url(campaign, "plan"),
        "addPhase": editor_url(campaign, "add-phase"),
    }
    has_cycles = bool(saved.count or projected)
    if campaign.status == "pre_campaign" and has_cycles:
        actions["transition"] = editor_url(campaign, "start")
        actions["transitionLabel"] = "Start campaign"
    elif campaign.status == "in_progress" and current is None and has_cycles:
        actions["transition"] = editor_url(campaign, "start")
        actions["transitionLabel"] = (
            "Start cycle"
            if plan.order_for(header.next_position) > 1
            else "Start first cycle"
        )
    elif campaign.status == "in_progress" and current is not None:
        has_following = CampaignCycle.objects.filter(
            campaign=campaign, archived=False, order__gt=current.order
        ).exists() or bool(projected)
        action = "advance" if has_following else "finish"
        actions["transition"] = editor_url(campaign, action)
        actions["transitionLabel"] = (
            "Advance cycle" if has_following else "Finish campaign"
        )
    continuation = (
        plan.order_for(header.next_position)
        - 1
        + (len(projected) if not selected.has_next() else 0)
    )
    following_position = header.next_position + len(projected)
    has_continuation = not selected.has_next() and (
        plan.mode == "repeating" or following_position < plan.length
    )
    return ScheduleDisplay(
        **common,
        configured=True,
        currentName=current.name if current else "No current cycle",
        currentPhase=current.phase.name if current else "",
        currentPhaseId=str(current.phase_id) if current else "",
        rows=tuple(rows),
        phases=phase_display,
        plan={
            "mode": plan.mode,
            "steps": [
                asdict(step)
                for step in s.editable_steps(
                    s.PlanContinuation(plan, following_position)
                )
            ],
            "startsAfter": f"Cycle {continuation}",
            "nextPosition": header.next_position,
        }
        if has_continuation
        else None,
        actions=actions if manage else {},
        previousHref=base
        + "?"
        + urlencode({"page": selected.previous_page_number(), "preview": preview})
        if selected.has_previous()
        else "",
        nextHref=base
        + "?"
        + urlencode({"page": selected.next_page_number(), "preview": preview})
        if selected.has_next()
        else "",
        moreHref=base
        + "?"
        + urlencode({"page": selected.number, "preview": min(preview + 12, 100)})
        if not selected.has_next() and preview < 100 and len(projected) == preview
        else "",
    )
