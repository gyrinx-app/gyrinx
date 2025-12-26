# Cost Entry Points Call Graph

This document shows the call graphs from template entry points to the underlying cost calculation methods.

## Overview

After removing the READ path from `caches["core_list_cache"]`, cost calculations now flow through the facts system or direct calculation methods.

## Template Entry Points

### 1. List-Level Cost Display

#### `list.facts_with_fallback.wealth` (Homepage, User page, Lists page)
```
Template: {{ list.facts_with_fallback.wealth }}
         │
         ▼
List.facts_with_fallback() → ListFacts
         │
         ├─► If list not dirty → ListFacts.wealth
         │                              │
         │                              ▼
         │                       rating + stash + credits
         │
         └─► Else (fallback) → Calculate from:
                  │
                  ├─► self.rating (cached_property)
                  │       │
                  │       └─► sum(f.cost_int_cached for f in active_fighters)
                  │
                  ├─► self.stash_fighter_cost_int (cached_property)
                  │       │
                  │       └─► stash_fighter.cost_int_cached if exists else 0
                  │
                  └─► self.credits_current (DB field)
```

This is reasonable, and ideally we wouldn't have the fallback path but it'll only be hit if the list is dirty.

#### `list.cost_display` (List header)
```
Template: {{ list.cost_display }}
         │
         ▼
List.cost_display()
         │
         ├─► If can_use_facts (has action) and facts() not None (not dirty):
         │       └─► format_cost_display(facts.wealth)
         │
         └─► Else: format_cost_display(self.cost_int_cached)  [DEPRECATED PATH]
                    │
                    ▼
              List.cost_int_cached (cached_property)
                    │
                    ├─► track("deprecated_cost_int_cached_read")
                    │
                    ├─► If DEBUG: raise RuntimeError  [SCREAMS]
                    │
                    └─► facts_with_fallback().wealth
```

ACTION REQUIRED...

cost_display could be fully replaced with facts_with_fallback().wealth because:

- It uses facts if available
- Otherwise it falls back to direct calculation via cost_int_cached, which itself uses facts_with_fallback().wealth
- facts_with_fallback().wealth checks for facts first, then falls back to direct calculation

... so they produce the same result.

#### `list.rating_display` (List header)
```
Template: {{ list.rating_display }}
         │
         ▼
List.rating_display (cached_property)
         │
         ├─► If can_use_facts (has action) and facts() not None (not dirty):
         │       └─► format_cost_display(facts.rating)
         │
         └─► Else: format_cost_display(self.rating)
                    │
                    └─► sum(f.cost_int_cached for f in active_fighters)
```

ACTION REQUIRED: This could also be replaced with format_cost_display(facts_with_fallback().rating) for the same reasons as cost_display.

#### `list.facts.rating/stash/credits/wealth` (List header, Performance page)
```
Template: {{ list.facts.rating }} / {{ list.facts.wealth }}
         │
         ▼
List.facts()
         │
         └─► Returns cached ListFacts if:
                 - dirty = False
                 - latest_action_cached has facts
             Otherwise returns None
```

This might need to be replaced with facts_with_fallback() calls in templates, depending on whether we want to show stale data or recalc on dirty lists.

#### `list.cost_int` (Campaign start)
```
Template: {{ list.cost_int }}
         │
         ▼
List.cost_int()  [Direct calculation, not cached]
         │
         ├─► rating = sum(f.cost_int() for non-stash fighters)
         ├─► stash = stash_fighter.cost_int() if exists
         ├─► wealth = rating + stash + credits_current
         └─► check_wealth_sync(wealth)  [Tracking if out of sync]
```

ACTION REQUIRED: There is way too much logic in that template -- it should be removed to somewhere else. And it's a direct calculation method that does not use facts at all, which should be avoided in favor of using facts_with_fallback().wealth,

### 2. Fighter-Level Cost Display

#### `fighter.cost_display` (Fighter cards)
```
Template: {{ fighter.cost_display }}
         │
         ▼
ListFighter.cost_display()
         │
         ├─► If can_use_facts (has action) and facts() not None (not dirty):
         │       └─► format_cost_display(facts.rating)
         │
         └─► Else: format_cost_display(self.cost_int_cached)
                    │
                    ▼
              ListFighter.cost_int_cached (cached_property)
                    │
                    └─► base_cost + advancement_cost + sum(equipment costs)
```

### 3. Assignment-Level Cost Display

#### `assign.cost_display` (Weapon edit, Card content)
```
Template: {{ assign.cost_display }}
         │
         ▼
ListFighterEquipmentAssignment.cost_display()
         │
         └─► format_cost_display(self.cost_int_cached)
                    │
                    ▼
              cost_int_cached (cached_property)
                    │
                    └─► If has_total_cost_override: total_cost_override
                        Else: calculated cost from equipment + profiles + accessories + upgrades
```

ACTION REQUIRED: We should be able to use facts at this level too

## Key Properties

### `can_use_facts`
```
List.can_use_facts (cached_property)
         │
         └─► True if latest_action_cached exists
             (requires with_latest_actions() prefetch)
```

### Facts System vs Direct Calculation

| Method | Uses Facts | Uses Direct Calc | Notes |
|--------|-----------|------------------|-------|
| `facts_with_fallback()` | Yes (fast path) | Yes (fallback) | Primary entry point |
| `cost_display()` | Yes (if available) | Via cost_int_cached | Deprecated fallback |
| `rating_display` | Yes (if available) | Via rating | Direct calc fallback |
| `cost_int()` | No | Yes | Always direct calc |
| `cost_int_cached` | Via facts_with_fallback | Yes | DEPRECATED - tracks usage |

## Signal Handlers (Still Active)

The following signal handlers still WRITE to `caches["core_list_cache"]` but these writes are now ignored:
- Post-save on ListFighter
- Post-save on ListFighterEquipmentAssignment
- M2M changes on weapon_profiles, weapon_accessories, upgrades

These writes are harmless and will be removed in a future phase.

## Tracking Events

| Event | Trigger | Purpose |
|-------|---------|---------|
| `deprecated_cost_int_cached_read` | List.cost_int_cached called | Track deprecated usage |
| `facts_fallback` | facts_with_fallback() uses fallback | Track lists without cached facts |
| `list_cost_out_of_sync` | Detected mismatch | Track sync issues |
| `list_cost_refresh` | Manual refresh via view | Track refresh operations |

## Migration Status

- ✅ READ path from in-memory cache removed
- ✅ cost_int_cached uses facts_with_fallback() with tracking
- ✅ DEBUG mode raises exception on deprecated path
- ⏳ WRITE path still active (harmless, to be removed later)
- ⏳ Views need proper prefetching with with_latest_actions()
