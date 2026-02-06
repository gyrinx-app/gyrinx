# Stats & Statlines

## Overview

Stats and statlines define the numerical characteristics of fighters in Necromunda -- values like Movement, Weapon Skill, Toughness, and so on. In Gyrinx, a list represents a user's collection of fighters (called a "gang" in Necromunda). These stats are managed through a flexible content library system that supports both the standard twelve-stat fighter profile and entirely custom stat layouts for non-standard units like vehicles.

The stats system has two layers. The first is a set of individual stat definitions (`ContentStat`) that describe what each stat means and how it should be displayed. The second is a statline composition system that groups those stats into ordered layouts (`ContentStatlineType`) and assigns concrete values to specific fighters (`ContentStatline`). This separation means you define a stat like "Front Toughness" once, then reuse it across multiple statline types without duplication.

When users view their fighters in the application, the statline appears as a compact table at the top of each fighter card. Stats are displayed with short abbreviations as column headers (M, WS, BS, etc.) and the corresponding values below. Some stats are visually highlighted, and visual group separators can break the statline into logical sections. The stat display properties you configure here directly control how equipment modifiers and advancements calculate and format their effects.

## Key Concepts

**Stat** -- A single measurable characteristic, such as Movement or Weapon Skill. Each stat has display properties that tell the system how to format its values and how modifiers should be applied.

**Statline Type** -- A template that defines which stats appear in a statline and in what order. For example, the standard fighter statline type includes M, WS, BS, S, T, W, I, A, Ld, Cl, Wil, and Int. A vehicle statline type might include different stats like Front Toughness, Side Toughness, and Rear Toughness.

**Statline** -- A concrete set of stat values assigned to a specific `ContentFighter`. It links a fighter to a statline type and stores the actual numeric values for each stat in that type.

**Legacy Statline** -- The original system where stat values are stored as direct fields on `ContentFighter` (e.g., `movement`, `weapon_skill`). This still works and is the default for fighters that do not have a custom statline assigned. Most standard fighters use this approach.

**Custom Statline** -- The newer system where stat values are stored in separate `ContentStatline` and `ContentStatlineStat` records. This is required for fighters whose stats do not match the standard twelve-stat layout, such as vehicles.

## Models

### `ContentStat`

Represents a single stat definition that can be shared across multiple statline types. This is the canonical source of truth for what a stat is, how it is abbreviated, and how its values should be formatted and modified.

| Field | Type | Description |
|-------|------|-------------|
| `field_name` | CharField (unique) | Internal identifier, auto-generated from `full_name` on first save (e.g., `movement`, `front_toughness`). Read-only in admin. |
| `short_name` | CharField | Short display abbreviation shown in stat table headers (e.g., `M`, `WS`, `Fr`). |
| `full_name` | CharField | Full human-readable name (e.g., `Movement`, `Weapon Skill`, `Front Toughness`). |
| `is_inverted` | BooleanField | When true, "improving" this stat means decreasing the number. Used for target-roll stats like Cool, where 3+ is better than 4+. This flag controls modifier direction. |
| `is_inches` | BooleanField | When true, values are displayed with a trailing quote mark to indicate inches (e.g., `5"`). |
| `is_modifier` | BooleanField | When true, values are displayed with a plus prefix for positive numbers (e.g., `+3`). Used for accuracy-style modifiers. |
| `is_target` | BooleanField | When true, values are displayed with a trailing plus to indicate a target roll (e.g., `3+`). |

The four display-property flags (`is_inverted`, `is_inches`, `is_modifier`, `is_target`) serve two purposes. First, they control how stat values are formatted when displayed. Second, and more importantly, they tell the modifier system how to correctly apply "improve" and "worsen" effects. For example, if `is_inverted` is true, an "improve" modifier will subtract from the value rather than add to it, because a lower number is better for that stat.

The `field_name` is auto-generated from `full_name` when first saved: the name is lowercased, non-alphanumeric characters are replaced with underscores, and multiple underscores are collapsed. Once created, it is read-only in the admin interface and serves as the stable identifier used throughout the system.

