"""Bounded schedule reads and the display contract for campaign planning."""

from dataclasses import asdict, dataclass
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Exists, Max, OuterRef, Q
from django.urls import reverse

from n26.core import schedule as s
from n26.core.cycle_data import calendar_from_data, steps_from_data
from n26.core.models import (
    Campaign,
    CampaignCycle,
    CampaignCycleTransition,
    CampaignPhase,
    CampaignPlan,
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


def dashboard_summary(campaign, user):
    from n26 import flags

    if not flags.enabled(flags.CYCLE_TRACKING, user):
        return None
    header = (
        CampaignSchedule.objects.filter(campaign=campaign)
        .select_related("current_cycle__phase")
        .first()
    )
    if header is None:
        if campaign.owner_id != user.pk:
            return None
        return DashboardCycles(
            "", "", "", schedule_url(campaign), editor_url(campaign, "setup")
        )
    if header.current_cycle is None:
        return DashboardCycles(
            "No current cycle", "", schedule_url(campaign), schedule_url(campaign), ""
        )
    return DashboardCycles(
        header.current_cycle.name,
        header.current_cycle.phase.name,
        reverse("n26-campaign-cycle", args=[campaign.pk, header.current_cycle_id]),
        schedule_url(campaign),
        "",
    )


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
    dateSettingsRequired: bool = False


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
        CampaignPhase.objects.filter(campaign=campaign)
        .annotate(
            saved_count=Count("cycles"),
            used_in_history=Exists(
                CampaignCycleTransition.objects.filter(campaign=campaign).filter(
                    Q(previous_phase_id=OuterRef("pk"))
                    | Q(current_phase_id=OuterRef("pk"))
                )
            ),
        )
        .order_by("created", "id")
    )
    phase_names = {str(phase.pk): phase.name for phase in phases}
    plans = list(CampaignPlan.objects.filter(campaign=campaign).only("steps"))
    used = {step["phase_id"] for plan in plans for step in plan.steps}
    saved = Paginator(
        CampaignCycle.objects.filter(campaign=campaign)
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
    number = page or ((focus.order if focus else current_order or 1) - 1) // 50 + 1
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
                )
            )
    phase_display = tuple(
        {
            "id": str(phase.pk),
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
            and not phase.saved_count
            and not phase.used_in_history
            and str(phase.pk) not in used
            else "",
        }
        for phase in phases
    )
    actions = {
        "plan": editor_url(campaign, "plan"),
    }
    if campaign.status == "pre_campaign":
        actions["transition"] = editor_url(campaign, "start")
        actions["transitionLabel"] = "Start campaign"
    elif campaign.status == "in_progress" and current is None:
        actions["transition"] = editor_url(campaign, "start")
        actions["transitionLabel"] = "Start first cycle"
    elif campaign.status == "in_progress":
        has_following = current.order < saved.count or bool(projected)
        action = "advance" if has_following else "finish"
        actions["transition"] = editor_url(campaign, action)
        actions["transitionLabel"] = (
            "Advance cycle" if has_following else "Finish campaign"
        )
    continuation = saved.count + (len(projected) if not selected.has_next() else 0)
    following_position = header.next_position + len(projected)
    has_continuation = not selected.has_next() and (
        plan.mode == "repeating" or following_position < plan.length
    )
    return ScheduleDisplay(
        **common,
        configured=True,
        dateSettingsRequired=not header.date_settings,
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
