# Equipment & Weapons

## Overview

The equipment and weapons area of the content library defines every item that fighters can carry, wear, or wield in
Gyrinx. This spans everything from basic armour and grenades through to exotic weaponry with multiple firing modes. When
a user creates a list -- their collection of fighters (called a "gang" in Necromunda) -- and assigns equipment to those
fighters, the data they interact with comes from these content models.

Equipment and weapons share a single underlying model (`ContentEquipment`) but diverge in an important way: weapons have
one or more weapon profiles (`ContentWeaponProfile`) attached to them, which define stat lines like range, strength, and
damage. Equipment without any weapon profiles is treated as non-weapon gear. This distinction is determined automatically
-- you never mark an item as "weapon" or "gear" explicitly. Instead, add weapon profiles to an equipment item and it
becomes a weapon.

Beyond the core equipment and weapon profile models, this area also covers weapon traits (special rules like Rapid Fire
or Blaze), weapon accessories (sights, suspensors), equipment upgrades (cyberteknika, genesmithing), and equipment
categories that organise items into groups for display and filtering.

## Key Concepts

**Equipment vs. weapon.** All items start as `ContentEquipment`. An equipment item that has at least one
`ContentWeaponProfile` is considered a weapon. One without any profiles is non-weapon gear. This is evaluated
automatically based on the presence of linked weapon profiles.

**Equipment categories and groups.** Every equipment item belongs to a `ContentEquipmentCategory`, and each category
belongs to one of four groups: Gear, Vehicle & Mount, Weapons & Ammo, or Other. These groups control display ordering in
the admin and in user-facing equipment lists.

**Availability (rarity).** Equipment, weapon profiles, and weapon accessories each have an availability level that
controls where they can be purchased and whether a dice roll is needed. The availability system uses a letter code plus an
optional numeric level.

**Cost expressions.** Most costs are simple integers, but the `ContentEquipment.cost` field is a text field that supports
non-numeric values like `2D6x10` for random-cost items. Weapon accessories can also use cost expressions that calculate
their price relative to the base weapon cost.

**The dirty system.** When you change a cost in the content library, Gyrinx automatically detects the change and marks
all affected user lists and fighter assignments as "dirty". A dirty assignment is one whose stored cost no longer matches
the current content library cost. On save, the application walks every dirty assignment, recalculates the fighter's
rating and the list's total rating, and -- for lists in campaign mode -- creates an audit trail entry recording the old
and new cost and adjusts the list's credits (charging more if the cost increased, refunding if it decreased). This
propagation is fully automatic: saving the content change is the only action required. Other documentation files
reference this section as the canonical description of the dirty/cost recalculation system.

**Modifiers.** Equipment, upgrades, and accessories can each carry modifiers that change a fighter's stats, grant skills,
or add rules. These are managed through the separate Modifiers system and attached via many-to-many relationships. For
full details on the modifier system and how modifiers are created and applied, see [Modifiers](modifiers.md).

## Models

### `ContentEquipmentCategory`

Organises equipment items into named categories such as "Pistols", "Basic Weapons", "Armour", or "Grenades". Each
category belongs to a group that controls its position in the overall ordering.

#### Fields

| Field | Type | Description |
|---|---|---|
| `name` | CharField | Unique name for the category (e.g. "Heavy Weapons"). |
| `group` | CharField (choices) | One of `Gear`, `Vehicle & Mount`, `Weapons & Ammo`, or `Other`. Controls sort order. |
| `restricted_to` | ManyToManyField (`ContentHouse`) | If set, only fighters from these houses can access equipment in this category. Leave blank for universally available categories. |
| `visible_only_if_in_equipment_list` | BooleanField | When `True`, this category is hidden on a fighter's card unless the fighter actually has equipment from this category assigned. Useful for categories like "Status Items" that should not appear as empty slots. |

#### Fighter Category Restrictions

