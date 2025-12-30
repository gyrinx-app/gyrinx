# Fighter Cost System Design Guide

This document explains the design philosophy and architectural decisions behind Gyrinx's fighter cost calculation system.

> **See also:** [Fighter Cost System Reference](fighter-cost-system-reference.md) for implementation details, code locations, and API reference.

## Quick Overview

```
LIST
├── cost_int() = sum(fighter.cost_int()) + stash_fighter.cost_int() + credits_current
│
├── ListFighter (non-archived, non-stash)
│   └── cost_int() = _base_cost_int + _advancement_cost_int + sum(assignment.cost_int())
│   │
│   ├── _base_cost_int
│   │   ├── cost_override (direct override on ListFighter)
│   │   ├── ContentFighterHouseOverride.cost (house-specific)
│   │   └── ContentFighter.cost_int() (base template cost)
│   │
│   ├── _advancement_cost_int
│   │   └── ListFighterAdvancement.cost_increase (non-archived only)
│   │
│   └── ListFighterEquipmentAssignment (via VirtualListFighterEquipmentAssignment wrapper)
│       └── cost_int() = base_cost + profiles_cost + accessories_cost + upgrades_cost
│       │
│       ├── base_cost_int
│       │   ├── total_cost_override (if set)
│       │   ├── cost_override (if set)
│       │   ├── linked_equipment_parent → returns 0
│       │   ├── ContentFighterEquipmentListItem.cost (fighter-specific)
│       │   └── ContentEquipment.cost_int() (base equipment cost)
│       │
│       ├── weapon_profiles_cost_int
│       │   └── ContentWeaponProfile (M2M: weapon_profiles_field)
│       │       ├── ContentFighterEquipmentListItem.cost (override)
│       │       ├── ContentEquipmentListExpansion cost (override)
│       │       └── ContentWeaponProfile.cost_int() (base)
│       │
│       ├── weapon_accessories_cost_int
│       │   └── ContentWeaponAccessory (M2M: weapon_accessories_field)
│       │       ├── cost_expression (% of weapon base cost)
│       │       ├── ContentFighterEquipmentListWeaponAccessory.cost
│       │       ├── ContentEquipmentListExpansion cost
│       │       └── ContentWeaponAccessory.cost_int()
│       │
│       └── upgrade_cost_int
│           └── ContentEquipmentUpgrade (M2M: upgrades_field)
│               ├── cumulative calc (for SINGLE mode)
│               ├── ContentFighterEquipmentListUpgrade.cost
│               └── ContentEquipmentUpgrade.cost
│
├── Stash Fighter (special ListFighter where content_fighter.is_stash=True)
│   └── stash_fighter_cost_int (same structure as above)
│
└── credits_current (IntegerField on List)
```

### Special Cost Cases

| Condition                                             | Cost Behavior      |
|-------------------------------------------------------|--------------------|
| Default equipment (`ContentFighterDefaultAssignment`) | Cost = 0           |
| Linked equipment (`child_fighter` set)                | Cost = 0           |
| Sold fighter (`capture_info.sold_to_guilders=True`)   | Cost = 0           |
| Archived fighter/advancement                          | Excluded from cost |

## Why This Complexity?

The fighter cost system might seem complex at first glance, but this complexity serves specific game mechanics from Necromunda. The system needs to handle:

1. Multiple sources of truth: Different rulebooks specify different costs for the same equipment depending on the fighter
2. House-specific rules: Some houses get discounts or pay premiums for certain fighters
3. Campaign progression: Fighters become more expensive as they gain experience
4. Equipment flexibility: The same weapon can have different profiles at different costs
5. Legacy rules: Special gang rules that allow using equipment from other houses

## Core Design Principles

### 1. Override Hierarchy

The system follows a clear hierarchy for determining costs:

```
User Input > Game Rules > Base Values
```

This hierarchy ensures that:

- Players have ultimate control: Manual overrides always win
- Special rules are respected: House and fighter-specific costs apply automatically
- Defaults are sensible: Base costs from the rulebook are the fallback

### 2. Zero-Cost Patterns

Several patterns result in zero cost:

- Default equipment: Starting gear doesn't add to fighter cost
- Linked relationships: Avoid double-counting when equipment creates fighters
- Child items: Prevents cascading costs in equipment hierarchies

These patterns exist because:

- Starting equipment is already factored into the fighter's base cost
- Some equipment represents the same item in different contexts
- The game rules specify certain items as "free" under specific conditions

### 3. Virtual Assignments

The `VirtualListFighterEquipmentAssignment` abstraction exists to unify two different concepts:

- Default assignments: Equipment that comes with the fighter
- Player assignments: Equipment added by the player

This design allows:

- Consistent cost calculation regardless of source
- Clean separation between game rules and player choices
- Easy toggling between default and custom equipment

## Architectural Decisions

