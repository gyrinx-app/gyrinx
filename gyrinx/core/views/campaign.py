import logging
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import OuterRef, Q, Subquery
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import generic

from gyrinx import messages
from gyrinx.core.forms.campaign import (
    AssetTransferForm,
    CampaignActionForm,
    CampaignActionOutcomeForm,
    CampaignAssetForm,
    CampaignAssetTypeForm,
    CampaignCopyFromForm,
    CampaignCopyToForm,
    CampaignResourceTypeForm,
    CampaignSubAssetForm,
    EditCampaignForm,
    NewCampaignForm,
    ResourceModifyForm,
)
from gyrinx.core.handlers.campaign_copy import (
    check_copy_conflicts,
    copy_campaign_content,
)
from gyrinx.core.handlers.campaign_operations import handle_campaign_start
from gyrinx.core.handlers.fighter.capture import handle_fighter_return_to_owner
from gyrinx.core.models.campaign import (
    Campaign,
    CampaignAction,
    CampaignAsset,
    CampaignAssetType,
    CampaignListResource,
    CampaignResourceType,
    CampaignSubAsset,
)
from gyrinx.core.models.events import EventNoun, EventVerb, log_event
from gyrinx.core.models.invitation import CampaignInvitation
from gyrinx.core.models.list import CapturedFighter, List
from gyrinx.core.utils import get_return_url, safe_redirect
from gyrinx.models import is_int, is_valid_uuid
from gyrinx.tracker import track

# Constants for transaction limits
MAX_CREDITS = 10000
MAX_RANSOM_CREDITS = 10000

logger = logging.getLogger(__name__)


def ensure_campaign_list_resources(campaign, resource_types, campaign_lists):
    """
    Ensure all lists have resources for all resource types.

    This defensive function creates missing CampaignListResource records
    using bulk operations to minimize database queries. It handles edge cases
    where resources weren't created due to race conditions, transaction failures,
    or other issues during resource type/list addition.

    Args:
        campaign: The Campaign object
        resource_types: Iterable of CampaignResourceType objects
        campaign_lists: Iterable of List objects in the campaign

    Returns:
        int: Number of missing resources created
    """
    # Convert to lists to allow multiple iterations
    all_lists = list(campaign_lists)
    all_resource_types = list(resource_types)

    # Early return if nothing to check
    if not all_lists or not all_resource_types:
        return 0

    # Bulk query existing resources
    existing_resources = CampaignListResource.objects.filter(
        campaign=campaign,
        list__in=all_lists,
        resource_type__in=all_resource_types,
    ).values_list("list_id", "resource_type_id")

    # Build set of existing pairs for O(1) lookup
    existing_pairs = set(existing_resources)

    # Find missing resources
    to_create = []
    for resource_type in all_resource_types:
        for list_obj in all_lists:
            pair = (list_obj.id, resource_type.id)
            if pair not in existing_pairs:
                to_create.append(
                    CampaignListResource(
                        campaign=campaign,
                        resource_type=resource_type,
                        list=list_obj,
                        amount=resource_type.default_amount,
                        owner=campaign.owner,
                    )
                )

    # Bulk create missing resources
    if to_create:
        with transaction.atomic():
            CampaignListResource.objects.bulk_create(to_create)

    return len(to_create)


def get_campaign_resource_types_with_resources(campaign):
    """
    Get resource types with their list resources prefetched and ordered.

    This helper function ensures consistent prefetching across views.
    Only includes resources for lists that are currently in the campaign.
    """
    # Get the IDs of lists currently in the campaign
    campaign_list_ids = campaign.lists.values_list("id", flat=True)

    return campaign.resource_types.prefetch_related(
        models.Prefetch(
            "list_resources",
            queryset=CampaignListResource.objects.filter(list_id__in=campaign_list_ids)
            .select_related("list")
            .order_by("list__name"),
        )
    )


