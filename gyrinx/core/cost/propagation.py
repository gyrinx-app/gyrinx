"""Cost propagation functions for updating cached rating fields."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.conf import settings

from gyrinx.tracing import traced
from gyrinx.tracker import track

if TYPE_CHECKING:
    from gyrinx.core.models.list import (
        List,
        ListFighter,
        ListFighterEquipmentAssignment,
    )


@dataclass
class TransactDelta:
    """Represents a rating change to propagate."""

    old_rating: int
    new_rating: int
    list: "List"

    @property
    def delta(self) -> int:
        """Calculate the difference between new and old rating."""
        return self.new_rating - self.old_rating

    @property
    def has_change(self) -> bool:
        """Check if there's an actual change in rating."""
        return self.delta != 0


def _should_propagate(lst: "List") -> bool:
    """
    Check if propagation should occur based on feature flag.

    Matches the guard condition in List.create_action().
    """
    return bool(lst.latest_action and settings.FEATURE_LIST_ACTION_CREATE_INITIAL)


@traced("propagate_from_assignment")
def propagate_from_assignment(
    assignment: "ListFighterEquipmentAssignment",
    rating_delta: TransactDelta,
) -> TransactDelta:
    """
    Propagate rating changes to assignment and fighter cached fields.

    Updates:
    - assignment.rating_current
    - fighter.rating_current

    Does NOT update List - that's handled by create_action().

    Clears dirty flags along the path.

    This should be called within a transaction.

    Only propagates when the list action system is enabled (list has a
    latest_action and FEATURE_LIST_ACTION_CREATE_INITIAL is True).

    Args:
        assignment: The equipment assignment whose cost changed
        rating_delta: The change in the assignment's rating

    Returns:
        TransactDelta representing the rating change (for future use)
    """
    if not _should_propagate(rating_delta.list):
        return rating_delta

    if not rating_delta.has_change:
        # No change, return zero-delta
        return TransactDelta(
            old_rating=0,
            new_rating=0,
            list=rating_delta.list,
        )

    if rating_delta.new_rating < 0:
        track(
            "negative_rating_propagation_assignment_from_assignment",
            assignment_id=str(assignment.id),
            old_rating=rating_delta.old_rating,
            new_rating=rating_delta.new_rating,
        )

    # Update assignment
    assignment.rating_current = max(0, rating_delta.new_rating)
    assignment.dirty = False
    assignment.save(update_fields=["rating_current", "dirty"])

    # Walk up to fighter
    fighter = assignment.list_fighter
    new_fighter_rating = int(fighter.rating_current + rating_delta.delta)

    if new_fighter_rating < 0:
        track(
            "negative_rating_propagation_fighter_from_assignment",
            assignment_id=str(assignment.id),
            fighter_id=str(fighter.id),
            old_rating=rating_delta.old_rating,
            new_rating=rating_delta.new_rating,
        )

    fighter.rating_current = max(0, new_fighter_rating)
    fighter.dirty = False
    fighter.save(update_fields=["rating_current", "dirty"])

    # Return delta for future use
    # NOTE: List is NOT updated here - create_action() does that
    return TransactDelta(
        old_rating=rating_delta.old_rating,
        new_rating=rating_delta.new_rating,
        list=rating_delta.list,
    )


@traced("propagate_from_fighter")
def propagate_from_fighter(
    fighter: "ListFighter",
    rating_delta: TransactDelta,
) -> TransactDelta:
    """
    Propagate a rating change from a fighter.

    Use when fighter's own cost changes (e.g., base cost override,
    advancement cost change).

    Updates:
    - fighter.rating_current

    Does NOT update List - that's handled by create_action().

    Clears dirty flags along the path.

    This should be called within a transaction (typically inside transact()).

    Only propagates when the list action system is enabled (list has a
    latest_action and FEATURE_LIST_ACTION_CREATE_INITIAL is True).

    Args:
        fighter: The fighter whose cost changed
        rating_delta: The change in the fighter's rating

    Returns:
        TransactDelta representing the rating change (for future use)
    """
    if not _should_propagate(rating_delta.list):
        return rating_delta

    if not rating_delta.has_change:
        # No change, return zero-delta
        return TransactDelta(
            old_rating=0,
            new_rating=0,
            list=rating_delta.list,
        )

    if rating_delta.new_rating < 0:
        track(
            "negative_rating_propagation_fighter_from_fighter",
            fighter_id=str(fighter.id),
            old_rating=rating_delta.old_rating,
            new_rating=rating_delta.new_rating,
        )

    # Update fighter
    fighter.rating_current = max(0, rating_delta.new_rating)
    fighter.dirty = False
    fighter.save(update_fields=["rating_current", "dirty"])

    # Return delta for future use
    # NOTE: List is NOT updated here - create_action() does that
    return TransactDelta(
        old_rating=rating_delta.old_rating,
        new_rating=rating_delta.new_rating,
        list=rating_delta.list,
    )
