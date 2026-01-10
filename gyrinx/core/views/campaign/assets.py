"""Campaign asset management views."""

from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.forms.campaign import (
    AssetTransferForm,
    CampaignAssetForm,
    CampaignAssetTypeForm,
)
from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAction,
    CampaignAsset,
    CampaignAssetType,
)
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.utils import get_return_url, safe_redirect
from gyrinx.tracker import track


@login_required
def campaign_assets(request, id):
    """
    Manage assets for a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` whose assets are being managed.
    ``asset_types``
        List of :model:`core.CampaignAssetType` objects for this campaign.

    **Template**

    :template:`core/campaign/campaign_assets.html`
    """
    campaign = get_object_or_404(Campaign, id=id)

    # Get the IDs of lists currently in the campaign
    campaign_list_ids = campaign.lists.values_list("id", flat=True)

    # Get all asset types for this campaign with their assets
    # Only include assets held by lists that are currently in the campaign (or unowned assets)
    # select_related("asset_type") is needed for properties_with_labels to access property_schema
    asset_types = campaign.asset_types.prefetch_related(
        models.Prefetch(
            "assets",
            queryset=CampaignAsset.objects.filter(
                models.Q(holder_id__in=campaign_list_ids)
                | models.Q(holder__isnull=True)
            ).select_related("holder", "asset_type"),
        )
    )

    # Log viewing campaign assets
    if request.user.is_authenticated:
        log_event(
            user=request.user,
            noun=EventNoun.CAMPAIGN_ASSET,
            verb=EventVerb.VIEW,
            object=campaign,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            asset_types_count=asset_types.count(),
        )

    return render(
        request,
        "core/campaign/campaign_assets.html",
        {
            "campaign": campaign,
            "asset_types": asset_types,
            "is_owner": request.user == campaign.owner,
        },
    )


@login_required
def campaign_asset_type_new(request, id):
    """
    Create a new asset type for a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the asset type is being created for.
    ``form``
        A CampaignAssetTypeForm for creating the asset type.

    **Template**

    :template:`core/campaign/campaign_asset_type_new.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    # Prevent creation of new asset types for archived campaigns
    if campaign.archived:
        messages.error(
            request,
            "Cannot create new asset types for archived campaigns.",
        )
        return redirect("core:campaign-assets", campaign.id)

    if request.method == "POST":
        form = CampaignAssetTypeForm(request.POST, campaign=campaign)
        if form.is_valid():
            asset_type = form.save(commit=False)
            asset_type.campaign = campaign
            asset_type.owner = request.user
            asset_type.save()

            # Log the asset type creation
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_ASSET,
                verb=EventVerb.CREATE,
                object=asset_type,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                asset_type_name=asset_type.name_singular,
                asset_type_plural=asset_type.name_plural,
            )

            track(
                "campaign_asset_type_created",
                campaign_id=str(campaign.id),
                has_properties=bool(asset_type.property_schema),
                has_sub_assets=bool(asset_type.sub_asset_schema),
            )

            messages.success(
                request, f"Asset type '{asset_type.name_singular}' created."
            )
            return HttpResponseRedirect(
                reverse("core:campaign-assets", args=(campaign.id,))
            )
    else:
        form = CampaignAssetTypeForm(campaign=campaign)

    return render(
        request,
        "core/campaign/campaign_asset_type_new.html",
        {"form": form, "campaign": campaign},
    )


@login_required
def campaign_asset_type_edit(request, id, type_id):
    """
    Edit an existing asset type.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the asset type belongs to.
    ``asset_type``
        The :model:`core.CampaignAssetType` being edited.
    ``form``
        A CampaignAssetTypeForm for editing the asset type.

    **Template**

    :template:`core/campaign/campaign_asset_type_edit.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    asset_type = get_object_or_404(CampaignAssetType, id=type_id, campaign=campaign)

    if request.method == "POST":
        form = CampaignAssetTypeForm(request.POST, instance=asset_type)
        if form.is_valid():
            form.save()

            # Log the asset type update
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_ASSET,
                verb=EventVerb.UPDATE,
                object=asset_type,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                asset_type_name=asset_type.name_singular,
                asset_type_plural=asset_type.name_plural,
            )

            messages.success(request, "Asset type updated.")
            return HttpResponseRedirect(
                reverse("core:campaign-assets", args=(campaign.id,))
            )
    else:
        form = CampaignAssetTypeForm(instance=asset_type)

    return render(
        request,
        "core/campaign/campaign_asset_type_edit.html",
        {"form": form, "campaign": campaign, "asset_type": asset_type},
    )


@login_required
@transaction.atomic
def campaign_asset_type_remove(request, id, type_id):
    """
    Remove an asset type from a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the asset type belongs to.
    ``asset_type``
        The :model:`core.CampaignAssetType` being removed.

    **Template**

    :template:`core/campaign/campaign_asset_type_remove.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    asset_type = get_object_or_404(CampaignAssetType, id=type_id, campaign=campaign)

    # Prevent removal from archived campaigns
    if campaign.archived:
        messages.error(request, "Cannot remove asset types from archived campaigns.")
        return HttpResponseRedirect(
            reverse("core:campaign-assets", args=(campaign.id,))
        )

    if request.method == "POST":
        # Store info for logging before deletion
        asset_type_name = asset_type.name_singular
        asset_type_plural = asset_type.name_plural
        assets_count = asset_type.assets.count()

        # Delete the asset type (cascades to assets)
        asset_type.delete()

        # Log the removal event
        log_event(
            user=request.user,
            noun=EventNoun.CAMPAIGN_ASSET,
            verb=EventVerb.DELETE,
            object=campaign,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            asset_type_name=asset_type_name,
            asset_type_plural=asset_type_plural,
            assets_deleted=assets_count,
        )

        messages.success(request, f"Asset type '{asset_type_name}' has been removed.")

        return HttpResponseRedirect(
            reverse("core:campaign-assets", args=(campaign.id,))
        )

    # GET request - show confirmation page
    return render(
        request,
        "core/campaign/campaign_asset_type_remove.html",
        {
            "campaign": campaign,
            "asset_type": asset_type,
            "assets_count": asset_type.assets.count(),
        },
    )


