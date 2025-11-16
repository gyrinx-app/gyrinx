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


@dataclass
class ListCloneResult:
    """Result of cloning a list."""

    original_list: List
    cloned_list: List
    original_action: ListAction
    cloned_action: Optional[ListAction]


@transaction.atomic
def handle_list_clone(
    *,
    user,
    original_list: List,
    name: str = None,
    owner=None,
    public: bool = None,
    **kwargs,
) -> ListCloneResult:
    """
    Handle list cloning with cost field copying and ListAction creation.

    Creates a clone with copied cost fields and creates ListActions:
    - On original list: Records that it was cloned
    - On cloned list: Records creation as clone (if FEATURE_LIST_ACTION_CREATE_INITIAL)

    Args:
        user: The user performing the clone
        original_list: The list to clone
        name: Name for the clone (defaults to original name + suffix)
        owner: Owner of the clone (defaults to original owner)
        public: Public setting for the clone (defaults to original public)
        **kwargs: Additional fields to set on the clone

    Returns:
        ListCloneResult with original list, cloned list, and actions
    """
    # Capture original list name before any operations
    # (in case caller has modified original_list in memory)
    original_list_name = original_list.name

    # Set defaults
    if owner is None:
        owner = original_list.owner
    if name is None:
        name = f"{original_list_name} (Clone)"
    if public is not None:
        kwargs["public"] = public

    # Clone the list (this now copies cost fields automatically)
    cloned_list = original_list.clone(name=name, owner=owner, **kwargs)

    # Create ListAction on original list recording the clone
    original_action = original_list.create_action(
        user=user,
        action_type=ListActionType.CLONE,
        description=f"List cloned to '{cloned_list.name}'",
    )

    # Create ListAction on cloned list if feature flag is enabled
    cloned_action = None
    if settings.FEATURE_LIST_ACTION_CREATE_INITIAL:
        cloned_action = ListAction.objects.create(
            user=user,
            owner=user,
            list=cloned_list,
            action_type=ListActionType.CREATE,
            description=f"Cloned from '{original_list_name}'",
            applied=True,
        )

    return ListCloneResult(
        original_list=original_list,
        cloned_list=cloned_list,
        original_action=original_action,
        cloned_action=cloned_action,
    )
