"""Campaign list and detail views."""

from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db import models
from django.shortcuts import get_object_or_404
from django.views import generic

from gyrinx.core.models.campaign import Campaign, CampaignAction, CampaignAsset
from gyrinx.core.models.invitation import CampaignInvitation
from gyrinx.core.models.list import CapturedFighter

from .common import (
    ensure_campaign_list_resources,
    get_campaign_resource_types_with_resources,
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