class Campaigns(generic.ListView):
    template_name = "core/campaign/campaigns.html"
    context_object_name = "campaigns"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            Campaign.objects.all().select_related("owner").prefetch_related("lists")
        )

        # Apply "My campaigns only" filter - default to "my" campaigns if user is authenticated
        if self.request.user.is_authenticated:
            # Check if "my" parameter is explicitly set to "0" to show public campaigns
            show_my_campaigns = self.request.GET.get(
                "my", "1"
            )  # Default to "1" (my campaigns)
            if show_my_campaigns == "1":
                # Show campaigns where user is owner
                queryset = queryset.filter(owner=self.request.user)
            else:
                # Only show public campaigns if explicitly requested
                queryset = queryset.filter(public=True)
        else:
            # For unauthenticated users, only show public campaigns
            queryset = queryset.filter(public=True)

        # Apply "Participating only" filter
        show_participating = self.request.GET.get("participating", "0")
        if show_participating == "1" and self.request.user.is_authenticated:
            # Show campaigns where user has lists
            queryset = queryset.filter(lists__owner=self.request.user).distinct()

        # Apply archived filter (default off)
        show_archived = self.request.GET.get("archived", "0")
        if show_archived == "1":
            # Show ONLY archived campaigns
            queryset = queryset.filter(archived=True)
        else:
            # Show only non-archived campaigns by default
            queryset = queryset.filter(archived=False)

        # Apply status filter
        status_filters = self.request.GET.getlist("status")
        if status_filters:
            queryset = queryset.filter(status__in=status_filters)

        # Apply search filter
        search_query = self.request.GET.get("q")
        if search_query:
            search_vector = SearchVector("name", "narrative", "owner__username")
            search_q = SearchQuery(search_query)
            queryset = queryset.annotate(search=search_vector).filter(search=search_q)

        return queryset.order_by("name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add status choices for the filter
        context["status_choices"] = Campaign.STATUS_CHOICES
        return context


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
        Retrieve the :model:`core.Campaign` by its `id` with prefetched actions and lists.
        """
        return get_object_or_404(
            Campaign.objects.prefetch_related(
                "lists",
                models.Prefetch(
                    "actions",
                    queryset=CampaignAction.objects.select_related(
                        "user", "list"
                    ).order_by("-created"),
                ),
            ),
            id=self.kwargs["id"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        campaign = self.object
        user = self.request.user

        # Check if user can log actions (owner or has a list in campaign, and campaign is in progress and not archived)
        if user.is_authenticated:
            context["can_log_actions"] = (
                campaign.is_in_progress
                and not campaign.archived
                and (
                    campaign.owner == user or campaign.lists.filter(owner=user).exists()
                )
            )
        else:
            context["can_log_actions"] = False

        # Get asset types with their assets for the summary
        context["asset_types"] = campaign.asset_types.prefetch_related(
            models.Prefetch(
                "assets",
                queryset=CampaignAsset.objects.select_related("holder", "asset_type"),
            )
        )

        # Get recent battles
        context["battles_limit"] = 5
        context["recent_battles"] = (
            campaign.battles.select_related("owner")
            .prefetch_related("participants", "winners")
            .order_by("-date", "-created")[: context["battles_limit"]]
        )

        # Get resource types with their list resources
        context["resource_types"] = get_campaign_resource_types_with_resources(campaign)

        # Defensive fix: Ensure all lists have resources for all resource types
        # This handles edge cases where resources weren't created due to race conditions,
        # transaction failures, or other issues during resource type/list addition
        if campaign.is_in_progress:
            campaign_lists = campaign.lists.all()
            ensure_campaign_list_resources(
                campaign=campaign,
                resource_types=context["resource_types"],
                campaign_lists=campaign_lists,
            )

        # Create a resource lookup dictionary for efficient template rendering
        # Structure: {list_id: {resource_type_id: resource}}
        resource_lookup = {}
        for resource_type in context["resource_types"]:
            for resource in resource_type.list_resources.all():
                if resource.list_id not in resource_lookup:
                    resource_lookup[resource.list_id] = {}
                resource_lookup[resource.list_id][resource_type.id] = resource
        context["resource_lookup"] = resource_lookup

        # Get pending invitations for the campaign
        context["pending_invitations"] = (
            CampaignInvitation.objects.filter(
                campaign=campaign, status=CampaignInvitation.PENDING
            )
            .select_related("list", "list__owner")
            .order_by("-created")
        )

        # Get captured fighters for the campaign
        if campaign.is_in_progress:
            context["captured_fighters"] = (
                CapturedFighter.objects.filter(
                    models.Q(capturing_list__campaigns=campaign)
                    | models.Q(fighter__list__campaigns=campaign)
                )
                .select_related(
                    "fighter",
                    "fighter__list",
                    "fighter__content_fighter",
                    "capturing_list",
                )
                .order_by("-captured_at")
            )

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

    if request.method == "POST":
        list_id = request.POST.get("list_id")
        if list_id:
            try:
                list_to_add = List.objects.get(id=list_id)
                # Check if user can add this list (either owner or public)
                if list_to_add.owner == request.user or list_to_add.public:
                    # Check if list is in campaign mode (cannot be cloned-from)
                    if list_to_add.status == List.CAMPAIGN_MODE:
                        error_message = (
                            "Lists in campaign mode cannot be added to other campaigns."
                        )
                    else:
                        # Check if an invitation already exists
                        invitation, created = CampaignInvitation.objects.get_or_create(
                            campaign=campaign,
                            list=list_to_add,
                            defaults={"owner": request.user},
                        )

                        # Check for auto-accept condition (same owner)
                        if campaign.owner == list_to_add.owner:
                            # If invitation was declined, reset to pending so it can be accepted
                            if invitation.is_declined:
                                invitation.status = CampaignInvitation.PENDING
                                invitation.save()  # Required to persist the status change

                            # Try to accept the invitation
                            if invitation.accept():
                                messages.success(
                                    request,
                                    f"{list_to_add.name} has been added to the campaign.",
                                )

                                # Log the auto-accept event regardless of whether the invitation was just created
                                log_event(
                                    user=request.user,
                                    noun=EventNoun.CAMPAIGN_INVITATION,
                                    verb=EventVerb.CREATE
                                    if created
                                    else EventVerb.UPDATE,
                                    object=invitation,
                                    request=request,
                                    campaign_name=campaign.name,
                                    list_invited_id=str(list_to_add.id),
                                    list_invited_name=list_to_add.name,
                                    list_owner=list_to_add.owner.username,
                                    action="invitation_auto_accepted",
                                )

                                track(
                                    "campaign_list_added",
                                    campaign_id=str(campaign.id),
                                )
                            else:
                                # If accept() returned False, the invitation was already accepted
                                if (
                                    invitation.is_accepted
                                    and list_to_add in campaign.lists.all()
                                ):
                                    messages.info(
                                        request,
                                        f"{list_to_add.name} is already in the campaign.",
                                    )
                                else:
                                    # Should not happen if we handled declined above, but fallback
                                    messages.info(
                                        request, f"Could not add {list_to_add.name}."
                                    )

                        elif created:
                            # Log the invitation creation event
                            log_event(
                                user=request.user,
                                noun=EventNoun.CAMPAIGN_INVITATION,
                                verb=EventVerb.CREATE,
                                object=invitation,
                                request=request,
                                campaign_name=campaign.name,
                                list_invited_id=str(list_to_add.id),
                                list_invited_name=list_to_add.name,
                                list_owner=list_to_add.owner.username,
                                action="invitation_sent",
                            )

                            # Show success message
                            messages.success(
                                request,
                                f"Invitation sent to {list_to_add.name}.",
                            )
                        else:
                            # Check if the invitation is still pending
                            if invitation.is_pending:
                                messages.info(
                                    request,
                                    f"An invitation for {list_to_add.name} is already pending.",
                                )
                            elif invitation.is_accepted:
                                # Check if the list is actually in the campaign
                                if list_to_add in campaign.lists.all():
                                    messages.info(
                                        request,
                                        f"{list_to_add.name} has already accepted the invitation and is in the campaign.",
                                    )
                                else:
                                    # List was removed, reset invitation to pending
                                    invitation.status = CampaignInvitation.PENDING
                                    invitation.save()
                                    messages.success(
                                        request,
                                        f"Invitation re-sent to {list_to_add.name}.",
                                    )
                            elif invitation.is_declined:
                                # Reset declined invitation to pending
                                invitation.status = CampaignInvitation.PENDING
                                invitation.save()
                                messages.success(
                                    request,
                                    f"Invitation re-sent to {list_to_add.name}.",
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

    # When we show the set of available lists, we want to exclude those that are already
    # in the campaign, and those that have pending/accepted invitations.

    # First, get the most recent invitation for each list to this campaign

    # Subquery to get the most recent invitation's ID for each list
    most_recent_invitation = (
        CampaignInvitation.objects.filter(campaign=campaign, list=OuterRef("list_id"))
        .order_by("-created")
        .values("id")[:1]
    )

    # Get the list IDs where the most recent invitation is pending
    pending_invitation_list_ids = CampaignInvitation.objects.filter(
        id__in=Subquery(most_recent_invitation),
        status=CampaignInvitation.PENDING,
    ).values_list("list_id", flat=True)

    # Exclude both pending invitations and lists that are already in the campaign
    excluded_list_ids = list(pending_invitation_list_ids)

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
        ).filter(Q(search=search_query) | Q(name__icontains=request.GET.get("q")))

    # Filter by owner type
    owner_filter = request.GET.get("owner", "all")
    if owner_filter == "mine":
        lists = lists.filter(owner=request.user)
    elif owner_filter == "others":
        # Only show public lists from other users
        lists = lists.filter(public=True).exclude(owner=request.user)

    # Exclude and order by name, prefetch latest actions for facts system
    lists = (
        lists.exclude(id__in=excluded_list_ids)
        .with_latest_actions()
        .select_related("content_house", "owner")
        .order_by("name")
    )

    # Paginate the results
    paginator = Paginator(lists, 20)  # Show 20 lists per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Get current campaign lists for display
    current_lists = campaign.lists.select_related("owner", "content_house").order_by(
        "name"
    )

    # Get pending invitations for display
    pending_invitations = (
        CampaignInvitation.objects.filter(
            campaign=campaign, status=CampaignInvitation.PENDING
        )
        .select_related("list", "list__owner", "list__content_house")
        .order_by("-created")
    )

    return render(
        request,
        "core/campaign/campaign_add_lists.html",
        {
            "campaign": campaign,
            "lists": page_obj,  # Pass the page object instead of the full queryset
            "page_obj": page_obj,  # Also pass page_obj for pagination controls
            "error_message": error_message,
            "current_lists": current_lists,
            "pending_invitations": pending_invitations,
        },
    )


@login_required
@transaction.atomic
def campaign_remove_list(request, id, list_id):
    """
    Remove a list from a campaign.

    Allows the campaign owner or list owner to remove a list from a campaign.
    The list is disconnected from the campaign and archived if in campaign mode.

    **Context**

    ``campaign``
        The :model:`core.Campaign` being edited.
    ``list``
        The :model:`core.List` being removed.

    **Template**

    :template:`core/campaign/campaign_remove_list.html`
    """
    campaign = get_object_or_404(Campaign, id=id)
    list_to_remove = get_object_or_404(List, id=list_id)

    # Check permissions - campaign owner or list owner can remove
    if request.user != campaign.owner and request.user != list_to_remove.owner:
        messages.error(
            request, "You don't have permission to remove this list from the campaign."
        )
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Check if the list is actually in this campaign
    if list_to_remove not in campaign.lists.all():
        messages.error(request, "This list is not in this campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Don't allow removal from post-campaign
    if campaign.is_post_campaign:
        messages.error(request, "Lists cannot be removed from a completed campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    if request.method == "POST":
        # Store list info for logging before removal
        list_name = list_to_remove.name
        list_house = (
            list_to_remove.content_house.name if list_to_remove.content_house else ""
        )
        list_owner_username = list_to_remove.owner.username

        # Un-assign any campaign assets held by this list
        assets_unassigned_count = 0
        for asset in CampaignAsset.objects.filter(
            holder=list_to_remove, asset_type__campaign=campaign
        ):
            asset.holder = None
            asset.save()
            assets_unassigned_count += 1

        # Create campaign action for list removal
        CampaignAction.objects.create(
            campaign=campaign,
            user=request.user,
            list=list_to_remove,
            description=f"Gang '{list_name}' has been removed from the campaign by {request.user.username}",
            owner=request.user,
        )

        # Remove the list from the campaign
        campaign.lists.remove(list_to_remove)

        # If the list is in campaign mode, archive it
        archive_message = ""
        if list_to_remove.status == List.CAMPAIGN_MODE:
            list_to_remove.archived = True
            list_to_remove.campaign = None  # Clear the campaign field
            list_to_remove.save()
            archive_message = " and archived"

        # Log the removal event
        log_event(
            user=request.user,
            noun=EventNoun.CAMPAIGN,
            verb=EventVerb.REMOVE,
            object=campaign,
            request=request,
            campaign_name=campaign.name,
            list_removed_id=str(list_to_remove.id),
            list_removed_name=list_name,
            list_owner=list_owner_username,
        )

        track("campaign_list_removed", campaign_id=str(campaign.id))

        # Show success message
        house_text = f" ({list_house})" if list_house else ""
        messages.success(
            request,
            f"{list_name}{house_text} has been removed from the campaign{archive_message}.",
        )

        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # GET request - show confirmation page
    return render(
        request,
        "core/campaign/campaign_remove_list.html",
        {
            "campaign": campaign,
            "list": list_to_remove,
        },
    )


@login_required
@transaction.atomic
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

            # Log the campaign creation event
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN,
                verb=EventVerb.CREATE,
                object=campaign,
                request=request,
                campaign_name=campaign.name,
                public=campaign.public,
            )

            track("campaign_created", campaign_id=str(campaign.id))

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
            # Pass user to save() for phase change logging
            updated_campaign = form.save(user=request.user)

            # Log the campaign update event
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN,
                verb=EventVerb.UPDATE,
                object=updated_campaign,
                request=request,
                campaign_name=updated_campaign.name,
            )

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
    ``return_url``
        Optional. A URL to return to after logging the action. Can be provided as a GET or POST parameter. Used for navigation after form submission.
    ``gang``
        Optional. If provided as a GET parameter, pre-selects a gang/list in the form.

    **Template**

    :template:`core/campaign/campaign_log_action.html`
    """
    campaign = get_object_or_404(Campaign, id=id)

    # Check if user is part of the campaign (owner or has a list in it) and campaign is in progress and not archived
    user_lists_in_campaign = campaign.lists.filter(owner=request.user).exists()
    if (
        not campaign.is_in_progress
        or campaign.archived
        or (campaign.owner != request.user and not user_lists_in_campaign)
    ):
        messages.error(request, "You cannot log actions for this campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Get return URL for back/cancel navigation
    default_url = reverse("core:campaign", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    error_message = None
    if request.method == "POST":
        form = CampaignActionForm(request.POST, campaign=campaign, user=request.user)
        return_url = request.POST.get("return_url")
        if form.is_valid():
            action = form.save(commit=False)
            action.campaign = campaign
            action.user = request.user
            action.save()

            # Log the campaign action event
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_ACTION,
                verb=EventVerb.CREATE,
                object=action,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                description=action.description,
            )

            track(
                "campaign_action_logged",
                campaign_id=str(campaign.id),
                has_dice=bool(action.dice_count),
            )

            # Redirect to outcome edit page, passing along return_url
            outcome_url = reverse(
                "core:campaign-action-outcome", args=(campaign.id, action.id)
            )
            return HttpResponseRedirect(
                f"{outcome_url}?{urlencode({'return_url': return_url})}"
            )
    else:
        return_url = request.GET.get("return_url")

        # Pre-populate gang/list if provided
        gang = request.GET.get("gang")
        initial = {}
        if gang:
            initial["list"] = gang

        form = CampaignActionForm(campaign=campaign, user=request.user, initial=initial)

    return render(
        request,
        "core/campaign/campaign_log_action.html",
        {
            "form": form,
            "campaign": campaign,
            "error_message": error_message,
            "return_url": return_url,
        },
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
    ``return_url``
        Optional. A URL to return to after editing the outcome. Can be provided as a GET or POST parameter. Used for navigation after form submission.

    **Template**

    :template:`core/campaign/campaign_action_outcome.html`
    """
    campaign = get_object_or_404(Campaign, id=id)
    action = get_object_or_404(CampaignAction, id=action_id, campaign=campaign)

    # Check if user can edit this action (only the creator)
    if action.user != request.user:
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Get return URL for back/cancel navigation
    default_url = reverse("core:campaign", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    error_message = None
    if request.method == "POST":
        return_url = request.POST.get("return_url")
        form = CampaignActionOutcomeForm(request.POST, instance=action)
        if form.is_valid():
            form.save()

            # Log the action outcome update
            log_event(
                user=request.user,
                noun=EventNoun.CAMPAIGN_ACTION,
                verb=EventVerb.UPDATE,
                object=action,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                outcome=action.outcome,
            )

            # Check which button was clicked
            if "save_and_new" in request.POST:
                # Redirect to create another action, preserving return_url
                new_action_url = reverse(
                    "core:campaign-action-new", args=(campaign.id,)
                )
                return HttpResponseRedirect(
                    f"{new_action_url}?{urlencode({'return_url': return_url})}"
                )
            else:
                # Default: redirect to return URL
                return safe_redirect(request, return_url, fallback_url=default_url)
    else:
        return_url = request.GET.get("return_url")
        form = CampaignActionOutcomeForm(instance=action)

    return render(
        request,
        "core/campaign/campaign_action_outcome.html",
        {
            "form": form,
            "campaign": campaign,
            "action": action,
            "error_message": error_message,
            "return_url": return_url,
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
        if gang_id and is_valid_uuid(gang_id):
            # Filter actions by the specific list/gang
            actions = actions.filter(list_id=gang_id)

        # Apply author filter if provided (user IDs are integers, not UUIDs)
        author_id = self.request.GET.get("author")
        if author_id and is_int(author_id):
            actions = actions.filter(user__id=author_id)

        # Apply battle filter if provided
        battle_id = self.request.GET.get("battle")
        if battle_id and is_valid_uuid(battle_id):
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

        # Check if user can log actions (owner or has a list in campaign, and campaign is in progress and not archived)
        user = self.request.user
        if user.is_authenticated:
            context["can_log_actions"] = (
                self.campaign.is_in_progress
                and not self.campaign.archived
                and (
                    self.campaign.owner == user
                    or self.campaign.lists.filter(owner=user).exists()
                )
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
        try:
            with transaction.atomic():
                # Handle campaign start (creates ListActions and CampaignActions)
                result = handle_campaign_start(
                    user=request.user,
                    campaign=campaign,
                )

                # Log the campaign start event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.ACTIVATE,
                    object=campaign,
                    request=request,
                    campaign_name=campaign.name,
                    action="started",
                )

                track(
                    "campaign_started",
                    campaign_id=str(campaign.id),
                    list_count=len(result.list_results),
                )

                messages.success(
                    request,
                    f"Campaign has been started! {len(result.list_results)} gang(s) joined.",
                )
        except ValidationError as e:
            messages.validation(request, e)

        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # For GET request, show confirmation page
    if not campaign.can_start_campaign():
        messages.error(request, "This campaign cannot be started.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Prefetch lists with latest actions for efficient facts_with_fallback() in template
    lists = (
        List.objects.filter(campaign=campaign)
        .select_related("owner")
        .with_latest_actions()
    )

    return render(
        request,
        "core/campaign/campaign_start.html",
        {"campaign": campaign, "lists": lists},
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

                # Log the campaign end event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.DEACTIVATE,
                    object=campaign,
                    request=request,
                    campaign_name=campaign.name,
                    action="ended",
                )

                track("campaign_ended", campaign_id=str(campaign.id))

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

                # Log the campaign reopen event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.ACTIVATE,
                    object=campaign,
                    request=request,
                    campaign_name=campaign.name,
                    action="reopened",
                )

                track("campaign_reopened", campaign_id=str(campaign.id))

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
def archive_campaign(request, id):
    """
    Archive or unarchive a :model:`core.Campaign`.

    Only the campaign owner can archive a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` to be archived or unarchived.

    **Template**

    :template:`core/campaign/campaign_archive.html`
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if request.method == "POST":
        with transaction.atomic():
            if request.POST.get("archive") == "1":
                # Prevent archiving in-progress campaigns
                if campaign.is_in_progress:
                    messages.error(
                        request,
                        f"Cannot archive {campaign.name} while it is in progress. Please end the campaign first.",
                    )
                    return HttpResponseRedirect(
                        reverse("core:campaign", args=(campaign.id,))
                    )

                campaign.archive()

                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=campaign,
                    description=f"Campaign Archived: {campaign.name} has been archived",
                    outcome="Campaign has been archived",
                )

                # Log the archive event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.ARCHIVE,
                    object=campaign,
                    request=request,
                    campaign_name=campaign.name,
                )

                messages.success(request, "Campaign has been archived.")
            else:
                campaign.unarchive()

                CampaignAction.objects.create(
                    user=request.user,
                    owner=request.user,
                    campaign=campaign,
                    description=f"Campaign Unarchived: {campaign.name} has been unarchived",
                    outcome="Campaign has been unarchived",
                )

                # Log the unarchive event
                log_event(
                    user=request.user,
                    noun=EventNoun.CAMPAIGN,
                    verb=EventVerb.RESTORE,
                    object=campaign,
                    request=request,
                    campaign_name=campaign.name,
                )

                messages.success(request, "Campaign has been unarchived.")

        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    return render(
        request,
        "core/campaign/campaign_archive.html",
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
    campaign = get_object_or_404(Campaign.objects.prefetch_related("lists"), id=id)

    # Check if user owns the campaign or any list in it
    user_owns_list = any(
        list.owner_id == request.user.id for list in campaign.lists.all()
    )
    if campaign.owner != request.user and not user_owns_list:
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

    # Log viewing captured fighters
    log_event(
        user=request.user,
        noun=EventNoun.CAMPAIGN,
        verb=EventVerb.VIEW,
        object=campaign,
        request=request,
        page="captured_fighters",
        campaign_id=str(campaign.id),
        campaign_name=campaign.name,
        captured_fighters_count=captured_fighters.count(),
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
    from gyrinx.core.handlers.fighter.capture import handle_fighter_sell_to_guilders

    campaign = get_object_or_404(Campaign, id=id)

    # Get the captured fighter - must be in this campaign and not sold
    captured_fighter = get_object_or_404(
        CapturedFighter,
        fighter_id=fighter_id,
        capturing_list__campaign=campaign,
        sold_to_guilders=False,
    )

    # Check permissions: must be capturing list owner OR campaign owner
    if (
        request.user != captured_fighter.capturing_list.owner
        and request.user != campaign.owner
    ):
        raise Http404()

    # Get return URL for back/cancel navigation
    default_url = reverse("core:campaign-captured-fighters", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        credits = request.POST.get("credits", 0)
        try:
            credits = int(credits) if credits else 0
            if credits < 0:
                raise ValueError("Credits cannot be negative")
            if credits > MAX_CREDITS:
                raise ValueError(f"Credits cannot exceed {MAX_CREDITS:,}")
        except ValueError as e:
            # Use the error message directly since we control the ValueError messages
            messages.error(request, str(e))
            # Redirect safely back to the form
            return safe_redirect(
                request,
                request.path,
                fallback_url=default_url,
            )

        # Call the handler
        result = handle_fighter_sell_to_guilders(
            user=request.user,
            captured_fighter=captured_fighter,
            sale_price=credits,
        )

        # Log the fighter sale event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.UPDATE,
            object=result.fighter,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            action="sold_to_guilders",
            fighter_name=result.fighter.name,
            original_list=result.fighter.list.name,
            capturing_list=result.capturing_list.name,
            credits=credits,
        )

        track("campaign_fighter_sold", campaign_id=str(campaign.id))

        messages.success(
            request, f"{result.fighter.name} has been sold to the guilders."
        )
        return safe_redirect(request, return_url, fallback_url=default_url)

    return render(
        request,
        "core/campaign/fighter_sell_to_guilders.html",
        {
            "campaign": campaign,
            "captured_fighter": captured_fighter,
            "return_url": return_url,
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

    # Get the captured fighter - must be in this campaign and not sold
    captured_fighter = get_object_or_404(
        CapturedFighter,
        fighter_id=fighter_id,
        capturing_list__campaign=campaign,
        sold_to_guilders=False,
    )

    # Check permissions: must be capturing list owner OR campaign owner OR captured fighter owner
    if (
        request.user != captured_fighter.capturing_list.owner
        and request.user != campaign.owner
        and request.user != captured_fighter.fighter.list.owner
    ):
        raise Http404()

    # Get return URL for back/cancel navigation
    default_url = reverse("core:campaign-captured-fighters", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        ransom = request.POST.get("ransom", 0)
        try:
            ransom = int(ransom) if ransom else 0
            if ransom < 0:
                raise ValueError("Ransom cannot be negative")
            if ransom > MAX_RANSOM_CREDITS:
                raise ValueError(f"Ransom cannot exceed {MAX_RANSOM_CREDITS:,}")
        except ValueError as e:
            # Use the error message directly since we control the ValueError messages
            messages.error(request, str(e))
            # Redirect safely back to the form
            return safe_redirect(
                request,
                request.path,
                fallback_url=default_url,
            )

        # Store fighter info before handler (fighter object may be modified)
        fighter = captured_fighter.fighter
        original_list = fighter.list
        capturing_list = captured_fighter.capturing_list
        fighter_name = fighter.name

        try:
            # Call the handler
            result = handle_fighter_return_to_owner(
                user=request.user,
                captured_fighter=captured_fighter,
                ransom_amount=ransom,
            )

            # Log the fighter return event
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=result.fighter,
                request=request,
                campaign_id=str(campaign.id),
                campaign_name=campaign.name,
                action="returned_to_owner",
                fighter_name=fighter_name,
                original_list=original_list.name,
                capturing_list=capturing_list.name,
                ransom=ransom,
            )
            track("campaign_fighter_ransomed", campaign_id=str(campaign.id))

            messages.success(
                request, f"{fighter_name} has been returned to {original_list.name}."
            )
            return safe_redirect(request, return_url, fallback_url=default_url)

        except ValidationError as e:
            messages.validation(request, e)
            return safe_redirect(
                request,
                request.path,
                fallback_url=default_url,
            )

    return render(
        request,
        "core/campaign/fighter_return_to_owner.html",
        {
            "campaign": campaign,
            "captured_fighter": captured_fighter,
            "return_url": return_url,
        },
    )


@login_required
def fighter_release(request, id, fighter_id):
    """
    Release a captured fighter without ransom or sale.

    **Context**

    ``campaign``
        The :model:`core.Campaign` the fighter belongs to.
    ``captured_fighter``
        The :model:`core.CapturedFighter` being released.

    **Template**

    :template:`core/campaign/fighter_release.html`
    """
    from gyrinx.core.handlers.fighter.capture import handle_fighter_release

    campaign = get_object_or_404(Campaign, id=id)

    # Get the captured fighter - must be in this campaign and not sold
    captured_fighter = get_object_or_404(
        CapturedFighter,
        fighter_id=fighter_id,
        capturing_list__campaign=campaign,
        sold_to_guilders=False,
    )

    # Check permissions: must be capturing list owner OR campaign owner OR captured fighter owner
    if (
        request.user != captured_fighter.capturing_list.owner
        and request.user != campaign.owner
        and request.user != captured_fighter.fighter.list.owner
    ):
        raise Http404()

    # Get return URL for back/cancel navigation
    default_url = reverse("core:campaign-captured-fighters", args=(campaign.id,))
    return_url = get_return_url(request, default_url)

    if request.method == "POST":
        # Store info before handler (capture record will be deleted)
        fighter = captured_fighter.fighter
        original_list = fighter.list
        capturing_list = captured_fighter.capturing_list
        fighter_name = fighter.name

        # Call the handler
        result = handle_fighter_release(
            user=request.user,
            captured_fighter=captured_fighter,
        )

        # Log the fighter release event
        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.UPDATE,
            object=result.fighter,
            request=request,
            campaign_id=str(campaign.id),
            campaign_name=campaign.name,
            fighter_name=fighter_name,
            action="released",
            capturing_list=capturing_list.name,
            original_list=original_list.name,
        )
        track("campaign_fighter_released", campaign_id=str(campaign.id))

        messages.success(
            request,
            f"{fighter_name} has been released back to {original_list.name}.",
        )

        return safe_redirect(request, return_url, fallback_url=default_url)

    return render(
        request,
        "core/campaign/fighter_release.html",
        {
            "campaign": campaign,
            "captured_fighter": captured_fighter,
            "return_url": return_url,
        },
    )


def campaign_battles(request, id):
    """
    View all battles in a campaign.

    **Context**

    ``campaign``
        The :model:`core.Campaign` whose battles are being viewed.
    ``battles``
        QuerySet of :model:`core.Battle` objects for this campaign.

    **Template**

    :template:`core/campaign/campaign_battles.html`
    """
    campaign = get_object_or_404(Campaign.objects.prefetch_related("lists"), id=id)

    battles = (
        campaign.battles.select_related("owner")
        .prefetch_related("participants", "winners")
        .order_by("-date", "-created")
    )

    return render(
        request,
        "core/campaign/campaign_battles.html",
        {
            "campaign": campaign,
            "battles": battles,
        },
    )


# Campaign Sub-Asset Views


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


@login_required
def campaign_copy_from(request, id):
    """Copy assets and resources FROM another campaign TO this campaign.

    This view allows a campaign admin to copy asset types, assets (with sub-assets),
    and resource types from another campaign they own into the current campaign.
    """
    campaign = get_object_or_404(Campaign, id=id, owner=request.user)

    if campaign.archived:
        messages.error(request, "Cannot copy to an archived campaign.")
        return HttpResponseRedirect(reverse("core:campaign", args=(campaign.id,)))

    # Check if user has other campaigns to copy from
    other_campaigns = Campaign.objects.filter(owner=request.user).exclude(
        pk=campaign.pk
    )
    if not other_campaigns.exists():
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
                    Campaign, id=source_id, owner=request.user
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

                # Perform the copy
                result = copy_campaign_content(
                    source_campaign=source_campaign,
                    target_campaign=campaign,
                    user=request.user,
                    asset_type_ids=asset_type_ids if asset_type_ids else None,
                    resource_type_ids=resource_type_ids if resource_type_ids else None,
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
                )

                track(
                    "campaign_copy_from",
                    campaign_id=str(campaign.id),
                    source_campaign_id=str(source_campaign.id),
                    asset_types_copied=result.asset_types_copied,
                    assets_copied=result.assets_copied,
                    resource_types_copied=result.resource_types_copied,
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
                Campaign, id=source_id, owner=request.user
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

                # Check for conflicts
                conflicts = check_copy_conflicts(
                    source_campaign=source_campaign,
                    target_campaign=campaign,
                    asset_type_ids=asset_type_ids if asset_type_ids else None,
                    resource_type_ids=resource_type_ids if resource_type_ids else None,
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
    if not has_asset_types and not has_resource_types:
        messages.info(
            request,
            "This campaign has no asset types or resource types to copy.",
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

                # Perform the copy
                result = copy_campaign_content(
                    source_campaign=campaign,
                    target_campaign=target_campaign,
                    user=request.user,
                    asset_type_ids=asset_type_ids if asset_type_ids else None,
                    resource_type_ids=resource_type_ids if resource_type_ids else None,
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
                )

                track(
                    "campaign_copy_to",
                    campaign_id=str(campaign.id),
                    target_campaign_id=str(target_campaign.id),
                    asset_types_copied=result.asset_types_copied,
                    assets_copied=result.assets_copied,
                    resource_types_copied=result.resource_types_copied,
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

            # Check for conflicts
            conflicts = check_copy_conflicts(
                source_campaign=campaign,
                target_campaign=target_campaign,
                asset_type_ids=asset_type_ids if asset_type_ids else None,
                resource_type_ids=resource_type_ids if resource_type_ids else None,
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
