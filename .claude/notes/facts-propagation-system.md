# Facts & Propagation System Architecture

> **ARCHIVED**: This internal working document has been superseded by public documentation. See:
> - [Fighter Cost System Reference](../../docs/fighter-cost-system-reference.md) - Facts API
> - [Cost Handler Development Guide](../../docs/how-to-guides/handler-development.md) - Handler patterns
> - [Cost Propagation Architecture](../../docs/technical-design/cost-propagation-architecture.md) - Technical details
>
> This file is kept for historical reference only.

## Overview

The codebase has TWO systems for keeping cached values in sync:

1. **Facts System** - Pull-based: Recalculate from database on demand
2. **Propagation System** - Push-based: Update cached values incrementally when changes occur

## Facts System

### Core Methods

```
facts()          -> Returns cached NamedTuple or None if dirty
facts_from_db()  -> Recalculates from DB, optionally updates cached fields
```

### Data Flow

```
List.facts_from_db()
├── Walks all fighters via listfighter_set
├── For each fighter: calls fighter.cost_int()
│   ├── Checks is_child_fighter (0 if linked)
│   ├── Checks should_have_zero_cost (captured/sold)
│   ├── Returns base_cost + equipment costs
├── Separates stash vs non-stash fighters
├── Returns ListFacts(rating, stash, credits, wealth)
└── If update=True: saves rating_current, stash_current, dirty=False
```

### When Used

- Object creation via `create_with_facts()`
- Clone operations
- Manual refresh (`refresh_list_cost` view)
- Anywhere outside the action/propagation system

## Propagation System

### Core Functions (gyrinx/core/cost/propagation.py)

```python
propagate_from_assignment(assignment, Delta)  # Equipment added/removed
propagate_from_fighter(fighter, Delta)        # Fighter changes
```

### Data Flow

```
Handler detects change
├── Calculates delta (cost difference)
├── Calls propagate_from_* with Delta(delta=N, list=lst)
├── propagate_from_assignment:
│   ├── Updates assignment.rating_current += delta
│   ├── Updates fighter.rating_current += delta
│   ├── Sets dirty=False on both
│   └── Does NOT update List (create_action does that)
├── propagate_from_fighter:
│   ├── Updates fighter.rating_current += delta
│   ├── Sets dirty=False
│   └── Does NOT update List
└── create_action:
    └── Updates list.rating_current/stash_current via delta
```

### Guard Condition

Propagation only runs when:
```python
def _should_propagate(lst):
    return lst.latest_action and settings.FEATURE_LIST_ACTION_CREATE_INITIAL
```

This means:
- List must have at least one ListAction (initial state recorded)
- Feature flag must be enabled

## The Two Systems Interact

### Scenario: Handler adds equipment

```
handle_equipment_addition()
├── If _should_propagate():
│   ├── propagate_from_assignment() updates fighter.rating_current
│   └── create_action() updates list.rating_current
└── Else:
    └── Nothing updates cached values (they're dirty)
```

### Scenario: Clone operation (OUTSIDE propagation)

```
fighter.clone()
├── Creates new fighter with equipment
├── If _should_propagate():
│   └── Handler will call propagate, DON'T call facts_from_db
└── Else:
    └── MUST call facts_from_db() to set rating_current
```

This is why `ListFighter.clone()` has the conditional:
```python
if not (clone.list.latest_action and settings.FEATURE_LIST_ACTION_CREATE_INITIAL):
    clone.facts_from_db(update=True)
```

## Critical Invariant

**Only ONE system should update cached values for any given operation.**

| Operation | System | Why |
|-----------|--------|-----|
| Handler (add/remove equipment) | Propagation | Incremental delta |
| Clone | Facts | Not in handler context |
| Direct create | Facts | No delta to propagate |
| Signal-triggered create | Facts | No handler context |

## The create_with_facts() Pattern

Guarantees correct initial state:
1. Creates object (dirty=True by default)
2. Immediately calls facts_from_db(update=True)
3. Object now has dirty=False and correct rating_current

Alternative (facts_from_db after M2M):
1. Create object (dirty=True)
2. Add M2M relations (equipment profiles, etc.)
3. Call facts_from_db(update=True)
4. Object now has dirty=False and correct rating_current

## Edge Cases

### Child Fighters

Child fighters have `cost_int() = 0` but only AFTER `source_assignment` link exists.

Sequence matters:
```python
# WRONG: cost_int() returns base_cost
lf = ListFighter.objects.create(...)
lf.facts_from_db()  # Calculates wrong value!
assignment.child_fighter = lf

# RIGHT: cost_int() returns 0
lf = ListFighter.objects.create(...)
assignment.child_fighter = lf
assignment.save()
lf.facts_from_db()  # Now is_child_fighter=True, cost=0
```

### Stash Fighters

Stash fighters contribute to `stash_current` not `rating_current`.
Facts system handles this by checking `fighter.is_stash`.

### Clone with Equipment

When cloning a list, stash equipment is cloned via:
```python
for assignment in original_stash._direct_assignments():
    assignment.clone(list_fighter=new_stash)
```

`assignment.clone()` updates its own `rating_current` but NOT the fighter's.
Must call `new_stash.facts_from_db(update=True)` after all equipment cloned.

## Debug Visibility

New properties for debugging:
```python
List.debug_facts_in_sync       # True if facts() matches calculated values
ListFighter.debug_facts_in_sync  # True if facts().rating == cost_int()
```

Used in debug templates to show red flag when out of sync.