### Why Multiple Override Models?

Instead of a single override table, the system uses:

- `ContentFighterHouseOverride`
- `ContentFighterEquipmentListItem`
- `ContentFighterEquipmentListWeaponAccessory`

This separation provides:

- Type safety: Each override type has appropriate relationships
- Query performance: Indexed lookups for specific override types
- Clear semantics: Each model represents a distinct game concept

### Why Property-Based Calculations?

Costs are calculated via properties (`_base_cost_int`, `cost_int()`) rather than stored values because:

- Costs change frequently: Equipment modifications, campaign events
- Multiple factors: Too many variables to efficiently denormalize
- Data integrity: Calculated values can't become stale

### Why a Dual Cache Architecture?

The system uses two complementary caching strategies:

1. **Facts System (Pull-Based)**: Database fields (`rating_current`, `dirty`) store cached values at every level - List, ListFighter, and ListFighterEquipmentAssignment. Views call `facts()` for O(1) reads.

2. **Propagation System (Push-Based)**: When handlers modify costs, they call `propagate_from_assignment()` or `propagate_from_fighter()` to incrementally update cached values.

This dual approach provides:

- Instant reads: `facts()` returns immediately without calculation
- Strong consistency: Handler operations keep caches accurate
- Eventual consistency: Content model changes mark trees dirty
- Graceful fallback: Dirty objects recalculate on next read

The critical invariant is that **only ONE system updates cached values for any given operation** - handlers use propagation, non-handler operations use facts_from_db().

> **See also:** [Cost Propagation Architecture](technical-design/cost-propagation-architecture.md) for technical details.

### The Equipment List Fighter Pattern

The `equipment_list_fighter` property enables the Legacy Fighter system:

```python
@property
def equipment_list_fighter(self):
    return self.legacy_content_fighter or self.content_fighter
```

This solution:

- Requires no schema changes to existing override models
- Transparently redirects cost lookups
- Maintains backward compatibility

## Evolution and Legacy

### The "Legacy" System Name

The term "legacy" in the codebase has dual meaning:

1. Game mechanic: The Gang Legacy rule for Venators
2. Historical artifact: This was retrofitted into an existing system

The implementation shows signs of evolution:

- Comments indicate it was added for a specific gang type
- The abstraction layer (`equipment_list_fighter`) suggests careful integration
- Test coverage focuses on edge cases discovered during development

### Migration from YAML to Database

The codebase shows evidence of migrating from YAML-based content to database models:

- Deprecated YAML import commands
- JSON schema validation files
- Database models that mirror YAML structure

This migration improved:

- Performance: Database queries vs. file parsing
- Flexibility: Runtime content modifications
- Consistency: Foreign key constraints ensure data integrity

## Trade-offs and Considerations

### Complexity vs. Flexibility

The system chooses flexibility over simplicity because:

- Necromunda's rules are inherently complex
- House rules and campaign modifications are common
- Player communities create custom content

### Performance vs. Accuracy

Calculated costs ensure accuracy but require:

- Multiple database queries per fighter
- Complex aggregations for list totals
- Caching to maintain reasonable performance

### Explicit vs. Implicit Behavior

The system favors explicit cost calculations:

- No hidden modifiers
- Clear override precedence
- Traceable cost breakdowns

This transparency helps players understand and trust the system.

## Future Considerations

### Implemented Optimizations

These optimizations from earlier planning are now in place:

1. Denormalized cost summaries: `rating_current` fields at all three levels (List, Fighter, Assignment)
2. Prefetching methods: `with_related_data()`, `with_latest_actions()` reduce N+1 queries
3. Smart cache invalidation: `dirty` flags allow lazy recalculation only when needed
4. Handler-based propagation: Incremental updates avoid full tree traversal

### Remaining Potential Optimizations

1. Background recalculation: Async task to refresh dirty objects during low activity
2. Batch operations: Bulk update methods for mass equipment changes

### Extensibility Points

The current design supports future features:

- Trading post pricing: Different costs for buying vs. roster value
- Campaign cost modifiers: Territory bonuses, special events
- Cost history tracking: Track how fighter costs change over time

### Maintenance Considerations

The system's maintainability relies on:

- Clear override hierarchy: New developers can trace cost calculations
- Comprehensive tests: Edge cases are documented in test form
- Consistent patterns: Similar problems solved in similar ways

## Conclusion

The fighter cost system's complexity is a reflection of the complexity of Necromunda and our need for an easy-to-manage content library. Each architectural decision supports specific game mechanics while maintaining reasonable performance and developer experience. The system balances:

- Accuracy: Faithful implementation of game rules
- Flexibility: Support for house rules and customization
- Performance: Responsive user experience through caching
- Maintainability: Clear patterns and comprehensive tests

Understanding these design decisions helps when extending the system or debugging cost calculations.
