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


def get_list_attributes(list_obj):
    """
    Get the attributes and their assigned values for a list.

    Args:
        list_obj: The List instance

    Returns:
        dict: Mapping of ContentAttribute to list of assigned value names
    """
    from gyrinx.content.models import ContentAttribute
    from gyrinx.core.models.list import ListAttributeAssignment

    attributes = {}
    # Filter attributes to only those available to this house
    available_attributes = (
        ContentAttribute.objects.filter(
            Q(restricted_to__isnull=True) | Q(restricted_to=list_obj.content_house)
        )
        .distinct()
        .order_by("name")
    )

    for attribute in available_attributes:
        assignments = ListAttributeAssignment.objects.filter(
            list=list_obj, attribute_value__attribute=attribute, archived=False
        ).select_related("attribute_value")

        # Get the value names
        value_names = [a.attribute_value.name for a in assignments]
        attributes[attribute] = value_names

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