Categories can be further restricted to specific fighter categories (Leader, Champion, Ganger, etc.) using the
`ContentEquipmentCategoryFighterRestriction` inline. When restrictions are set, only fighters of the listed categories
can equip items from this category.

#### Fighter Equipment Category Limits

When a category has fighter category restrictions, you can also set per-fighter limits using the
`ContentFighterEquipmentCategoryLimit` inline. This controls the maximum number of items from a category that a specific
fighter type can carry. For example, you might limit a Ganger to 1 item from the "Special Weapons" category. Limits can
only be configured on categories that already have fighter category restrictions.

#### Admin Interface

- **Search:** by name and group.
- **Filters:** group, restricted houses, and `visible_only_if_in_equipment_list`.
- **Inlines:** Fighter Category Restrictions, Fighter Equipment Category Limits.

---

### `ContentEquipment`

The central model for all equipment items. Each record represents a distinct piece of gear or weapon that can be
assigned to fighters.

#### Fields

| Field | Type | Description |
|---|---|---|
| `name` | CharField | The item name (e.g. "Lasgun", "Mesh Armour"). Must be unique within its category. |
| `category` | ForeignKey (`ContentEquipmentCategory`) | The category this item belongs to. |
| `cost` | CharField | The credit cost at the Trading Post. This is a text field to support expressions like `2D6x10` for random costs. For weapons, this base cost is typically overridden by the Standard weapon profile cost. |
| `rarity` | CharField (choices) | The availability code. See the Availability System section below. |
| `rarity_roll` | IntegerField | The numeric availability level needed to acquire this item (e.g. `9` means a 9+ roll). Blank for Common items. |
| `upgrade_mode` | CharField (choices) | Either `SINGLE` or `MULTI`. Controls how upgrades are presented and costed. See Upgrades below. |
| `upgrade_stack_name` | CharField | A label for the upgrade track, such as "Augmentation" or "Upgrade". Used in display. Defaults to "Upgrade" if blank. |
| `modifiers` | ManyToManyField (`ContentMod`) | Modifiers that apply to the fighter when this equipment is equipped. Filtered in admin to show only fighter-affecting modifiers (stat changes, rules, skills, skill tree access, psyker discipline access). |

#### Uniqueness

Equipment names must be unique within their category (`unique_together = ["name", "category"]`). You can have two items
named "Stub Gun" only if they are in different categories.

#### Is This a Weapon?

An equipment item is considered a weapon if it has at least one `ContentWeaponProfile` linked to it. The queryset
annotates every equipment record with a `has_weapon_profiles` flag automatically, so you do not need to set this
yourself.

#### Admin Interface

- **Search:** by name, category name, and weapon profile name.
- **Filters:** by category.
- **Inlines:** Weapon Profiles, Equipment-Fighter Links, Equipment-Equipment Links, Equipment Upgrades.
- **Actions:** Clone (see below).

---

### `ContentWeaponProfile`

Defines a weapon's stat line. Every weapon has at least one profile. A weapon with a blank-name profile has a single
"Standard" firing mode. Weapons with multiple profiles represent different firing modes (e.g. a combi-weapon with
bolter and melta profiles).

#### Fields

| Field | Type | Description |
|---|---|---|
| `equipment` | ForeignKey (`ContentEquipment`) | The parent equipment item. |
| `name` | CharField | The profile name. Leave blank for the Standard (default) profile. Named profiles represent alternate firing modes (e.g. "Krak", "Frag"). Do not include a leading hyphen. |
| `cost` | IntegerField | The credit cost. Standard (blank-name) profiles must have zero cost. Named profiles with a positive cost represent upgrades the user can purchase (e.g. paying extra for a special ammo type). |
| `rarity` | CharField (choices) | Availability code for this specific profile. |
| `rarity_roll` | IntegerField | Availability level for this profile. |
| `range_short` | CharField | Short range (e.g. `8"`). Automatically appends `"` if a number is entered without one. |
| `range_long` | CharField | Long range (e.g. `24"`). Same auto-formatting. |
| `accuracy_short` | CharField | Short range accuracy modifier (e.g. `+1`). |
| `accuracy_long` | CharField | Long range accuracy modifier (e.g. `-1`). |
| `strength` | CharField | Weapon strength (e.g. `4`, `S+2`). |
| `armour_piercing` | CharField | Armour Piercing value (e.g. `-1`). |
| `damage` | CharField | Damage value (e.g. `2`). |
| `ammo` | CharField | Ammo roll value (e.g. `4+`). |
| `traits` | ManyToManyField (`ContentWeaponTrait`) | Weapon traits such as Rapid Fire, Knockback, or Blaze. |

