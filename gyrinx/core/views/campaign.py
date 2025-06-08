from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db import models
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
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
from gyrinx.core.models.list import List


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
        Retrieve the :model:`core.Campaign` by its `id`.
        """
        return get_object_or_404(Campaign, id=self.kwargs["id"])

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

        # Get resource types with their list resources
        context["resource_types"] = get_campaign_resource_types_with_resources(campaign)

        # Prefetch recent actions with related list data
        context["campaign"] = Campaign.objects.prefetch_related(
            models.Prefetch(
                "actions",
                queryset=CampaignAction.objects.select_related("user", "list").order_by("-created")
            )
        ).get(id=campaign.id)

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
    ``added_list``
        The most recently added list (if any).
    ``error_message``
        None or a string describing a form error.

    **Template**

    :template:`core/campaign/campaign_add_lists.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    # Check if campaign is in a state where lists can be added
    if not campaign.is_pre_campaign:
        messages.error(request, "Lists can only be added before a campaign starts.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))
    added_list = None
    error_message = None

    if request.method == "POST":
        list_id = request.POST.get("list_id")
        if list_id:
            try:
                list_to_add = List.objects.get(id=list_id)
                # Check if user can add this list (either owner or public)
                if list_to_add.owner == request.user or list_to_add.public:
                    campaign.lists.add(list_to_add)
                    added_list = list_to_add
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
                        + "#added"
                    )
                else:
                    error_message = "You can only add your own lists or public lists."
            except List.DoesNotExist:
                error_message = "List not found."

    # Get lists that can be added (user's own lists or public lists)
    # Only show lists in list building mode
    lists = List.objects.filter(
        (models.Q(owner=request.user) | models.Q(public=True))
        & models.Q(status=List.LIST_BUILDING)
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

    # Check if we just added a list
    if request.GET.get("added") and not added_list:
        # Try to get the most recently added list
        latest_list = campaign.lists.order_by("-id").first()
        if latest_list:
            added_list = latest_list

    return render(
        request,
        "core/campaign/campaign_add_lists.html",
        {
            "campaign": campaign,
            "lists": lists,
            "added_list": added_list,
            "error_message": error_message,
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
        
        # Start with all campaign actions with list relationship
        actions = self.campaign.actions.select_related("user", "list").order_by("-created")
        
        # Apply text search filter if provided
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            actions = actions.annotate(
                search=SearchVector("description", "outcome", "user__username")
            ).filter(search=SearchQuery(search_query))
        
        # Apply gang filter if provided
        gang_id = self.request.GET.get("gang")
        if gang_id:
            # Filter actions by users who own the specified list/gang
            actions = actions.filter(
                user__in=List.objects.filter(
                    id=gang_id, 
                    campaign=self.campaign
                ).values_list("owner", flat=True)
            )
        
        # Apply author filter if provided
        author_id = self.request.GET.get("author")
        if author_id:
            actions = actions.filter(user__id=author_id)
        
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
        context["campaign_lists"] = self.campaign.lists.select_related("owner", "content_house").order_by("name")
        
        # Get all users who have performed actions for the author filter
        context["action_authors"] = (
            self.campaign.actions
            .values_list("user__id", "user__username")
            .distinct()
            .order_by("user__username")
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
        if campaign.start_campaign():
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
        if campaign.end_campaign():
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
