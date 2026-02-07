"""Campaign attribute management views."""

import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.forms.campaign import (
    CampaignAttributeTypeForm,
    CampaignAttributeValueForm,
    CampaignListAttributeAssignmentForm,
)
from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAttributeType,
    CampaignAttributeValue,
)
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.utils import get_return_url, safe_redirect

logger = logging.getLogger(__name__)


@login_required
def campaign_attributes(request, id):
    """
    Manage attributes for a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` whose attributes are being managed.
    ``attribute_types``
        List of :model:`core.CampaignAttributeType` objects with prefetched values
        and assignments.

    **Template**

    :template:`core/campaign/campaign_attributes.html`
    """
    campaign = get_object_or_404(Campaign, id=id)

    attribute_types = campaign.attribute_types.prefetch_related(
        "values",
        "values__list_assignments",
        "values__list_assignments__list",
    ).order_by("name")

    user = request.user
    is_owner = user == campaign.owner
    user_lists = campaign.lists.filter(owner=user) if user.is_authenticated else []
    user_list_ids = set(user_lists.values_list("id", flat=True))

    # Build assignment lookup: {attribute_type_id: {list_id: [assignment, ...]}}
    assignment_lookup = {}
    for attr_type in attribute_types:
        type_assignments = {}
        for value in attr_type.values.all():
            for assignment in value.list_assignments.all():
                type_assignments.setdefault(assignment.list_id, []).append(assignment)
        assignment_lookup[attr_type.id] = type_assignments

    if user.is_authenticated:
        log_event(
            user=user,
            noun=EventNoun.CAMPAIGN,
            verb=EventVerb.VIEW,
            object=campaign,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            action="view_attributes",
        )

    return render(
        request,
        "core/campaign/campaign_attributes.html",
        {
            "campaign": campaign,
            "attribute_types": attribute_types,
            "is_owner": is_owner,
            "user_lists": user_lists,
            "user_list_ids": user_list_ids,
            "assignment_lookup": assignment_lookup,
        },
    )


@login_required
@transaction.atomic
def campaign_attribute_type_new(request, id):
    """
    Create a new attribute type for a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the attribute type is being created for.
    ``form``
        A CampaignAttributeTypeForm for creating the attribute type.

    **Template**

    :template:`core/campaign/campaign_attribute_type_new.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if campaign.archived:
        messages.error(
            request,
            "Cannot create new attribute types for archived Campaigns.",
        )
        return redirect("core:campaign-attributes", campaign.id)

    if request.method == "POST":
        form = CampaignAttributeTypeForm(request.POST)
        if form.is_valid():
            try:
                attribute_type = form.save(commit=False)
                attribute_type.campaign = campaign
                attribute_type.owner = request.user
                attribute_type.save_with_user(user=request.user)

                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.CREATE,
                    object=attribute_type,
                    request=request,
                    campaign_id=str(campaign.id),
                    campaign_name=campaign.name,
                    action="create_attribute_type",
                    attribute_type_name=attribute_type.name,
                )

                messages.success(
                    request, f"Attribute type '{attribute_type.name}' created."
                )
                return HttpResponseRedirect(
                    reverse("core:campaign-attributes", args=(campaign.id,))
                )
            except ValidationError:
                logger.exception("Validation error creating attribute type")
                messages.error(
                    request,
                    "Failed to create attribute type. Please check your input and try again.",
                )
            except Exception:
                logger.exception("Unexpected error creating attribute type")
                messages.error(
                    request,
                    "Failed to create attribute type. Please try again.",
                )
    else:
        form = CampaignAttributeTypeForm()

    return render(
        request,
        "core/campaign/campaign_attribute_type_new.html",
        {"form": form, "campaign": campaign},
    )


@login_required
def campaign_attribute_type_edit(request, id, type_id):
    """
    Edit an existing attribute type.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the attribute type belongs to.
    ``attribute_type``
        The :model:`core.CampaignAttributeType` being edited.
    ``form``
        A CampaignAttributeTypeForm for editing the attribute type.

    **Template**

    :template:`core/campaign/campaign_attribute_type_edit.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    attribute_type = get_object_or_404(
        CampaignAttributeType, id=type_id, campaign=campaign
    )

    if request.method == "POST":
        form = CampaignAttributeTypeForm(request.POST, instance=attribute_type)
        if form.is_valid():
            form.save()

            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN,
                verb=EventVerb.UPDATE,
                object=attribute_type,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                action="update_attribute_type",
                attribute_type_name=attribute_type.name,
            )

            messages.success(request, "Attribute type updated.")
            return HttpResponseRedirect(
                reverse("core:campaign-attributes", args=(campaign.id,))
            )
    else:
        form = CampaignAttributeTypeForm(instance=attribute_type)

    return render(
        request,
        "core/campaign/campaign_attribute_type_edit.html",
        {"form": form, "campaign": campaign, "attribute_type": attribute_type},
    )


@login_required
@transaction.atomic
def campaign_attribute_type_remove(request, id, type_id):
    """
    Remove an attribute type from a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the attribute type belongs to.
    ``attribute_type``
        The :model:`core.CampaignAttributeType` being removed.

    **Template**

    :template:`core/campaign/campaign_attribute_type_remove.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    attribute_type = get_object_or_404(
        CampaignAttributeType, id=type_id, campaign=campaign
    )

    if campaign.archived:
        messages.error(
            request, "Cannot remove attribute types from archived Campaigns."
        )
        return HttpResponseRedirect(
            reverse("core:campaign-attributes", args=(campaign.id,))
        )

    if request.method == "POST":
        attribute_type_name = attribute_type.name
        values_count = attribute_type.values.count()

        attribute_type.delete()

        log_event(
            user=request.user,
            noun=EventNoun.CAMPAIGN,
            verb=EventVerb.DELETE,
            object=campaign,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            action="delete_attribute_type",
            attribute_type_name=attribute_type_name,
            values_deleted=values_count,
        )

        messages.success(
            request, f"Attribute type '{attribute_type_name}' has been removed."
        )

        return HttpResponseRedirect(
            reverse("core:campaign-attributes", args=(campaign.id,))
        )

    return render(
        request,
        "core/campaign/campaign_attribute_type_remove.html",
        {
            "campaign": campaign,
            "attribute_type": attribute_type,
            "values_count": attribute_type.values.count(),
        },
    )


