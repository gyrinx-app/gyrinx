"""Handlers for list operations (creation, cloning, etc.)."""

from dataclasses import dataclass

from django.db import transaction

from gyrinx.tracing import traced
from n23.content.models import ContentFighter
from n23.core.models.action import ListAction, ListActionType
from n23.core.models.list import List, ListFighter


@dataclass
class ListCreationResult:
    """Result of creating a list."""

    lst: List
    stash_fighter: ListFighter | None
    initial_action: ListAction


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
    initial ListAction recording the creation.

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

    # Bootstrap the action chain: every list records its creation
    initial_action = ListAction.objects.create(
        user=user,
        owner=user,
        list=lst,
        action_type=ListActionType.CREATE,
        description="List created",
        applied=True,
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
    cloned_action: ListAction


def book_clone_actions(
    *, user, original_list: List, cloned_list: List, original_list_name: str = None
) -> tuple[ListAction, ListAction]:
    """Record the ListActions for a clone: CLONE on the source, CREATE on the clone.

    The CREATE action's deltas read the clone's freshly-recomputed caches
    (``rating_current``/``stash_current``/``credits_current``), so this MUST run *after*
    the clone is fully populated (``List._populate_clone_from`` / ``facts_from_db`` done).
    Booking it against an empty clone would write zero deltas and leave a permanent break
    in the audit chain at the clone seam (see the ``handle_list_clone`` history for #1222).

    Split out so the async campaign-start task (issue #1222) can book identical actions
    after populating a stub, without duplicating the delta logic.

    Returns ``(original_action, cloned_action)``.
    """
    if original_list_name is None:
        original_list_name = original_list.name

    # Create ListAction on original list recording the clone
    original_action = original_list.create_action(
        user=user,
        action_type=ListActionType.CLONE,
        description=f"List cloned to '{cloned_list.name}'",
    )

    # The CREATE action represents creating the list from nothing, so the
    # before values are 0 and the deltas are the CLONE's own values.
    #
    # Book the clone's freshly-recomputed caches (List.clone() ran
    # facts_from_db() on it), NOT original_list.rating_current. A
    # list-building gang's cached rating can be stale — caches drift until
    # something recomputes them — and the clone can legitimately differ
    # from its source (e.g. skipped fighters). Recording the source's value
    # here writes a rating the clone's real cost immediately contradicts:
    # the very next action, CAMPAIGN_START, prices the gang with a fresh
    # cost_int(), so a stale source leaves a permanent chain break at the
    # clone seam. The clone's own caches are the source of truth for what
    # it actually is.
    cloned_action = ListAction.objects.create(
        user=user,
        owner=cloned_list.owner,
        list=cloned_list,
        action_type=ListActionType.CREATE,
        description=f"Cloned from '{original_list_name}'",
        applied=True,
        rating_before=0,
        stash_before=0,
        credits_before=0,
        rating_delta=cloned_list.rating_current,
        stash_delta=cloned_list.stash_current,
        credits_delta=cloned_list.credits_current,
    )

    return original_action, cloned_action


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
    - On original list: Records that it was cloned
    - On cloned list: Records creation as clone

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

    # Book the CLONE (on original) and CREATE (on clone) actions. Deltas read the
    # clone's freshly-recomputed caches, so this runs after clone() populated it.
    original_action, cloned_action = book_clone_actions(
        user=user,
        original_list=original_list,
        cloned_list=cloned_list,
        original_list_name=original_list_name,
    )

    return ListCloneResult(
        original_list=original_list,
        cloned_list=cloned_list,
        original_action=original_action,
        cloned_action=cloned_action,
    )
