"""Cost propagation functions for updating cached rating fields."""

from dataclasses import dataclass

from django.conf import settings

from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.tracing import traced
from gyrinx.tracker import track


@dataclass
class Delta:
    """Represents a rating change to propagate."""

    # Core fields
    delta: int

    # References
    list: List

    @property
    def has_change(self) -> bool:
        """Check if there's an actual change in rating."""
        return self.delta != 0


def _should_propagate(lst: "List") -> bool:
    """
    Check if propagation should occur based on feature flag.

    This guard condition is critical for avoiding double-counting bugs. The codebase
    has TWO systems for keeping cached values (rating_current, etc.) in sync:

    1. **Facts System** (pull-based): `facts_from_db()` recalculates from database
    2. **Propagation System** (push-based): `propagate_from_*()` applies incremental deltas

    Only ONE system should update cached values for any given operation:

    - When guard is TRUE: Handlers use propagation, clone methods do NOT call facts_from_db()
    - When guard is FALSE: facts_from_db() must be called explicitly after creation/cloning

    The guard requires BOTH conditions:
    - `lst.latest_action`: List has recorded initial state (bootstrap action exists)
    - `FEATURE_LIST_ACTION_CREATE_INITIAL`: Feature flag is enabled

    This same condition appears in:
    - ListFighter.clone() - decides whether to call facts_from_db()
    - List.create_action() - decides whether to record actions
    - All propagate_from_*() functions - decides whether to update cached fields

    Matches the guard condition in List.create_action().
    """
    return bool(lst.latest_action and settings.FEATURE_LIST_ACTION_CREATE_INITIAL)


@traced("propagate_from_assignment")
def propagate_from_assignment(
    assignment: "ListFighterEquipmentAssignment",
    delta: Delta,
) -> Delta:
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
    if not _should_propagate(delta.list):
        return delta

    if not delta.has_change:
        # No change, return zero-delta
        return delta

    new_assignment_rating = int(assignment.rating_current + delta.delta)

    if new_assignment_rating < 0:
        track(
            "negative_rating_propagation_assignment_from_assignment",
            assignment_id=str(assignment.id),
            old_rating=assignment.rating_current,
            new_rating=new_assignment_rating,
        )

    # Update assignment
    assignment.rating_current = max(0, new_assignment_rating)
    assignment.dirty = False
    assignment.save(update_fields=["rating_current", "dirty"])

    # Walk up to fighter
    fighter = assignment.list_fighter
    new_fighter_rating = int(fighter.rating_current + delta.delta)

    if new_fighter_rating < 0:
        track(
            "negative_rating_propagation_fighter_from_assignment",
            assignment_id=str(assignment.id),
            fighter_id=str(fighter.id),
            old_rating=fighter.rating_current,
            new_rating=new_fighter_rating,
        )

    fighter.rating_current = max(0, new_fighter_rating)
    fighter.dirty = False
    fighter.save(update_fields=["rating_current", "dirty"])

    # Return delta for future use
    # NOTE: List is NOT updated here - create_action() does that
    return delta


@traced("propagate_from_fighter")
def propagate_from_fighter(
    fighter: "ListFighter",
    delta: Delta,
) -> Delta:
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
    if not _should_propagate(delta.list):
        return delta

    if not delta.has_change:
        # No change, return zero-delta
        return delta

    new_fighter_rating = int(fighter.rating_current + delta.delta)

    if new_fighter_rating < 0:
        track(
            "negative_rating_propagation_fighter_from_fighter",
            fighter_id=str(fighter.id),
            old_rating=fighter.rating_current,
            new_rating=new_fighter_rating,
        )

    # Update fighter
    fighter.rating_current = max(0, new_fighter_rating)
    fighter.dirty = False
    fighter.save(update_fields=["rating_current", "dirty"])

    # Return delta for future use
    # NOTE: List is NOT updated here - create_action() does that
    return delta
