"""Fighter psyker powers views."""

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx.content.models import (
    ContentFighterPsykerPowerDefaultAssignment,
    ContentPsykerPower,
)
from gyrinx.core.models.events import EventVerb
from gyrinx.core.models.list import ListFighterPsykerPowerAssignment


@login_required
def edit_list_fighter_powers(request, id, fighter_id):
    """
    Edit the psyker powers of an existing :model:`core.ListFighter`.

    **Context**

    ``form``
        A ListFighterPowersForm for selecting fighter powers.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/list_fighter_psyker_powers_edit.html`
    """
    from gyrinx.core.views.fighter.helpers import (
        FighterEditMixin,
        build_virtual_psyker_power_assignments,
        get_common_query_params,
        get_fighter_powers,
        group_available_assignments,
    )

    # Use helper to get fighter and list
    helper = FighterEditMixin()
    lst, fighter = helper.get_fighter_and_list(request, id, fighter_id)

    error_message = None
    if request.method == "POST":
        power_id = request.POST.get("psyker_power_id", None)
        if not power_id:
            return HttpResponseRedirect(
                reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
            )

        if request.POST.get("action") == "remove":
            kind = request.POST.get("assign_kind")
            if kind == "default":
                default_assign = get_object_or_404(
                    ContentFighterPsykerPowerDefaultAssignment,
                    psyker_power=power_id,
                    fighter=fighter.content_fighter_cached,
                )
                fighter.disabled_pskyer_default_powers.add(default_assign)
                fighter.save()

                # Log the power removal event
                helper.log_fighter_event(
                    request,
                    fighter,
                    lst,
                    EventVerb.UPDATE,
                    field="psyker_powers",
                    action="remove_default_power",
                    power_name=default_assign.psyker_power.name,
                )

                return HttpResponseRedirect(
                    reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
                )
            elif kind == "assigned":
                assign = get_object_or_404(
                    ListFighterPsykerPowerAssignment,
                    psyker_power=power_id,
                    list_fighter=fighter,
                )
                power_name = assign.psyker_power.name
                assign.delete()

                # Log the power removal event
                helper.log_fighter_event(
                    request,
                    fighter,
                    lst,
                    EventVerb.UPDATE,
                    field="psyker_powers",
                    action="remove_assigned_power",
                    power_name=power_name,
                )

                return HttpResponseRedirect(
                    reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
                )
            else:
                error_message = "Invalid action."
        elif request.POST.get("action") == "enable":
            # Enable a disabled default power
            default_assign = get_object_or_404(
                ContentFighterPsykerPowerDefaultAssignment,
                psyker_power=power_id,
                fighter=fighter.content_fighter_cached,
            )
            fighter.disabled_pskyer_default_powers.remove(default_assign)
            fighter.save()

            # Log the power enable event
            helper.log_fighter_event(
                request,
                fighter,
                lst,
                EventVerb.UPDATE,
                field="psyker_powers",
                action="enable_default_power",
                power_name=default_assign.psyker_power.name,
            )

            return HttpResponseRedirect(
                reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
            )
        elif request.POST.get("action") == "add":
            power = get_object_or_404(
                ContentPsykerPower,
                id=power_id,
            )
            assign = ListFighterPsykerPowerAssignment(
                list_fighter=fighter,
                psyker_power=power,
            )
            assign.save()

            # Log the power add event
            helper.log_fighter_event(
                request,
                fighter,
                lst,
                EventVerb.UPDATE,
                field="psyker_powers",
                action="add_power",
                power_name=power.name,
            )

            return HttpResponseRedirect(
                reverse("core:list-fighter-powers-edit", args=(lst.id, fighter.id))
            )

    # Get query parameters
    params = get_common_query_params(request)

    # Get powers using helper
    powers = get_fighter_powers(fighter, params["show_restricted"])

    # Build assignments using helper
    all_assigns = build_virtual_psyker_power_assignments(powers, fighter)

    # Separate current powers (unfiltered) from available powers
    # Include disabled defaults in current powers
    current_powers = [
        a
        for a in all_assigns
        if a.kind() in ["default", "assigned"] or getattr(a, "is_disabled", False)
    ]

    # Apply search filter only for the available powers grid
    if params["search_query"]:
        filtered_powers = powers.filter(
            Q(name__icontains=params["search_query"])
            | Q(discipline__name__icontains=params["search_query"])
        )
        assigns = build_virtual_psyker_power_assignments(filtered_powers, fighter)
    else:
        assigns = all_assigns

    # Group available powers by discipline using helper
    available_disciplines = group_available_assignments(assigns, "disc")
    # Rename 'group' to 'discipline' and 'items' to 'powers' for template compatibility
    for disc_data in available_disciplines:
        disc_data["discipline"] = disc_data.pop("group")
        disc_data["powers"] = disc_data.pop("items")

    return render(
        request,
        "core/list_fighter_psyker_powers_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "powers": powers,
            "assigns": assigns,
            "current_powers": current_powers,
            "available_disciplines": available_disciplines,
            "error_message": error_message,
            **params,  # Includes search_query and show_restricted
        },
    )