@login_required
@transaction.atomic
def campaign_attribute_value_new(request, id, type_id):
    """
    Create a new value for an attribute type.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the attribute type belongs to.
    ``attribute_type``
        The :model:`core.CampaignAttributeType` the value is being created for.
    ``form``
        A CampaignAttributeValueForm for creating the value.

    **Template**

    :template:`core/campaign/campaign_attribute_value_new.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    attribute_type = get_object_or_404(
        CampaignAttributeType, id=type_id, campaign=campaign
    )

    if campaign.archived:
        messages.error(request, "Cannot create values for archived Campaigns.")
        return HttpResponseRedirect(
            reverse("core:campaign-attributes", args=(campaign.id,))
        )

    if request.method == "POST":
        form = CampaignAttributeValueForm(request.POST)
        if form.is_valid():
            try:
                attribute_value = form.save(commit=False)
                attribute_value.attribute_type = attribute_type
                attribute_value.owner = request.user
                attribute_value.save_with_user(user=request.user)

                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.CREATE,
                    object=attribute_value,
                    request=request,
                    campaign_id=str(campaign.id),
                    campaign_name=campaign.name,
                    action="create_attribute_value",
                    attribute_type_name=attribute_type.name,
                    attribute_value_name=attribute_value.name,
                )

                messages.success(
                    request,
                    f"Value '{attribute_value.name}' created for {attribute_type.name}.",
                )
                return HttpResponseRedirect(
                    reverse("core:campaign-attributes", args=(campaign.id,))
                )
            except ValidationError:
                logger.exception("Validation error creating attribute value")
                messages.error(
                    request,
                    "Failed to create value. Please check your input and try again.",
                )
            except Exception:
                logger.exception("Unexpected error creating attribute value")
                messages.error(request, "Failed to create value. Please try again.")
    else:
        form = CampaignAttributeValueForm()

    return render(
        request,
        "core/campaign/campaign_attribute_value_new.html",
        {
            "form": form,
            "campaign": campaign,
            "attribute_type": attribute_type,
        },
    )


@login_required
def campaign_attribute_value_edit(request, id, value_id):
    """
    Edit an existing attribute value.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the value belongs to.
    ``attribute_value``
        The :model:`core.CampaignAttributeValue` being edited.
    ``form``
        A CampaignAttributeValueForm for editing the value.

    **Template**

    :template:`core/campaign/campaign_attribute_value_edit.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    attribute_value = get_object_or_404(
        CampaignAttributeValue, id=value_id, attribute_type__campaign=campaign
    )

    if request.method == "POST":
        form = CampaignAttributeValueForm(request.POST, instance=attribute_value)
        if form.is_valid():
            form.save()

            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN,
                verb=EventVerb.UPDATE,
                object=attribute_value,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                action="update_attribute_value",
                attribute_type_name=attribute_value.attribute_type.name,
                attribute_value_name=attribute_value.name,
            )

            messages.success(request, "Attribute value updated.")
            return HttpResponseRedirect(
                reverse("core:campaign-attributes", args=(campaign.id,))
            )
    else:
        form = CampaignAttributeValueForm(instance=attribute_value)

    return render(
        request,
        "core/campaign/campaign_attribute_value_edit.html",
        {
            "form": form,
            "campaign": campaign,
            "attribute_value": attribute_value,
        },
    )


@login_required
@transaction.atomic
def campaign_attribute_value_remove(request, id, value_id):
    """
    Remove an attribute value.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the value belongs to.
    ``attribute_value``
        The :model:`core.CampaignAttributeValue` being removed.

    **Template**

    :template:`core/campaign/campaign_attribute_value_remove.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    attribute_value = get_object_or_404(
        CampaignAttributeValue, id=value_id, attribute_type__campaign=campaign
    )

    if campaign.archived:
        messages.error(request, "Cannot remove values from archived Campaigns.")
        return HttpResponseRedirect(
            reverse("core:campaign-attributes", args=(campaign.id,))
        )

    if request.method == "POST":
        attribute_type_name = attribute_value.attribute_type.name
        value_name = attribute_value.name
        assignments_count = attribute_value.list_assignments.count()

        attribute_value.delete()

        log_event(
            user=request.user,
            noun=EventNoun.CAMPAIGN,
            verb=EventVerb.DELETE,
            object=campaign,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            action="delete_attribute_value",
            attribute_type_name=attribute_type_name,
            attribute_value_name=value_name,
            assignments_deleted=assignments_count,
        )

        messages.success(request, f"Value '{value_name}' has been removed.")

        return HttpResponseRedirect(
            reverse("core:campaign-attributes", args=(campaign.id,))
        )

    return render(
        request,
        "core/campaign/campaign_attribute_value_remove.html",
        {
            "campaign": campaign,
            "attribute_value": attribute_value,
            "assignments_count": attribute_value.list_assignments.count(),
        },
    )


