"""Views for vehicle addition flow."""

import uuid
from typing import Optional
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from pydantic import BaseModel, ValidationError

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentFighterProfile,
    ContentFighter,
)
from gyrinx.core.forms.vehicle import (
    CrewSelectionForm,
    VehicleConfirmationForm,
    VehicleSelectionForm,
)
from gyrinx.core.handlers.fighter import handle_vehicle_purchase
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List


class VehicleFlowParams(BaseModel):
    """Parameters for the vehicle addition flow."""

    action: Optional[str] = None
    vehicle_equipment_id: Optional[uuid.UUID] = None
    crew_name: str | None = None
    crew_fighter_id: Optional[uuid.UUID] = None


@login_required
def new_vehicle(request, id):
    """
    Redirect to the start of the vehicle addition flow.
    """
    lst = get_object_or_404(List, id=id, owner=request.user)

    # Check if list is archived
    if lst.archived:
        messages.error(request, "Cannot add vehicles to an archived list.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return redirect("core:list-vehicle-select", id=lst.id)


@login_required
def vehicle_select(request, id):
    """
    Step 1: Select a vehicle from available equipment with ContentEquipmentFighterProfile.
    """
    lst = get_object_or_404(List, id=id, owner=request.user)

    # Check if list is archived
    if lst.archived:
        messages.error(request, "Cannot add vehicles to an archived list.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = VehicleSelectionForm(request.POST, list_instance=lst)
        if form.is_valid():
            vehicle_equipment = form.cleaned_data["vehicle_equipment"]

            action = request.POST.get("action")
            if action == "add_to_stash":
                # Go to confirmation step with stash action
                params = VehicleFlowParams(
                    vehicle_equipment_id=vehicle_equipment.id, action=action
                )
                query_string = urlencode(params.model_dump(exclude_none=True))
                return HttpResponseRedirect(
                    reverse("core:list-vehicle-confirm", args=(lst.id,))
                    + f"?{query_string}"
                )
            elif action == "select_crew":
                # Redirect to crew selection step
                params = VehicleFlowParams(
                    vehicle_equipment_id=vehicle_equipment.id, action=action
                )
                query_string = urlencode(params.model_dump(exclude_none=True))
                return HttpResponseRedirect(
                    reverse("core:list-vehicle-crew", args=(lst.id,))
                    + f"?{query_string}"
                )

    else:
        form = VehicleSelectionForm(list_instance=lst)

    return render(
        request,
        "core/vehicle_select.html",
        {
            "form": form,
            "list": lst,
            "step": 1,
            "total_steps": 3,
        },
    )


@login_required
def vehicle_crew(request, id):
    """
    Step 2: Select a crew member for the vehicle.
    """
    lst = get_object_or_404(List, id=id, owner=request.user)

    # Check if list is archived
    if lst.archived:
        messages.error(request, "Cannot add vehicles to an archived list.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Parse flow parameters
    try:
        params = VehicleFlowParams.model_validate(request.GET.dict())
    except ValidationError:
        messages.error(request, "Invalid flow parameters.")
        return redirect("core:list-vehicle-select", id=lst.id)

    if not params.vehicle_equipment_id:
        messages.error(request, "Vehicle not selected.")
        return redirect("core:list-vehicle-select", id=lst.id)

    vehicle_equipment = get_object_or_404(
        ContentEquipment, id=params.vehicle_equipment_id
    )

    if request.method == "POST":
        form = CrewSelectionForm(
            request.POST, list_instance=lst, vehicle_equipment=vehicle_equipment
        )
        if form.is_valid():
            # Update params with crew info
            params.action = form.cleaned_data["action"]
            params.crew_name = form.cleaned_data["crew_name"]
            params.crew_fighter_id = form.cleaned_data["crew_fighter"].id

            query_string = urlencode(params.model_dump(exclude_none=True))

            return HttpResponseRedirect(
                reverse("core:list-vehicle-confirm", args=(lst.id,))
                + f"?{query_string}"
            )
    else:
        form = CrewSelectionForm(list_instance=lst, vehicle_equipment=vehicle_equipment)

    return render(
        request,
        "core/vehicle_crew.html",
        {
            "form": form,
            "list": lst,
            "vehicle_equipment": vehicle_equipment,
            "params": params,
            "step": 2,
            "total_steps": 3,
        },
    )


@login_required
def vehicle_confirm(request, id):
    """
    Step 3: Confirm vehicle and crew creation.
    """
    lst = get_object_or_404(List, id=id, owner=request.user)

    # Check if list is archived
    if lst.archived:
        messages.error(request, "Cannot add vehicles to an archived list.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Parse flow parameters
    try:
        params = VehicleFlowParams.model_validate(request.GET.dict())
    except ValidationError:
        messages.error(request, "Invalid flow parameters.")
        return redirect("core:list-vehicle-select", id=lst.id)

    if (params.action == "add_to_stash" and not params.vehicle_equipment_id) or (
        params.action == "select_crew"
        and (
            not params.vehicle_equipment_id
            or not params.crew_fighter_id
            or not params.crew_name
        )
    ):
        messages.error(request, "Missing required information.")
        return redirect("core:list-vehicle-select", id=lst.id)

    vehicle_equipment = get_object_or_404(
        ContentEquipment, id=params.vehicle_equipment_id
    )

    # Get the vehicle fighter profile
    profile = (
        ContentEquipmentFighterProfile.objects.filter(equipment=vehicle_equipment)
        .select_related("content_fighter")
        .first()
    )

    if not profile:
        messages.error(request, "Invalid vehicle equipment.")
        return redirect("core:list-vehicle-select", id=lst.id)

    vehicle_fighter = profile.content_fighter

    crew_fighter = None
    if params.action == "select_crew":
        crew_fighter = get_object_or_404(ContentFighter, id=params.crew_fighter_id)

    if request.method == "POST":
        form = VehicleConfirmationForm(request.POST)
        if form.is_valid():
            # Calculate total cost before transaction (for display in error case)
            vehicle_cost = vehicle_fighter.cost_for_house(lst.content_house)
            crew_cost = (
                crew_fighter.cost_for_house(lst.content_house) if crew_fighter else 0
            )
            total_cost = vehicle_cost + crew_cost
            is_stash = params.action == "add_to_stash"

            # Call handler to handle business logic
            try:
                result = handle_vehicle_purchase(
                    user=request.user,
                    lst=lst,
                    vehicle_equipment=vehicle_equipment,
                    vehicle_fighter=vehicle_fighter,
                    crew_fighter=crew_fighter,
                    crew_name=params.crew_name,
                    is_stash=is_stash,
                )

                # Extract results for HTTP-specific operations
                crew = result.crew_fighter

                # Log the vehicle addition (HTTP-specific tracking)
                log_event(
                    user=request.user,
                    noun=EventNoun.LIST_FIGHTER,
                    verb=EventVerb.CREATE,
                    object=crew,
                    request=request,
                    fighter_name=crew.name,
                    list_id=str(lst.id),
                    list_name=lst.name,
                    is_vehicle_crew=True,
                    vehicle_equipment_id=str(vehicle_equipment.id),
                    vehicle_equipment_name=vehicle_equipment.name,
                    action=params.action,
                )

                messages.success(
                    request,
                    f"Vehicle '{vehicle_equipment.name}' and crew member '{crew.name}' added successfully!",
                )

                # Redirect to list with crew member highlighted
                query_params = urlencode(dict(flash=crew.id))
                return HttpResponseRedirect(
                    reverse("core:list", args=(lst.id,))
                    + f"?{query_params}"
                    + f"#{str(crew.id)}"
                )
            except DjangoValidationError as e:
                # Handler failed - no cleanup needed (transaction rolled back)
                error_message = ". ".join(e.messages)
                messages.error(request, error_message)
                return render(
                    request,
                    "core/vehicle_confirm.html",
                    {
                        "form": form,
                        "list": lst,
                        "vehicle_equipment": vehicle_equipment,
                        "vehicle_fighter": vehicle_fighter,
                        "crew_fighter": crew_fighter,
                        "crew_name": params.crew_name,
                        "params": params,
                        "vehicle_cost": vehicle_cost,
                        "crew_cost": crew_cost,
                        "total_cost": total_cost,
                        "step": 3,
                        "total_steps": 3,
                    },
                )
    else:
        form = VehicleConfirmationForm()

    # Calculate total cost
    vehicle_cost = vehicle_fighter.cost_for_house(lst.content_house)
    crew_cost = crew_fighter.cost_for_house(lst.content_house) if crew_fighter else 0
    total_cost = vehicle_cost + crew_cost

    return render(
        request,
        "core/vehicle_confirm.html",
        {
            "form": form,
            "list": lst,
            "vehicle_equipment": vehicle_equipment,
            "vehicle_fighter": vehicle_fighter,
            "crew_fighter": crew_fighter,
            "crew_name": params.crew_name,
            "params": params,
            "vehicle_cost": vehicle_cost,
            "crew_cost": crew_cost,
            "total_cost": total_cost,
            "step": 3,
            "total_steps": 3,
        },
    )
