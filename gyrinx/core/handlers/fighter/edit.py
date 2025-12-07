"""Handler for fighter edit operations."""

from dataclasses import dataclass, field
from typing import Any, Optional

from django.db import transaction

from gyrinx.content.models import ContentFighter
from gyrinx.core.handlers.fighter.advancement import _is_fighter_stash_linked
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import ListFighter
from gyrinx.tracing import traced


@dataclass
class FieldChange:
    """Represents a single field change on a fighter."""

    field_name: str
    old_value: Any
    new_value: Any
    description: str
    rating_delta: int = 0
    stash_delta: int = 0


@dataclass
class FighterEditResult:
    """Result of editing fighter properties."""

    fighter: ListFighter
    changes: list[FieldChange] = field(default_factory=list)
    list_actions: list[ListAction] = field(default_factory=list)


@traced("_generate_field_description")
def _generate_field_description(
    field_name: str,
    old_value: Any,
    new_value: Any,
    cost_delta: int = 0,
) -> str:
    """Generate a human-readable description for a field change."""
    if field_name == "name":
        return f"Renamed from '{old_value}' to '{new_value}'"

    if field_name == "content_fighter":
        old_name = old_value.name() if old_value else "None"
        new_name = new_value.name() if new_value else "None"
        return f"Changed type from {old_name} to {new_name}"

    if field_name == "legacy_content_fighter":
        if old_value is None and new_value is not None:
            return f"Set legacy fighter to {new_value.name()}"
        elif old_value is not None and new_value is None:
            return f"Removed legacy fighter {old_value.name()}"
        else:
            old_name = old_value.name() if old_value else "None"
            new_name = new_value.name() if new_value else "None"
            return f"Changed legacy fighter from {old_name} to {new_name}"

    if field_name == "category_override":
        if old_value in (None, "") and new_value not in (None, ""):
            return f"Set category override to {new_value}"
        elif old_value not in (None, "") and new_value in (None, ""):
            return f"Removed category override ({old_value})"
        else:
            return f"Changed category override from {old_value} to {new_value}"

    if field_name == "cost_override":
        if old_value is None and new_value is not None:
            return f"Set cost override to {new_value}\u00a2 ({cost_delta:+}\u00a2)"
        elif old_value is not None and new_value is None:
            return f"Removed cost override of {old_value}\u00a2 ({cost_delta:+}\u00a2)"
        else:
            return f"Changed cost override from {old_value}\u00a2 to {new_value}\u00a2 ({cost_delta:+}\u00a2)"

    # Fallback for unknown fields
    return f"Changed {field_name} from {old_value} to {new_value}"


@traced("calculate_cost_delta")
def _calculate_cost_delta(
    fighter: ListFighter,
    old_cost_override: Optional[int],
    new_cost_override: Optional[int],
) -> int:
    """
    Calculate the cost delta when changing cost_override.

    The delta is the difference between the new effective cost and the old effective cost.

    Cases:
    1. No override -> Set override: new_override - calculated_cost
    2. Has override -> Clear override: calculated_cost - old_override
    3. Change override: new_override - old_override
    4. No change: 0
    """
    # Get the calculated cost (without any override)
    calculated_cost = fighter._base_cost_before_override()

    # Determine old effective cost
    if old_cost_override is not None:
        old_effective_cost = old_cost_override
    else:
        old_effective_cost = calculated_cost

    # Determine new effective cost
    if new_cost_override is not None:
        new_effective_cost = new_cost_override
    else:
        new_effective_cost = calculated_cost

    return new_effective_cost - old_effective_cost


