"""Campaign copy functionality views."""

from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.forms.campaign import CampaignCopyFromForm, CampaignCopyToForm
from gyrinx.core.handlers.campaign_copy import (
    check_copy_conflicts,
    copy_campaign_content,
)
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.tracker import track


@login_required
def campaign_copy_from(request, id):
    """Copy assets and resources FROM another campaign TO this campaign.

    This view allows a campaign admin to copy asset types, assets (with sub-assets),
    and resource types from another campaign they own or from template campaigns
    into the current campaign.
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if campaign.archived:
        messages.error(request, "Cannot copy to an archived campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Check if user has other campaigns or template campaigns to copy from
    other_campaigns = Campaign.objects.filter(owner=request.user).exclude(
        pk=campaign.pk
    )
    template_campaigns_exist = (
        Campaign.objects.filter(template=True).exclude(pk=campaign.pk).exists()
    )
    if not other_campaigns.exists() and not template_campaigns_exist:
        messages.info(
            request,
            "You don't have any other campaigns to copy from. "
            "Create another campaign with assets and resources first.",
        )
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    source_campaign = None
    conflicts = None
    show_confirmation = False

    if request.method == "POST":
        action = request.POST.get("action", "preview")

        # If confirming after preview, get the source campaign from hidden field
        if action == "confirm":
            source_id = request.POST.get("source_campaign_id")
            if source_id:
                source_campaign = get_object_or_404(
                    Campaign.objects.filter(
                        models.Q(owner=request.user) | models.Q(template=True)
                    ),
                    id=source_id,
                )

                # Validate source campaign is not archived (race condition check)
                if source_campaign.archived:
                    messages.error(request, "Cannot copy from an archived campaign.")
                    return HttpResponseRedirect(
                        reverse("core:campaign", args=(campaign.id,))
                    )

                # Get selected types from hidden fields
                asset_type_ids = request.POST.getlist("selected_asset_types")
                resource_type_ids = request.POST.getlist("selected_resource_types")
                attribute_type_ids = request.POST.getlist("selected_attribute_types")

                # Perform the copy
                result = copy_campaign_content(
                    source_campaign=source_campaign,
                    target_campaign=campaign,
                    user=request.user,
                    asset_type_ids=asset_type_ids if asset_type_ids else None,
                    resource_type_ids=resource_type_ids if resource_type_ids else None,
                    attribute_type_ids=(
                        attribute_type_ids if attribute_type_ids else None
                    ),
                )

                # Log event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.UPDATE,
                    object=campaign,
                    request=request,
                    campaign_id=str(campaign.id),
                    campaign_name=campaign.name,
                    action="copy_from",
                    source_campaign_id=str(source_campaign.id),
                    source_campaign_name=source_campaign.name,
                    asset_types_copied=result.asset_types_copied,
                    assets_copied=result.assets_copied,
                    sub_assets_copied=result.sub_assets_copied,
                    resource_types_copied=result.resource_types_copied,
                    attribute_types_copied=result.attribute_types_copied,
                    attribute_values_copied=result.attribute_values_copied,
                )

                track(
                    "campaign_copy_from",
                    campaign_id=str(campaign.id),
                    source_campaign_id=str(source_campaign.id),
                    asset_types_copied=result.asset_types_copied,
                    assets_copied=result.assets_copied,
                    resource_types_copied=result.resource_types_copied,
                    attribute_types_copied=result.attribute_types_copied,
                )

                # Build success message
                parts = []
                if result.asset_types_copied:
                    parts.append(f"{result.asset_types_copied} asset type(s)")
                if result.assets_copied:
                    parts.append(f"{result.assets_copied} asset(s)")
                if result.sub_assets_copied:
                    parts.append(f"{result.sub_assets_copied} sub-asset(s)")
                if result.resource_types_copied:
                    parts.append(f"{result.resource_types_copied} resource type(s)")
                if result.attribute_types_copied:
                    parts.append(f"{result.attribute_types_copied} attribute type(s)")
                if result.attribute_values_copied:
                    parts.append(f"{result.attribute_values_copied} attribute value(s)")

                if parts:
                    messages.success(
                        request,
                        f"Successfully copied {', '.join(parts)} from {source_campaign.name}.",
                    )
                else:
                    messages.info(
                        request,
                        "No new content was copied (all items already exist or were skipped).",
                    )

                return HttpResponseRedirect(
                    reverse("core:campaign", args=(campaign.id,))
                )

        # Preview mode - check for source selection first
        source_id = request.POST.get("source_campaign")
        if source_id:
            source_campaign = get_object_or_404(
                Campaign.objects.filter(
                    models.Q(owner=request.user) | models.Q(template=True)
                ),
                id=source_id,
            )

            # Create form with source campaign for type selection
            form = CampaignCopyFromForm(
                request.POST,
                target_campaign=campaign,
                user=request.user,
                source_campaign_obj=source_campaign,
            )

            if form.is_valid():
                asset_type_ids = form.cleaned_data.get("asset_types", [])
                resource_type_ids = form.cleaned_data.get("resource_types", [])
                attribute_type_ids = form.cleaned_data.get("attribute_types", [])

                # Check for conflicts
                conflicts = check_copy_conflicts(
                    source_campaign=source_campaign,
                    target_campaign=campaign,
                    asset_type_ids=asset_type_ids if asset_type_ids else None,
                    resource_type_ids=resource_type_ids if resource_type_ids else None,
                    attribute_type_ids=(
                        attribute_type_ids if attribute_type_ids else None
                    ),
                )

                show_confirmation = True
        else:
            form = CampaignCopyFromForm(
                target_campaign=campaign,
                user=request.user,
            )
    else:
        form = CampaignCopyFromForm(
            target_campaign=campaign,
            user=request.user,
        )

    # Get template campaigns (exclude the target campaign)
    template_campaigns = (
        Campaign.objects.filter(template=True).exclude(pk=campaign.pk).order_by("name")
    )

    return render(
        request,
        "core/campaign/campaign_copy_from.html",
        {
            "campaign": campaign,
            "form": form,
            "source_campaign": source_campaign,
            "conflicts": conflicts,
            "show_confirmation": show_confirmation,
            "template_campaigns": template_campaigns,
        },
    )


@login_required
def campaign_copy_to(request, id):
    """Copy assets and resources FROM this campaign TO another campaign.

    This view allows any user to copy asset types, assets (with sub-assets),
    and resource types from a campaign they can view to their own campaigns.
    This enables "template campaigns" that others can copy from.
    """
    # Allow copying from any campaign the user can access (owned or public)
    campaign = get_object_or_404(
        Campaign.objects.filter(models.Q(owner=request.user) | models.Q(public=True)),
        id=id,
    )

    # Check if this campaign has any content to copy
    has_asset_types = campaign.asset_types.exists()
    has_resource_types = campaign.resource_types.exists()
    has_attribute_types = campaign.attribute_types.exists()
    if not has_asset_types and not has_resource_types and not has_attribute_types:
        messages.info(
            request,
            "This campaign has no asset types, resource types, or attribute types to copy.",
        )
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Check if user has other campaigns to copy to
    other_campaigns = Campaign.objects.filter(
        owner=request.user, archived=False
    ).exclude(pk=campaign.pk)
    if not other_campaigns.exists():
        messages.info(
            request,
            "You don't have any other campaigns to copy to. "
            "Create another campaign first.",
        )
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    target_campaign = None
    conflicts = None
    show_confirmation = False

    if request.method == "POST":
        action = request.POST.get("action", "preview")

        # If confirming after preview
        if action == "confirm":
            target_id = request.POST.get("target_campaign_id")
            if target_id:
                target_campaign = get_object_or_404(
                    Campaign, id=target_id, owner=request.user
                )

                # Validate target campaign is not archived (race condition check)
                if target_campaign.archived:
                    messages.error(request, "Cannot copy to an archived campaign.")
                    return HttpResponseRedirect(
                        reverse("core:campaign", args=(campaign.id,))
                    )

                # Get selected types from hidden fields
                asset_type_ids = request.POST.getlist("selected_asset_types")
                resource_type_ids = request.POST.getlist("selected_resource_types")
                attribute_type_ids = request.POST.getlist("selected_attribute_types")

                # Perform the copy
                result = copy_campaign_content(
                    source_campaign=campaign,
                    target_campaign=target_campaign,
                    user=request.user,
                    asset_type_ids=asset_type_ids if asset_type_ids else None,
                    resource_type_ids=resource_type_ids if resource_type_ids else None,
                    attribute_type_ids=(
                        attribute_type_ids if attribute_type_ids else None
                    ),
                )

                # Log event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.UPDATE,
                    object=target_campaign,
                    request=request,
                    campaign_id=str(target_campaign.id),
                    campaign_name=target_campaign.name,
                    action="copy_to",
                    source_campaign_id=str(campaign.id),
                    source_campaign_name=campaign.name,
                    asset_types_copied=result.asset_types_copied,
                    assets_copied=result.assets_copied,
                    sub_assets_copied=result.sub_assets_copied,
                    resource_types_copied=result.resource_types_copied,
                    attribute_types_copied=result.attribute_types_copied,
                    attribute_values_copied=result.attribute_values_copied,
                )

                track(
                    "campaign_copy_to",
                    campaign_id=str(campaign.id),
                    target_campaign_id=str(target_campaign.id),
                    asset_types_copied=result.asset_types_copied,
                    assets_copied=result.assets_copied,
                    resource_types_copied=result.resource_types_copied,
                    attribute_types_copied=result.attribute_types_copied,
                )

                # Build success message
                parts = []
                if result.asset_types_copied:
                    parts.append(f"{result.asset_types_copied} asset type(s)")
                if result.assets_copied:
                    parts.append(f"{result.assets_copied} asset(s)")
                if result.sub_assets_copied:
                    parts.append(f"{result.sub_assets_copied} sub-asset(s)")
                if result.resource_types_copied:
                    parts.append(f"{result.resource_types_copied} resource type(s)")
                if result.attribute_types_copied:
                    parts.append(f"{result.attribute_types_copied} attribute type(s)")
                if result.attribute_values_copied:
                    parts.append(f"{result.attribute_values_copied} attribute value(s)")

                if parts:
                    messages.success(
                        request,
                        f"Successfully copied {', '.join(parts)} to {target_campaign.name}.",
                    )
                else:
                    messages.info(
                        request,
                        "No new content was copied (all items already exist or were skipped).",
                    )

                return HttpResponseRedirect(
                    reverse("core:campaign", args=(target_campaign.id,))
                )

        # Preview mode
        form = CampaignCopyToForm(
            request.POST,
            source_campaign=campaign,
            user=request.user,
        )

        if form.is_valid():
            target_campaign = form.cleaned_data["target_campaign"]
            asset_type_ids = form.cleaned_data.get("asset_types", [])
            resource_type_ids = form.cleaned_data.get("resource_types", [])
            attribute_type_ids = form.cleaned_data.get("attribute_types", [])

            # Check for conflicts
            conflicts = check_copy_conflicts(
                source_campaign=campaign,
                target_campaign=target_campaign,
                asset_type_ids=asset_type_ids if asset_type_ids else None,
                resource_type_ids=resource_type_ids if resource_type_ids else None,
                attribute_type_ids=(attribute_type_ids if attribute_type_ids else None),
            )

            show_confirmation = True
    else:
        form = CampaignCopyToForm(
            source_campaign=campaign,
            user=request.user,
        )

    return render(
        request,
        "core/campaign/campaign_copy_to.html",
        {
            "campaign": campaign,
            "form": form,
            "target_campaign": target_campaign,
            "conflicts": conflicts,
            "show_confirmation": show_confirmation,
        },
    )
