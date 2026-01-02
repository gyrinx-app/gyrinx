"""
Utility functions for the core app.
"""

from django.db.models import Q
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme


def safe_redirect(request, url, fallback_url="/"):
    """
    Perform a safe redirect, ensuring the URL is allowed.

    Args:
        request: The current HTTP request
        url: The URL to redirect to
        fallback_url: The URL to use if validation fails (default: "/")

    Returns:
        HttpResponseRedirect to either the validated URL or the fallback
    """
    # Validate the URL is safe
    if url and url_has_allowed_host_and_scheme(
        url=url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return HttpResponseRedirect(url)

    # Fall back to the provided fallback URL
    return HttpResponseRedirect(fallback_url)


def build_safe_url(request, path=None, query_string=None):
    """
    Build a safe URL from path and query string components.

    Args:
        request: The current HTTP request
        path: The path component (default: request.path)
        query_string: The query string (without '?')

    Returns:
        A safe URL string that can be used for redirects
    """
    # Use current path if not provided
    if path is None:
        path = request.path

    # Build the full URL
    if query_string:
        url = f"{path}?{query_string}"
    else:
        url = path

    # Validate the URL is safe
    if url_has_allowed_host_and_scheme(
        url=url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return url

    # Return just the path if validation fails
    return path


def get_return_url(request, default_url):
    """
    Get a validated return URL from request parameters.

    Extracts return_url from POST data (for form submissions) or GET parameters.
    Validates the URL for security and falls back to default_url if invalid.

    Args:
        request: The HTTP request object
        default_url: Fallback URL if return_url is missing or invalid

    Returns:
        str: A validated URL safe for redirects

    Example:
        default_url = reverse("core:list", args=(list.id,))
        return_url = get_return_url(request, default_url)
    """
    # Check POST first (form submissions), then GET (query params)
    return_url = request.POST.get("return_url") or request.GET.get(
        "return_url", default_url
    )

    # Validate the URL is safe
    if return_url and url_has_allowed_host_and_scheme(
        url=return_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return return_url

    # Fall back to the provided default URL
    return default_url


def get_list_attributes(list_obj):
    """
    Get the attributes and their assigned values for a list.

    Args:
        list_obj: The List instance

    Returns:
        list: List of dicts with attribute info to avoid object access in templates
    """
    from gyrinx.content.models import ContentAttribute
    from gyrinx.core.models.list import ListAttributeAssignment

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

    # Get all available attributes in a single query using values to avoid object queries
    available_attributes = list(
        ContentAttribute.objects.filter(
            Q(restricted_to__isnull=True) | Q(restricted_to=list_obj.content_house)
        )
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
    return list_obj.held_assets.select_related("asset_type")


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

    from gyrinx.core.models import CampaignAction

    return (
        CampaignAction.objects.filter(campaign=list_obj.campaign, list=list_obj)
        .select_related("user", "list")
        .order_by("-created")[:limit]
    )
