# Design: Spyrer Kill Count, Glitch Count & Power Boost (Issue #706)

## Problem

Spyrer fighters have two unique mechanics not currently supported:

1. **Kill Count** -- Incremented each time a Spyrer takes an enemy Out of Action. Players can spend 4 Kill Count points to roll on the Power Boost table, gaining permanent stat modifications and a rating increase. Alternatively, they can choose to clear all Glitches instead (handled by manually editing the Glitch Counter to 0 and reducing Kill Count by 4).

2. **Glitch Count** -- Incremented via Spyrer-specific injuries ("Hunting Rig Glitches"). If a Spyrer's Glitch Count exceeds their Toughness, the hunting rig shuts down and the fighter is deleted from the roster.

These are fighter-level counters that need to be:
- Manually editable by the user
- Displayed alongside XP on the fighter card
- Connected to a dice-rolling flow (Kill Count -> Power Boost table)
- Connected to the modifier system (Power Boost results modify fighter stats)

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Counter storage | Separate `ListFighterCounter` model | Generic: supports any number of counter types per fighter, extensible for future mechanics |
| Counter creation | On-demand when user edits | Counter row displayed by detecting content_fighter match via prefetch; `ListFighterCounter` record created only when user edits the value |
| Injury auto-increment | Manual only (v1) | Users edit counter values themselves; auto-increment can be added later |
| Spending flow | `ContentRollFlow` defines a content-driven multi-step flow | Links counter to roll table; generates the UI flow from content data |
| Flow entry point | Button on counter edit page | User navigates: fighter card -> edit counter -> "Use Suit Evolution" button -> roll flow |
| Clear Glitches | Manual counter editing | No special flow needed; user sets Glitch Counter to 0 and reduces Kill Count by 4 manually |
| Power Boost removal | Removable | Follows advancement deletion pattern: reverse stat mods and rating increase |
| Pack support | No (base content only) | Standard Django models; only admins can create via admin interface |

## Existing Patterns

### Closest analogs

| System | Pattern | Relevance |
|--------|---------|-----------|
| **XP / Advancements** | Counter (`xp_current`) + multi-step wizard + cost propagation | Kill Count spending flow |
| **Injuries** | Content definition + ListFighter M2M + modifiers M2M + restricted by house/category | Power Boost as mod source |
| **Modifier system** | `_mods()` collects from 5 sources, applied at display time | Power Boost results as 6th mod source |
| **Dirty/propagation** | `set_dirty()` -> `facts_from_db()` -> `rating_current` update | Power Boost rating_increase propagation |

### Key architectural constraint: generic, not Spyrer-specific

The models support any fighter-type-specific counter and roll table, not just Spyrers. Future fighters with similar mechanics can reuse the same infrastructure.

## Proposed Architecture

### New Content Models (content app)

#### 1. `ContentCounter`

A named counter that can be attached to specific content fighters.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (max 255) | Display name (e.g., "Kill Count", "Glitch Count"). |
| `description` | TextField (blank) | Explanation of the counter's purpose. |
| `restricted_to_fighters` | M2M(ContentFighter) | Which content fighters show this counter. |
| `display_order` | PositiveIntegerField | Ordering on the fighter card. |

Standard `Content` base class (not pack-filterable). Admin-managed only.

#### 2. `ContentRollTable`

A dice table definition.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (max 255) | Table name (e.g., "Power Boost Table"). |
| `description` | TextField (blank) | Explanation of the table's purpose. |
| `dice` | CharField (max 10) | Dice configuration: "D6", "D66", "2D6". |

#### 3. `ContentRollTableRow`

Individual results on a roll table.

| Field | Type | Description |
|-------|------|-------------|
| `table` | FK(ContentRollTable) | Parent table. Cascade delete. |
| `roll_value` | CharField (max 20) | Dice result or range (e.g., "1", "2-3", "4-5", "6"). |
| `name` | CharField (max 255) | Result name (e.g., "Improved Reflexes"). |
| `description` | TextField (blank) | What the result does. |
| `modifiers` | M2M(ContentMod) | Stat/trait/rule changes applied to the fighter. |
| `rating_increase` | IntegerField (default 0) | Rating increase when this result is gained. |
| `sort_order` | PositiveIntegerField | Display ordering within the table. |

Uses the existing `ContentMod` polymorphic system -- same M2M pattern as injuries, equipment, upgrades, and accessories.

**Constraints**: `unique_together: (table, sort_order)`.

#### 4. `ContentRollFlow`

Links a counter to a roll table, defining the "spend X, roll on Y" multi-step flow.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (max 255) | Flow name (e.g., "Suit Evolution -- Power Boost"). |
| `description` | TextField (blank) | Instructions shown to the user. |
| `counter` | FK(ContentCounter) | Which counter to spend. |
| `cost` | PositiveIntegerField | How many counter points to spend (e.g., 4). |
| `roll_table` | FK(ContentRollTable) | Table to roll on. |

The view logic for this flow:
1. Check counter value >= cost
2. Show available flows for this counter on the counter edit page
3. User picks a flow -> roll dice -> show result from table
4. Confirm: deduct counter, create `ListFighterRollTableRowAssignment`, propagate cost

