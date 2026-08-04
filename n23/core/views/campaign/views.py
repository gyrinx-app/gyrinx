"""Campaign list and detail views."""

from django.db import models
from django.db.models import Count, Max, Q
from django.db.models.functions import Coalesce, Lower
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.http import urlencode
from django.views import generic

from n23.core.models.campaign import Campaign, CampaignAction, CampaignAsset
from n23.core.utils import search_queryset
from n23.core.models.invitation import CampaignInvitation
from n23.core.models.list import CapturedFighter, List

from .common import (
    ensure_campaign_list_resources,
    get_campaign_resource_types_with_resources,
)
from .gang_sort import (
    DEFAULT_GANG_SORT,
    build_sort_options,
    resolve_gang_sort,
    sort_lists,
)


class Campaigns(generic.ListView):
    template_name = "core/campaign/campaigns.html"
    context_object_name = "campaigns"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            Campaign.objects.all()
            .select_related("owner", "owner__profile")
            .prefetch_related("lists")
        )

        # Apply "Your Campaigns Only" filter - default to user's campaigns if authenticated
        if self.request.user.is_authenticated:
            # Check if "my" parameter is explicitly set to "0" to show public campaigns
            show_my_campaigns = self.request.GET.get(
                "my", "1"
            )  # Default to "1" (your campaigns)
            if show_my_campaigns == "1":
                # Show campaigns where user is owner
                queryset = queryset.filter(owner=self.request.user)
            else:
                # Show public campaigns plus private campaigns the user participates in
                queryset = queryset.filter(
                    Q(public=True) | Q(lists__owner=self.request.user)
                ).distinct()
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
        status_filters_raw = self.request.GET.getlist("status")
        # Filter out empty strings and "all" marker
        status_filters = [s for s in status_filters_raw if s and s != "all"]
        if status_filters:
            queryset = queryset.filter(status__in=status_filters)
        elif status_filters_raw:
            # Had values but all filtered out (e.g. empty string for "None") - show nothing
            queryset = queryset.none()

        # Apply search filter
        search_query = self.request.GET.get("q")
        if search_query:
            queryset = search_queryset(
                queryset, search_query, ["name", "narrative", "owner__username"]
            )

        # Star count is always available for display; sorting can use it.
        queryset = queryset.annotate(star_count=Count("starred_by", distinct=True))

        # Sorting: recently updated (default), alphabetical, or most starred.
        sort = self.request.GET.get("sort", "recent")
        if sort == "name":
            return queryset.order_by(Lower("name"))
        elif sort == "stars":
            return queryset.order_by("-star_count", Lower("name"))
        else:
            # Most recent campaign action, falling back to modified time.
            return queryset.annotate(latest_action_at=Max("actions__created")).order_by(
                Coalesce("latest_action_at", "modified").desc()
            )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add status choices for the filter
        context["status_choices"] = Campaign.STATUS_CHOICES

        # Current sort, for the sort control.
        context["current_sort"] = self.request.GET.get("sort", "recent")

        # Pinned campaigns for the sidebar (the user's own private pins).
        # Mirror the main queryset so the shared row partial renders identically.
        if self.request.user.is_authenticated:
            context["pinned_campaigns"] = (
                self.request.user.pinned_campaigns.filter(archived=False)
                .select_related("owner", "owner__profile")
                .prefetch_related("lists")
                .annotate(star_count=Count("starred_by", distinct=True))
                .order_by("name")
            )
        else:
            context["pinned_campaigns"] = []

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
            Campaign.objects.select_related(
                "group_attribute_type",
                # owner__profile is for the breadcrumb supporter badge.
                "owner__profile",
            ).prefetch_related(
                "packs",
                "lists",
                "admins",
                models.Prefetch(
                    "actions",
                    queryset=CampaignAction.objects.select_related(
                        "user", "list", "template_campaign"
                    ).order_by("-created"),
                ),
            ),
            id=self.kwargs["id"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        campaign = self.object
        user = self.request.user

        # Are any member gangs still being cloned in the background (#1222)? Computed from
        # the prefetched lists (no extra query) so the page can poll for completion.
        context["has_cloning_lists"] = any(
            lst.status == List.CLONING_IN_PROGRESS for lst in campaign.lists.all()
        )
        if context["has_cloning_lists"]:
            from n23.core.handlers.campaign_operations import (
                campaign_start_group_key,
            )

            # Poll the generic task-group status endpoint for this campaign's clone tasks.
            context["cloning_status_url"] = (
                reverse("tasks:group-status")
                + "?"
                + urlencode({"group": campaign_start_group_key(campaign.id)})
            )

        # Check if user can log actions (owner or has a fully-joined list in the campaign,
        # and the campaign is in progress and not archived). active_lists() excludes
        # CLONING_IN_PROGRESS stubs (#1222) — a user whose only gang is still joining has no
        # selectable gang in the action form, so shouldn't be offered the Log Action UI yet.
        if user.is_authenticated:
            context["can_log_actions"] = (
                campaign.is_in_progress
                and not campaign.archived
                and (
                    campaign.is_admin(user)
                    or campaign.active_lists().filter(owner=user).exists()
                )
            )
        else:
            context["can_log_actions"] = False

        # Get asset types with their assets for the summary. prefetch sub_assets
        # so the dashboard's asset.sub_asset_counts doesn't run N+1 queries.
        context["asset_types"] = campaign.asset_types.prefetch_related(
            models.Prefetch(
                "assets",
                queryset=CampaignAsset.objects.select_related(
                    "holder", "asset_type"
                ).prefetch_related("sub_assets"),
            )
        )

        # Get recent battles (archived battles are hidden)
        context["battles_limit"] = 5
        active_battles = campaign.battles.filter(archived=False)
        context["battles_count"] = active_battles.count()
        context["recent_battles"] = (
            active_battles.select_related("owner")
            .prefetch_related("participants", "winners")
            .order_by("-date", "-created")[: context["battles_limit"]]
        )

        # Get resource types with their list resources
        context["resource_types"] = get_campaign_resource_types_with_resources(campaign)

        # Defensive fix: Ensure all lists have resources for all resource types
        # This handles edge cases where resources weren't created due to race conditions,
        # transaction failures, or other issues during resource type/list addition.
        # Only seed fully-joined gangs — a CLONING_IN_PROGRESS stub gets its resources
        # when its background clone task finishes (#1222).
        if campaign.is_in_progress:
            campaign_lists = campaign.active_lists()
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

        # Get attribute types with their values and assignments
        attribute_types = campaign.attribute_types.prefetch_related(
            "values",
            "values__list_assignments",
            "values__list_assignments__list",
        ).order_by("name")
        context["attribute_types"] = attribute_types

        # Build attribute assignment lookup: {type_id: {list_id: [assignment, ...]}}
        attribute_assignment_lookup = {}
        for attr_type in attribute_types:
            type_assignments = {}
            for value in attr_type.values.all():
                for assignment in value.list_assignments.all():
                    type_assignments.setdefault(assignment.list_id, []).append(
                        assignment
                    )
            attribute_assignment_lookup[attr_type.id] = type_assignments
        context["attribute_assignment_lookup"] = attribute_assignment_lookup

        # Gang table ordering (#1459). The viewer's ?sort= wins, then the campaign's
        # stored default, then wealth highest-first. Sorting is done in Python over
        # the prefetched lists — the cost figures are cached columns and the
        # resource amounts are already in resource_lookup, so this costs no queries.
        gang_sort = resolve_gang_sort(
            self.request.GET.get("sort"),
            campaign.default_gang_sort,
            context["resource_types"],
            resource_lookup,
        )
        context["gang_sort"] = gang_sort
        context["gang_sort_options"] = build_sort_options(
            gang_sort, context["resource_types"]
        )
        # Admins can promote whatever they're looking at to the campaign default.
        context["can_set_default_gang_sort"] = gang_sort.token != (
            campaign.default_gang_sort or DEFAULT_GANG_SORT
        )

        sorted_lists = sort_lists(list(campaign.lists.all()), gang_sort)
        context["sorted_lists"] = sorted_lists

        # Grouping can be switched off for a view (?group=0) so the sort runs across
        # every gang in the campaign rather than within each group.
        group_attribute_type = campaign.group_attribute_type
        show_groups = (
            bool(group_attribute_type) and self.request.GET.get("group") != "0"
        )
        context["show_groups"] = show_groups

        # The grouping attribute has its own heading row when grouped, so it only
        # earns a column of its own when groups are off.
        context["visible_attribute_types"] = [
            attr_type
            for attr_type in attribute_types
            if not (show_groups and attr_type.id == group_attribute_type.id)
        ]

        # Build grouped lists data for the template
        if show_groups:
            group_assignments = attribute_assignment_lookup.get(
                group_attribute_type.id, {}
            )
            # Build: list of (group_value_name, group_colour, [lists])
            # Lists without a group assignment go into an "Unassigned" group
            group_value_lists = {}
            for lst in sorted_lists:
                assignments = group_assignments.get(lst.id, [])
                if assignments:
                    # Single-select, so take the first assignment
                    val = assignments[0].attribute_value
                    key = (val.name, val.colour, val.pk)
                else:
                    key = ("Unassigned", "", None)
                group_value_lists.setdefault(key, []).append(lst)

            # Sort groups: named groups by value name, "Unassigned" at the end.
            # Gangs within a group keep the order set by the chosen sort.
            grouped_lists = []
            for (name, colour, pk), lists in sorted(
                group_value_lists.items(),
                key=lambda x: (x[0][2] is None, x[0][0]),
            ):
                grouped_lists.append(
                    {
                        "name": name,
                        "colour": colour,
                        "lists": lists,
                    }
                )
            context["grouped_lists"] = grouped_lists

        context["is_admin"] = campaign.is_admin(user)
        context["campaign_packs"] = campaign.packs.all()

        # Admins (superusers) may impersonate the arbitrator (campaign owner),
        # unless already impersonating. Hidden for the owner (can't self-impersonate).
        from n23.core.impersonation import can_impersonate_target

        context["can_impersonate_arbitrator"] = not getattr(
            self.request, "is_impersonating", False
        ) and can_impersonate_target(user, campaign.owner)

        # Pin/star state for the header toggle buttons.
        context["star_count"] = campaign.starred_by.count()
        if user.is_authenticated:
            context["is_pinned"] = campaign.pinned_by.filter(pk=user.pk).exists()
            context["is_starred"] = campaign.starred_by.filter(pk=user.pk).exists()
            # Admins or participants (users with a list in the campaign) may pin.
            context["can_pin"] = (
                campaign.is_admin(user) or campaign.lists.filter(owner=user).exists()
            )
        else:
            context["is_pinned"] = False
            context["is_starred"] = False
            context["can_pin"] = False

        # Notification banners for this campaign (scoped to the viewing recipient).
        if user.is_authenticated:
            from n23.core.models.notification import Notification

            context["notification_banners"] = Notification.objects.banners_for(
                user, campaign=campaign
            )

        return context
