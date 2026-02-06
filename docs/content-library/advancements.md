# Advancements

## Overview

Advancements represent how fighters grow and improve over the course of a Necromunda campaign. When a fighter earns enough experience points (XP), their player can spend those points to improve characteristics, learn new skills, or acquire new equipment. The advancement system in Gyrinx manages the equipment-based advancement options that content administrators configure through the content library. In this context, a list represents a user's collection of fighters (called a "gang" in Necromunda).

The content library models covered here -- `ContentAdvancementEquipment` and `ContentAdvancementAssignment` -- specifically handle equipment advancements. These define what equipment a fighter can gain by spending XP, along with the costs, restrictions, and selection methods. Characteristic increases and skill advancements are configured elsewhere through the stat and skill systems, with their XP costs and rating increases defined in the application code rather than the content library.

When a user purchases an equipment advancement for one of their fighters, the system deducts the XP cost, increases the fighter's rating by the configured amount, and creates the corresponding equipment assignment on the fighter automatically. This directly affects the fighter's value and the list's overall gang rating.

## Key Concepts

**Equipment Advancement** (`ContentAdvancementEquipment`): A named advancement option that defines what equipment a fighter can gain, how much it costs in XP, and how it affects the fighter's rating. Each equipment advancement can offer multiple specific equipment options through its assignments.

**Advancement Assignment** (`ContentAdvancementAssignment`): A specific piece of equipment (optionally with upgrades) that a fighter receives when they take a particular equipment advancement. An equipment advancement can have many assignments, representing the pool of options a fighter selects from.

**Chosen vs Random Selection**: Each equipment advancement can allow the player to choose their equipment (`enable_chosen`) or have it randomly selected (`enable_random`), or both. This mirrors the tabletop game's advancement tables where some results let you pick and others are rolled randomly.

**XP Cost**: The experience points a fighter must spend to purchase the advancement. This is deducted from the fighter's current XP balance.

**Cost Increase**: The credit value added to the fighter's rating when they take the advancement. This affects the list's total gang rating, which is used for balancing campaigns.

## Models

### `ContentAdvancementEquipment`

This model defines a named equipment advancement that fighters can purchase with XP. It controls the cost, selection method, and which fighters are eligible.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (255) | The name of the advancement, displayed to users in the advancement selection form. For example, "Legendary Name" or "Gang Equipment". |
| `xp_cost` | PositiveIntegerField | The XP cost to purchase this advancement. Deducted from the fighter's `xp_current` when applied. |
| `cost_increase` | IntegerField (default: 0) | The credit increase applied to the fighter's rating when this advancement is taken. This value propagates up to the list's `rating_current`. |
| `enable_random` | BooleanField (default: False) | When enabled, the advancement appears as a "Random [Name]" option. The system randomly selects one assignment from the pool, filtering out options the fighter already has. |
| `enable_chosen` | BooleanField (default: False) | When enabled, the advancement appears as a "Chosen [Name]" option. The player picks which assignment they want from the available pool. |
| `restricted_to_houses` | ManyToManyField to `ContentHouse` (blank) | If any houses are selected, only fighters belonging to those houses can take this advancement. When left empty, the advancement is available to all houses. |
| `restricted_to_fighter_categories` | JSONField (default: []) | A list of fighter category strings (e.g., `["GANGER", "CHAMPION"]`) that can take this advancement. When empty, all fighter categories are eligible. Uses the `FighterCategoryChoices` values: `LEADER`, `CHAMPION`, `GANGER`, `JUVE`, `CREW`, `EXOTIC_BEAST`, `SPECIALIST`, and others. |

#### Validation Rules

- At least one of `enable_random` or `enable_chosen` must be set to `True`. The model's `clean()` method enforces this, and the admin form will display an error if neither is enabled.

#### Relationships

- Has many `ContentAdvancementAssignment` records through the `assignments` reverse relation.
- References `ContentHouse` through `restricted_to_houses` for house-based filtering.

