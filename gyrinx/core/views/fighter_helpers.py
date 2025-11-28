"""Helper functions and mixins for fighter-related views."""

from collections import defaultdict
from typing import Any, Dict, List as ListType, Optional

from django.db.models import Exists, OuterRef, Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404

from gyrinx.content.models import (
    ContentFighterPsykerPowerDefaultAssignment,
)
from gyrinx.content.models.psyker import ContentPsykerDiscipline, ContentPsykerPower
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterPsykerPowerAssignment,
    VirtualListFighterPsykerPowerAssignment,
)


class FighterEditMixin:
    """Mixin for fighter edit views."""

    def get_fighter_and_list(self, request: HttpRequest, id: str, fighter_id: str):
        """Get fighter and list with ownership check."""
        lst = get_object_or_404(List, id=id, owner=request.user)
        fighter = get_object_or_404(
            ListFighter.objects.with_related_data(),
            id=fighter_id,
            list=lst,
            owner=lst.owner,
        )
        return lst, fighter

    def log_fighter_event(
        self,
        request: HttpRequest,
        fighter: ListFighter,
        lst: List,
        verb: EventVerb,
        field: Optional[str] = None,
        **extra,
    ):
        """Log fighter-related events."""
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=verb,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            field=field,
            **extra,
        )


def get_common_query_params(request: HttpRequest) -> Dict[str, Any]:
    """Extract common query parameters."""
    return {
        "search_query": request.GET.get("q", "").strip(),
        "show_restricted": request.GET.get("restricted", "0") == "1",
    }


def build_virtual_psyker_power_assignments(
    powers, fighter: ListFighter
) -> ListType[VirtualListFighterPsykerPowerAssignment]:
    """Build virtual assignment objects from power queryset."""
    assigns = []
    for power in powers:
        if power.assigned_direct:
            assigns.append(
                VirtualListFighterPsykerPowerAssignment.from_assignment(
                    ListFighterPsykerPowerAssignment(
                        list_fighter=fighter,
                        psyker_power=power,
                    ),
                )
            )
        elif power.assigned_default:
            assigns.append(
                VirtualListFighterPsykerPowerAssignment.from_default_assignment(
                    ContentFighterPsykerPowerDefaultAssignment(
                        fighter=fighter.content_fighter_cached,
                        psyker_power=power,
                    ),
                    fighter=fighter,
                )
            )
        elif hasattr(power, "disabled_default") and power.disabled_default:
            # Create a disabled default assignment
            assign = VirtualListFighterPsykerPowerAssignment.from_default_assignment(
                ContentFighterPsykerPowerDefaultAssignment(
                    fighter=fighter.content_fighter_cached,
                    psyker_power=power,
                ),
                fighter=fighter,
            )
            # Mark it as disabled
            assign.is_disabled = True
            assigns.append(assign)
        else:
            assigns.append(
                VirtualListFighterPsykerPowerAssignment(
                    fighter=fighter, psyker_power=power
                )
            )
    return assigns


def group_available_assignments(
    assigns: ListType[Any], group_attr: str, filter_assigned: bool = True
) -> ListType[Dict[str, Any]]:
    """Group assignments by a given attribute."""
    available_by_group = defaultdict(list)

    for assign in assigns:
        if filter_assigned:
            # For psyker powers, kind() is a method
            kind = assign.kind() if hasattr(assign.kind, "__call__") else assign.kind
            if kind in ["default", "assigned"]:
                continue
        group_value = getattr(assign, group_attr)
        available_by_group[group_value].append(assign)

    # Convert to list of dicts for template
    return [
        {"group": group, "items": items}
        for group, items in sorted(available_by_group.items())
    ]


def get_fighter_powers(fighter: ListFighter, show_restricted: bool = False):
    """Get available psyker powers for a fighter."""
    # TODO: A fair bit of this logic should live in the model, or a manager method
    disabled_defaults = fighter.disabled_pskyer_default_powers.values("id")

    # Get available disciplines including equipment modifications
    available_disciplines = fighter.get_available_psyker_disciplines()

    # Build the disciplines query
    if show_restricted:
        # Show all disciplines when restricted is enabled
        disciplines_query = ContentPsykerDiscipline.objects.all()
    else:
        # Default behavior: only show assigned or generic disciplines
        disciplines_query = ContentPsykerDiscipline.objects.filter(
            Q(id__in=[d.id for d in available_disciplines]) | Q(generic=True)
        ).distinct()

    powers = (
        ContentPsykerPower.objects.filter(
            # Get powers via disciplines
            Q(discipline__in=disciplines_query)
            # ...and get powers that are assigned to this fighter by default
            | Q(
                fighter_assignments__fighter=fighter.content_fighter_cached,
            )
        )
        .distinct()
        .prefetch_related("discipline")
        .annotate(
            assigned_direct=Exists(
                ListFighterPsykerPowerAssignment.objects.filter(
                    list_fighter=fighter,
                    psyker_power=OuterRef("pk"),
                ).values("psyker_power_id")
            ),
            assigned_default=Exists(
                ContentFighterPsykerPowerDefaultAssignment.objects.filter(
                    fighter=fighter.content_fighter_cached,
                    psyker_power=OuterRef("pk"),
                )
                .exclude(id__in=disabled_defaults)
                .values("psyker_power_id")
            ),
            disabled_default=Exists(
                ContentFighterPsykerPowerDefaultAssignment.objects.filter(
                    fighter=fighter.content_fighter_cached,
                    psyker_power=OuterRef("pk"),
                    id__in=disabled_defaults,
                ).values("psyker_power_id")
            ),
        )
    )

    return powers