### New Core Models (core app)

#### 5. `ListFighterCounter`

Tracks the current value of a counter for a specific fighter.

| Field | Type | Description |
|-------|------|-------------|
| `fighter` | FK(ListFighter, related_name="counters") | The fighter. |
| `counter` | FK(ContentCounter) | Which counter. |
| `value` | IntegerField (default 0) | Current counter value. |

**Constraints**: `unique_together: (fighter, counter)`.

Inherits from `AppBase` (UUID pk, owner tracking, archive, history).

**Display vs creation**: The counter row is displayed on the fighter card by detecting that the fighter's `content_fighter` is in a `ContentCounter.restricted_to_fighters` set (using prefetched data). No `ListFighterCounter` record exists yet at this point -- the display shows a default value of 0. When the user navigates to the counter edit page and saves a value, the `ListFighterCounter` record is created at that point.

**Prefetching**: `ContentCounter` objects with their `restricted_to_fighters` are prefetched so that the fighter card can detect applicable counters without additional queries.

#### 6. `ListFighterRollTableRowAssignment`

Records that a fighter has gained a specific roll table result. This is the new **mod source**.

| Field | Type | Description |
|-------|------|-------------|
| `fighter` | FK(ListFighter, related_name="roll_table_results") | The fighter. |
| `row` | FK(ContentRollTableRow) | Which result was gained. |
| `date_received` | DateTimeField (auto_now_add) | When the result was applied. |
| `rating_increase` | IntegerField | Copied from row at creation time (for audit trail). |
| `notes` | TextField (blank) | Optional notes. |
| `campaign_action` | OneToOneField(CampaignAction, nullable) | Link to dice roll record. |

Inherits from `AppBase`.

Pattern mirrors `ListFighterInjury` and `ListFighterAdvancement`.

**Deletion**: Removing a `ListFighterRollTableRowAssignment` reverses the rating increase and removes the stat modifiers (same pattern as advancement deletion).

### Integration Points

#### Modifier System

Add roll table results as the 6th mod source in `ListFighter._mods()`:

```python
# In _mods() method, alongside existing injury mods:
if self.list.is_campaign_mode:
    for result in self.roll_table_results.all():
        roll_table_mods.extend(result.row.modifiers.all())
```

Follows the exact same pattern as injury mods. Modifiers are applied at display time via the existing `_apply_mods()` mechanism.

#### Cost Propagation

When a `ListFighterRollTableRowAssignment` is created:
1. `propagate_from_fighter(fighter, Delta(delta=rating_increase, list=lst))`
2. `fighter.rating_current += rating_increase`
3. Create a `ListAction` recording the change

When removed (reversal):
1. `propagate_from_fighter(fighter, Delta(delta=-rating_increase, list=lst))`
2. `fighter.rating_current -= rating_increase`
3. Create a `ListAction` recording the reversal

This mirrors the advancement handler pattern exactly.

#### Counter Display

On the fighter card, counters are displayed next to XP for fighters whose `content_fighter` is in a `ContentCounter.restricted_to_fighters` set. The display is driven by prefetched `ContentCounter` data -- no `ListFighterCounter` record needs to exist. If a `ListFighterCounter` record exists, its value is shown; otherwise, 0 is displayed.

#### Roll Flow UI

Content-driven multi-step flow, entered from the counter edit page:

1. **Counter edit page**: Shows counter value with edit form. If `ContentRollFlow` entries exist for this counter and the current value >= flow cost, show a button: "Use Suit Evolution"
2. **Roll step**: Dice roll interface showing the table and result
3. **Confirm step**: Review result details (name, stat changes, rating increase), then apply

Views: `roll_flow_start`, `roll_flow_roll`, `roll_flow_confirm`
Handler: `handle_roll_flow()` -- transactional, creates assignment + deducts counter + propagates cost + records CampaignAction
Templates: `core/fighter/roll_flow_*.html`

#### Prefetch Optimisation

Add to `ListFighterQuerySet.with_related_data()`:
```python
"counters",
"counters__counter",
"roll_table_results",
"roll_table_results__row__modifiers",
```

Also prefetch `ContentCounter` with `restricted_to_fighters` for counter display detection.

## Implementation Plan

### Phase 1: Content Models + Counter Display
- `ContentCounter`, `ContentRollTable`, `ContentRollTableRow`, `ContentRollFlow` models
- `ListFighterCounter` model
- Admin configuration for all new content models
- Data migration to create Kill Count and Glitch Count content + Power Boost table rows
- Display counters on fighter card next to XP (detect via content_fighter match)
- Counter edit page with manual value editing (creates ListFighterCounter on save)

### Phase 2: Power Boost Flow
- `ListFighterRollTableRowAssignment` model
- Integration with modifier system (`_mods()`)
- Cost propagation for rating increases
- Roll flow views, templates, forms (the multi-step wizard from counter edit page)
- Campaign action integration
- Power Boost removal with rating reversal
- Display Power Boost results on fighter card

### Phase 3: Polish
- Prefetch optimisation for new relations
- Performance query snapshot updates
- Documentation updates (content-library docs)
- Comprehensive tests for all new models, views, handlers