All stat fields are `CharField` rather than numeric fields because some values include special characters (e.g. `S+2`
for strength, `4+` for ammo rolls, `E` for template range). Leave a field blank to show a dash on the fighter card.
Do not enter a literal `-` character -- blank fields are automatically displayed as dashes.

#### Validation Rules

- Standard (blank-name) profiles must have `cost` of 0.
- Profile names must not start with a hyphen.
- Profile names must not be `(Standard)` literally.
- Cost cannot be negative.
- Smart quotes (curly quotes) are rejected in stat fields.
- Range values that start with a digit automatically get a trailing `"` appended.

#### Uniqueness

Profile names must be unique within their parent equipment (`unique_together = ["equipment", "name"]`).

#### Admin Interface

Weapon profiles appear as a stacked inline on the `ContentEquipment` admin page. They can also be managed directly
through their own admin page with search by name and autocomplete on the equipment field.

---

### `ContentWeaponTrait`

A named trait that can be assigned to weapon profiles. Traits represent special rules that modify how a weapon behaves
in the game, such as "Rapid Fire (1)", "Knockback", "Blaze", or "Scarce".

#### Fields

| Field | Type | Description |
|---|---|---|
| `name` | CharField | The unique trait name. |

Traits are simple named records. The game rule text itself lives in the rulebook -- the content library just tracks
which traits exist so they can be linked to weapon profiles.

#### Admin Interface

- **Search:** by name.

---

### `ContentWeaponAccessory`

Accessories that can be attached to weapons to modify their capabilities, such as sights, suspensors, or mono-sights.

#### Fields

| Field | Type | Description |
|---|---|---|
| `name` | CharField | Unique accessory name (e.g. "Telescopic Sight"). |
| `cost` | IntegerField | Base credit cost. Used when no cost expression is provided. |
| `cost_expression` | CharField | Optional formula for calculating cost relative to the weapon's base cost. When provided, this overrides the fixed `cost` field. |
| `rarity` | CharField (choices) | Availability code. |
| `rarity_roll` | IntegerField | Availability level. |
| `modifiers` | ManyToManyField (`ContentMod`) | Modifiers applied to the weapon's stat line and traits when this accessory is attached. |

#### Cost Expressions

