"""Cost routing utilities for determining stash vs rating allocation."""

from typing import TYPE_CHECKING

from gyrinx.tracing import traced

if TYPE_CHECKING:
    from gyrinx.core.models.list import ListFighter


@traced("is_stash_linked")
def is_stash_linked(fighter: "ListFighter") -> bool:
    """
    Determine if a fighter's costs route to stash or rating.

    A fighter is stash-linked if:
    1. It IS a stash fighter directly, OR
    2. It's a child fighter (vehicle/exotic beast) linked to equipment
       owned by a stash fighter.

    Note: Child fighters linked to stash CAN receive advancements (they are
    not is_stash=True themselves), but their cost changes go to stash_current.

    Args:
        fighter: The fighter to check

    Returns:
        True if costs should go to stash_current instead of rating_current
    """
    # Direct stash fighter
    if fighter.is_stash:
        return True

    # Child fighter (vehicle/exotic beast) linked to stash via source_assignment
    if fighter.is_child_fighter:
        parent_assignment = fighter.source_assignment.first()
        if parent_assignment:
            return parent_assignment.list_fighter.is_stash

    return False
