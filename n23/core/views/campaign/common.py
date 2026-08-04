"""Common utilities for campaign views."""

from django.db import models, transaction
from django.shortcuts import get_object_or_404

from n23.core.models.campaign import Campaign, CampaignListResource


def get_campaign_admin_or_404(request, id):
    """Fetch a campaign the user can administer (owner or shared admin), or 404.

    Drop-in replacement for ``get_object_or_404(Campaign, id=id, owner=request.user)``
    in views that gate on campaign administration. The shared-admin branch uses a
    subquery rather than a join on the admins M2M, so no .distinct() is needed.
    """
    return get_object_or_404(
        Campaign.objects.filter(
            models.Q(owner=request.user)
            | models.Q(id__in=Campaign.objects.filter(admins=request.user))
        ),
        id=id,
    )


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