#### Admin Configuration

The admin interface for `ContentAdvancementEquipment` is organized into three fieldset sections:

1. **Main fields** -- `name`, `xp_cost`, and `cost_increase`.
2. **Assignment Selection** -- The `enable_chosen` and `enable_random` checkboxes, with an inline form below for adding `ContentAdvancementAssignment` records directly.
3. **Restrictions** (collapsed by default) -- `restricted_to_houses` (shown as a horizontal filter widget) and `restricted_to_fighter_categories` (shown as checkboxes).

The list view shows columns for `name`, `xp_cost`, `cost_increase`, `enable_chosen`, `enable_random`, an "Assignment Options" count, and a "Restrictions" summary. You can filter the list by `enable_chosen`, `enable_random`, and `restricted_to_houses`. The search box matches against the `name` field.

### `ContentAdvancementAssignment`

This model represents a specific equipment configuration that a fighter can gain through an advancement. Each assignment links a base equipment item and optionally includes upgrades.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `advancement` | ForeignKey to `ContentAdvancementEquipment` (nullable) | The equipment advancement this assignment belongs to. Links back to the parent advancement that offers this option. |
| `equipment` | ForeignKey to `ContentEquipment` | The base equipment item the fighter receives. This is the core piece of gear granted by the advancement. |
| `upgrades_field` | ManyToManyField to `ContentEquipmentUpgrade` (blank) | Optional upgrades that come pre-attached to the equipment. When the advancement is applied, both the equipment and these upgrades are added to the fighter's equipment assignment. |

#### Display

The string representation of an assignment shows the equipment name followed by any upgrade names in parentheses. For example, an assignment with a "Lasgun" and a "Hotshot Pack" upgrade would display as "Lasgun (Hotshot Pack)".

#### Relationships

- Belongs to a `ContentAdvancementEquipment` through the `advancement` foreign key.
- References `ContentEquipment` for the base equipment item. See [Equipment & Weapons](equipment-and-weapons.md) for details on the equipment models.
- References `ContentEquipmentUpgrade` for any pre-configured upgrades. See [Equipment & Weapons](equipment-and-weapons.md) for details on the equipment models.

#### Admin Configuration

The admin list view shows columns for `equipment`, an upgrade count, and the parent `advancement`. You can search by equipment name or advancement name, and filter by equipment category or advancement.

The upgrades field uses a horizontal filter widget, and when editing an assignment inline from its parent advancement, the upgrades are filtered to only show upgrades available for the selected equipment.

Assignments can also be managed inline when editing a `ContentAdvancementEquipment` record. The inline form shows `equipment` (with autocomplete) and `upgrades_field` (with horizontal filter), and you can add multiple assignments at once.

## How It Works in the Application

### The Advancement Flow

When a user wants to advance a fighter, they go through a multi-step process:

1. **Dice choice** (campaign mode only) -- Gangers and Exotic Beasts can optionally roll 2d6 to determine their advancement type. The dice result maps to a specific characteristic increase. Other fighter categories skip this step.

