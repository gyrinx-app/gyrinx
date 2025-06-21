# Fighter Cost System Design Guide

This document explains the design philosophy and architectural decisions behind Gyrinx's fighter cost calculation system.

## Why This Complexity?

The fighter cost system might seem complex at first glance, but this complexity serves specific game mechanics from Necromunda. The system needs to handle:

1. **Multiple Sources of Truth**: Different rulebooks specify different costs for the same equipment depending on the fighter
2. **House-Specific Rules**: Some houses get discounts or pay premiums for certain fighters
3. **Campaign Progression**: Fighters become more expensive as they gain experience
4. **Equipment Flexibility**: The same weapon can have different profiles at different costs
5. **Legacy Rules**: Special gang rules that allow using equipment from other houses

## Core Design Principles

### 1. Override Hierarchy

The system follows a clear hierarchy for determining costs:
```
User Input > Game Rules > Base Values
```

This hierarchy ensures that:
- **Players have ultimate control**: Manual overrides always win
- **Special rules are respected**: House and fighter-specific costs apply automatically
- **Defaults are sensible**: Base costs from the rulebook are the fallback

### 2. Zero-Cost Patterns

Several patterns result in zero cost:
- **Default Equipment**: Starting gear doesn't add to fighter cost
- **Linked Relationships**: Avoid double-counting when equipment creates fighters
- **Child Items**: Prevents cascading costs in equipment hierarchies

These patterns exist because:
- Starting equipment is already factored into the fighter's base cost
- Some equipment represents the same item in different contexts
- The game rules specify certain items as "free" under specific conditions

### 3. Virtual Assignments

The `VirtualListFighterEquipmentAssignment` abstraction exists to unify two different concepts:
- **Default assignments**: Equipment that comes with the fighter
- **Player assignments**: Equipment added by the player

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
- **Type safety**: Each override type has appropriate relationships
- **Query performance**: Indexed lookups for specific override types
- **Clear semantics**: Each model represents a distinct game concept

### Why Property-Based Calculations?

Costs are calculated via properties (`_base_cost_int`, `cost_int()`) rather than stored values because:
- **Costs change frequently**: Equipment modifications, campaign events
- **Multiple factors**: Too many variables to efficiently denormalize
- **Data integrity**: Calculated values can't become stale

### Why Caching at the List Level?

The cache operates at the list level rather than individual fighters because:
- **Invalidation simplicity**: Any change invalidates one cache key
- **Common access pattern**: Users typically view entire lists
- **Memory efficiency**: Fewer cache keys to manage

### The Equipment List Fighter Pattern

The `equipment_list_fighter` property enables the Legacy Fighter system:
```python
@property
def equipment_list_fighter(self):
    return self.legacy_content_fighter or self.content_fighter
```

This elegant solution:
- Requires no schema changes to existing override models
- Transparently redirects cost lookups
- Maintains backward compatibility

## Evolution and Legacy

### The "Legacy" System Name

The term "legacy" in the codebase has dual meaning:
1. **Game mechanic**: The Gang Legacy rule for Venators
2. **Historical artifact**: This was retrofitted into an existing system

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
- **Performance**: Database queries vs. file parsing
- **Flexibility**: Runtime content modifications
- **Consistency**: Foreign key constraints ensure data integrity

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

### Potential Optimizations

1. **Denormalized cost summaries**: Store calculated costs with generation numbers
2. **Bulk calculation methods**: Reduce N+1 queries for list views
3. **Smarter cache invalidation**: Only recalculate affected fighters

### Extensibility Points

The current design supports future features:
- **Trading post pricing**: Different costs for buying vs. roster value
- **Campaign cost modifiers**: Territory bonuses, special events
- **Cost history tracking**: Track how fighter costs change over time

### Maintenance Considerations

The system's maintainability relies on:
- **Clear override hierarchy**: New developers can trace cost calculations
- **Comprehensive tests**: Edge cases are documented in test form
- **Consistent patterns**: Similar problems solved in similar ways

## Lessons Learned

### 1. Game Rules Drive Architecture

The complexity in the cost system directly maps to complexity in Necromunda's rules. Attempting to simplify would break game fidelity.

### 2. Override Systems Need Hierarchy

Without clear precedence rules, override systems become unpredictable. The explicit hierarchy prevents confusion.

### 3. Caching Is Essential

The calculated nature of costs makes caching critical for performance. The simple list-level cache strikes a good balance.

### 4. Virtual Models Enable Clean APIs

The Virtual assignment pattern provides a clean API over messy underlying data relationships.

## Conclusion

The fighter cost system's complexity is a direct reflection of the game it models. Each architectural decision supports specific game mechanics while maintaining reasonable performance and developer experience. The system successfully balances:

- **Accuracy**: Faithful implementation of game rules
- **Flexibility**: Support for house rules and customization  
- **Performance**: Responsive user experience through caching
- **Maintainability**: Clear patterns and comprehensive tests

Understanding these design decisions helps when extending the system or debugging cost calculations. The key insight is that the complexity serves a purpose - enabling players to accurately model their Necromunda gangs with all the nuances the tabletop game provides.