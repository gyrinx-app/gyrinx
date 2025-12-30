# Cost Handler Development Guide

This guide explains how to create handlers that modify cost-related data in Gyrinx. Handlers encapsulate business logic for operations like purchasing equipment, removing items, and selling from stash.

> **Prerequisites**: Familiarity with [Fighter Cost System Reference](../fighter-cost-system-reference.md) and Django transactions.

## Overview

Handlers are functions that:

1. Perform business logic atomically (within a transaction)
2. Calculate cost deltas before and after changes
3. Propagate cost changes through the cache hierarchy
4. Create `ListAction` records for audit trails

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `Delta` | `gyrinx/core/cost/propagation.py` | Represents a cost change to propagate |
| `propagate_from_assignment()` | `gyrinx/core/cost/propagation.py` | Updates assignment and fighter cache |
| `propagate_from_fighter()` | `gyrinx/core/cost/propagation.py` | Updates fighter cache |
| `is_stash_linked()` | `gyrinx/core/cost/routing.py` | Determines rating vs stash routing |
| `create_action()` | `gyrinx/core/models/list.py` | Creates ListAction and updates list cache |

---

## Handler Structure

Every cost handler follows this pattern:

```python
from dataclasses import dataclass
from typing import Optional

from django.db import transaction

from gyrinx.core.cost.propagation import Delta, propagate_from_assignment
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.tracing import traced


@dataclass
class MyOperationResult:
    """Result of the operation."""
    # Include relevant return data
    cost_delta: int
    description: str
    list_action: ListAction


@traced("handle_my_operation")
@transaction.atomic
def handle_my_operation(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    # ... other required args
) -> MyOperationResult:
    """
    Handle the operation atomically.

    Docstring should explain:
    1. What operations are performed
    2. Args and their purposes
    3. What's returned
    4. What exceptions can be raised
    """
    # 1. Capture before values
    # 2. Calculate cost delta
    # 3. Build ListAction args
    # 4. Perform the mutation
    # 5. Propagate cost changes
    # 6. Create ListAction
    # 7. Return result
```

### Required Decorators

- `@traced("handler_name")` - Enables tracing for performance monitoring
- `@transaction.atomic` - Ensures all operations succeed or none do

### Result Dataclasses

Always return a typed result dataclass rather than a tuple or dict:

```python
@dataclass
class EquipmentPurchaseResult:
    assignment: ListFighterEquipmentAssignment
    total_cost: int
    description: str
    list_action: ListAction
    campaign_action: Optional[CampaignAction]
```

---

## The Delta Pattern

The `Delta` dataclass represents a cost change that needs to propagate up the cache hierarchy:

```python
from gyrinx.core.cost.propagation import Delta

delta = Delta(
    delta=total_cost,  # The amount to add (positive) or remove (negative)
    list=lst,          # Reference to the list (for guard condition)
)

# Check if there's an actual change
if delta.has_change:
    propagate_from_assignment(assignment, delta)
```

### Calculating Deltas

For additions (purchases):

```python
total_cost = assignment.cost_int()
delta = Delta(delta=total_cost, list=lst)
```

For removals:

```python
equipment_cost = assignment.cost_int()
delta = Delta(delta=-equipment_cost, list=lst)  # Negative!
```

For changes (upgrades):

```python
old_cost = assignment.upgrade_cost_int()
new_cost = sum(assignment._upgrade_cost_with_override(u) for u in new_upgrades)
cost_difference = new_cost - old_cost  # Can be positive or negative
delta = Delta(delta=cost_difference, list=lst)
```

---

## Propagation Functions

### When to Use Which

| Scenario | Function | Example |
|----------|----------|---------|
| Equipment added/removed/changed | `propagate_from_assignment()` | Purchase, accessory addition |
| Fighter-level change (no assignment) | `propagate_from_fighter()` | Advancement, base cost override |
| Deleting assignment | `propagate_from_fighter()` | Equipment removal (assignment deleted) |

### propagate_from_assignment()

Updates both the assignment and its parent fighter:

```python
from gyrinx.core.cost.propagation import propagate_from_assignment, Delta

propagate_from_assignment(assignment, Delta(delta=total_cost, list=lst))

# What it does:
# 1. assignment.rating_current += delta
# 2. fighter.rating_current += delta
# 3. Sets dirty=False on both
# 4. Does NOT update List (create_action does that)
```

### propagate_from_fighter()

