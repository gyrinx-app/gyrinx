"""Fighter state, injuries, and capture views."""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.forms.list import AddInjuryForm, EditFighterStateForm
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.list import List, ListFighter, ListFighterInjury
from gyrinx.core.views.list.common import get_clean_list_or_404


@login_required
def list_fighter_injuries_edit(request, id, fighter_id):
    """
    Edit injuries for a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` whose injuries are being managed.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_injuries_edit.html`
    """

    # Allow both list owner and campaign owner to manage injuries
    lst = get_clean_list_or_404(
        List.objects.with_related_data().filter(
            Q(owner=request.user) | Q(campaign__owner=request.user)
        ),
        id=id,
    )

    # Verify permissions
    if lst.owner != request.user:
        if not (lst.campaign and lst.campaign.owner == request.user):
            messages.error(
                request,
                "You don't have permission to manage injuries for this fighter.",
            )
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(
            request, "Injuries can only be managed for fighters in campaign mode."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request,
        "core/list_fighter_injuries_edit.html",
        {
            "list": lst,
            "fighter": fighter,
        },
    )


@login_required
def list_fighter_state_edit(request, id, fighter_id):
    """
    Edit the injury state of a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``form``
        An EditFighterStateForm for changing the fighter's state.
    ``fighter``
        The :model:`core.ListFighter` whose state is being changed.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_state_edit.html`
    """

    from gyrinx.core.models.campaign import CampaignAction

    # Allow both list owner and campaign owner to manage fighter state
    lst = get_clean_list_or_404(
        List.objects.filter(Q(owner=request.user) | Q(campaign__owner=request.user)),
        id=id,
    )

    # Verify permissions
    if lst.owner != request.user:
        if not (lst.campaign and lst.campaign.owner == request.user):
            messages.error(
                request,
                "You don't have permission to manage fighter state for this list.",
            )
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(request, "Fighter state can only be managed in campaign mode.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = EditFighterStateForm(request.POST, fighter=fighter)
        if form.is_valid():
            old_state = fighter.get_injury_state_display()
            new_state = form.cleaned_data["fighter_state"]

            # Only update if state actually changed
            if fighter.injury_state != new_state:
                # If changing to dead state, redirect to kill confirmation instead
                if new_state == ListFighter.DEAD:
                    # Don't save the state change here - let the kill view handle it
                    return HttpResponseRedirect(
                        reverse("core:list-fighter-kill", args=(lst.id, fighter.id))
                    )
                # If resurrecting from dead to active, redirect to resurrect confirmation
                elif (
                    new_state == ListFighter.ACTIVE
                    and fighter.injury_state == ListFighter.DEAD
                ):
                    # Don't save the state change here - let the resurrect view handle it
                    return HttpResponseRedirect(
                        reverse(
                            "core:list-fighter-resurrect", args=(lst.id, fighter.id)
                        )
                    )

                with transaction.atomic():
                    fighter.injury_state = new_state
                    fighter.save()

                    new_state_display = dict(ListFighter.INJURY_STATE_CHOICES)[
                        new_state
                    ]

                    # Log to campaign action
                    if lst.campaign:
                        description = f"State Change: {fighter.name} changed from {old_state} to {new_state_display}"
                        if form.cleaned_data.get("reason"):
                            description += f" - {form.cleaned_data['reason']}"

                        CampaignAction.objects.create(
                            user=request.user,
                            owner=request.user,
                            campaign=lst.campaign,
                            list=lst,
                            description=description,
                            outcome=f"{fighter.name} is now {new_state_display}",
                        )

                messages.success(
                    request, f"Updated {fighter.name}'s state to {new_state_display}"
                )
            else:
                messages.info(request, "Fighter state was not changed.")

            return HttpResponseRedirect(
                reverse("core:list-fighter-injuries-edit", args=(lst.id, fighter.id))
            )
    else:
        form = EditFighterStateForm(fighter=fighter)

    return render(
        request,
        "core/list_fighter_state_edit.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
        },
    )