**Admin interface:** Searchable by `field_name`, `short_name`, and `full_name`. The list view shows all three name fields. The `field_name` field is read-only since it is auto-generated.

### `ContentStatlineType`

Defines a type of statline -- essentially a named template for a particular layout of stats. Different fighter categories can use different statline types.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (unique) | The name of this statline type (e.g., `Fighter`, `Vehicle`, `Crew`). |

A statline type on its own is just a name. Its stats are defined through `ContentStatlineTypeStat` records, which are managed as inlines on the statline type's admin page.

**Admin interface:** Searchable by name. The list view shows the name and a count of how many stats belong to the type. The stat composition is managed through an inline table directly on the statline type edit page.

### `ContentStatlineTypeStat`

Links a `ContentStat` to a `ContentStatlineType` with positioning and visual display settings. This is the join table that defines which stats appear in a statline type and how they are arranged.

| Field | Type | Description |
|-------|------|-------------|
| `statline_type` | ForeignKey to `ContentStatlineType` | The statline type this stat belongs to. |
| `stat` | ForeignKey to `ContentStat` | The stat definition being included. |
| `position` | IntegerField | Display order position. Lower numbers appear first (leftmost in the stat table). |
| `is_highlighted` | BooleanField | Whether this stat gets a highlighted background in the UI. In the standard fighter statline, Ld, Cl, Wil, and Int are highlighted. |
| `is_first_of_group` | BooleanField | Whether this stat starts a new visual group, which adds a left border separator in the display. Used to visually separate stat clusters. |

Each stat can only appear once per statline type (enforced by the `unique_together` constraint on `statline_type` and `stat`). Records are ordered by `statline_type` then `position`.

This model also exposes `field_name`, `short_name`, and `full_name` as properties that delegate to the underlying `ContentStat`, making it convenient to access stat details without an extra lookup.

**Admin interface:** Managed as an inline on `ContentStatlineType`. The inline shows the stat dropdown, position, highlighting toggle, and group-start toggle, ordered by position.

### `ContentStatline`

Assigns a statline type to a specific `ContentFighter` and serves as the container for that fighter's stat values. Each fighter can have at most one custom statline (enforced as a `OneToOneField`).

| Field | Type | Description |
|-------|------|-------------|
| `content_fighter` | OneToOneField to `ContentFighter` | The fighter this statline belongs to. Accessed via `content_fighter.custom_statline`. |
| `statline_type` | ForeignKey to `ContentStatlineType` | The type of statline, which determines which stats need values. |

When you save a `ContentStatline` in the admin, the system automatically creates `ContentStatlineStat` entries with a default value of `-` for any stats required by the statline type that do not already have values. This means you can create the statline, save it, and then fill in the actual values.

Validation on existing statlines checks that all stats required by the statline type have corresponding `ContentStatlineStat` records. This validation is skipped during initial creation since the stat records are created after the statline is saved.

**Admin interface:** Searchable by fighter type and statline type name. Filterable by statline type. The list view shows the fighter and statline type. Stat values are managed through the `ContentStatlineStat` inline. The fighter field uses autocomplete. The statline is also available as an inline on the `ContentFighter` admin page, limited to one per fighter.

### `ContentStatlineStat`

Stores a single stat value within a `ContentStatline`. This is where the actual numbers live for fighters using the custom statline system.

| Field | Type | Description |
|-------|------|-------------|
| `statline` | ForeignKey to `ContentStatline` | The statline this value belongs to. |
| `statline_type_stat` | ForeignKey to `ContentStatlineTypeStat` | The stat position within the statline type that this value corresponds to. |
| `value` | CharField | The stat value as a string (e.g., `5"`, `12`, `4+`, `-`). Values are stored as-is and include any formatting characters. |

Each stat can only have one value per statline (enforced by `unique_together` on `statline` and `statline_type_stat`). Records are ordered by the `position` of their `statline_type_stat`.

