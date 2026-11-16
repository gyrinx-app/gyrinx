"""Bounded schedule reads and the display contract for campaign planning."""

from dataclasses import asdict, dataclass
from datetime import date
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Max, OuterRef, Q, Subquery
from django.urls import reverse

from n26.core import schedule as s
from n26.core.cycle_data import steps_from_data
from n26.core.cycles import calendar_for_timeline, with_cycle_activity
from n26.core.models import (
    Campaign,
    CampaignCycle,
    CampaignPhase,
    CampaignPhaseOccurrence,
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


def _phase_end(plan, next_position, phase_id, *, saved_count=None):
    """Find the end of the next generated block without expanding the pattern."""
    projected = s.project(
        s.PlanContinuation(plan, next_position, saved_count=saved_count), limit=1
    )
    if not projected:
        return (
            saved_count + 1 if saved_count is not None else plan.order_for(plan.length)
        ), None
    first = projected[0]
    if first.phase_id != phase_id:
        return first.order, first.phase_id
    index = next(
        i for i, step in enumerate(plan.steps) if step.id == first.source.step_id
    )
    boundary = first.order + plan.steps[index].count - first.source.offset
    following = index + 1
    if following < len(plan.steps):
        return boundary, plan.steps[following].phase_id
    if plan.mode == "repeating":
        return boundary, plan.steps[0].phase_id
    return boundary, None


def dashboard_summary(campaign, user):
    from n26 import flags

    if not flags.enabled(flags.CYCLE_TRACKING, user):
        return None
    different_phase = CampaignCycle.objects.filter(
        campaign_id=OuterRef("campaign_id"), archived=False
    ).exclude(
        Q(phase_occurrence_id=OuterRef("current_cycle__phase_occurrence_id"))
        | Q(phase_occurrence__isnull=True, phase_id=OuterRef("current_cycle__phase_id"))
    )
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
    projected = s.project(
        s.PlanContinuation(plan, header.next_position, saved_count=saved_count), limit=1
    )
    current = header.current_cycle
    complete = campaign.status == Campaign.Status.POST_CAMPAIGN
    summary = dict(
        name=current.name if current else "No current cycle",
        phase=current.phase.name if current else "",
        cycle_href=schedule_url(campaign),
        schedule_href=schedule_url(campaign),
        setup_href="",
        mode=plan.mode,
        cycle_limit=saved_count + plan.length - header.next_position
        if plan.mode == "fixed"
        else None,
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
                if saved_count > 0
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
                plan,
                header.next_position,
                str(current.phase_id),
                saved_count=saved_count,
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
        active = CampaignCycle.objects.filter(campaign=campaign, archived=False)
        counts = active.aggregate(
            current=Count("pk", filter=Q(order__lte=current.order)),
            previous=Count("pk", filter=Q(order__lte=previous)),
            boundary=Count("pk", filter=Q(order__lt=boundary))
            if header.following_phase_order is not None
            else Count("pk"),
        )
        visible_boundary = (
            counts["boundary"] + 1
            if header.following_phase_order is not None
            else boundary
        )
        summary.update(
            order=counts["current"],
            phase_position=counts["current"] - counts["previous"],
            phase_count=visible_boundary - counts["previous"] - 1
            if visible_boundary is not None
            else None,
            cycles_until_phase=visible_boundary - counts["current"]
            if next_phase and not complete
            else None,
        )
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
    occurrenceId: str = ""
    moveHref: str = ""
    duplicateHref: str = ""


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
        .select_related(
            "active_plan", "current_cycle__phase", "current_cycle__phase_occurrence"
        )
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
    occurrences = list(
        CampaignPhaseOccurrence.objects.filter(campaign=campaign, archived=False)
        .select_related("phase")
        .order_by("position", "id")
    )
    plan = s.Plan(
        str(header.active_plan_id),
        header.active_plan.mode,
        steps_from_data(header.active_plan.steps),
        header.active_plan.starts_after_order,
        header.active_plan.start_position,
    )
    active_cycles = CampaignCycle.objects.filter(campaign=campaign, archived=False)
    distribution = active_cycles.aggregate(count=Count("pk"), last=Max("order"))
    linked_definitions = {str(o.phase_id) for o in occurrences}
    planned_definitions = {step.phase_id for step in plan.steps}
    needs_adoption = (
        (distribution["last"] or 0) != distribution["count"]
        or any(o.position != number for number, o in enumerate(occurrences, 1))
        or any(
            str(phase.pk) not in linked_definitions | planned_definitions
            for phase in phases
        )
        or active_cycles.filter(
            Q(phase_occurrence__isnull=True)
            | Q(phase_occurrence__archived=True)
            | ~Q(phase_id=F("phase_occurrence__phase_id"))
        ).exists()
    )
    metadata = None
    if needs_adoption:
        from n26.core.cycles import _load_locked

        metadata = _load_locked(campaign)
        by_phase = {str(phase.pk): phase for phase in phases}
        occurrences = [
            CampaignPhaseOccurrence(
                id=o.id,
                campaign=campaign,
                phase=by_phase[o.phase_id],
                position=o.position,
                continues_pattern=o.continues_pattern,
            )
            for o in metadata.occurrences
            if not o.archived
        ]
    adopted_cycles = {c.id: c for c in metadata.cycles} if metadata else {}
    by_occurrence = {str(o.pk): o for o in occurrences}

    def adopt_cycle(cycle):
        if cycle is not None and (adopted := adopted_cycles.get(str(cycle.pk))):
            cycle.order = adopted.order
            cycle.phase_occurrence = by_occurrence[adopted.occurrence_id]
        return cycle

    adopt_cycle(current)
    current_order = current.order if current else 0
    last_recorded = (
        with_cycle_activity(
            CampaignCycle.objects.filter(campaign=campaign, archived=False)
        )
        .filter(has_activity=True)
        .select_related("phase_occurrence")
        .order_by("-order")
        .first()
    )
    adopt_cycle(last_recorded)
    frontier = max(current_order, last_recorded.order if last_recorded else 0)
    frontier_block = max(
        current.phase_occurrence.position
        if current and current.phase_occurrence_id
        else 0,
        last_recorded.phase_occurrence.position
        if last_recorded and last_recorded.phase_occurrence_id
        else 0,
    )
    block_counts = {
        str(item["phase_occurrence_id"]): item
        for item in CampaignCycle.objects.filter(campaign=campaign, archived=False)
        .values("phase_occurrence_id")
        .annotate(
            count=Count("id"),
            last=Max("order"),
            first=Max("order", filter=Q(order__gt=frontier)),
        )
    }
    if metadata is not None:
        block_counts = {}
        for cycle in metadata.cycles:
            if cycle.archived:
                continue
            item = block_counts.setdefault(cycle.occurrence_id, {"count": 0, "last": 0})
            item["count"] += 1
            item["last"] = max(item["last"], cycle.order)
            if cycle.order > frontier:
                item["first"] = max(item.get("first", 0), cycle.order)
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
    adopt_cycle(focus)
    anchor = focus.order if focus else current_order or 1
    ordinal = (
        sum(not c.archived and c.order <= anchor for c in metadata.cycles)
        if metadata is not None
        else CampaignCycle.objects.filter(
            campaign=campaign, archived=False, order__lte=anchor
        ).count()
    )
    number = page or (max(ordinal, 1) - 1) // SAVED_PAGE_SIZE + 1
    selected = saved.get_page(number)
    rows = []
    for index, cycle in enumerate(selected, start=1):
        adopt_cycle(cycle)
        key = str(cycle.pk)
        visible_order = (selected.number - 1) * SAVED_PAGE_SIZE + index
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
                cycle.custom_name or f"Cycle {visible_order}",
                visible_order,
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
                if manage and cycle.order > frontier
                else "",
                occurrenceId=str(cycle.phase_occurrence_id)
                if cycle.phase_occurrence_id
                else "",
                moveHref=editor_url(campaign, "move-cycle", cycle=key)
                if manage and cycle.order > frontier
                else "",
                duplicateHref=editor_url(campaign, "duplicate-cycle", cycle=key)
                if manage
                else "",
            )
        )
    projected = s.project(
        s.PlanContinuation(
            plan,
            header.next_position,
            calendar_for_timeline(
                campaign, header.date_settings, saved_count=saved.count
            ),
            saved.count,
        ),
        limit=preview,
    )
    preview_blocks = []
    occurrence_names = {str(o.pk): o for o in occurrences}
    last_occurrence = occurrences[-1] if occurrences else None
    source_blocks = set()
    if last_occurrence is not None and last_occurrence.continues_pattern:
        source_blocks = {
            (str(plan_id), repetition, step)
            for plan_id, repetition, step in CampaignCycle.objects.filter(
                campaign=campaign,
                phase_occurrence_id=last_occurrence.pk,
                source_plan__isnull=False,
            )
            .exclude(customized_fields__contains=["occurrence_id"])
            .values_list("source_plan_id", "repetition", "source_step")
            .distinct()
        }

    if metadata is not None and last_occurrence is not None:
        source_blocks = {
            s._source_block(c)
            for c in metadata.cycles
            if c.occurrence_id == str(last_occurrence.pk)
            and c.source.position is not None
            and "occurrence_id" not in c.customized_fields
        }

    def preview_block(cycle):
        block = last_occurrence
        matches = block is not None and s._can_continue_occurrence(
            plan=plan,
            next_position=header.next_position,
            occurrence=s.PhaseOccurrence(
                str(block.pk),
                str(block.phase_id),
                block.position,
                continues_pattern=block.continues_pattern,
            ),
            continuation_occurrence_id=str(header.continuation_occurrence_id)
            if header.continuation_occurrence_id
            else None,
            source_blocks=source_blocks,
            source=cycle.source,
        )
        key = (
            str(block.pk)
            if matches
            else f"preview-{cycle.source.position.plan_id}-{cycle.source.repetition}-{cycle.source.step_id}"
        )
        return key, str(block.phase_id) if matches else cycle.phase_id

    for cycle in projected:
        block_id, display_phase = preview_block(cycle)
        if block_id not in occurrence_names and not any(
            item[0] == block_id for item in preview_blocks
        ):
            preview_blocks.append((block_id, display_phase))
    if not selected.has_next():
        for cycle in projected:
            block_id, display_phase = preview_block(cycle)
            rows.append(
                CycleLine(
                    f"projected-{cycle.source.position.index}",
                    cycle.name,
                    cycle.order,
                    display_phase,
                    phase_names[display_phase],
                    "Projected",
                    cycle.starts_on.isoformat() if cycle.starts_on else "",
                    cycle.ends_on.isoformat() if cycle.ends_on else "",
                    "",
                    "",
                    "",
                    "",
                    occurrenceId=block_id,
                )
            )
    phase_display = []
    for occurrence in occurrences:
        phase = occurrence.phase
        key = str(occurrence.pk)
        counts = block_counts.get(key, {})
        editable = (
            bool(counts.get("first"))
            or not counts
            and occurrence.position > frontier_block
        )
        structural = occurrence.position > frontier_block
        phase_display.append(
            {
                "id": key,
                "phaseId": str(phase.pk),
                "number": occurrence.position,
                "name": phase.name,
                "description": phase.description,
                "effects": phase.effects,
                "rewards": phase.rewards,
                "count": counts.get("count", 0),
                "editHref": editor_url(campaign, "phase", phase=key)
                if manage and editable
                else "",
                "duplicateHref": editor_url(campaign, "duplicate-phase", phase=key)
                if manage
                else "",
                "deleteHref": editor_url(campaign, "delete-phase", phase=key)
                if manage and structural
                else "",
                "moveHref": editor_url(campaign, "move-phase", phase=key)
                if manage and structural
                else "",
                "addCycleHref": editor_url(campaign, "add-cycle", phase=key)
                if manage
                and (
                    counts.get("last", 0) >= frontier
                    and bool(counts)
                    or not counts
                    and occurrence.position > frontier_block
                )
                else "",
                "addPhaseHref": editor_url(campaign, "add-phase", after=key)
                if manage and occurrence.position >= frontier_block
                else "",
            }
        )
    by_definition = {str(phase.pk): phase for phase in phases}
    for number, (key, phase_id) in enumerate(
        preview_blocks, start=len(occurrences) + 1
    ):
        phase = by_definition[phase_id]
        phase_display.append(
            {
                "id": key,
                "phaseId": phase_id,
                "number": number,
                "name": phase.name,
                "description": phase.description,
                "effects": phase.effects,
                "rewards": phase.rewards,
                "count": 0,
                "generated": True,
                "editHref": "",
                "duplicateHref": "",
                "deleteHref": "",
            }
        )
    phase_display = tuple(phase_display)

    actions = {
        "plan": editor_url(campaign, "plan"),
        "addPhase": editor_url(campaign, "add-phase"),
    }
    if plan.mode == "repeating":
        actions["pattern"] = editor_url(campaign, "pattern")
        actions["planCycles"] = editor_url(campaign, "plan-cycles")
    has_cycles = bool(saved.count or projected)
    if campaign.status == "pre_campaign" and has_cycles:
        actions["transition"] = editor_url(campaign, "start")
        actions["transitionLabel"] = "Start campaign"
    elif campaign.status == "in_progress" and current is None and has_cycles:
        actions["transition"] = editor_url(campaign, "start")
        actions["transitionLabel"] = (
            "Start cycle" if saved.count > 0 else "Start first cycle"
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
    continuation = saved.count + (len(projected) if not selected.has_next() else 0)
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
