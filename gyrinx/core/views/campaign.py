from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db import models, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import generic

from gyrinx.core.forms.campaign import (
    AssetTransferForm,
    CampaignActionForm,
    CampaignActionOutcomeForm,
    CampaignAssetForm,
    CampaignAssetTypeForm,
    CampaignResourceTypeForm,
    EditCampaignForm,
    NewCampaignForm,
    ResourceModifyForm,
)
from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAction,
    CampaignAsset,
    CampaignAssetType,
    CampaignListResource,
    CampaignResourceType,
)
from gyrinx.core.models.list import List, CapturedFighter


def get_campaign_resource_types_with_resources(campaign):
    """
    Get resource types with their list resources prefetched and ordered.

    This helper function ensures consistent prefetching across views.
    """
    return campaign.resource_types.prefetch_related(
        models.Prefetch(
            "list_resources",
            queryset=CampaignListResource.objects.select_related("list").order_by(
                "list__name"
            ),
        )
    )


class Campaigns(generic.ListView):
    template_name = "core/campaign/campaigns.html"
    context_object_name = "campaigns"

    def get_queryset(self):
        return Campaign.objects.filter(public=True)


class CampaignDetailView(generic.DetailView):
    """
    Display a single :model:`core.Campaign` object.

    **Context**

    ``campaign``
        The requested :model:`core.Campaign` object.

    **Template**

    :template:`core/campaign/campaign.html`
    """

    template_name = "core/campaign/campaign.html"
    context_object_name = "campaign"

    def get_object(self):
        """
        Retrieve the :model:`core.Campaign` by its `id` with prefetched actions.
        """
        return get_object_or_404(
            Campaign.objects.prefetch_related(
                models.Prefetch(
                    "actions",
                    queryset=CampaignAction.objects.select_related(
                        "user", "list"
                    ).order_by("-created"),
                )
            ),
            id=self.kwargs["id"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        campaign = self.object
        user = self.request.user

        # Check if user can log actions (owner or has a list in campaign, and campaign is in progress)
        if user.is_authenticated:
            context["can_log_actions"] = campaign.is_in_progress and (
                campaign.owner == user or campaign.lists.filter(owner=user).exists()
            )
        else:
            context["can_log_actions"] = False

        # Get asset types with their assets for the summary
        context["asset_types"] = campaign.asset_types.prefetch_related(
            models.Prefetch(
                "assets", queryset=CampaignAsset.objects.select_related("holder")
            )
        )

        # Get recent battles
        context["recent_battles"] = (
            campaign.battles.select_related("owner")
            .prefetch_related("participants", "winners")
            .order_by("-date", "-created")[:5]
        )

        # Get resource types with their list resources
        context["resource_types"] = get_campaign_resource_types_with_resources(campaign)

        context["is_owner"] = user == campaign.owner
        return context


@login_required
def campaign_add_lists(request, id):
    """
    Add lists to a campaign.

    Allows the campaign owner to search for and add lists to their campaign.
    Only available for campaigns in pre-campaign or in-progress status.

    **Context**

    ``campaign``
        The :model:`core.Campaign` being edited.
    ``lists``
        Available :model:`core.List` objects that can be added.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_add_lists.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    # Check if campaign is in a state where lists can be added
    if campaign.is_post_campaign:
        messages.error(request, "Lists cannot be added to a completed campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    error_message = None
    show_confirmation = False

    if request.method == "POST":
        list_id = request.POST.get("list_id")
        confirm = request.POST.get("confirm") == "true"

        if list_id:
            try:
                list_to_add = List.objects.get(id=list_id)
                # Check if user can add this list (either owner or public)
                if list_to_add.owner == request.user or list_to_add.public:
                    # For in-progress campaigns, require confirmation
                    if campaign.is_in_progress and not confirm:
                        show_confirmation = True
                        # Don't redirect, show confirmation instead
                    else:
                        # Use the new method to add the list
                        added_list = campaign.add_list_to_campaign(list_to_add)
                        # Show success message
                        messages.success(
                            request,
                            f"{added_list.name}{f' ({added_list.content_house.name})' if added_list.content_house else ''} has been added to the campaign.",
                        )
                        # Redirect to the same page with the search params preserved
                        query_params = []
                        if request.GET.get("q"):
                            query_params.append(f"q={request.GET.get('q')}")
                        if request.GET.get("owner"):
                            query_params.append(f"owner={request.GET.get('owner')}")
                        query_str = "&".join(query_params)
                        return HttpResponseRedirect(
                            reverse("core:campaign-add-lists", args=(campaign.id,))
                            + (f"?{query_str}" if query_str else "")
                        )
                else:
                    error_message = "You can only add your own lists or public lists."
            except List.DoesNotExist:
                error_message = "List not found."

    # Get lists that can be added (user's own lists or public lists)
    # Only show lists in list building mode and not archived
    lists = List.objects.filter(
        (models.Q(owner=request.user) | models.Q(public=True))
        & models.Q(status=List.LIST_BUILDING)
        & models.Q(archived=False)
    )

    # If the campaign has started, exclude lists that have been cloned into it
    if campaign.is_in_progress or campaign.is_post_campaign:
        # The campaign lists have original_list pointing to the source lists
        cloned_original_ids = campaign.lists.values_list("original_list_id", flat=True)
        lists = lists.exclude(id__in=cloned_original_ids)
    else:
        # Pre-campaign: exclude lists that are directly added
        lists = lists.exclude(id__in=campaign.lists.values_list("id", flat=True))

    # Apply search filter if provided
    if request.GET.get("q"):
        search_query = SearchQuery(request.GET.get("q"))
        lists = lists.annotate(
            search=SearchVector("name", "content_house__name", "owner__username")
        ).filter(search=search_query)

    # Filter by owner type
    owner_filter = request.GET.get("owner", "all")
    if owner_filter == "mine":
        lists = lists.filter(owner=request.user)
    elif owner_filter == "others":
        # Only show public lists from other users
        lists = lists.filter(public=True).exclude(owner=request.user)

    # Order by name
    lists = lists.order_by("name")

    # If showing confirmation, get the list to confirm
    list_to_confirm = None
    if show_confirmation and list_id:
        try:
            list_to_confirm = List.objects.get(id=list_id)
        except List.DoesNotExist:
            pass

    return render(
        request,
        "core/campaign/campaign_add_lists.html",
        {
            "campaign": campaign,
            "lists": lists,
            "error_message": error_message,
            "show_confirmation": show_confirmation,
            "list_to_confirm": list_to_confirm,
        },
    )


@login_required
def new_campaign(request):
    """
    Create a new :model:`core.Campaign` owned by the current user.

    **Context**

    ``form``
        A NewCampaignForm for entering the name and details of the new campaign.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_new.html`
    """
    error_message = None
    if request.method == "POST":
        form = NewCampaignForm(request.POST)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.owner = request.user
            campaign.save()

            # Automatically create a "Reputation" resource type for all campaigns
            CampaignResourceType.objects.create(
                campaign=campaign,
                name="Reputation",
                description="Gang reputation gained during the campaign",
                default_amount=0,
                owner=request.user,
            )

            return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))
    else:
        form = NewCampaignForm(
            initial={
                "name": request.GET.get("name", ""),
            }
        )

    return render(
        request,
        "core/campaign/campaign_new.html",
        {"form": form, "error_message": error_message},
    )


@login_required
def edit_campaign(request, id):
    """
    Edit an existing :model:`core.Campaign` owned by the current user.

    **Context**

    ``form``
        A EditCampaignForm for editing the campaign's details.
    ``campaign``
        The :model:`core.Campaign` being edited.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_edit.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    error_message = None
    if request.method == "POST":
        form = EditCampaignForm(request.POST, instance=campaign)
        if form.is_valid():
            updated_campaign = form.save(commit=False)
            updated_campaign.save()
            return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))
    else:
        form = EditCampaignForm(instance=campaign)

    return render(
        request,
        "core/campaign/campaign_edit.html",
        {"form": form, "campaign": campaign, "error_message": error_message},
    )


@login_required
def campaign_log_action(request, id):
    """
    Log a new action for a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the action is being logged for.
    ``form``
        A CampaignActionForm for entering the action details.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_log_action.html`
    """
    campaign = get_object_or_404(Campaign, id=id)

    # Check if user is part of the campaign (owner or has a list in it) and campaign is in progress
    user_lists_in_campaign = campaign.lists.filter(owner=request.user).exists()
    if not campaign.is_in_progress or (
        campaign.owner != request.user and not user_lists_in_campaign
    ):
        messages.error(request, "You cannot log actions for this campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    error_message = None
    if request.method == "POST":
        form = CampaignActionForm(request.POST, campaign=campaign, user=request.user)
        if form.is_valid():
            action = form.save(commit=False)
            action.campaign = campaign
            action.user = request.user
            action.save()

            # Redirect to outcome edit page
            return HttpResponseRedirect(
                reverse("core:campaign-action-outcome", args=(campaign.id, action.id))
            )
    else:
        form = CampaignActionForm(campaign=campaign, user=request.user)

    return render(
        request,
        "core/campaign/campaign_log_action.html",
        {"form": form, "campaign": campaign, "error_message": error_message},
    )


@login_required
def campaign_action_outcome(request, id, action_id):
    """
    Edit the outcome of a campaign action.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the action belongs to.
    ``action``
        The :model:`core.CampaignAction` being edited.
    ``form``
        A CampaignActionOutcomeForm for editing the outcome.
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_action_outcome.html`
    """
    campaign = get_object_or_404(Campaign, id=id)
    action = get_object_or_404(CampaignAction, id=action_id, campaign=campaign)

    # Check if user can edit this action (only the creator)
    if action.user != request.user:
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    error_message = None
    if request.method == "POST":
        form = CampaignActionOutcomeForm(request.POST, instance=action)
        if form.is_valid():
            form.save()

            # Check which button was clicked
            if "save_and_new" in request.POST:
                # Redirect to create another action
                return HttpResponseRedirect(
                    reverse("core:campaign-action-new", args=(campaign.id,))
                )
            else:
                # Default: redirect to campaign
                return HttpResponseRedirect(
                    reverse("core:campaign", args=(campaign.id,))
                )
    else:
        form = CampaignActionOutcomeForm(instance=action)

    return render(
        request,
        "core/campaign/campaign_action_outcome.html",
        {
            "form": form,
            "campaign": campaign,
            "action": action,
            "error_message": error_message,
        },
    )


class CampaignActionList(generic.ListView):
    """
    Display all actions for a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` whose actions are being displayed.
    ``object_list``
        The list of :model:`core.CampaignAction` objects.

    **Template**

    :template:`core/campaign/campaign_actions.html`
    """

    template_name = "core/campaign/campaign_actions.html"
    context_object_name = "actions"
    paginate_by = 50

    def get_queryset(self):
        self.campaign = get_object_or_404(Campaign, id=self.kwargs["id"])

        # Start with all campaign actions with list and battle relationships
        actions = self.campaign.actions.select_related(
            "user", "list", "battle"
        ).order_by("-created")

        # Apply text search filter if provided
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            actions = actions.annotate(
                search=SearchVector("description", "outcome", "user__username")
            ).filter(search=SearchQuery(search_query))

        # Apply gang filter if provided
        gang_id = self.request.GET.get("gang")
        if gang_id:
            # Filter actions by the specific list/gang
            actions = actions.filter(list_id=gang_id)

        # Apply author filter if provided
        author_id = self.request.GET.get("author")
        if author_id:
            actions = actions.filter(user__id=author_id)

        # Apply battle filter if provided
        battle_id = self.request.GET.get("battle")
        if battle_id:
            # Filter actions by the specific battle
            actions = actions.filter(battle_id=battle_id)

        # Apply timeframe filter if provided
        timeframe = self.request.GET.get("timeframe", "all")
        if timeframe != "all":
            now = timezone.now()
            if timeframe == "24h":
                actions = actions.filter(created__gte=now - timedelta(hours=24))
            elif timeframe == "7d":
                actions = actions.filter(created__gte=now - timedelta(days=7))
            elif timeframe == "30d":
                actions = actions.filter(created__gte=now - timedelta(days=30))

        return actions

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["campaign"] = self.campaign

        # Get all lists/gangs in the campaign for the gang filter
        context["campaign_lists"] = self.campaign.lists.select_related(
            "owner", "content_house"
        ).order_by("name")

        # Get all users who have performed actions for the author filter
        context["action_authors"] = (
            self.campaign.actions.values_list("user__id", "user__username")
            .distinct()
            .order_by("user__username")
        )

        # Get all battles in the campaign for the battle filter
        context["campaign_battles"] = (
            self.campaign.battles.select_related("owner")
            .prefetch_related("participants", "winners")
            .order_by("-date", "-created")
        )

        # Check if user can log actions (owner or has a list in campaign, and campaign is in progress)
        user = self.request.user
        if user.is_authenticated:
            context["can_log_actions"] = self.campaign.is_in_progress and (
                self.campaign.owner == user
                or self.campaign.lists.filter(owner=user).exists()
            )
        else:
            context["can_log_actions"] = False
        return context


@login_required
def start_campaign(request, id):
    """
    Start a campaign (transition from pre-campaign to in-progress).

    Only the campaign owner can start a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` to be started.

    **Template**

    :template:`core/campaign/campaign_start.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if request.method == "POST":
        with transaction.atomic():
            if campaign.start_campaign():
                # Log the campaign start action
                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=campaign,
                    description=f"Campaign Started: {campaign.name} is now active",
                    outcome="Campaign transitioned from pre-campaign to active status",
                )
                messages.success(request, "Campaign has been started!")
            else:
                if not campaign.lists.exists():
                    messages.error(request, "Cannot start campaign without any lists.")
                else:
                    messages.error(request, "Campaign cannot be started.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # For GET request, show confirmation page
    if not campaign.can_start_campaign():
        messages.error(request, "This campaign cannot be started.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    return render(
        request,
        "core/campaign/campaign_start.html",
        {"campaign": campaign},
    )


@login_required
def end_campaign(request, id):
    """
    End a campaign (transition from in-progress to post-campaign).

    Only the campaign owner can end a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` to be ended.

    **Template**

    :template:`core/campaign/campaign_end.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if request.method == "POST":
        with transaction.atomic():
            if campaign.end_campaign():
                # Log the campaign end action
                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=campaign,
                    description=f"Campaign Ended: {campaign.name} has concluded",
                    outcome="Campaign transitioned from active to post-campaign status",
                )
                messages.success(request, "Campaign has been ended!")
            else:
                messages.error(request, "Campaign cannot be ended.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # For GET request, show confirmation page
    if not campaign.can_end_campaign():
        messages.error(request, "This campaign cannot be ended.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    return render(
        request,
        "core/campaign/campaign_end.html",
        {"campaign": campaign},
    )


@login_required
def reopen_campaign(request, id):
    """
    Reopen a campaign (transition from post-campaign back to in-progress).

    Only the campaign owner can reopen a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` to be reopened.

    **Template**

    :template:`core/campaign/campaign_reopen.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if request.method == "POST":
        with transaction.atomic():
            if campaign.reopen_campaign():
                # Log the campaign reopen action
                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=campaign,
                    description=f"Campaign Reopened: {campaign.name} is active again",
                    outcome="Campaign transitioned from post-campaign back to active status",
                )
                messages.success(request, "Campaign has been reopened!")
            else:
                messages.error(request, "Campaign cannot be reopened.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # For GET request, show confirmation page
    if not campaign.can_reopen_campaign():
        messages.error(request, "This campaign cannot be reopened.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    return render(
        request,
        "core/campaign/campaign_reopen.html",
        {"campaign": campaign},
    )


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

    # Get all asset types for this campaign with their assets
    asset_types = campaign.asset_types.prefetch_related(
        models.Prefetch(
            "assets", queryset=CampaignAsset.objects.select_related("holder")
        )
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

    if request.method == "POST":
        form = CampaignAssetTypeForm(request.POST)
        if form.is_valid():
            asset_type = form.save(commit=False)
            asset_type.campaign = campaign
            asset_type.owner = request.user
            asset_type.save()
            messages.success(
                request, f"Asset type '{asset_type.name_singular}' created."
            )
            return HttpResponseRedirect(
                reverse("core:campaign-assets", args=(campaign.id,))
            )
    else:
        form = CampaignAssetTypeForm()

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
    asset_type = get_object_or_404(CampaignAssetType, id=type_id, campaign=campaign)

    if request.method == "POST":
        form = CampaignAssetForm(request.POST, asset_type=asset_type)
        if form.is_valid():
            asset = form.save(commit=False)
            asset.asset_type = asset_type
            asset.owner = request.user
            asset.save()
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
        form = CampaignAssetForm(asset_type=asset_type)

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
        form = CampaignAssetForm(request.POST, instance=asset)
        if form.is_valid():
            form.save()
            messages.success(request, "Asset updated.")
            return HttpResponseRedirect(
                reverse("core:campaign-assets", args=(campaign.id,))
            )
    else:
        form = CampaignAssetForm(instance=asset)

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
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)
    asset = get_object_or_404(CampaignAsset, id=asset_id, asset_type__campaign=campaign)

    if request.method == "POST":
        form = AssetTransferForm(request.POST, asset=asset)
        if form.is_valid():
            new_holder = form.cleaned_data["new_holder"]
            asset.transfer_to(new_holder, user=request.user)
            messages.success(request, "Asset transferred successfully.")
            return HttpResponseRedirect(
                reverse("core:campaign-assets", args=(campaign.id,))
            )
    else:
        form = AssetTransferForm(asset=asset)

    return render(
        request,
        "core/campaign/campaign_asset_transfer.html",
        {"form": form, "campaign": campaign, "asset": asset},
    )


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

    if request.method == "POST":
        form = CampaignResourceTypeForm(request.POST)
        if form.is_valid():
            resource_type = form.save(commit=False)
            resource_type.campaign = campaign
            resource_type.owner = request.user
            resource_type.save()

            # If campaign is already started, allocate resources to existing lists
            if campaign.is_in_progress:
                for list_obj in campaign.lists.all():
                    CampaignListResource.objects.create(
                        campaign=campaign,
                        resource_type=resource_type,
                        list=list_obj,
                        amount=resource_type.default_amount,
                        owner=request.user,
                    )

            messages.success(request, f"Resource type '{resource_type.name}' created.")
            return HttpResponseRedirect(
                reverse("core:campaign-resources", args=(campaign.id,))
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

    if request.method == "POST":
        form = ResourceModifyForm(request.POST, resource=resource)
        if form.is_valid():
            modification = form.cleaned_data["modification"]
            try:
                resource.modify_amount(modification, user=request.user)
                messages.success(request, "Resource updated successfully.")
            except ValueError as e:
                messages.error(request, str(e))
            return HttpResponseRedirect(
                reverse("core:campaign-resources", args=(campaign.id,))
            )
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
        },
    )


@login_required
def campaign_captured_fighters(request, id):
    """
    View all fighters captured by lists in this campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` whose captured fighters are being viewed.
    ``captured_fighters``
        QuerySet of :model:`core.CapturedFighter` objects.

    **Template**

    :template:`core/campaign/campaign_captured_fighters.html`
    """
    campaign = get_object_or_404(Campaign, id=id)

    # Check if user owns the campaign or any list in it
    if (
        campaign.owner != request.user
        and not campaign.lists.filter(owner=request.user).exists()
    ):
        messages.error(
            request,
            "You don't have permission to view this campaign's captured fighters.",
        )
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Get all captured fighters for lists in this campaign
    captured_fighters = (
        CapturedFighter.objects.filter(
            models.Q(capturing_list__campaigns=campaign)
            | models.Q(fighter__list__campaigns=campaign)
        )
        .select_related(
            "fighter", "fighter__list", "fighter__content_fighter", "capturing_list"
        )
        .order_by("-captured_at")
    )

    return render(
        request,
        "core/campaign/campaign_captured_fighters.html",
        {
            "campaign": campaign,
            "captured_fighters": captured_fighters,
        },
    )


@login_required
def fighter_sell_to_guilders(request, id, fighter_id):
    """
    Sell a captured fighter to the guilders.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the fighter belongs to.
    ``captured_fighter``
        The :model:`core.CapturedFighter` being sold.

    **Template**

    :template:`core/campaign/fighter_sell_to_guilders.html`
    """
    campaign = get_object_or_404(Campaign, id=id)
    captured_fighter = get_object_or_404(
        CapturedFighter,
        fighter_id=fighter_id,
        capturing_list__owner=request.user,
        sold_to_guilders=False,
    )

    if request.method == "POST":
        credits = request.POST.get("credits", 0)
        try:
            credits = int(credits) if credits else 0
            if credits < 0:
                raise ValueError("Credits cannot be negative")
        except ValueError:
            messages.error(request, "Invalid credit amount.")
            # Validate the redirect URL for security
            redirect_url = request.path
            if not url_has_allowed_host_and_scheme(
                url=redirect_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                redirect_url = reverse(
                    "core:campaign_captured_fighters", args=[campaign.id]
                )
            return HttpResponseRedirect(redirect_url)

        with transaction.atomic():
            # Sell the fighter
            captured_fighter.sell_to_guilders(credits=credits)

            # Add credits to capturing gang
            if credits > 0:
                captured_fighter.capturing_list.credits_current += credits
                captured_fighter.capturing_list.save()

            # Log campaign action
            CampaignAction.objects.create(
                campaign=campaign,
                user=request.user,
                list=captured_fighter.capturing_list,
                description=f"Sold {captured_fighter.fighter.name} from {captured_fighter.fighter.list.name} to the guilders"
                + (f" for {credits} credits" if credits > 0 else ""),
            )

        messages.success(
            request, f"{captured_fighter.fighter.name} has been sold to the guilders."
        )
        return HttpResponseRedirect(
            reverse("core:campaign-captured-fighters", args=(campaign.id,))
        )

    return render(
        request,
        "core/campaign/fighter_sell_to_guilders.html",
        {
            "campaign": campaign,
            "captured_fighter": captured_fighter,
        },
    )


@login_required
def fighter_return_to_owner(request, id, fighter_id):
    """
    Return a captured fighter to their original gang.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the fighter belongs to.
    ``captured_fighter``
        The :model:`core.CapturedFighter` being returned.

    **Template**

    :template:`core/campaign/fighter_return_to_owner.html`
    """
    campaign = get_object_or_404(Campaign, id=id)
    captured_fighter = get_object_or_404(
        CapturedFighter,
        fighter_id=fighter_id,
        capturing_list__owner=request.user,
        sold_to_guilders=False,
    )

    if request.method == "POST":
        ransom = request.POST.get("ransom", 0)
        try:
            ransom = int(ransom) if ransom else 0
            if ransom < 0:
                raise ValueError("Ransom cannot be negative")
        except ValueError:
            messages.error(request, "Invalid ransom amount.")
            # Validate the redirect URL for security
            redirect_url = request.path
            if not url_has_allowed_host_and_scheme(
                url=redirect_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                redirect_url = reverse(
                    "core:campaign_captured_fighters", args=[campaign.id]
                )
            return HttpResponseRedirect(redirect_url)

        original_list = captured_fighter.fighter.list
        capturing_list = captured_fighter.capturing_list
        fighter_name = captured_fighter.fighter.name

        # Process ransom payment
        if ransom > 0:
            if original_list.credits_current < ransom:
                messages.error(
                    request,
                    f"{original_list.name} doesn't have enough credits to pay the ransom.",
                )
                # Validate the redirect URL for security
                redirect_url = request.path
                if not url_has_allowed_host_and_scheme(
                    url=redirect_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    redirect_url = reverse(
                        "core:campaign_captured_fighters", args=[campaign.id]
                    )
                return HttpResponseRedirect(redirect_url)

        with transaction.atomic():
            if ransom > 0:
                # Transfer credits
                original_list.credits_current -= ransom
                original_list.save()
                capturing_list.credits_current += ransom
                capturing_list.save()

                # Log ransom payment
                CampaignAction.objects.create(
                    campaign=campaign,
                    user=request.user,
                    list=original_list,
                    description=f"Paid {ransom} credit ransom to {capturing_list.name} for {fighter_name}",
                )

            # Return the fighter
            captured_fighter.return_to_owner(credits=ransom)

            # Log return action
            CampaignAction.objects.create(
                campaign=campaign,
                user=request.user,
                list=capturing_list,
                description=f"Returned {fighter_name} to {original_list.name}"
                + (f" for {ransom} credits" if ransom > 0 else ""),
            )

        messages.success(
            request, f"{fighter_name} has been returned to {original_list.name}."
        )
        return HttpResponseRedirect(
            reverse("core:campaign-captured-fighters", args=(campaign.id,))
        )

    return render(
        request,
        "core/campaign/fighter_return_to_owner.html",
        {
            "campaign": campaign,
            "captured_fighter": captured_fighter,
        },
    )
