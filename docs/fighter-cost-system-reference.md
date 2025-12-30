# Fighter Cost System Reference Guide

This document provides a comprehensive reference for the fighter cost calculation system in Gyrinx, including how costs are calculated, overridden, and displayed throughout the application.

> **See also:** [Fighter Cost System Design Guide](fighter-cost-system-design.md) for the design philosophy and architectural decisions behind this system.

## Overview

The fighter cost system calculates the total cost of a fighter by combining:

- Base fighter cost
- Equipment costs
- Weapon profile costs
- Weapon accessory costs
- Equipment upgrade costs
- Campaign advancement costs

## Cost Calculation Flow

### 1. List Total Cost

The total cost of a list is calculated by:

```
Total List Cost = Sum of all fighter costs + Current credits
```

Implementation: `List.cost_int()` in `gyrinx/core/models/list.py:137`

### 2. Fighter Cost

Each fighter's cost is calculated as:

```
Fighter Cost = Base Cost + Advancement Cost + Sum of Equipment Assignment Costs
```

Implementation: `ListFighter.cost_int()` in `gyrinx/core/models/list.py:543`

### 3. Base Fighter Cost

The base cost follows this priority hierarchy:

1. User override: `ListFighter.cost_override` (if set)
2. Child fighter: 0 (if fighter is child of another)
3. House override: `ContentFighterHouseOverride.cost` (if exists)
4. Content fighter: `ContentFighter.base_cost`

Implementation: `ListFighter._base_cost_int` property in `gyrinx/core/models/list.py:567`

### 4. Equipment Assignment Cost

Each equipment assignment's cost is:

```
Assignment Cost = Base Equipment Cost + Profile Costs + Accessory Costs + Upgrade Costs
```

Or if total cost override is set:

```
Assignment Cost = total_cost_override
```

Implementation: `ListFighterEquipmentAssignment.cost_int()` in `gyrinx/core/models/list.py:1333`

### 5. Equipment Base Cost

Equipment base cost priority:

1. Assignment override: `ListFighterEquipmentAssignment.cost_override`
2. Linked equipment: 0 (if equipment is linked/child)
3. Fighter equipment list: `ContentFighterEquipmentListItem.cost`
4. Base equipment: `ContentEquipment.cost`

Implementation: `ListFighterEquipmentAssignment._equipment_cost_with_override()` in `gyrinx/core/models/list.py:1354`

### 6. Weapon Profile Cost

Profile costs follow this priority:

1. Default assignment: 0 (if profile is part of default assignment)
2. Fighter equipment list: `ContentFighterEquipmentListItem.cost` (with weapon_profile)
3. Base profile: `ContentWeaponProfile.cost`

Implementation: `ListFighterEquipmentAssignment._profile_cost_with_override_for_profile()` in `gyrinx/core/models/list.py:1404`

### 7. Weapon Accessory Cost

Accessory costs follow this priority:

1. Default assignment: 0 (if accessory is part of default assignment)
2. Fighter equipment list: `ContentFighterEquipmentListWeaponAccessory.cost`
3. Base accessory: `ContentWeaponAccessory.cost`

Implementation: `ListFighterEquipmentAssignment._accessory_cost_with_override()` in `gyrinx/core/models/list.py:1469`

### 8. Equipment Upgrade Cost

Upgrade costs depend on the equipment's upgrade mode:

- Multi mode: Individual upgrade cost
- Single mode: Cumulative cost (sum of all upgrades up to selected position)

Implementation: `ContentEquipmentUpgrade.cost_int()` in `gyrinx/content/models.py:1528`

### 9. Campaign Advancement Cost

In campaign mode, advancements increase fighter cost:

```
Advancement Cost = Sum of all cost_increase values from ListFighterAdvancement
```

## Cost Override Models

### ContentFighterHouseOverride

Allows specific fighters to have different costs when added to specific houses.

Fields:

- `fighter`: The ContentFighter
- `house`: The ContentHouse
- `cost`: The override cost (nullable)

### ContentFighterEquipmentListItem

Defines fighter-specific costs for equipment and weapon profiles.

Fields:

- `fighter`: The ContentFighter
- `equipment`: The ContentEquipment
- `weapon_profile`: Optional specific profile
- `cost`: The override cost

### ContentFighterEquipmentListWeaponAccessory

Defines fighter-specific costs for weapon accessories.

Fields:

- `fighter`: The ContentFighter
- `weapon_accessory`: The ContentWeaponAccessory
- `cost`: The override cost

## Legacy Fighter System

The legacy fighter system supports the Venators' Gang Legacy rule, allowing them to use equipment from another house's fighter:

1. Legacy fighter: Set via `ListFighter.legacy_content_fighter`
2. Equipment list fighter: Property that returns legacy fighter if set, otherwise regular content fighter
3. Cost overrides: Check equipment_list_fighter for proper legacy support

Implementation: `ListFighter.equipment_list_fighter` property

## Special Cost Rules

### Zero Cost Items