The `cost_expression` field allows accessory prices to scale with the weapon they are attached to. The expression is
evaluated safely using the `simpleeval` library (not Python's built-in `eval`). The variable `cost_int` represents the
base weapon's integer cost.

Available functions: `min()`, `max()`, `round()`, `ceil()`, `floor()`.

For example, the expression `ceil(cost_int * 0.25 / 5) * 5` would price the accessory at 25% of the weapon cost,
rounded up to the nearest 5 credits. If evaluation fails for any reason, the system falls back to the fixed `cost`
value.

#### Admin Interface

- **Search:** by name.

---

### `ContentEquipmentUpgrade`

Represents an upgrade that can be applied to a piece of equipment. Upgrades are used for systems like cyberteknika
(where each level builds on the previous) and genesmithing (where each option is independent).

#### Fields

| Field | Type | Description |
|---|---|---|
| `equipment` | ForeignKey (`ContentEquipment`) | The parent equipment item this upgrade belongs to. |
| `name` | CharField | The upgrade name. Must be unique within the parent equipment. |
| `position` | IntegerField | The position in the upgrade stack. Used for ordering and cumulative cost calculation in `SINGLE` mode. |
| `cost` | IntegerField | The credit cost of this upgrade level. Interpretation depends on the parent equipment's `upgrade_mode`. |
| `modifiers` | ManyToManyField (`ContentMod`) | Modifiers applied to the equipment or fighter when this upgrade is active. |

#### Upgrade Modes

The parent `ContentEquipment` controls how upgrades behave via its `upgrade_mode` field:

- **SINGLE mode:** Upgrades form a sequential stack. The fighter progresses through upgrade levels in order. Costs are
  cumulative -- the total cost of reaching a level equals the sum of all upgrade costs at that position and below. For
  example, if a cyberteknika has three levels costing 10, 15, and 20, reaching level 3 costs 10 + 15 + 20 = 45 credits.

- **MULTI mode:** Each upgrade is an independent option. The fighter can pick any combination. Each upgrade's cost
  stands on its own and is not summed with others.

The `upgrade_stack_name` on the parent equipment provides the display label (e.g. "Augmentation", "Upgrade") for the
upgrade track.

#### Admin Interface

Upgrades appear as a tabular inline on the `ContentEquipment` admin page. They can also be managed directly with
search by name and equipment name, and autocomplete on the equipment field.

---

## Availability System

Equipment, weapon profiles, and weapon accessories all use the same availability system with two fields working
together:

| Code | Label | Meaning |
|---|---|---|
| `C` | Common | Freely available at the Trading Post. No roll required. |
| `R` | Rare | Available at the Trading Post but requires a successful availability roll. |
| `I` | Illegal | Available through the Black Market. Requires an availability roll. |
| `E` | Exclusive | Not available for purchase at the Trading Post. Used for items that can only be obtained through special means (starting equipment, scenario rewards, etc.). |
| `U` | Unique | Unique to a specific fighter. Not available for general purchase. Only used on `ContentEquipment`, not on profiles or accessories. |

The `rarity_roll` field specifies the target number for the availability roll (e.g. `8` means the item is available on
an 8+). This field should be left blank for Common items and is typically in the range of 7-12 for Rare and Illegal
items.

## How It Works in the Application

### Equipment on Fighter Cards

When a user views a fighter card, the application displays two categories of equipment:

1. **Weapons** -- shown in a table with their full stat line (range, accuracy, strength, AP, damage, ammo) and trait
   list. If a weapon has multiple profiles, each profile appears as a separate row.

2. **Non-weapon gear** -- shown as a simpler list grouped by category.

Categories with `visible_only_if_in_equipment_list` set to `True` only appear on the fighter card when the fighter has
at least one item from that category. This prevents empty category headings from cluttering the display.

### Assigning Equipment to Fighters

Users assign equipment to their list fighters through the application interface. The system checks equipment
categories, house restrictions, and fighter category restrictions to determine what each fighter is allowed to equip.
Costs are drawn from the fighter's available credits, and the list's total rating is updated accordingly.

Equipment can also be granted to fighters through the advancement system during campaigns. See
[Advancements](advancements.md).

### Cost Overrides

The base cost on `ContentEquipment` and `ContentWeaponProfile` can be overridden on a per-fighter-type basis through
the equipment availability system. When a fighter-specific cost override exists, it takes precedence over the base
cost. This is how different fighter types can pay different prices for the same item. Fighter-specific equipment lists
and cost overrides are configured through the equipment availability system. See [Equipment Availability &
Restrictions](equipment-availability.md) for details.

### Cost Change Propagation

When you change the `cost` field on any content model in this area, the system automatically:

1. Detects that the cost has changed (via a pre-save signal).
2. Marks all user-level equipment assignments (`ListFighterEquipmentAssignment`) that reference this content as
   "dirty" -- meaning their stored cost no longer matches the current content library cost.
3. After saving, recalculates ratings for every affected list by walking each dirty assignment, updating the
   fighter's rating, and recomputing the list total.
4. For lists in campaign mode, creates an audit trail entry recording the old and new cost and adjusts the list's
   credits (charging more if the cost increased, refunding if it decreased).

This means you can correct a pricing error in the content library and have it automatically reflected across all user
lists that use that item. No manual intervention is needed beyond saving the content change. This section is the
canonical description of the dirty/cost recalculation system; other documentation files reference it.

### Modifiers on Equipment

When equipment, upgrades, or accessories carry modifiers, those modifiers are applied to the fighter's stat line and
rules whenever the item is assigned. For weapon accessories, modifiers affect the weapon's profile stats and traits
rather than the fighter directly. For full details on the modifier system and how modifiers are created and applied, see
[Modifiers](modifiers.md).

## Common Admin Tasks

### Adding a New Weapon

1. Open the Equipment admin and click "Add".
2. Enter the weapon name and select the appropriate category (e.g. "Basic Weapons").
3. Set the `cost` field. For weapons, this base cost is typically overridden by the Standard profile cost, but it
   serves as a fallback.
4. Set the availability (`rarity`) and availability level (`rarity_roll`) if applicable.
5. In the **Weapon Profiles** inline, add a profile with a blank name for the Standard firing mode. Enter the full
   stat line (range, accuracy, strength, AP, damage, ammo) and select any applicable traits.
6. If the weapon has additional firing modes, add more profiles with descriptive names. Set their cost to the
   additional credits required above the Standard profile price.
7. Save.

### Adding a New Piece of Non-Weapon Gear

1. Open the Equipment admin and click "Add".
2. Enter the item name and select the appropriate category (e.g. "Armour", "Personal Equipment").
3. Set the `cost` field to the credit price.
4. Set availability as needed.
5. If the equipment modifies the fighter (e.g. armour that changes a save stat), attach the relevant modifiers.
6. Do not add any weapon profiles.
7. Save.

### Cloning an Equipment Item

When you need to create a variation of an existing item, use the clone action rather than re-entering everything
manually:

1. In the Equipment list view, select the item or items you want to clone.
2. From the action dropdown, select "Clone selected Equipment" and click Go.
3. The system creates a copy of each selected item with "(Clone)" appended to the name. All weapon profiles and their
   traits are also duplicated.
4. Open the cloned item and edit the name, cost, profiles, or other fields as needed.

### Setting Up Equipment with Upgrades

1. Create the base equipment item (e.g. a cyberteknika implant) with its base cost.
2. Set `upgrade_mode` to `SINGLE` for sequential upgrade tracks, or `MULTI` for independent options.
3. Optionally set `upgrade_stack_name` to a descriptive label (e.g. "Augmentation").
4. In the **Equipment Upgrades** inline, add each upgrade level with a name, position (for ordering), and cost.
5. Attach any modifiers to each upgrade level as needed.

For `SINGLE` mode, pay attention to the `position` field. Costs accumulate from position 0 upward, so the total cost
to reach any level is the sum of all levels at or below that position.

### Creating a New Equipment Category

1. Open the Equipment Categories admin and click "Add".
2. Enter the category name and select the group (`Gear`, `Weapons & Ammo`, `Vehicle & Mount`, or `Other`).
3. If this category should only be visible when a fighter actually has equipment from it, check
   `visible_only_if_in_equipment_list`.
4. If the category is house-specific, add houses to the `restricted_to` field.
5. If only certain fighter categories should access this equipment, add Fighter Category Restrictions in the inline.
6. If you need per-fighter limits on items from this category, add Fighter Equipment Category Limits (this requires
   fighter category restrictions to be set first).

### Correcting a Cost Error

If you discover that an equipment item, weapon profile, upgrade, or accessory has an incorrect cost:

1. Open the relevant record in the admin.
2. Change the `cost` field to the correct value.
3. Save.

The dirty system automatically propagates the change to all affected user lists. In campaign mode, lists will receive
a cost change audit entry and their credits will be adjusted. You do not need to take any additional action.
