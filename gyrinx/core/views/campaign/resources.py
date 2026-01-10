"""Campaign resource management views."""

import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.forms.campaign import CampaignResourceTypeForm, ResourceModifyForm
from gyrinx.core.models.campaign import (
    Campaign,
    CampaignListResource,
    CampaignResourceType,
)
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.utils import get_return_url, safe_redirect
from gyrinx.core.views.campaign.common import (
    ensure_campaign_list_resources,
    get_campaign_resource_types_with_resources,
)
from gyrinx.tracker import track

# Constants for transaction limits
MAX_CREDITS = 10000

logger = logging.getLogger(__name__)


@login_required
def campaign_resources(request, id):
    """
    Manage resources for a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` whose resources are being managed.
    ``resource_types``
        List of :model:`core.CampaignResourceType` objects for this campaign.

    **Template**

    :template:`core/campaign/campaign_resources.html`
    """
    campaign = get_object_or_404(Campaign, id=id)

    # Get all resource types with their list resources
    resource_types = get_campaign_resource_types_with_resources(campaign)

    # Check permissions
    user = request.user
    is_owner = user == campaign.owner
    user_lists = campaign.lists.filter(owner=user) if user.is_authenticated else []

    # Log viewing campaign resources
    if user.is_authenticated:
        log_event(
            user=user,
            noun=EventNoun.CAMPAIGN_RESOURCE,
            verb=EventVerb.VIEW,
            object=campaign,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            resource_types_count=len(resource_types),
        )

    return render(
        request,
        "core/campaign/campaign_resources.html",
        {
            "campaign": campaign,
            "resource_types": resource_types,
            "is_owner": is_owner,
            "user_lists": user_lists,
        },
    )


@login_required
@transaction.atomic
def campaign_resource_type_new(request, id):
    """
    Create a new resource type for a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the resource type is being created for.
    ``form``
        A CampaignResourceTypeForm for creating the resource type.

    **Template**

    :template:`core/campaign/campaign_resource_type_new.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    # Prevent creation of new resource types for archived campaigns
    if campaign.archived:
        messages.error(
            request,
            "Cannot create new resource types for archived campaigns.",
        )
        return redirect("core:campaign-resources", campaign.id)

    if request.method == "POST":
        form = CampaignResourceTypeForm(request.POST)
        if form.is_valid():
            try:
                resource_type = form.save(commit=False)
                resource_type.campaign = campaign
                resource_type.owner = request.user
                resource_type.save()

                # If campaign is already started, allocate resources to existing lists
                if campaign.is_in_progress:
                    campaign_lists = list(campaign.lists.all())
                    ensure_campaign_list_resources(
                        campaign=campaign,
                        resource_types=[resource_type],
                        campaign_lists=campaign_lists,
                    )

                # Log the resource type creation
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN_RESOURCE,
                    verb=EventVerb.CREATE,
                    object=resource_type,
                    request=request,
                    campaign_id=str(campaign.id),
                    campaign_name=campaign.name,
                    resource_type_name=resource_type.name,
                    default_amount=resource_type.default_amount,
                    lists_allocated=campaign.lists.count()
                    if campaign.is_in_progress
                    else 0,
                )

                messages.success(
                    request, f"Resource type '{resource_type.name}' created."
                )
                return HttpResponseRedirect(
                    reverse("core:campaign-resources", args=(campaign.id,))
                )
            except ValidationError:
                logger.exception("Validation error creating resource type")
                messages.error(
                    request,
                    "Failed to create resource type. Please check your input and try again.",
                )
            except Exception:
                logger.exception("Unexpected error creating resource type")
                messages.error(
                    request,
                    "Failed to create resource type. Please try again.",
                )
    else:
        form = CampaignResourceTypeForm()

    return render(
        request,
        "core/campaign/campaign_resource_type_new.html",
        {"form": form, "campaign": campaign},
    )


@login_required
def campaign_resource_type_edit(request, id, type_id):
    """
    Edit an existing resource type.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the resource type belongs to.
    ``resource_type``
        The :model:`core.CampaignResourceType` being edited.
    ``form``
        A CampaignResourceTypeForm for editing the resource type.

    **Template**

    :template:`core/campaign/campaign_resource_type_edit.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    resource_type = get_object_or_404(
        CampaignResourceType, id=type_id, campaign=campaign
    )

    if request.method == "POST":
        form = CampaignResourceTypeForm(request.POST, instance=resource_type)
        if form.is_valid():
            form.save()

            # Log the resource type update
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_RESOURCE,
                verb=EventVerb.UPDATE,
                object=resource_type,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                resource_type_name=resource_type.name,
                default_amount=resource_type.default_amount,
            )

            messages.success(request, "Resource type updated.")
            return HttpResponseRedirect(
                reverse("core:campaign-resources", args=(campaign.id,))
            )
    else:
        form = CampaignResourceTypeForm(instance=resource_type)

    return render(
        request,
        "core/campaign/campaign_resource_type_edit.html",
        {"form": form, "campaign": campaign, "resource_type": resource_type},
    )


@login_required
@transaction.atomic
def campaign_resource_type_remove(request, id, type_id):
    """
    Remove a resource type from a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the resource type belongs to.
    ``resource_type``
        The :model:`core.CampaignResourceType` being removed.

    **Template**

    :template:`core/campaign/campaign_resource_type_remove.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    resource_type = get_object_or_404(
        CampaignResourceType, id=type_id, campaign=campaign
    )

    # Prevent removal from archived campaigns
    if campaign.archived:
        messages.error(request, "Cannot remove resource types from archived campaigns.")
        return HttpResponseRedirect(
            reverse("core:campaign-resources", args=(campaign.id,))
        )

    if request.method == "POST":
        # Store info for logging before deletion
        resource_type_name = resource_type.name
        resources_count = resource_type.list_resources.count()

        # Delete the resource type (cascades to list resources)
        resource_type.delete()

        # Log the removal event
        log_event(
            user=request.user,
            noun=EventNoun.CAMPAIGN_RESOURCE,
            verb=EventVerb.DELETE,
            object=campaign,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            resource_type_name=resource_type_name,
            resources_deleted=resources_count,
        )

        messages.success(
            request, f"Resource type '{resource_type_name}' has been removed."
        )

        return HttpResponseRedirect(
            reverse("core:campaign-resources", args=(campaign.id,))
        )

    # GET request - show confirmation page
    return render(
        request,
        "core/campaign/campaign_resource_type_remove.html",
        {
            "campaign": campaign,
            "resource_type": resource_type,
            "resources_count": resource_type.list_resources.count(),
        },
    )