@traced("detect_field_changes")
def _detect_field_changes(
    fighter: ListFighter,
    old_name: Optional[str],
    old_content_fighter: Optional[ContentFighter],
    old_legacy_content_fighter: Optional[ContentFighter],
    old_category_override: Optional[str],
    old_cost_override: Optional[int],
    is_stash_linked: bool,
) -> list[FieldChange]:
    """
    Detect which fields have changed by comparing old values with fighter's current values.

    The fighter object should already have new values applied. We compare the old values
    passed as parameters with the fighter's current values to detect changes.

    Note: For optional fields, we use _UNCHANGED sentinel to mean "skip this comparison".
    """
    changes = []

    # Name change
    if old_name is not None and old_name != fighter.name:
        changes.append(
            FieldChange(
                field_name="name",
                old_value=old_name,
                new_value=fighter.name,
                description=_generate_field_description("name", old_name, fighter.name),
            )
        )

    # Content fighter change
    if (
        old_content_fighter is not None
        and old_content_fighter != fighter.content_fighter
    ):
        changes.append(
            FieldChange(
                field_name="content_fighter",
                old_value=old_content_fighter,
                new_value=fighter.content_fighter,
                description=_generate_field_description(
                    "content_fighter", old_content_fighter, fighter.content_fighter
                ),
            )
        )

    # Legacy content fighter change (can be set to None)
    if old_legacy_content_fighter is not _UNCHANGED:
        new_value = fighter.legacy_content_fighter
        if old_legacy_content_fighter != new_value:
            changes.append(
                FieldChange(
                    field_name="legacy_content_fighter",
                    old_value=old_legacy_content_fighter,
                    new_value=new_value,
                    description=_generate_field_description(
                        "legacy_content_fighter", old_legacy_content_fighter, new_value
                    ),
                )
            )

    # Category override change (can be set to empty string)
    if old_category_override is not _UNCHANGED:
        new_value = fighter.category_override
        if old_category_override != new_value:
            changes.append(
                FieldChange(
                    field_name="category_override",
                    old_value=old_category_override,
                    new_value=new_value,
                    description=_generate_field_description(
                        "category_override", old_category_override, new_value
                    ),
                )
            )

    # Cost override change (can be set to None, and affects rating/stash)
    if old_cost_override is not _UNCHANGED:
        new_value = fighter.cost_override
        if old_cost_override != new_value:
            cost_delta = _calculate_cost_delta(fighter, old_cost_override, new_value)
            changes.append(
                FieldChange(
                    field_name="cost_override",
                    old_value=old_cost_override,
                    new_value=new_value,
                    description=_generate_field_description(
                        "cost_override", old_cost_override, new_value, cost_delta
                    ),
                    rating_delta=cost_delta if not is_stash_linked else 0,
                    stash_delta=cost_delta if is_stash_linked else 0,
                )
            )

    return changes


# Sentinel value to distinguish "not provided" from "set to None"
class _Unchanged:
    """Sentinel to indicate a field was not provided (vs explicitly set to None)."""

    def __repr__(self):
        return "<UNCHANGED>"


_UNCHANGED = _Unchanged()


@traced("handle_fighter_edit")
@transaction.atomic
def handle_fighter_edit(
    *,
    user,
    fighter: ListFighter,
    old_name: Optional[str] = None,
    old_content_fighter: Optional[ContentFighter] = None,
    old_legacy_content_fighter: Optional[ContentFighter] = _UNCHANGED,
    old_category_override: Optional[str] = _UNCHANGED,
    old_cost_override: Optional[int] = _UNCHANGED,
) -> Optional[FighterEditResult]:
    """
    Handle fighter property edits with ListAction tracking.

    The fighter object should already have the new values applied (e.g., by Django's
    ModelForm validation). This handler compares the old values with the fighter's
    current values to detect changes, saves the fighter, and creates ListActions.

    Creates a separate ListAction for each field that changes. Only cost_override
    changes include rating/stash deltas; other field changes have zero deltas
    (audit tracking only).

    Args:
        user: The user performing the edit
        fighter: The fighter with new values already applied (not yet saved)
        old_name: Previous name (None = skip comparison)
        old_content_fighter: Previous content fighter type (None = skip comparison)
        old_legacy_content_fighter: Previous legacy fighter (_UNCHANGED = skip)
        old_category_override: Previous category override (_UNCHANGED = skip)
        old_cost_override: Previous cost override (_UNCHANGED = skip)

    Returns:
        FighterEditResult with fighter and all created actions, or None if no changes
    """
    lst = fighter.list

    # Capture before values for ListAction
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # Determine if this fighter's cost changes go to stash
    is_stash_linked = _is_fighter_stash_linked(fighter)

    # Detect all changes by comparing old values with fighter's current (new) values
    changes = _detect_field_changes(
        fighter=fighter,
        old_name=old_name,
        old_content_fighter=old_content_fighter,
        old_legacy_content_fighter=old_legacy_content_fighter,
        old_category_override=old_category_override,
        old_cost_override=old_cost_override,
        is_stash_linked=is_stash_linked,
    )

    # If nothing changed, return None (idempotent)
    if not changes:
        return None

    # Save fighter (the new values were already applied by the form)
    fighter.save()

    # Create ListAction for each change
    list_actions = []
    for change in changes:
        # After each action, the "before" values for the next action are the "after" values
        # of the previous. But since we're in a single transaction and all changes happen
        # atomically, we use the original before values for all actions.
        action = lst.create_action(
            user=user,
            action_type=ListActionType.UPDATE_FIGHTER,
            subject_app="core",
            subject_type="ListFighter",
            subject_id=fighter.id,
            description=f"{fighter.name}: {change.description}",
            list_fighter=fighter,
            rating_delta=change.rating_delta,
            stash_delta=change.stash_delta,
            credits_delta=0,
            rating_before=rating_before,
            stash_before=stash_before,
            credits_before=credits_before,
        )
        if action is not None:
            list_actions.append(action)

        # Update before values for next action (cumulative tracking)
        rating_before += change.rating_delta
        stash_before += change.stash_delta

    return FighterEditResult(
        fighter=fighter,
        changes=changes,
        list_actions=list_actions,
    )
