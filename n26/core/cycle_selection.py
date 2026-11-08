"""Bounded saved-cycle choices and projected continuation for a battle form."""

from django.core.paginator import Paginator
from django.db import transaction

from n26.core import schedule as s
from n26.core.cycle_data import ref_data, steps_from_data
from n26.core.models import Campaign, CampaignCycle, CampaignSchedule


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
                "choices": [],
                "previous": None,
                "next": None,
            }
        saved = Paginator(
            CampaignCycle.objects.filter(campaign=campaign)
            .select_related("phase")
            .order_by("order"),
            50,
        )
        number = page or (header.current_cycle.order - 1) // 50 + 1
        chosen = saved.get_page(number)
        visible = list(chosen)
        if isinstance(selected, dict) and "cycle_id" in selected:
            identity = selected.get("cycle_id")
            if identity and not any(str(cycle.pk) == identity for cycle in visible):
                # Malformed and foreign IDs never become selectable options.
                from n26.core.fields import to_ulid

                try:
                    extra = (
                        CampaignCycle.objects.filter(
                            campaign=campaign, pk=to_ulid(identity)
                        )
                        .select_related("phase")
                        .first()
                    )
                except ValueError:
                    extra = None
                if extra:
                    visible.insert(0, extra)
        choices = []
        for cycle in visible:
            state = (
                "Current"
                if cycle.pk == header.current_cycle_id
                else "Past"
                if cycle.order < header.current_cycle.order
                else "Saved future"
            )
            choices.append(
                {
                    "value": ref_data(s.SavedCycleRef(str(cycle.pk))),
                    "label": f"{cycle.name} · {cycle.phase.name} · {state}",
                    "hint": "",
                    "isCurrent": cycle.pk == header.current_cycle_id,
                }
            )
        plan = s.Plan(
            str(header.active_plan_id),
            header.active_plan.mode,
            steps_from_data(header.active_plan.steps),
            header.active_plan.starts_after_order,
        )
        phase_names = dict(campaign.cycle_phases.values_list("id", "name"))
        phase_names = {str(key): name for key, name in phase_names.items()}
        for cycle in s.project(
            s.PlanContinuation(plan, header.next_position), limit=12
        ):
            first = plan.starts_after_order + header.next_position + 1
            choices.append(
                {
                    "value": ref_data(cycle.ref),
                    "label": f"{cycle.name} · {phase_names[cycle.phase_id]} · Projected",
                    "hint": f"Saving this battle also saves Cycle {first} through Cycle {cycle.order}. The current cycle remains {header.current_cycle.name}.",
                    "isCurrent": False,
                }
            )
        return {
            "configured": True,
            "current": header.current_cycle.name,
            "choices": choices,
            "previous": chosen.previous_page_number()
            if chosen.has_previous()
            else None,
            "next": chosen.next_page_number() if chosen.has_next() else None,
        }
