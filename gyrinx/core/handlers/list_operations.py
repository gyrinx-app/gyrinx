"""Handlers for list operations (creation, etc.)."""

from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.db import transaction

from gyrinx.content.models import ContentFighter
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import List, ListFighter


@dataclass
class ListCreationResult:
    """Result of creating a list."""

    lst: List
    stash_fighter: Optional[ListFighter]
    initial_action: Optional[ListAction]


@transaction.atomic
def handle_list_creation(
    *,
    user,
    lst: List,
    create_stash: bool,
) -> ListCreationResult:
    """
    Handle list creation with optional stash and initial action.

    Creates the list, optionally creates a stash fighter, and creates an
    initial ListAction if the feature flag is enabled.

    Args:
        user: The user creating the list
        lst: The list instance (not yet saved, but owner already set)
        create_stash: Whether to create a stash fighter

    Returns:
        ListCreationResult with created objects
    """
    # Save the list
    lst.save()

    # Create stash fighter if requested
    stash_fighter = None
    if create_stash:
        # Get or create the stash ContentFighter for this house
        stash_fighter_type, _ = ContentFighter.objects.get_or_create(
            house=lst.content_house,
            is_stash=True,
            defaults={
                "type": "Stash",
                "category": "STASH",
                "base_cost": 0,
            },
        )

        # Create the stash ListFighter
        stash_fighter = ListFighter.objects.create(
            name="Stash",
            content_fighter=stash_fighter_type,
            list=lst,
            owner=user,
        )

    # Create initial action if feature flag is enabled
    initial_action = None
    if settings.FEATURE_LIST_ACTION_CREATE_INITIAL:
        initial_action = ListAction.objects.create(
            user=user,
            owner=user,
            list=lst,
            action_type=ListActionType.CREATE,
            description="List created",
        )

    return ListCreationResult(
        lst=lst,
        stash_fighter=stash_fighter,
        initial_action=initial_action,
    )