2. **Advancement type selection** -- The user sees all available advancement options grouped into three sections: characteristic increases (from the fighter's statline), equipment advancements (from `ContentAdvancementEquipment` records), and skill/other options. Equipment advancements appear as "Chosen [Name]" or "Random [Name]" depending on their configuration. The XP cost and rating increase are pre-filled based on the selected option.

3. **Selection** (for chosen equipment and skills only) -- If the user selected a "Chosen" equipment advancement, they pick a specific assignment from the available pool. Assignments whose upgrades the fighter already has are automatically filtered out. For random equipment advancements, this step is skipped.

4. **Confirmation** -- The user confirms the advancement. For random equipment, the system selects a random assignment at this point. The advancement is then applied: XP is deducted, the fighter's rating increases, and the equipment (with any upgrades) is added to the fighter.

### Availability Filtering

Equipment advancements are filtered based on the fighter attempting to advance:

- **House restrictions**: If `restricted_to_houses` is set, the fighter's list must belong to one of those houses.
- **Fighter category restrictions**: If `restricted_to_fighter_categories` is set, the fighter's category must be in the list.
- **Duplicate filtering**: When selecting an assignment, the system excludes assignments whose upgrades the fighter already has on existing equipment. This prevents a fighter from gaining duplicate upgrades.

### Effect on Fighter Cost and Rating

When an equipment advancement is applied:

- The `xp_cost` is subtracted from the fighter's `xp_current` field.
- The `cost_increase` is added to the fighter's cost, which propagates up to the list's `rating_current` (or `stash_current` for stash-linked fighters like vehicles and exotic beasts).
- A `ListFighterEquipmentAssignment` is created linking the fighter to the equipment and its upgrades.
- A `ListFighterAdvancement` record is created to track the advancement for history and reversal purposes.

### Removing Advancements

Users can delete (archive) an advancement from the fighter's advancement history. When an equipment advancement is removed:

- The XP is restored to the fighter.
- The rating increase is reversed.
- However, the equipment itself must be removed manually by the user. The system displays a warning about this.

## Common Admin Tasks

### Creating a New Equipment Advancement

1. Navigate to the Equipment Advancements section in the admin.
2. Click "Add" to create a new `ContentAdvancementEquipment`.
3. Fill in the `name` (e.g., "Gang Weapons"), `xp_cost`, and `cost_increase`.
4. Enable at least one of `enable_chosen` or `enable_random`. Enable both if you want players to have either option.
5. In the inline section below, add one or more `ContentAdvancementAssignment` records by selecting equipment items and optionally attaching upgrades.
6. Optionally expand the Restrictions section to limit the advancement to specific houses or fighter categories.
7. Save the record.

### Adding Equipment Options to an Existing Advancement

1. Open the `ContentAdvancementEquipment` record you want to modify.
2. Scroll down to the inline assignment section.
3. Add a new row, select the `equipment`, and optionally select upgrades from the horizontal filter.
4. Save. The new option will immediately appear in the advancement selection form for eligible fighters.

### Restricting an Advancement to Specific Houses

1. Open the `ContentAdvancementEquipment` record.
2. Expand the "Restrictions" fieldset (it is collapsed by default).
3. Use the `restricted_to_houses` horizontal filter to move houses from the "Available" list to the "Chosen" list.
4. Save. Only fighters in lists belonging to the selected houses will see this advancement option.

### Restricting an Advancement to Specific Fighter Categories

1. Open the `ContentAdvancementEquipment` record.
2. Expand the "Restrictions" fieldset.
3. Check the boxes next to the fighter categories that should be eligible (e.g., `GANGER`, `CHAMPION`).
4. Save. Only fighters with a matching category will see this advancement option.

### Configuring an Advancement with Both Random and Chosen Options

Some advancements should offer both selection methods at different costs. Since `xp_cost` and `cost_increase` are set at the advancement level (not the selection method level), you will need to create two separate `ContentAdvancementEquipment` records if you want different costs for random versus chosen selection:

1. Create one record with `enable_random` checked and the random-specific XP cost and rating increase.
2. Create a second record with `enable_chosen` checked and the chosen-specific XP cost and rating increase.
3. Add the same set of assignments to both records.

If the random and chosen options should have the same cost, you can use a single record with both `enable_random` and `enable_chosen` enabled.

### Reviewing Existing Advancements

Use the list view filters to quickly audit your advancement configuration:

- Filter by `enable_chosen` or `enable_random` to see which selection methods are in use.
- Filter by `restricted_to_houses` to see advancements limited to specific factions.
- The "Assignment Options" column shows how many equipment options each advancement offers. An advancement with zero assignments will not be useful to players.
- The "Restrictions" column provides a summary of any house or category restrictions.
