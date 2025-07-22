"""Views for vehicle addition flow."""

import uuid
from typing import Optional
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
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
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List, ListFighter, ListFighterEquipmentAssignment


class VehicleFlowParams(BaseModel):
    """Parameters for the vehicle addition flow."""

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

            # Build query params for next step
            params = VehicleFlowParams(vehicle_equipment_id=vehicle_equipment.id)
            query_string = urlencode(params.model_dump(exclude_none=True))

            return HttpResponseRedirect(
                reverse("core:list-vehicle-crew", args=(lst.id,)) + f"?{query_string}"
            )
    else:
        form = VehicleSelectionForm(list_instance=lst)

        # Log viewing the vehicle selection form
        log_event(
            user=request.user,
            noun=EventNoun.LIST,
            verb=EventVerb.VIEW,
            object=lst,
            request=request,
            page="vehicle_select",
        )

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
            params.crew_name = form.cleaned_data["crew_name"]
            params.crew_fighter_id = form.cleaned_data["crew_fighter"].id

            query_string = urlencode(params.model_dump(exclude_none=True))

            return HttpResponseRedirect(
                reverse("core:list-vehicle-confirm", args=(lst.id,))
                + f"?{query_string}"
            )
    else:
        form = CrewSelectionForm(list_instance=lst, vehicle_equipment=vehicle_equipment)

        # Log viewing the crew selection form
        log_event(
            user=request.user,
            noun=EventNoun.LIST,
            verb=EventVerb.VIEW,
            object=lst,
            request=request,
            page="vehicle_crew",
            vehicle_equipment_id=str(vehicle_equipment.id),
        )

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

    if (
        not params.vehicle_equipment_id
        or not params.crew_fighter_id
        or not params.crew_name
    ):
        messages.error(request, "Missing required information.")
        return redirect("core:list-vehicle-select", id=lst.id)

    vehicle_equipment = get_object_or_404(
        ContentEquipment, id=params.vehicle_equipment_id
    )
    crew_fighter = get_object_or_404(ContentFighter, id=params.crew_fighter_id)

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

    if request.method == "POST":
        form = VehicleConfirmationForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Create the crew member
                crew = ListFighter.objects.create(
                    list=lst,
                    owner=lst.owner,
                    name=params.crew_name,
                    content_fighter=crew_fighter,
                )

                # Create the equipment assignment - this will trigger automatic vehicle creation
                ListFighterEquipmentAssignment.objects.create(
                    list_fighter=crew,
                    content_equipment=vehicle_equipment,
                )

                # Log the vehicle addition
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
    else:
        form = VehicleConfirmationForm()

        # Log viewing the confirmation form
        log_event(
            user=request.user,
            noun=EventNoun.LIST,
            verb=EventVerb.VIEW,
            object=lst,
            request=request,
            page="vehicle_confirm",
        )

    # Calculate total cost
    vehicle_cost = vehicle_equipment.cost_int()
    crew_cost = crew_fighter.cost_for_house(lst.content_house)
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
