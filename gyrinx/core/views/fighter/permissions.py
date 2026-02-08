"""Permission utilities for fighter views."""

import enum

from django.db.models import Q
from django.shortcuts import get_object_or_404

from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.views.list.common import get_clean_list_or_404


class Permission(enum.Enum):
    """Types of permission a user can have on a list/fighter."""

    OWNER = "owner"
    ARBITRATOR = "arbitrator"


def get_user_permissions(request, lst):
    """Return the set of permissions the current user has on this list."""
    perms = set()
    if lst.owner == request.user:
        perms.add(Permission.OWNER)
    if lst.campaign and lst.campaign.owner == request.user:
        perms.add(Permission.ARBITRATOR)
    return perms


def get_list_for_edit(request, id, *, required_permissions=None):
    """Fetch a list, checking that the user has at least one of the required permissions.

    The queryset is filtered by the required permissions, so users without
    access will get a 404 from get_clean_list_or_404.

    Args:
        request: The HTTP request.
        id: The list ID.
        required_permissions: Set of Permission values. The user must have at least one.
            Defaults to {OWNER, ARBITRATOR} (either can edit).

    Returns:
        (lst, perms) tuple. Raises Http404 if the list is not found or
        the user lacks permission.
    """
    if required_permissions is None:
        required_permissions = {Permission.OWNER, Permission.ARBITRATOR}

    # Build queryset filter from required permissions
    q_filter = Q()
    if Permission.OWNER in required_permissions:
        q_filter |= Q(owner=request.user)
    if Permission.ARBITRATOR in required_permissions:
        q_filter |= Q(campaign__owner=request.user)

    lst = get_clean_list_or_404(List.objects.filter(q_filter), id=id)
    perms = get_user_permissions(request, lst)

    return lst, perms


def get_list_and_fighter(request, id, fighter_id, *, required_permissions=None):
    """Fetch list and fighter with permission check.

    Args:
        request: The HTTP request.
        id: The list ID.
        fighter_id: The fighter ID.
        required_permissions: Set of Permission values. The user must have at least one.
            Defaults to {OWNER, ARBITRATOR}.

    Returns:
        (lst, fighter, perms) tuple. Raises Http404 if not found or denied.
    """
    lst, perms = get_list_for_edit(
        request, id, required_permissions=required_permissions
    )

    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        id=fighter_id,
        list=lst,
        owner=lst.owner,
    )

    return lst, fighter, perms