Updates only the fighter (use when assignment doesn't exist or will be deleted):

```python
from gyrinx.core.cost.propagation import propagate_from_fighter, Delta

propagate_from_fighter(fighter, Delta(delta=-equipment_cost, list=lst))

# What it does:
# 1. fighter.rating_current += delta
# 2. Sets dirty=False
# 3. Does NOT update List
```

### The Guard Condition

Propagation only runs when:

```python
def _should_propagate(lst):
    return lst.latest_action and settings.FEATURE_LIST_ACTION_CREATE_INITIAL
```

This prevents double-counting between the facts system (pull-based) and propagation system (push-based). You don't need to check this manually - the propagation functions handle it.

---

## Rating vs Stash Routing

Costs go to different fields depending on the fighter type:

| Fighter Type | Cost Field | `is_stash` | `is_stash_linked()` |
|--------------|------------|------------|---------------------|
| Active fighter | `rating_current` | `False` | `False` |
| Stash fighter | `stash_current` | `True` | `True` |
| Vehicle/beast on stash | `stash_current` | `False` | `True` |
| Vehicle/beast on active | `rating_current` | `False` | `False` |

### Using is_stash_linked()

For complex scenarios involving child fighters:

```python
from gyrinx.core.cost.routing import is_stash_linked

# Simple case: check direct stash
is_stash = fighter.is_stash
rating_delta = cost if not is_stash else 0
stash_delta = cost if is_stash else 0

# Complex case: child fighters (vehicles/exotic beasts)
is_stash = is_stash_linked(fighter)  # Checks parent assignment too
```

---

## Creating ListActions

Every cost change must create a `ListAction` to:

1. Track before/after values for audit
2. Apply deltas to the list's cached fields
3. Enable undo/history features

### Building ListAction Args

Capture before values and calculate deltas **before** any mutations:

```python
# Capture BEFORE values
rating_before = lst.rating_current
stash_before = lst.stash_current
credits_before = lst.credits_current

# Calculate deltas based on stash status
is_stash = fighter.is_stash
la_args = dict(
    rating_delta=total_cost if not is_stash else 0,
    stash_delta=total_cost if is_stash else 0,
    credits_delta=-total_cost if lst.is_campaign_mode else 0,
    rating_before=rating_before,
    stash_before=stash_before,
    credits_before=credits_before,
)
```

### Calling create_action()

```python
list_action = lst.create_action(
    user=user,
    action_type=ListActionType.ADD_EQUIPMENT,  # or UPDATE_EQUIPMENT, REMOVE_EQUIPMENT, etc.
    subject_app="core",
    subject_type="ListFighterEquipmentAssignment",
    subject_id=assignment.id,
    description="Added Lasgun to Ganger (10c)",
    list_fighter=fighter,
    list_fighter_equipment_assignment=assignment,  # None if deleted
    update_credits=True,  # Set True if credits_delta should be applied
    **la_args,
)
```

### Key Parameters

| Parameter | Purpose |
|-----------|---------|
| `rating_delta` | Change to `lst.rating_current` |
| `stash_delta` | Change to `lst.stash_current` |
| `credits_delta` | Change to `lst.credits_current` |
| `update_credits` | Set `True` to apply `credits_delta` to list |
| `*_before` | Before values for audit trail |

---

## Complete Example: Equipment Sale

This example shows a handler that sells equipment from stash, demonstrating negative deltas and credit addition:

```python
@dataclass
class EquipmentSaleResult:
    """Result of a successful equipment sale."""
    total_sale_credits: int
    total_equipment_cost: int
    description: str
    list_action: ListAction


@traced("handle_equipment_sale")
@transaction.atomic
def handle_equipment_sale(
    *,
    user,
    lst: List,
    fighter: ListFighter,
    assignment: ListFighterEquipmentAssignment,
    sale_price: int,
) -> EquipmentSaleResult:
    """
    Handle sale of equipment from stash.

    Operations:
    1. Validate fighter is stash
    2. Capture before values
    3. Calculate equipment cost and sale proceeds
    4. Delete assignment or remove components
    5. Propagate negative cost delta
    6. Create ListAction with credit increase
    """
    # 1. Validate
    if not fighter.is_stash:
        raise ValidationError("Can only sell from stash")

    # 2. Capture before values
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # 3. Calculate costs
    equipment_cost = assignment.cost_int()
    assignment_id = assignment.id

    # Deltas: stash decreases (negative), credits increase (positive)
    stash_delta = -equipment_cost
    credits_delta = sale_price
    rating_delta = 0  # Selling is from stash only

    # 4. Propagate BEFORE deletion (use propagate_from_fighter since assignment deleted)
    propagate_from_fighter(fighter, Delta(delta=-equipment_cost, list=lst))

    # 5. Delete assignment
    assignment.delete()

    # 6. Create ListAction
    description = f"Sold equipment for {sale_price}c"
    list_action = lst.create_action(
        user=user,
        action_type=ListActionType.REMOVE_EQUIPMENT,
        subject_app="core",
        subject_type="ListFighterEquipmentAssignment",
        subject_id=assignment_id,
        description=description,
        list_fighter=fighter,
        list_fighter_equipment_assignment=None,  # Deleted
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
        update_credits=True,  # Apply credit increase
    )

    return EquipmentSaleResult(
        total_sale_credits=sale_price,
        total_equipment_cost=equipment_cost,
        description=description,
        list_action=list_action,
    )
```

---

## Testing Handlers

Handlers are designed for easy testing without HTTP machinery:

```python
import pytest
from gyrinx.core.handlers.equipment.sale import handle_equipment_sale

@pytest.mark.django_db
def test_equipment_sale_updates_credits(user, list_with_stash):
    lst = list_with_stash
    stash = lst.stash_fighter
    assignment = stash.equipment_assignments.first()

    initial_credits = lst.credits_current
    equipment_cost = assignment.cost_int()
    sale_price = equipment_cost // 2

    result = handle_equipment_sale(
        user=user,
        lst=lst,
        fighter=stash,
        assignment=assignment,
        sale_price=sale_price,
    )

    lst.refresh_from_db()
    assert lst.credits_current == initial_credits + sale_price
    assert result.list_action is not None
```

---

## Existing Handlers Reference

| Handler | Location | Purpose |
|---------|----------|---------|
| `handle_equipment_purchase` | `handlers/equipment/purchase.py` | Buy equipment for fighter |
| `handle_accessory_purchase` | `handlers/equipment/purchase.py` | Add accessory to equipment |
| `handle_weapon_profile_purchase` | `handlers/equipment/purchase.py` | Add weapon profile |
| `handle_equipment_upgrade` | `handlers/equipment/purchase.py` | Change equipment upgrades |
| `handle_equipment_removal` | `handlers/equipment/removal.py` | Remove equipment from fighter |
| `handle_equipment_component_removal` | `handlers/equipment/removal.py` | Remove profile/accessory/upgrade |
| `handle_equipment_sale` | `handlers/equipment/sale.py` | Sell equipment from stash |
| `handle_equipment_reassignment` | `handlers/equipment/reassignment.py` | Move equipment between fighters |
| `handle_equipment_cost_override` | `handlers/equipment/cost_override.py` | Override equipment cost |
| `handle_fighter_advancement` | `handlers/fighter/advancement.py` | Apply advancement to fighter |
| `handle_fighter_kill` | `handlers/fighter/kill.py` | Kill fighter in campaign |

---

## Common Pitfalls

### 1. Forgetting to propagate before deletion

```python
# WRONG: Assignment deleted before propagation
assignment.delete()
propagate_from_assignment(assignment, delta)  # Error! Assignment gone

# RIGHT: Propagate first, then delete
propagate_from_fighter(fighter, delta)  # Use fighter-level propagation
assignment.delete()
```

### 2. Wrong propagation function for deletion

```python
# WRONG: Using assignment propagation when deleting
propagate_from_assignment(assignment, delta)
assignment.delete()

# RIGHT: Use fighter propagation when assignment will be deleted
propagate_from_fighter(fighter, delta)
assignment.delete()
```

### 3. Missing update_credits=True

```python
# WRONG: Credits delta calculated but not applied
lst.create_action(
    credits_delta=sale_price,
    # Missing update_credits=True
)

# RIGHT: Explicitly enable credit updates
lst.create_action(
    credits_delta=sale_price,
    update_credits=True,
)
```

### 4. Calculating deltas after mutation

```python
# WRONG: Cost calculated after changes
assignment.weapon_accessories_field.add(accessory)
cost = assignment.cost_int()  # Now includes new accessory

# RIGHT: Calculate before changes
cost = assignment.accessory_cost_int(accessory)  # Just the accessory
assignment.weapon_accessories_field.add(accessory)
```

---

## See Also

- [Fighter Cost System Reference](../fighter-cost-system-reference.md) - Cost calculation hierarchy
- [Fighter Cost System Design](../fighter-cost-system-design.md) - Design decisions and philosophy
- [Cost Propagation Architecture](../technical-design/cost-propagation-architecture.md) - Technical architecture
