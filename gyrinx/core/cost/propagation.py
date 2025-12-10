"""Cost propagation functions for updating cached rating fields."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from gyrinx.tracing import traced

if TYPE_CHECKING:
    from gyrinx.core.models.list import (
        ListFighter,
        ListFighterEquipmentAssignment,
    )


@dataclass
class TransactDelta:
    """Represents a rating change to propagate."""

    old_rating: int
    new_rating: int

    @property
    def delta(self) -> int:
        """Calculate the difference between new and old rating."""
        return self.new_rating - self.old_rating

    @property
    def has_change(self) -> bool:
        """Check if there's an actual change in rating."""
        return self.delta != 0


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

    Args:
        assignment: The equipment assignment whose cost changed
        rating_delta: The change in the assignment's rating

    Returns:
        TransactDelta representing the rating change (for future use)
    """
    if not rating_delta.has_change:
        # No change, return zero-delta
        return TransactDelta(
            old_rating=0,
            new_rating=0,
        )

    # Update assignment
    assignment.rating_current = rating_delta.new_rating
    assignment.dirty = False
    assignment.save(update_fields=["rating_current", "dirty"])

    # Walk up to fighter
    fighter = assignment.list_fighter
    fighter.rating_current += rating_delta.delta
    fighter.dirty = False
    fighter.save(update_fields=["rating_current", "dirty"])

    # Return delta for future use
    # NOTE: List is NOT updated here - create_action() does that
    return TransactDelta(
        old_rating=rating_delta.old_rating,
        new_rating=rating_delta.new_rating,
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

    Args:
        fighter: The fighter whose cost changed
        rating_delta: The change in the fighter's rating

    Returns:
        TransactDelta representing the rating change (for future use)
    """
    if not rating_delta.has_change:
        # No change, return zero-delta
        return TransactDelta(
            old_rating=0,
            new_rating=0,
        )

    # Update fighter
    fighter.rating_current = rating_delta.new_rating
    fighter.dirty = False
    fighter.save(update_fields=["rating_current", "dirty"])

    # Return delta for future use
    # NOTE: List is NOT updated here - create_action() does that
    return TransactDelta(
        old_rating=rating_delta.old_rating,
        new_rating=rating_delta.new_rating,
    )