@login_required
def campaign_resource_modify(request, id, resource_id):
    """
    Modify a list's resource amount.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the resource belongs to.
    ``resource``
        The :model:`core.CampaignListResource` being modified.
    ``form``
        A ResourceModifyForm for entering the modification amount.

    **Template**

    :template:`core/campaign/campaign_resource_modify.html`
    """
    campaign = get_object_or_404(Campaign, id=id)
    resource = get_object_or_404(
        CampaignListResource, id=resource_id, campaign=campaign
    )

    # Check permissions - owner can modify any, list owner can modify their own
    if request.user != campaign.owner and request.user != resource.list.owner:
        messages.error(request, "You don't have permission to modify this resource.")
        return HttpResponseRedirect(
            reverse("core:campaign-resources", args=(campaign.id,))
        )

    # Check if campaign is archived
    if campaign.archived:
        messages.error(request, "Cannot modify resources for archived campaigns.")
        return HttpResponseRedirect(
            reverse("core:campaign-resources", args=(campaign.id,))
        )

    # Check if campaign has started
    if campaign.is_pre_campaign:
        messages.error(
            request, "Resources cannot be modified before the campaign starts."
        )
        return HttpResponseRedirect(
            reverse("core:campaign-resources", args=(campaign.id,))
        )

    # Get return URL for back/cancel navigation
    default_url = reverse("core:campaign-resources", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        form = ResourceModifyForm(request.POST, resource=resource)
        if form.is_valid():
            modification = form.cleaned_data["modification"]
            try:
                resource.modify_amount(modification, user=request.user)

                # Log the resource modification event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN_RESOURCE,
                    verb=EventVerb.UPDATE,
                    object=resource,
                    request=request,
                    campaign_id=str(campaign.id),
                    campaign_name=campaign.name,
                    resource_type=resource.resource_type.name,
                    list_name=resource.list.name,
                    modification=modification,
                    new_amount=resource.amount,
                )

                track(
                    "campaign_resource_modified",
                    campaign_id=str(campaign.id),
                    resource_type=resource.resource_type.name,
                    delta=modification,
                )

                messages.success(request, "Resource updated successfully.")
            except ValueError as e:
                messages.error(request, str(e))
            return safe_redirect(request, return_url, fallback_url=default_url)
    else:
        form = ResourceModifyForm(resource=resource)

    return render(
        request,
        "core/campaign/campaign_resource_modify.html",
        {
            "form": form,
            "campaign": campaign,
            "resource": resource,
            "new_amount_preview": resource.amount,  # Will be updated via JS
            "return_url": return_url,
        },
    )
