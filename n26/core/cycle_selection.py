"""Bounded cycle choices, dates and adjacent-cycle navigation for battle forms."""

from django.core.paginator import Paginator
from django.db import transaction

from n26.core import schedule as s
from n26.core.cycle_data import (
    calendar_from_data,
    ref_data,
    ref_from_data,
    steps_from_data,
)
from n26.core.fields import to_ulid
from n26.core.models import Campaign, CampaignCycle, CampaignSchedule


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
        from n26.core.cycles import MAX_PREFIX

        current = header.current_cycle
        current_order = current.order if current else 0
        plan = s.Plan(
            str(header.active_plan_id),
            header.active_plan.mode,
            steps_from_data(header.active_plan.steps),
            header.active_plan.starts_after_order,
            header.active_plan.start_position,
        )
        last_position = header.next_position + MAX_PREFIX
        if plan.mode == "fixed":
            last_position = min(last_position, plan.length)
        last_order = plan.order_for(last_position) - 1
        anchor = current_order
        retained = selected_saved = None
        try:
            target = ref_from_data(selected) if selected is not None else None
            if isinstance(target, s.ProjectedCycleRef):
                retained = (
                    CampaignCycle.objects.filter(
                        campaign=campaign,
                        source_plan_id=to_ulid(target.position.plan_id),
                        source_position=target.position.index,
                    )
                    .select_related("phase")
                    .first()
                )
                if retained:
                    anchor = retained.order
                elif (
                    target.position.plan_id == plan.id
                    and header.next_position <= target.position.index < last_position
                ):
                    anchor = plan.order_for(target.position.index)
            elif isinstance(target, s.SavedCycleRef):
                selected_saved = (
                    header.current_cycle
                    if target.cycle_id == str(header.current_cycle_id)
                    else CampaignCycle.objects.filter(
                        campaign=campaign, pk=to_ulid(target.cycle_id)
                    )
                    .select_related("phase")
                    .first()
                )
                if selected_saved:
                    anchor = selected_saved.order
        except ValueError, s.ScheduleError:
            # Invalid retained selections do not become choices from another campaign.
            pass
        saved = Paginator(
            CampaignCycle.objects.filter(campaign=campaign)
            .select_related("phase")
            .order_by("order"),
            50,
        )
        chosen = saved.get_page(page or (min(anchor, saved.count) - 1) // 50 + 1)
        visible = list(chosen)
        visible_orders = {cycle.order for cycle in visible}
        for extra in (selected_saved, retained):
            if extra and extra.order not in visible_orders:
                visible.append(extra)
                visible_orders.add(extra.order)
        missing = {
            order
            for order in (anchor - 1, anchor + 1)
            if 1 <= order <= saved.count and order not in visible_orders
        }
        if missing:
            visible.extend(
                CampaignCycle.objects.filter(
                    campaign=campaign, order__in=missing
                ).select_related("phase")
            )
        choices = [
            _choice(
                ref_data(s.SavedCycleRef(str(cycle.pk))),
                cycle.order,
                cycle.name,
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
                    retained.order,
                    retained.name,
                    retained.phase.name,
                    current_order,
                    starts_on=retained.starts_on,
                    ends_on=retained.ends_on,
                    hint="This cycle is already saved. Retrying confirms the original battle save.",
                )
            )
        phase_names = {
            str(key): name
            for key, name in campaign.cycle_phases.values_list("id", "name")
        }
        start = max(header.next_position, plan.position_for(anchor) - 1)
        limit = min(12, last_position - start)
        if limit > 0:
            for cycle in s.project(
                s.PlanContinuation(
                    plan, start, calendar_from_data(header.date_settings)
                ),
                limit=limit,
            ):
                choices.append(
                    _choice(
                        ref_data(cycle.ref),
                        cycle.order,
                        cycle.name,
                        phase_names[cycle.phase_id],
                        current_order,
                        starts_on=cycle.starts_on,
                        ends_on=cycle.ends_on,
                    )
                )
        return {
            "configured": True,
            "current": current.name if current else "No current cycle",
            "currentValue": ref_data(s.SavedCycleRef(str(header.current_cycle_id)))
            if current
            else None,
            "lastOrder": last_order,
            "choices": sorted(choices, key=lambda choice: choice["order"]),
            "previous": chosen.previous_page_number()
            if chosen.has_previous()
            else None,
            "next": chosen.next_page_number() if chosen.has_next() else None,
        }
