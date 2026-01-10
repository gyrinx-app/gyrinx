"""Campaign sub-asset management views."""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.forms.campaign import CampaignSubAssetForm
from gyrinx.core.models.campaign import Campaign, CampaignAsset, CampaignSubAsset
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.tracker import track


@login_required
def campaign_sub_asset_new(request, id, asset_id, sub_asset_type):
    """
    Create a new sub-asset for a campaign asset.

    **Context**

    ``campaign``
        The :model:`core.Campaign` containing the asset.
    ``asset``
        The :model:`core.CampaignAsset` parent asset.
    ``sub_asset_type_key``
        The key of the sub-asset type being created.
    ``sub_asset_type_def``
        The schema definition for this sub-asset type.
    ``form``
        The :form:`core.CampaignSubAssetForm` for creating the sub-asset.

    **Template**

    :template:`core/campaign/campaign_sub_asset_new.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    asset = get_object_or_404(CampaignAsset, id=asset_id, asset_type__campaign=campaign)

    if campaign.archived:
        messages.error(request, "Cannot create sub-assets for archived campaigns.")
        return HttpResponseRedirect(
            reverse("core:campaign-asset-edit", args=(campaign.id, asset.id))
        )

    # Validate sub_asset_type exists in schema
    sub_asset_schemas = asset.asset_type.sub_asset_schema or {}
    if sub_asset_type not in sub_asset_schemas:
        messages.error(request, f"Invalid sub-asset type: {sub_asset_type}")
        return HttpResponseRedirect(
            reverse("core:campaign-asset-edit", args=(campaign.id, asset.id))
        )

    sub_asset_type_def = sub_asset_schemas[sub_asset_type]

    if request.method == "POST":
        form = CampaignSubAssetForm(
            request.POST,
            parent_asset=asset,
            sub_asset_type=sub_asset_type,
        )
        if form.is_valid():
            sub_asset = form.save(commit=False)
            sub_asset.parent_asset = asset
            sub_asset.sub_asset_type = sub_asset_type
            sub_asset.owner = request.user
            sub_asset.save()

            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_ASSET,
                verb=EventVerb.UPDATE,
                object=asset,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                sub_asset_name=sub_asset.name,
                sub_asset_type=sub_asset_type_def.get("label", sub_asset_type),
                action="added_sub_asset",
            )

            track(
                "campaign_sub_asset_created",
                campaign_id=str(campaign.id),
                sub_asset_type=sub_asset_type,
            )

            messages.success(
                request,
                f"{sub_asset_type_def.get('label', sub_asset_type)} '{sub_asset.name}' created.",
            )
            return HttpResponseRedirect(
                reverse("core:campaign-asset-edit", args=(campaign.id, asset.id))
            )
    else:
        form = CampaignSubAssetForm(
            parent_asset=asset,
            sub_asset_type=sub_asset_type,
        )

    return render(
        request,
        "core/campaign/campaign_sub_asset_new.html",
        {
            "campaign": campaign,
            "asset": asset,
            "sub_asset_type_key": sub_asset_type,
            "sub_asset_type_def": sub_asset_type_def,
            "form": form,
        },
    )


@login_required
def campaign_sub_asset_edit(request, id, asset_id, sub_asset_id):
    """
    Edit an existing sub-asset.

    **Context**

    ``campaign``
        The :model:`core.Campaign` containing the asset.
    ``asset``
        The :model:`core.CampaignAsset` parent asset.
    ``sub_asset``
        The :model:`core.CampaignSubAsset` being edited.
    ``sub_asset_type_def``
        The schema definition for this sub-asset type.
    ``form``
        The :form:`core.CampaignSubAssetForm` for editing the sub-asset.

    **Template**

    :template:`core/campaign/campaign_sub_asset_edit.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    asset = get_object_or_404(CampaignAsset, id=asset_id, asset_type__campaign=campaign)
    sub_asset = get_object_or_404(CampaignSubAsset, id=sub_asset_id, parent_asset=asset)

    if campaign.archived:
        messages.error(request, "Cannot edit sub-assets for archived campaigns.")
        return HttpResponseRedirect(
            reverse("core:campaign-asset-edit", args=(campaign.id, asset.id))
        )

    sub_asset_schemas = asset.asset_type.sub_asset_schema or {}
    sub_asset_type_def = sub_asset_schemas.get(sub_asset.sub_asset_type, {})

    if request.method == "POST":
        form = CampaignSubAssetForm(
            request.POST,
            instance=sub_asset,
            parent_asset=asset,
            sub_asset_type=sub_asset.sub_asset_type,
        )
        if form.is_valid():
            form.save()

            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_ASSET,
                verb=EventVerb.UPDATE,
                object=asset,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                sub_asset_name=sub_asset.name,
                sub_asset_type=sub_asset_type_def.get(
                    "label", sub_asset.sub_asset_type
                ),
                action="updated_sub_asset",
            )

            messages.success(request, f"'{sub_asset.name}' updated.")
            return HttpResponseRedirect(
                reverse("core:campaign-asset-edit", args=(campaign.id, asset.id))
            )
    else:
        form = CampaignSubAssetForm(
            instance=sub_asset,
            parent_asset=asset,
            sub_asset_type=sub_asset.sub_asset_type,
        )

    return render(
        request,
        "core/campaign/campaign_sub_asset_edit.html",
        {
            "campaign": campaign,
            "asset": asset,
            "sub_asset": sub_asset,
            "sub_asset_type_def": sub_asset_type_def,
            "form": form,
        },
    )


@login_required
@transaction.atomic
def campaign_sub_asset_remove(request, id, asset_id, sub_asset_id):
    """
    Remove a sub-asset.

    **Context**

    ``campaign``
        The :model:`core.Campaign` containing the asset.
    ``asset``
        The :model:`core.CampaignAsset` parent asset.
    ``sub_asset``
        The :model:`core.CampaignSubAsset` being removed.
    ``sub_asset_type_def``
        The schema definition for this sub-asset type.

    **Template**

    :template:`core/campaign/campaign_sub_asset_remove.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    asset = get_object_or_404(CampaignAsset, id=asset_id, asset_type__campaign=campaign)
    sub_asset = get_object_or_404(CampaignSubAsset, id=sub_asset_id, parent_asset=asset)

    if campaign.archived:
        messages.error(request, "Cannot remove sub-assets from archived campaigns.")
        return HttpResponseRedirect(
            reverse("core:campaign-asset-edit", args=(campaign.id, asset.id))
        )

    sub_asset_schemas = asset.asset_type.sub_asset_schema or {}
    sub_asset_type_def = sub_asset_schemas.get(sub_asset.sub_asset_type, {})

    if request.method == "POST":
        sub_asset_name = sub_asset.name
        sub_asset_type_key = sub_asset.sub_asset_type
        sub_asset_type_label = sub_asset_type_def.get("label", sub_asset.sub_asset_type)
        sub_asset.delete()

        log_event(
            user=request.user,
            noun=EventNoun.CAMPAIGN_ASSET,
            verb=EventVerb.UPDATE,
            object=asset,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            sub_asset_name=sub_asset_name,
            sub_asset_type=sub_asset_type_label,
            action="removed_sub_asset",
        )

        track(
            "campaign_sub_asset_removed",
            campaign_id=str(campaign.id),
            sub_asset_type=sub_asset_type_key,
        )

        messages.success(
            request,
            f"{sub_asset_type_label} '{sub_asset_name}' has been removed.",
        )
        return HttpResponseRedirect(
            reverse("core:campaign-asset-edit", args=(campaign.id, asset.id))
        )

    return render(
        request,
        "core/campaign/campaign_sub_asset_remove.html",
        {
            "campaign": campaign,
            "asset": asset,
            "sub_asset": sub_asset,
            "sub_asset_type_def": sub_asset_type_def,
        },
    )