@login_required
def mark_fighter_captured(request, id, fighter_id):
    """
    Mark a fighter as captured by another gang in the campaign.

    **Context**

    ``fighter``
        The :model:`core.ListFighter` being captured.
    ``list``
        The :model:`core.List` that owns this fighter.
    ``capturing_lists``
        Other gangs in the campaign that can capture this fighter.
    ``campaign``
        The :model:`core.Campaign` the lists belong to.

    **Template**

    :template:`core/list_fighter_mark_captured.html`
    """

    from gyrinx.core.handlers.fighter.capture import handle_fighter_capture

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(request, "Fighters can only be captured in campaign mode.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Check if fighter is already captured or sold
    if fighter.is_captured or fighter.is_sold_to_guilders:
        messages.error(request, "This fighter is already captured or sold.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Check if fighter is dead
    if fighter.injury_state == ListFighter.DEAD:
        messages.error(request, "Dead fighters cannot be captured.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Get the campaign
    campaign = lst.campaign
    if not campaign:
        messages.error(request, "This list is not part of a campaign.")
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    # Get other lists in the campaign that could capture this fighter
    capturing_lists = (
        campaign.campaign_lists.filter(status=List.CAMPAIGN_MODE)
        .exclude(id=lst.id)
        .order_by("name")
    )

    if not capturing_lists.exists():
        messages.error(
            request, "No other gangs in the campaign to capture this fighter."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        capturing_list_id = request.POST.get("capturing_list")
        if capturing_list_id:
            capturing_list = get_object_or_404(
                List, id=capturing_list_id, campaign=campaign
            )

            # Call the capture handler
            result = handle_fighter_capture(
                user=request.user,
                fighter=fighter,
                capturing_list=capturing_list,
            )

            # Show messages for removed equipment
            for assignment_id, equipment_cost in result.equipment_removed:
                messages.info(
                    request,
                    f"Linked equipment removed due to capture ({equipment_cost}¢).",
                )

            # Log the capture event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                action="captured",
                capturing_list_name=capturing_list.name,
                capturing_list_id=str(capturing_list.id),
            )

            messages.success(
                request,
                f"{fighter.name} has been marked as captured by {capturing_list.name}.",
            )
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    return render(
        request,
        "core/list_fighter_mark_captured.html",
        {
            "fighter": fighter,
            "list": lst,
            "capturing_lists": capturing_lists,
            "campaign": campaign,
        },
    )


@login_required
def list_fighter_add_injury(request, id, fighter_id):
    """
    Add an injury to a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``form``
        An AddInjuryForm for selecting the injury to add.
    ``fighter``
        The :model:`core.ListFighter` being injured.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_add_injury.html`
    """

    from gyrinx.core.models.campaign import CampaignAction

    # Allow both list owner and campaign owner to add injuries
    lst = get_clean_list_or_404(
        List.objects.filter(Q(owner=request.user) | Q(campaign__owner=request.user)),
        id=id,
    )

    # Verify permissions
    if lst.owner != request.user:
        if not (lst.campaign and lst.campaign.owner == request.user):
            messages.error(
                request,
                "You don't have permission to add injuries to this fighter.",
            )
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    # Check campaign mode
    if lst.status != List.CAMPAIGN_MODE:
        messages.error(
            request, "Injuries can only be added to fighters in campaign mode."
        )
        return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    if request.method == "POST":
        form = AddInjuryForm(request.POST, fighter=fighter)
        if form.is_valid():
            with transaction.atomic():
                injury = ListFighterInjury.objects.create_with_user(
                    user=request.user,
                    fighter=fighter,
                    injury=form.cleaned_data["injury"],
                    notes=form.cleaned_data.get("notes", ""),
                    owner=lst.owner,
                )

                # Update fighter state
                fighter.injury_state = form.cleaned_data["fighter_state"]
                fighter.save()

                # Log to campaign action
                if lst.campaign:
                    # Use the correct injury/damage term from the fighter's terminology
                    description = f"{fighter.term_injury_singular}: {fighter.name} suffered {injury.injury.name}"
                    if form.cleaned_data.get("notes"):
                        description += f" - {form.cleaned_data['notes']}"

                    # Update outcome to show fighter state
                    fighter_state_display = dict(ListFighter.INJURY_STATE_CHOICES)[
                        fighter.injury_state
                    ]
                    outcome = f"{fighter.name} was put into {fighter_state_display}"

                    CampaignAction.objects.create(
                        user=request.user,
                        owner=request.user,
                        campaign=lst.campaign,
                        list=lst,
                        description=description,
                        outcome=outcome,
                    )

                # Log the injury event
                log_event(
                    user=request.user,
                    noun=EventNoun.LIST_FIGHTER,
                    verb=EventVerb.UPDATE,
                    object=fighter,
                    request=request,
                    fighter_name=fighter.name,
                    list_id=str(lst.id),
                    list_name=lst.name,
                    action="injury_added",
                    injury_name=injury.injury.name,
                    injury_state=fighter.injury_state,
                )

            messages.success(
                request, f"Added injury '{injury.injury.name}' to {fighter.name}"
            )

            # If fighter state is dead, redirect to kill confirmation
            if form.cleaned_data["fighter_state"] == ListFighter.DEAD:
                return HttpResponseRedirect(
                    reverse("core:list-fighter-kill", args=(lst.id, fighter.id))
                )

            return HttpResponseRedirect(
                reverse("core:list-fighter-injuries-edit", args=(lst.id, fighter.id))
            )
    else:
        form = AddInjuryForm(fighter=fighter)

    return render(
        request,
        "core/list_fighter_add_injury.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
        },
    )


@login_required
def list_fighter_remove_injury(request, id, fighter_id, injury_id):
    """
    Remove an injury from a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``injury``
        The :model:`core.ListFighterInjury` to be removed.
    ``fighter``
        The :model:`core.ListFighter` being healed.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_remove_injury.html`
    """

    from gyrinx.core.models.campaign import CampaignAction

    # Allow both list owner and campaign owner to remove injuries
    lst = get_clean_list_or_404(
        List.objects.filter(Q(owner=request.user) | Q(campaign__owner=request.user)),
        id=id,
    )

    # Verify permissions
    if lst.owner != request.user:
        if not (lst.campaign and lst.campaign.owner == request.user):
            messages.error(
                request,
                "You don't have permission to remove injuries from this fighter.",
            )
            return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))

    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )
    injury = get_object_or_404(ListFighterInjury, id=injury_id, fighter=fighter)

    if request.method == "POST":
        with transaction.atomic():
            injury_name = injury.injury.name
            injury.delete()

            # Clear the prefetch cache to get accurate count
            fighter._prefetched_objects_cache = {}

            # If fighter has no more injuries, reset state to active
            if fighter.injuries.count() == 0:
                fighter.injury_state = ListFighter.ACTIVE
                fighter.save()
                outcome = "Fighter became available"
            else:
                outcome = "Injury removed"

            # Log to campaign action
            if lst.campaign:
                # Use the fighter's recovery terminology
                recovery_term = fighter.term_recovery_singular
                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=lst.campaign,
                    list=lst,
                    description=f"{recovery_term}: {fighter.name} recovered from {injury_name}",
                    outcome=outcome,
                )

            # Log the injury removal event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                action="injury_removed",
                injury_name=injury_name,
                injury_state=fighter.injury_state,
            )

        messages.success(request, f"Removed injury '{injury_name}' from {fighter.name}")
        return HttpResponseRedirect(
            reverse("core:list-fighter-injuries-edit", args=(lst.id, fighter.id))
        )

    return render(
        request,
        "core/list_fighter_remove_injury.html",
        {
            "injury": injury,
            "fighter": fighter,
            "list": lst,
        },
    )