@login_required
@transaction.atomic
def campaign_list_attribute_assign(request, id, list_id, type_id):
    """
    Assign attribute values to a list in a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign`.
    ``list``
        The :model:`core.List` being assigned attributes.
    ``attribute_type``
        The :model:`core.CampaignAttributeType` being assigned.
    ``form``
        A CampaignListAttributeAssignmentForm for managing assignments.

    **Template**

    :template:`core/campaign/campaign_list_attribute_assign.html`
    """
    campaign = get_object_or_404(Campaign, id=id)
    list_obj = get_object_or_404(campaign.lists, id=list_id)
    attribute_type = get_object_or_404(
        CampaignAttributeType, id=type_id, campaign=campaign
    )

    if request.user != list_obj.owner and request.user != campaign.owner:
        messages.error(
            request, "You don't have permission to modify this Gang's attributes."
        )
        return HttpResponseRedirect(
            reverse("core:campaign-attributes", args=(campaign.id,))
        )

    if campaign.archived:
        messages.error(request, "Cannot modify attributes for archived Campaigns.")
        return HttpResponseRedirect(
            reverse("core:campaign-attributes", args=(campaign.id,))
        )

    default_url = reverse("core:campaign-attributes", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        form = CampaignListAttributeAssignmentForm(
            request.POST,
            campaign=campaign,
            list_obj=list_obj,
            attribute_type=attribute_type,
        )
        if form.is_valid():
            try:
                form.save(user=request.user)

                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.UPDATE,
                    object=campaign,
                    request=request,
                    campaign_id=str(campaign.id),
                    campaign_name=campaign.name,
                    action="assign_list_attribute",
                    list_name=list_obj.name,
                    attribute_type_name=attribute_type.name,
                )

                messages.success(
                    request,
                    f"{attribute_type.name} updated for {list_obj.name}.",
                )
            except ValidationError as e:
                messages.error(request, str(e))

            return safe_redirect(request, return_url, fallback_url=default_url)
    else:
        form = CampaignListAttributeAssignmentForm(
            campaign=campaign,
            list_obj=list_obj,
            attribute_type=attribute_type,
        )

    return render(
        request,
        "core/campaign/campaign_list_attribute_assign.html",
        {
            "form": form,
            "campaign": campaign,
            "list": list_obj,
            "attribute_type": attribute_type,
            "return_url": return_url,
        },
    )
