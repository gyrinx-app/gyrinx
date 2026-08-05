"""Edition query helpers for lists.

Generic helpers that used to live here moved to the platform: request/redirect
validation to ``gyrinx.http``, and the model-agnostic queryset helpers to
``gyrinx.querysets``. What remains knows about gangs.
"""

from django.db.models import Q


def get_list_attributes(list_obj):
    """
    Get the attributes and their assigned values for a list.

    Args:
        list_obj: The List instance

    Returns:
        list: List of dicts with attribute info to avoid object access in templates
    """
    from n23.content.models import ContentAttribute
    from n23.core.models.list import ListAttributeAssignment

    # Get all assignments for this list in a single query
    all_assignments = list(
        ListAttributeAssignment.objects.filter(list=list_obj, archived=False)
        .select_related("attribute_value", "attribute_value__attribute")
        .values("attribute_value__attribute_id", "attribute_value__name")
    )

    # Build a map of attribute_id to value names
    assignment_map = {}
    for assignment in all_assignments:
        attr_id = assignment["attribute_value__attribute_id"]
        if attr_id not in assignment_map:
            assignment_map[attr_id] = []
        assignment_map[attr_id].append(assignment["attribute_value__name"])

    # Get all available attributes in a single query using values to avoid
    # object queries. Use with_packs() so pack-scoped attributes appear for
    # lists subscribed to the pack.
    available_attributes = list(
        ContentAttribute.objects.with_packs(
            list_obj.packs.all(), include_archived_items=True
        )
        .filter(Q(restricted_to__isnull=True) | Q(restricted_to=list_obj.content_house))
        .distinct()
        .order_by("name")
        .values("id", "name")
    )

    # Build result as list of dicts to prevent template object access
    attributes = []
    for attribute in available_attributes:
        attr_data = {
            "id": attribute["id"],
            "name": attribute["name"],
            "assignments": assignment_map.get(attribute["id"], []),
        }
        attributes.append(attr_data)

    return attributes


def get_list_campaign_resources(list_obj):
    """
    Get campaign resources held by a list.

    Args:
        list_obj: The List instance

    Returns:
        QuerySet of campaign resources with amount > 0
    """
    return list_obj.campaign_resources.filter(amount__gt=0).select_related(
        "resource_type"
    )


def get_list_held_assets(list_obj):
    """
    Get assets held by a list.

    Args:
        list_obj: The List instance

    Returns:
        QuerySet of held assets
    """
    # prefetch_related("sub_assets") because the list-page panel renders
    # asset.sub_asset_counts, which iterates sub_assets.all() (N+1 otherwise).
    return list_obj.held_assets.select_related("asset_type").prefetch_related(
        "sub_assets"
    )


def get_list_recent_campaign_actions(list_obj, limit=5):
    """
    Get recent campaign actions for a list.

    Args:
        list_obj: The List instance
        limit: Maximum number of actions to return (default: 5)

    Returns:
        QuerySet of recent campaign actions, or None if not in campaign mode
    """
    if not (list_obj.is_campaign_mode and list_obj.campaign):
        return None

    from n23.core.models import CampaignAction

    return (
        CampaignAction.objects.filter(campaign=list_obj.campaign, list=list_obj)
        .select_related("user", "list")
        .order_by("-created")[:limit]
    )
