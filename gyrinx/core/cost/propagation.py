"""Cost propagation functions for updating cached rating fields."""

from dataclasses import dataclass

from django.conf import settings
from django.db.models import F, Value
from django.db.models.functions import Greatest

from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)
from gyrinx.tracing import traced


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


def _apply_to_list(lst: "List", rating_delta: int = 0, stash_delta: int = 0) -> None:
    """Apply a rating/stash movement to the list-level cache.

    The single list-cache writer for the push path. Values clamp at zero
    (the fields are PositiveIntegerField); the dirty flag is untouched —
    recording an action never applies anything.

    The write is a DB-side atomic update (F expressions), so concurrent
    propagations against the same list cannot lose each other's deltas to a
    read-modify-write race. QuerySet.update matches how facts_from_db writes
    these cache columns: no signals, no history churn. The instance is
    mirrored in Python so callers see the post-move values without a refetch.
    """
    if not rating_delta and not stash_delta:
        return
    List.objects.filter(pk=lst.pk).update(
        rating_current=Greatest(Value(0), F("rating_current") + rating_delta),
        stash_current=Greatest(Value(0), F("stash_current") + stash_delta),
    )
    lst.rating_current = max(0, lst.rating_current + rating_delta)
    lst.stash_current = max(0, lst.stash_current + stash_delta)


def _fighter_list_deltas(fighter: "ListFighter", delta: int) -> dict:
    """Bucket a fighter-level movement into the list's rating or stash."""
    if fighter.is_stash:
        return {"stash_delta": delta}
    return {"rating_delta": delta}


@traced("propagate_from_assignment")
def propagate_from_assignment(
    assignment: "ListFighterEquipmentAssignment",
    delta: Delta,
    update_list: bool = True,
) -> Delta:
    """
    Propagate rating changes to assignment, fighter, and list cached fields.

    Updates:
    - assignment.rating_current
    - fighter.rating_current
    - list.rating_current or list.stash_current (by whether the holding
      fighter is the stash) — create_action() records but never applies

    Clears dirty flags on the assignment and fighter (not the list).

    This should be called within a transaction.

    Only propagates when the list action system is enabled (list has a
    latest_action and FEATURE_LIST_ACTION_CREATE_INITIAL is True).

    Args:
        assignment: The equipment assignment whose cost changed
        delta: The change in the assignment's rating

    Returns:
        The delta, for chaining
    """
    if not _should_propagate(delta.list):
        return delta

    if not delta.has_change:
        # No change, return zero-delta
        return delta

    # Update assignment (rating can be negative for negative-cost equipment)
    assignment.rating_current = int(assignment.rating_current + delta.delta)
    assignment.dirty = False
    assignment.save(update_fields=["rating_current", "dirty"])

    # Walk up to fighter (rating can be negative for negative-cost equipment)
    fighter = assignment.list_fighter
    fighter.rating_current = int(fighter.rating_current + delta.delta)
    fighter.dirty = False
    fighter.save(update_fields=["rating_current", "dirty"])

    # Walk up to the list: gear on the stash fighter moves the stash book,
    # gear on anyone else moves the rating book. Multi-step flows
    # (reassignment) pass update_list=False and apply their NET list
    # movement once via propagate_to_list, so an intermediate zero-clamp
    # can't distort the total.
    if update_list:
        _apply_to_list(delta.list, **_fighter_list_deltas(fighter, delta.delta))

    return delta


@traced("propagate_from_fighter")
def propagate_from_fighter(
    fighter: "ListFighter",
    delta: Delta,
    update_list: bool = True,
) -> Delta:
    """
    Propagate a rating change from a fighter.

    Use when fighter's own cost changes (e.g., base cost override,
    advancement cost change).

    Updates:
    - fighter.rating_current
    - list.rating_current or list.stash_current (by whether the fighter is
      the stash) — create_action() records but never applies

    Clears the fighter's dirty flag (not the list's).

    This should be called within a transaction (typically inside transact()).

    Only propagates when the list action system is enabled (list has a
    latest_action and FEATURE_LIST_ACTION_CREATE_INITIAL is True).

    Args:
        fighter: The fighter whose cost changed
        delta: The change in the fighter's rating

    Returns:
        The delta, for chaining
    """
    if not _should_propagate(delta.list):
        return delta

    if not delta.has_change:
        # No change, return zero-delta
        return delta

    # Update fighter (rating can be negative for negative-cost equipment)
    fighter.rating_current = int(fighter.rating_current + delta.delta)
    fighter.dirty = False
    fighter.save(update_fields=["rating_current", "dirty"])

    if update_list:
        _apply_to_list(delta.list, **_fighter_list_deltas(fighter, delta.delta))

    return delta


@traced("propagate_to_list")
def propagate_to_list(
    lst: "List",
    *,
    rating_delta: int = 0,
    stash_delta: int = 0,
) -> None:
    """
    Apply a list-level cache movement with no fighter-level counterpart.

    For flows where the list total moves but no individual fighter's own
    cached rating should change — archiving or selling a fighter (the
    fighter keeps its rating_current; it's simply excluded from the list
    aggregate), capture transfers, and similar. Buckets are explicit
    because there is no fighter to infer them from.

    Only propagates when the list action system is enabled, matching the
    other propagation entry points.
    """
    if not _should_propagate(lst):
        return
    _apply_to_list(lst, rating_delta=rating_delta, stash_delta=stash_delta)