- Stash fighters: Must have `base_cost = 0`
- Default assignments: Always cost 0
- Linked equipment: Child equipment in linked relationships cost 0
- Child fighters: Fighters created by equipment profiles cost 0

### Cost Display

All costs are displayed with the ¢ symbol using `format_cost_display()`:

- Regular display: "50¢"
- With sign: "+50¢" or "-50¢"
- Zero: "0¢"

## Virtual Equipment Assignment

The `VirtualListFighterEquipmentAssignment` class provides a unified interface for both:

- Direct equipment assignments (`ListFighterEquipmentAssignment`)
- Default equipment assignments (`ContentFighterDefaultAssignment`)

This allows consistent cost calculation regardless of assignment type.

## Facts System API

The facts system provides fast O(1) reads of cached cost values. Each cost-bearing model has database fields (`rating_current`, `dirty`) and methods to access them.

### Facts Dataclasses

Cached values are returned as immutable dataclasses (defined in `gyrinx/core/models/facts.py`):

```python
@dataclass(frozen=True)
class AssignmentFacts:
    rating: int

@dataclass(frozen=True)
class FighterFacts:
    rating: int

@dataclass(frozen=True)
class ListFacts:
    rating: int   # Sum of active fighter costs
    stash: int    # Stash fighter cost
    credits: int  # Liquid credits

    @property
    def wealth(self) -> int:
        return self.rating + self.stash + self.credits
```

### Cache Fields

Each level in the hierarchy has cached fields:

| Model | Fields |
|-------|--------|
| `List` | `rating_current`, `stash_current`, `credits_current`, `dirty` |
| `ListFighter` | `rating_current`, `dirty` |
| `ListFighterEquipmentAssignment` | `rating_current`, `dirty` |

### Facts Methods

Every cost-bearing model provides three methods:

#### facts() - Fast Cached Read

Returns cached values as a facts dataclass, or `None` if cache is stale:

```python
def facts(self) -> Optional[ListFacts]:
    """O(1) read from cached fields. Returns None if dirty=True."""
    if self.dirty:
        return None
    return ListFacts(
        rating=self.rating_current,
        stash=self.stash_current,
        credits=self.credits_current,
    )
```

#### facts_from_db() - Full Recalculation

Recalculates from database and optionally updates cache:

```python
def facts_from_db(self, update: bool = True) -> ListFacts:
    """
    Recalculate facts from database.

    If update=True: saves rating_current, clears dirty flag.
    Uses QuerySet.update() to bypass signals.
    """
```

#### facts_with_fallback() - Hybrid Read (List only)

Returns cached facts if clean, otherwise calculates without updating cache:

```python
def facts_with_fallback(self) -> ListFacts:
    """
    Get facts using cache if clean, otherwise calculate.
    Does NOT update cache - just reads or calculates.
    """
    facts = self.facts()
    if facts is not None:
        return facts
    # Calculate without updating cache
    return self._calculate_facts()
```

### When to Use Each Method

| Scenario | Method | Why |
|----------|--------|-----|
| Display in views | `facts()` then `facts_with_fallback()` | Fast read, fallback if stale |
| Object creation | `create_with_facts()` | Atomic creation with cache |
| Handler operations | Don't call - use propagation | Handlers use incremental updates |
| Manual refresh | `facts_from_db(update=True)` | Full recalculation |

### The create_with_facts() Pattern

For atomic object creation with correct initial cache state:

```python
# ListManager, ListFighterManager, ListFighterEquipmentAssignmentManager
def create_with_facts(self, **kwargs):
    """Create object and immediately calculate facts."""
    obj = self.create(**kwargs)  # dirty=True by default
    obj.facts_from_db(update=True)  # Now dirty=False
    return obj
```

### Display Methods

Display methods use the facts system internally:

```python
# List
def cost_display(self):
    facts = self.facts()
    if facts is not None:
        return format_cost_display(facts.wealth)
    return format_cost_display(self.facts_with_fallback().wealth)

# Similar for rating_display(), stash_fighter_cost_display()
```

### Dirty Flag Management

The `dirty` flag indicates cached values may be stale:

```python
# Mark as dirty (cascades upward)
assignment.set_dirty(save=True)  # Also marks fighter and list dirty
fighter.set_dirty(save=True)     # Also marks list dirty
lst.set_dirty(save=True)         # Only marks list dirty

# Cleared by:
# - facts_from_db(update=True)
# - Propagation functions (propagate_from_*)
```

## Cost Propagation

For write operations, the propagation system incrementally updates cached values rather than recalculating:

```python
from gyrinx.core.cost.propagation import propagate_from_assignment, Delta

# After adding equipment worth 10 credits
propagate_from_assignment(assignment, Delta(delta=10, list=lst))
# Updates: assignment.rating_current += 10, fighter.rating_current += 10
```

> **See also:** [Cost Handler Development Guide](how-to-guides/handler-development.md) for detailed handler patterns.

## Database Queries Optimization

The system uses several optimizations:

- `select_related()` for foreign keys
- `prefetch_related()` for many-to-many relationships
- Cached properties to avoid repeated calculations
- Annotation with cost overrides in querysets

### Prefetching for Facts System

To enable the facts system's `can_use_facts` property, views must use the appropriate prefetch:

```python
# Enables can_use_facts for list display
lists = List.objects.with_latest_actions()

# Full prefetch for detail views
lst = List.objects.with_related_data().get(pk=pk)

# Fighter-level prefetch
fighters = ListFighter.objects.with_related_data()
```

The `with_latest_actions()` method prefetches the most recent `ListAction`, which is required for the guard condition that enables the facts system.

## Common Usage Patterns

### Getting a List's Total Wealth

```python
# In views, always use prefetching first
lst = List.objects.with_latest_actions().get(pk=list_id)
wealth = lst.facts_with_fallback().wealth  # rating + stash + credits
```

### Getting a Fighter's Total Cost

```python
fighter = ListFighter.objects.get(id=fighter_id)
facts = fighter.facts()
if facts:
    total_cost = facts.rating  # Fast cached read
else:
    total_cost = fighter.cost_int()  # Full calculation
```

### Getting Equipment Cost with Override

```python
assignment = ListFighterEquipmentAssignment.objects.get(id=assignment_id)
facts = assignment.facts()
if facts:
    cost = facts.rating  # Fast cached read
else:
    cost = assignment.cost_int()  # Includes all overrides and sub-costs
```

### Checking for Cost Overrides

```python
# Fighter level
if fighter.has_cost_override:
    # User has manually set the cost

# Assignment level
if assignment.has_total_cost_override():
    # Total cost is manually overridden
```

## Error Handling

The system includes validation for:

- Negative costs (prevented in model `clean()` methods)
- Invalid cost strings (non-integer values)
- Circular equipment links
- Multiple fighter profiles for same equipment

## Cost Mixins

The cost system provides reusable mixins to standardize cost calculation behavior across models:

### CostMixin

`gyrinx.models.CostMixin` provides common cost methods for models with cost fields:

```python
class CostMixin(models.Model):
    """
    Mixin for models that have cost calculation logic.

    Attributes
    ----------
    cost_field_name : str
        The name of the field that stores the cost. Defaults to 'cost'.
        Can be overridden in subclasses if the field has a different name.
    """

    cost_field_name = "cost"

    def cost_int(self):
        """Returns the integer cost of this item."""

    def cost_display(self, show_sign=False):
        """Returns a readable cost string with currency symbol."""
```

Key features:

- Handles both integer and string cost fields
- Converts string costs to integers when possible
- Returns 0 for empty or non-numeric values
- Provides formatted display with ¢ symbol
- Supports custom field names via `cost_field_name` attribute

Usage example:

```python
class MyModel(CostMixin, models.Model):
    price = models.IntegerField()
    cost_field_name = "price"  # Override default field name
```

### FighterCostMixin

`gyrinx.models.FighterCostMixin` extends `CostMixin` for models with fighter-specific cost overrides:

```python
class FighterCostMixin(CostMixin):
    """
    Extended cost mixin for models that have fighter-specific cost overrides.
    """

    def cost_for_fighter_int(self):
        """Returns the fighter-specific cost if available."""
```

Key features:

- Inherits all functionality from `CostMixin`
- Adds `cost_for_fighter_int()` method
- Expects models to be annotated with `cost_for_fighter` attribute
- Raises `AttributeError` if annotation is missing

Usage with querysets:

```python
# Annotate queryset with fighter-specific costs
equipment = ContentEquipment.objects.with_cost_for_fighter(fighter)
cost = equipment.first().cost_for_fighter_int()
```

### Models Using Cost Mixins

The following models use these mixins:

- `ContentEquipment` (FighterCostMixin)
- `ContentWeaponProfile` (FighterCostMixin) - with custom `cost_display()` logic
- `ContentWeaponAccessory` (FighterCostMixin)
- `ContentEquipmentUpgrade` (CostMixin) - with custom `cost_int()` logic
- `ContentFighterEquipmentListItem` (CostMixin)
- `ContentFighterEquipmentListWeaponAccessory` (CostMixin)
- `ContentFighterEquipmentListUpgrade` (CostMixin)
- `ContentFighterDefaultAssignment` (CostMixin)

### Special Behaviors

Some models override the mixin methods for custom behavior:

ContentWeaponProfile:

- `cost_display()` returns empty for standard profiles (no name)
- Shows "+" prefix for named profiles with positive costs

ContentEquipmentUpgrade:

- `cost_int()` implements cumulative costs in SINGLE mode
- Sums all upgrades up to current position

## Testing

Key test files for the cost system:

- `gyrinx/core/tests/test_cost_display.py` - Cost formatting tests
- `gyrinx/core/tests/test_models_core.py` - Core cost calculation tests
- `gyrinx/core/tests/test_assignments.py` - Equipment assignment cost tests
- `gyrinx/content/tests/test_cost_methods.py` - Comprehensive tests for all cost mixins
