"""Handlers for list operations (creation, cloning, etc.)."""

from dataclasses import dataclass
from typing import Optional

from django.conf import settings
from django.db import transaction

from gyrinx.content.models import ContentFighter
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import List, ListFighter
from gyrinx.tracing import traced


@dataclass
class ListCreationResult:
    """Result of creating a list."""

    lst: List
    stash_fighter: Optional[ListFighter]
    initial_action: Optional[ListAction]


@traced("handle_list_creation")
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

    # Initialize cached values for the new list
    lst.facts_from_db(update=True)

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

        # Create the stash ListFighter with correct cached values
        stash_fighter = ListFighter.objects.create_with_facts(
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
    original_action: Optional[ListAction]
    cloned_action: Optional[ListAction]


@traced("handle_list_clone")
@transaction.atomic
def handle_list_clone(
    *,
    user,
    original_list: List,
    name: str = None,
    owner=None,
    public: bool = None,
    for_campaign=None,
    **kwargs,
) -> ListCloneResult:
    """
    Handle list cloning with cost field copying and ListAction creation.

    Creates a clone with copied cost fields and creates ListActions:
    - On original list: Records that it was cloned (for regular clones only)
    - On cloned list: Records creation as clone (if FEATURE_LIST_ACTION_CREATE_INITIAL)

    Args:
        user: The user performing the clone
        original_list: The list to clone
        name: Name for the clone. If not provided, regular clones default to
            "<original name> (Clone)", while campaign clones (when for_campaign
            is provided) default to the original name without a suffix.
        owner: Owner of the clone (defaults to original owner)
        public: Public setting for the clone (defaults to original public)
        for_campaign: If provided, creates a campaign mode clone for this campaign
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
        if for_campaign:
            name = original_list_name  # Campaign clones keep the same name
        else:
            name = f"{original_list_name} (Clone)"
    if public is not None:
        kwargs["public"] = public

    # Clone the list (this now copies cost fields automatically)
    cloned_list = original_list.clone(
        name=name, owner=owner, for_campaign=for_campaign, **kwargs
    )

    # Create ListAction on original list recording the clone (for regular clones only)
    # Campaign clones don't record on the original since it's a different workflow
    original_action = None
    if not for_campaign:
        original_action = original_list.create_action(
            user=user,
            action_type=ListActionType.CLONE,
            description=f"List cloned to '{cloned_list.name}'",
        )

    # Create ListAction on cloned list if feature flag is enabled
    cloned_action = None
    if settings.FEATURE_LIST_ACTION_CREATE_INITIAL:
        # The CREATE action represents creating the list from nothing,
        # so before values are 0 and deltas equal the cloned values.
        cloned_action = ListAction.objects.create(
            user=user,
            owner=owner,
            list=cloned_list,
            action_type=ListActionType.CREATE,
            description=f"Cloned from '{original_list_name}'",
            applied=True,
            rating_before=0,
            stash_before=0,
            credits_before=0,
            rating_delta=original_list.rating_current,
            stash_delta=original_list.stash_current,
            credits_delta=original_list.credits_current,
        )

        # Set up the latest_actions prefetch so that subsequent create_action calls work
        # Clear any cached None value from the @cached_property
        cloned_list.__dict__.pop("latest_action", None)
        # Set the prefetch list that latest_action property will check
        setattr(cloned_list, "latest_actions", [cloned_action])

    return ListCloneResult(
        original_list=original_list,
        cloned_list=cloned_list,
        original_action=original_action,
        cloned_action=cloned_action,
    )