The value field accepts any string up to 10 characters. You should include the appropriate formatting in the value itself (e.g., `5"` for an inches stat, `4+` for a target roll). The display properties on `ContentStat` are primarily used by the modifier system for calculations, not for formatting stored values.

Smart quotes are validated against and rejected in the admin form -- always use straight quote marks (`"`) rather than curly quotes.

**Admin interface:** Managed as an inline on `ContentStatline`. The inline shows the stat dropdown (filtered to only show stats valid for the parent statline's type) and the value field. When editing, the stat dropdown is automatically filtered based on the statline type.

## The Two-Tier Stat System

Gyrinx supports two ways of defining a fighter's stats, and the system transparently handles both.

### Legacy Direct Fields

The `ContentFighter` model has twelve built-in stat fields: `movement`, `weapon_skill`, `ballistic_skill`, `strength`, `toughness`, `wounds`, `initiative`, `attacks`, `leadership`, `cool`, `willpower`, and `intelligence`. These are simple `CharField` fields directly on the fighter.

When a fighter does not have a `ContentStatline` assigned, the system uses these fields to build the statline display. The legacy system hardcodes the stat order, and it always highlights Leadership, Cool, Willpower, and Intelligence as a group. It also hardcodes that Leadership starts a new visual group.

This is the simpler approach and works well for the vast majority of fighters that follow the standard Necromunda stat profile.

### Custom Statlines

When a fighter has a `ContentStatline` assigned (accessible via `content_fighter.custom_statline`), the system uses that instead of the legacy fields. The custom statline pulls its stats, their order, highlighting, and grouping from the associated `ContentStatlineType`.

This approach is necessary for units that have a different set of stats, such as vehicles with Front/Side/Rear Toughness values, or crew members with a reduced stat profile.

### How the System Chooses

When rendering a fighter's stats, the `ContentFighter.statline()` method first checks for a `custom_statline`. If one exists, it builds the stat list from `ContentStatlineStat` records. If not, it falls back to `_legacy_statline()`, which reads the twelve direct fields. This check is automatic and transparent -- you simply assign or remove a custom statline, and the display updates accordingly.

## Display Dataclasses

Two dataclasses are used to structure stat and rule data for template rendering.

**`StatlineDisplay`** represents a single stat for display in the fighter card template:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | str | Short display name (e.g., `M`, `WS`). |
| `field_name` | str | Internal field name, used for matching overrides and modifiers. |
| `value` | str | The displayed value, after applying overrides and modifiers. |
| `classes` | str | CSS classes for display, such as `border-start` for group separators. |
| `modded` | bool | Whether the value has been modified from the base value by equipment, upgrades, or manual overrides. When true, the value is displayed with a tooltip indicating it has been modified. |
| `highlight` | bool | Whether the stat should have a highlighted background. |

**`RulelineDisplay`** represents a single rule for display:

| Attribute | Type | Description |
|-----------|------|-------------|
| `value` | str | The rule text. |
| `modded` | bool | Whether this rule was added by a modifier. |

## How It Works in the Application

### Fighter Cards

When a user views their list, each fighter card shows a stat table at the top. The table header row displays the stat short names (M, WS, BS, etc.) and the body row shows the values. Stats marked as `is_highlighted` through the statline type get a subtle warning-coloured background. Stats marked as `is_first_of_group` get a left border to visually separate stat clusters.

If any stat has been modified (by equipment modifiers, advancements, or manual overrides), the value appears with a tooltip indicating it has been changed from the base value.

### Stat Overrides

Users can manually override stat values for their fighters through the "Edit Stats" interface. The system handles this differently depending on the statline type:

- **Legacy statline fighters:** Overrides are stored in `_override` fields directly on `ListFighter` (e.g., `movement_override`, `weapon_skill_override`). A non-empty override replaces the base value from `ContentFighter`.
- **Custom statline fighters:** Overrides are stored as `ListFighterStatOverride` records, which reference the specific `ContentStatlineTypeStat` being overridden.

### Equipment Modifiers

Equipment and weapon accessories can include `ContentModFighterStat` modifiers that alter a fighter's stats. These modifiers reference stats by `field_name` and use the display properties (`is_inverted`, `is_inches`, `is_modifier`, `is_target`) from `ContentStat` to determine how to correctly apply their effects.

For example, a modifier that "improves" Weapon Skill by 1 will subtract 1 from the value (because WS is `is_inverted` -- a lower target roll is better), and the result will be formatted with a trailing `+` (because WS is `is_target`).

### Performance

The custom statline system involves several related models and can be expensive to compute naively. In the application, the `ListFighter` queryset uses subqueries and annotations to pre-load custom statline data in a single query pass. The `annotated_content_fighter_statline` annotation fetches the full statline as a JSON array, avoiding N+1 query issues when rendering lists of fighters.

## Common Admin Tasks

### Defining a New Stat

1. Navigate to the Stats list in the admin.
2. Click "Add Stat".
3. Enter the `short_name` (e.g., `Fr`) and `full_name` (e.g., `Front Toughness`). The `field_name` will be auto-generated (e.g., `front_toughness`).
4. Set the display property flags as appropriate. For a toughness-like stat that is just a plain number, leave all four flags unchecked. For a target-roll stat like Weapon Skill, check `is_inverted` and `is_target`.
5. Save.

### Creating a New Statline Type

1. Navigate to the Statline Types list in the admin.
2. Click "Add Statline Type" and give it a descriptive name (e.g., `Vehicle`).
3. Save it once to create the record.
4. Use the inline table to add stats. For each stat, select the `ContentStat` from the dropdown, set its `position` (starting from 0 or 1), and optionally mark it as highlighted or as the start of a new visual group.
5. Save.

The stats will appear in the order defined by `position`, from left to right in the stat table.

### Assigning a Custom Statline to a Fighter

You can do this from either the fighter's admin page or the statline admin:

**From the fighter page:**

1. Navigate to the fighter in the Content Fighters admin.
2. In the "Fighter Statline" inline section, select the statline type from the dropdown.
3. Save. The system will automatically create stat value entries with `-` as the default value.
4. Navigate to the created statline (via the change link in the inline) to enter the actual stat values.

**From the statline admin:**

1. Navigate to the Fighter Statlines list.
2. Click "Add Fighter Statline".
3. Select the fighter (via autocomplete) and the statline type.
4. Save. Default stat entries are created automatically.
5. Fill in the stat values in the inline table and save again.

### Updating Stat Values

1. Navigate to the Fighter Statlines list and find the statline for the fighter you want to update.
2. Edit the `value` field for the relevant stats in the inline table.
3. Save.

Remember that values are stored as display strings. Enter them exactly as they should appear (e.g., `5"` for an inches value, `4+` for a target roll, `3` for a plain number, `-` for no value).

### Removing a Custom Statline

If you delete a fighter's `ContentStatline`, the fighter will fall back to using the legacy direct stat fields. Make sure the legacy fields have appropriate values if you do this.

1. Navigate to the fighter in the Content Fighters admin.
2. Check the delete checkbox on the "Fighter Statline" inline.
3. Save.

### Setting Display Properties for Correct Modifier Behaviour

The display flags on `ContentStat` are critical for the modifier system to work correctly. Here is a guide for common stat types:

| Stat Type | `is_inverted` | `is_inches` | `is_modifier` | `is_target` | Example |
|-----------|:---:|:---:|:---:|:---:|---------|
| Distance | No | Yes | No | No | Movement `5"` |
| Plain number | No | No | No | No | Strength `4`, Wounds `2` |
| Target roll | Yes | No | No | Yes | WS `3+`, BS `4+`, Cool `5+` |
| Roll modifier | No | No | Yes | No | Accuracy `+1` |

Getting these flags right ensures that when equipment or advancements modify a stat, the system correctly determines whether to add or subtract, and how to format the result.
