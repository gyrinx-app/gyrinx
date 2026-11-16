"""Bounded cycle choices, dates and adjacent-cycle navigation for battle forms."""

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q

from n26.core import schedule as s
from n26.core.cycle_data import (
    ref_data,
    ref_from_data,
    steps_from_data,
)
from n26.core.fields import to_ulid
from n26.core.models import (
    Campaign,
    CampaignCycle,
    CampaignPhaseOccurrence,
    CampaignSchedule,
)


def _choice(
    value, order, name, phase, current, *, starts_on=None, ends_on=None, hint=""
):
    return {
        "value": value,
        "order": order,
        "name": name,
        "phase": phase,
        "label": f"{name} · {phase}",
        "startsOn": starts_on.isoformat() if starts_on else None,
        "endsOn": ends_on.isoformat() if ends_on else None,
        "hint": hint,
        "isCurrent": order == current,
    }


def options(campaign, *, page=None, selected=None):
    with transaction.atomic():
        Campaign.objects.select_for_update(no_key=True).get(pk=campaign.pk)
        header = (
            CampaignSchedule.objects.select_related(
                "active_plan", "current_cycle__phase"
            )
            .filter(campaign=campaign)
            .first()
        )
        if header is None:
            return {
                "configured": False,
                "current": "",
                "currentValue": None,
                "lastOrder": 0,
                "choices": [],
                "previous": None,
                "next": None,
            }
        from n26.core.cycles import (
            MAX_PREFIX,
            calendar_for_timeline,
            continuation_sources,
        )

        current = header.current_cycle
        current_raw_order = current.order if current else 0
        plan = s.Plan(
            str(header.active_plan_id),
            header.active_plan.mode,
            steps_from_data(header.active_plan.steps),
            header.active_plan.starts_after_order,
            header.active_plan.start_position,
        )
        active = CampaignCycle.objects.filter(campaign=campaign, archived=False)
        counts = active.aggregate(
            total=Count("pk"),
            current=Count("pk", filter=Q(order__lte=current_raw_order)),
        )
        saved_count = counts["total"]
        current_order = counts["current"]
        last_position = header.next_position + MAX_PREFIX
        if plan.mode == "fixed":
            last_position = min(last_position, plan.length)
        last_order = saved_count + last_position - header.next_position
        anchor = current_order
        anchor_raw_order = current_raw_order
        retained = selected_saved = None
        try:
            target = ref_from_data(selected) if selected is not None else None
            if isinstance(target, s.ProjectedCycleRef):
                retained = (
                    CampaignCycle.objects.filter(
                        campaign=campaign,
                        archived=False,
                        source_plan_id=to_ulid(target.position.plan_id),
                        source_position=target.position.index,
                    )
                    .select_related("phase")
                    .first()
                )
                if retained:
                    anchor_raw_order = retained.order
                    anchor = active.filter(order__lte=retained.order).count()
                elif (
                    target.position.plan_id == plan.id
                    and header.next_position <= target.position.index < last_position
                ):
                    anchor = (
                        saved_count + target.position.index - header.next_position + 1
                    )
                    anchor_raw_order = None
            elif isinstance(target, s.SavedCycleRef):
                selected_saved = (
                    header.current_cycle
                    if target.cycle_id == str(header.current_cycle_id)
                    else CampaignCycle.objects.filter(
                        campaign=campaign, archived=False, pk=to_ulid(target.cycle_id)
                    )
                    .select_related("phase")
                    .first()
                )
                if selected_saved:
                    anchor_raw_order = selected_saved.order
                    anchor = active.filter(order__lte=selected_saved.order).count()
        except ValueError, s.ScheduleError:
            # Invalid retained selections do not become choices from another campaign.
            pass
        saved = Paginator(
            CampaignCycle.objects.filter(campaign=campaign, archived=False)
            .select_related("phase")
            .order_by("order"),
            50,
        )
        chosen = saved.get_page(page or (max(anchor, 1) - 1) // 50 + 1)
        visible = list(chosen)
        positions = {
            cycle.order: (chosen.number - 1) * 50 + index
            for index, cycle in enumerate(visible, start=1)
        }
        visible_orders = {cycle.order for cycle in visible}
        for extra in (selected_saved, retained):
            if extra and extra.order not in visible_orders:
                visible.append(extra)
                visible_orders.add(extra.order)
        adjacent = CampaignCycle.objects.filter(
            campaign=campaign, archived=False
        ).select_related("phase")
        previous_cycle = (
            adjacent.order_by("-order").first()
            if anchor_raw_order is None
            else adjacent.filter(order__lt=anchor_raw_order).order_by("-order").first()
        )
        next_cycle = (
            None
            if anchor_raw_order is None
            else adjacent.filter(order__gt=anchor_raw_order).order_by("order").first()
        )
        for extra in (previous_cycle, next_cycle):
            if extra and extra.order not in visible_orders:
                visible.append(extra)
                visible_orders.add(extra.order)
        missing = {cycle.order for cycle in visible} - positions.keys()
        if missing:
            ranks = active.aggregate(
                **{
                    f"position_{order}": Count("pk", filter=Q(order__lte=order))
                    for order in missing
                }
            )
            positions.update({order: ranks[f"position_{order}"] for order in missing})
        choices = [
            _choice(
                ref_data(s.SavedCycleRef(str(cycle.pk))),
                positions[cycle.order],
                cycle.custom_name or f"Cycle {positions[cycle.order]}",
                cycle.phase.name,
                current_order,
                starts_on=cycle.starts_on,
                ends_on=cycle.ends_on,
            )
            for cycle in visible
        ]
        if retained:
            choices.append(
                _choice(
                    selected,
                    positions[retained.order],
                    retained.custom_name or f"Cycle {positions[retained.order]}",
                    retained.phase.name,
                    current_order,
                    starts_on=retained.starts_on,
                    ends_on=retained.ends_on,
                    hint="This cycle is already saved. Retrying confirms the original battle save.",
                )
            )
        phase_names = {
            str(key): name
            for key, name in campaign.cycle_phases.filter(archived=False).values_list(
                "id", "name"
            )
        }
        tail = (
            CampaignPhaseOccurrence.objects.filter(campaign=campaign, archived=False)
            .order_by("-position")
            .first()
        )
        source_blocks = set()
        if tail is not None and tail.continues_pattern:
            source_blocks = continuation_sources(campaign, tail.pk)
        start = header.next_position + max(0, anchor - saved_count - 2)
        limit = min(12, last_position - start)
        if limit > 0:
            for cycle in s.project(
                s.PlanContinuation(
                    plan,
                    start,
                    calendar_for_timeline(
                        campaign, header.date_settings, saved_count=saved_count
                    ),
                    saved_count + start - header.next_position,
                ),
                limit=limit,
            ):
                phase_id = cycle.phase_id
                if tail is not None and s._can_continue_occurrence(
                    plan=plan,
                    next_position=header.next_position,
                    occurrence=s.PhaseOccurrence(
                        str(tail.pk),
                        str(tail.phase_id),
                        tail.position,
                        continues_pattern=tail.continues_pattern,
                    ),
                    continuation_occurrence_id=str(header.continuation_occurrence_id)
                    if header.continuation_occurrence_id
                    else None,
                    source_blocks=source_blocks,
                    source=cycle.source,
                ):
                    phase_id = str(tail.phase_id)
                choices.append(
                    _choice(
                        ref_data(cycle.ref),
                        cycle.order,
                        cycle.name,
                        phase_names[phase_id],
                        current_order,
                        starts_on=cycle.starts_on,
                        ends_on=cycle.ends_on,
                    )
                )
        first_projected_order = saved_count + 1
        previous_order = (
            anchor - 1
            if anchor > first_projected_order
            else positions[previous_cycle.order]
            if previous_cycle
            else None
        )
        next_order = (
            anchor + 1
            if anchor >= first_projected_order and anchor < last_order
            else positions[next_cycle.order]
            if next_cycle
            else first_projected_order
            if anchor < first_projected_order <= last_order
            else None
        )
        return {
            "configured": True,
            "current": (current.custom_name or f"Cycle {current_order}")
            if current
            else "No current cycle",
            "currentValue": ref_data(s.SavedCycleRef(str(header.current_cycle_id)))
            if current
            else None,
            "lastOrder": last_order,
            "adjacent": {
                "anchor": anchor,
                "previous": previous_order,
                "next": next_order,
            },
            "choices": sorted(choices, key=lambda choice: choice["order"]),
            "previous": chosen.previous_page_number()
            if chosen.has_previous()
            else None,
            "next": chosen.next_page_number() if chosen.has_next() else None,
        }
