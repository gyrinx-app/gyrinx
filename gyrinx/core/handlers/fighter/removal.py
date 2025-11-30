"""Handlers for fighter removal operations.

These handlers extract business logic for deletion/removal operations,
making them directly testable without HTTP machinery.
"""

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from django.db import transaction

from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import (
    List,
    ListFighter,
)


def _calculate_refund_credits(
    *,
    lst: List,
    cost: int,
    request_refund: bool,
) -> tuple[int, bool]:
    """
    Calculate credits delta based on refund request and campaign mode.

    Refunds are ONLY allowed in campaign mode.

    Args:
        lst: The list
        cost: The item cost being removed
        request_refund: Whether user requested refund

    Returns:
        Tuple of (credits_delta, refund_applied)
    """
    refund_applied = request_refund and lst.is_campaign_mode
    credits_delta = cost if refund_applied else 0
    return credits_delta, refund_applied


@dataclass
class FighterArchiveResult:
    """Result of archiving or unarchiving a fighter."""

    fighter: ListFighter
    archived: bool  # True if archived, False if unarchived
    fighter_cost: int
    refund_applied: bool  # Only relevant when archiving
    description: str
    list_action: Optional[ListAction]


@transaction.atomic
def handle_fighter_archive_toggle(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    archive: bool,
    request_refund: bool,
) -> FighterArchiveResult:
    """
    Handle archiving or unarchiving a fighter.

    This handler provides a single implementation for both archive and
    unarchive operations, reducing code duplication in the view.

    This handler performs the following operations atomically:
    1. Captures before values for ListAction
    2. Calculates fighter cost
    3. For archive: validates and calculates refund (only in campaign mode)
    4. Performs archive or unarchive operation
    5. Creates ListAction to track the operation

    Args:
        user: User performing the operation
        lst: List containing fighter
        fighter: Fighter to archive/unarchive
        archive: True to archive, False to unarchive
        request_refund: Whether user requested refund (only applies to archive)

    Returns:
        FighterArchiveResult with operation details
    """
    # Capture BEFORE values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Calculate fighter cost
    fighter_cost = fighter.cost_int()
    is_stash = fighter.is_stash

    if archive:
        # Archiving: remove fighter cost from rating/stash
        rating_delta = -fighter_cost if not is_stash else 0
        stash_delta = -fighter_cost if is_stash else 0

        # Validate and calculate refund
        credits_delta, refund_applied = _calculate_refund_credits(
            lst=lst,
            cost=fighter_cost,
            request_refund=request_refund,
        )

        # Perform archive
        fighter.archive()

        # Build description
        description = f"Archived {fighter.name} ({fighter_cost}¢)"
        if refund_applied:
            description += f" - refund applied (+{fighter_cost}¢)"
    else:
        # Unarchiving: add fighter cost back to rating/stash
        rating_delta = fighter_cost if not is_stash else 0
        stash_delta = fighter_cost if is_stash else 0
        credits_delta = 0
        refund_applied = False

        # Perform unarchive
        fighter.unarchive()

        # Build description
        description = f"Restored {fighter.name} ({fighter_cost}¢)"

    # Create ListAction
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        list_fighter=fighter,
        description=description,
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
        update_credits=archive,  # Only apply credits on archive (when refund may occur)
    )

    return FighterArchiveResult(
        fighter=fighter,
        archived=archive,
        fighter_cost=fighter_cost,
        refund_applied=refund_applied,
        description=description,
        list_action=list_action,
    )


@dataclass
class FighterDeletionResult:
    """Result of deleting a fighter."""

    fighter_id: UUID
    fighter_name: str
    fighter_cost: int
    refund_applied: bool
    description: str
    list_action: Optional[ListAction]


@transaction.atomic
def handle_fighter_deletion(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    request_refund: bool,
) -> FighterDeletionResult:
    """
    Handle deletion of a fighter from a list.

    This handler performs the following operations atomically:
    1. Captures before values for ListAction
    2. Calculates fighter cost before deletion
    3. Validates and calculates refund (only in campaign mode)
    4. Stores fighter details before deletion
    5. Deletes the fighter
    6. Creates ListAction to track the deletion

    Args:
        user: User performing deletion
        lst: List containing fighter
        fighter: Fighter to delete
        request_refund: Whether user requested refund (only applied in campaign mode)

    Returns:
        FighterDeletionResult with deletion details
    """
    # Capture BEFORE values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Calculate cost BEFORE deletion
    fighter_cost = fighter.cost_int()
    fighter_id = fighter.id
    fighter_name = fighter.name
    is_stash = fighter.is_stash

    # Calculate deltas based on fighter type
    rating_delta = -fighter_cost if not is_stash else 0
    stash_delta = -fighter_cost if is_stash else 0

    # Validate and calculate refund
    credits_delta, refund_applied = _calculate_refund_credits(
        lst=lst,
        cost=fighter_cost,
        request_refund=request_refund,
    )

    # Delete the fighter
    fighter.delete()

    # Build description
    description = f"Removed {fighter_name} ({fighter_cost}¢)"
    if refund_applied:
        description += f" - refund applied (+{fighter_cost}¢)"

    # Create ListAction
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.REMOVE_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter_id,
        description=description,
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
        update_credits=True,
    )

    return FighterDeletionResult(
        fighter_id=fighter_id,
        fighter_name=fighter_name,
        fighter_cost=fighter_cost,
        refund_applied=refund_applied,
        description=description,
        list_action=list_action,
    )