@login_required
def campaign_asset_new(request, id, type_id):
    """
    Create a new asset for a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the asset is being created for.
    ``asset_type``
        The :model:`core.CampaignAssetType` this asset belongs to.
    ``form``
        A CampaignAssetForm for creating the asset.

    **Template**

    :template:`core/campaign/campaign_asset_new.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    asset_type: CampaignAssetType = get_object_or_404(
        CampaignAssetType, id=type_id, campaign=campaign
    )

    # Prevent creation of new assets for archived campaigns
    if campaign.archived:
        messages.error(
            request,
            "Cannot create new assets for archived campaigns.",
        )
        return redirect("core:campaign-assets", campaign.id)

    if request.method == "POST":
        form = CampaignAssetForm(request.POST, asset_type=asset_type, campaign=campaign)
        if form.is_valid():
            asset: CampaignAsset = form.save(commit=False)
            asset.asset_type = asset_type
            asset.owner = request.user
            asset.save()

            # Log the asset creation event
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_ASSET,
                verb=EventVerb.CREATE,
                object=asset,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                asset_name=asset.name,
                asset_type=asset_type.name_singular,
            )

            track(
                "campaign_asset_created",
                campaign_id=str(campaign.id),
                asset_type=asset_type.name_singular,
            )

            messages.success(request, f"Asset '{asset.name}' created.")

            # Check which button was clicked
            if "save_and_add_another" in request.POST:
                # Redirect back to the same form to create another
                return HttpResponseRedirect(
                    reverse(
                        "core:campaign-asset-new", args=(campaign.id, asset_type.id)
                    )
                )
            else:
                # Default: redirect to assets list
                return HttpResponseRedirect(
                    reverse("core:campaign-assets", args=(campaign.id,))
                )
    else:
        form = CampaignAssetForm(asset_type=asset_type, campaign=campaign)

    return render(
        request,
        "core/campaign/campaign_asset_new.html",
        {"form": form, "campaign": campaign, "asset_type": asset_type},
    )


@login_required
def campaign_asset_edit(request, id, asset_id):
    """
    Edit an existing asset.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the asset belongs to.
    ``asset``
        The :model:`core.CampaignAsset` being edited.
    ``form``
        A CampaignAssetForm for editing the asset.

    **Template**

    :template:`core/campaign/campaign_asset_edit.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    asset = get_object_or_404(CampaignAsset, id=asset_id, asset_type__campaign=campaign)

    if request.method == "POST":
        form = CampaignAssetForm(request.POST, instance=asset, campaign=campaign)
        if form.is_valid():
            form.save()

            # Log the asset update
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_ASSET,
                verb=EventVerb.UPDATE,
                object=asset,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                asset_name=asset.name,
                asset_description=asset.description[:100]
                if asset.description
                else None,
                asset_holder=asset.holder.name if asset.holder else None,
            )

            messages.success(request, "Asset updated.")
            return HttpResponseRedirect(
                reverse("core:campaign-assets", args=(campaign.id,))
            )
    else:
        form = CampaignAssetForm(instance=asset, campaign=campaign)

    return render(
        request,
        "core/campaign/campaign_asset_edit.html",
        {"form": form, "campaign": campaign, "asset": asset},
    )


@login_required
def campaign_asset_transfer(request, id, asset_id):
    """
    Transfer an asset to a new holder.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the asset belongs to.
    ``asset``
        The :model:`core.CampaignAsset` being transferred.
    ``form``
        An AssetTransferForm for selecting the new holder.

    **Template**

    :template:`core/campaign/campaign_asset_transfer.html`
    """
    campaign = get_object_or_404(Campaign, id=id)
    asset = get_object_or_404(CampaignAsset, id=asset_id, asset_type__campaign=campaign)

    # Check if user has permission: must be either campaign owner or owner of the list holding the asset
    has_permission = request.user == campaign.owner or (
        asset.holder and request.user == asset.holder.owner
    )

    if not has_permission:
        messages.error(request, "You don't have permission to transfer this asset.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Check if campaign is archived
    if campaign.archived:
        messages.error(request, "Cannot transfer assets for archived campaigns.")
        return HttpResponseRedirect(
            reverse("core:campaign-assets", args=(campaign.id,))
        )

    # Check if campaign has started
    if campaign.is_pre_campaign:
        messages.error(
            request, "Assets cannot be transferred before the campaign starts."
        )
        return HttpResponseRedirect(
            reverse("core:campaign-assets", args=(campaign.id,))
        )

    # Get return URL for back/cancel navigation
    default_url = reverse("core:campaign-assets", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        form = AssetTransferForm(request.POST, asset=asset)
        if form.is_valid():
            new_holder = form.cleaned_data["new_holder"]
            old_holder = asset.holder
            asset.transfer_to(new_holder, user=request.user)

            # Log the asset transfer
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_ASSET,
                verb=EventVerb.UPDATE,
                object=asset,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                asset_name=asset.name,
                transfer_from=old_holder.name if old_holder else "Unassigned",
                transfer_to=new_holder.name if new_holder else "Unassigned",
                action="transfer",
            )

            track(
                "campaign_asset_transferred",
                campaign_id=str(campaign.id),
                asset_type=asset.asset_type.name_singular,
            )

            messages.success(request, "Asset transferred successfully.")
            return safe_redirect(request, return_url, fallback_url=default_url)
    else:
        form = AssetTransferForm(asset=asset)

    return render(
        request,
        "core/campaign/campaign_asset_transfer.html",
        {"form": form, "campaign": campaign, "asset": asset, "return_url": return_url},
    )


@login_required
@transaction.atomic
def campaign_asset_remove(request, id, asset_id):
    """
    Remove an individual asset from a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the asset belongs to.
    ``asset``
        The :model:`core.CampaignAsset` being removed.

    **Template**

    :template:`core/campaign/campaign_asset_remove.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    asset = get_object_or_404(CampaignAsset, id=asset_id, asset_type__campaign=campaign)

    # Prevent removal from archived campaigns
    if campaign.archived:
        messages.error(request, "Cannot remove assets from archived campaigns.")
        return HttpResponseRedirect(
            reverse("core:campaign-assets", args=(campaign.id,))
        )

    if request.method == "POST":
        # Store info for logging before deletion
        asset_name = asset.name
        asset_type_name = asset.asset_type.name_singular
        holder_name = asset.holder.name if asset.holder else "Unowned"

        # Delete the asset
        asset.delete()

        if campaign.is_in_progress:
            # Create campaign action for asset deletion
            CampaignAction.objects.create(
                campaign=campaign,
                user=request.user,
                owner=request.user,
                description=f"Asset Removed: {asset_name} ({asset_type_name}) has been removed from the campaign",
            )

        # Log the removal event
        log_event(
            user=request.user,
            noun=EventNoun.CAMPAIGN_ASSET,
            verb=EventVerb.DELETE,
            object=campaign,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            asset_name=asset_name,
            asset_type=asset_type_name,
            holder=holder_name,
        )

        messages.success(request, f"Asset '{asset_name}' has been removed.")

        return HttpResponseRedirect(
            reverse("core:campaign-assets", args=(campaign.id,))
        )

    # GET request - show confirmation page
    return render(
        request,
        "core/campaign/campaign_asset_remove.html",
        {
            "campaign": campaign,
            "asset": asset,
        },
    )
