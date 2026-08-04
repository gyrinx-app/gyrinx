# Equipment Availability & Restrictions

## Overview

This documentation explains how to configure fighter-specific equipment lists and restrictions for the equipment system documented in [Equipment & Weapons](equipment-and-weapons.md).

The equipment availability and restrictions system controls which equipment each fighter type can access, and at what cost. A list represents a user's collection of fighters (called a "gang" in Necromunda). In Necromunda, different fighter types have access to different equipment lists with varying prices -- a Leader might buy a Power Sword for 40 credits while a Ganger pays 50, and some equipment categories are entirely off-limits to certain fighter types.

This area of the content library lets you configure all of these rules. It includes fighter-specific equipment lists with custom pricing, category-level restrictions that limit which fighter types can browse certain equipment groups, availability presets that control default Trading Post filters, and linking models that connect equipment items to fighters or other equipment for automatic creation.

When a user opens the weapons or gear page for one of their fighters, the application combines all of these configurations to determine exactly which items appear, what prices are shown, and which categories are visible. Getting this configuration right is essential for an accurate game experience.

## Key Concepts

**Equipment List** -- The set of equipment items available to a specific fighter type, as published in the rulebook. Each fighter type (e.g. "Goliath Forge Boss") has its own equipment list with potentially different costs for the same items.

**Equipment List Cost Override** -- When an equipment item appears on a fighter's equipment list at a price different from the base Trading Post price, that fighter-specific price is an equipment list cost override (stored on `ContentFighterEquipmentListItem.cost`).

**Fighter Category** -- The broad classification of a fighter (Leader, Champion, Ganger, Juve, etc.). Category restrictions operate at this level rather than on individual fighter types.

**Availability** -- Each equipment item and weapon profile has an availability type (Common, Rare, Illegal, Exclusive, Unique) and optionally an availability level (a numeric value representing the dice roll needed). These control what appears in the Trading Post.

**Equipment List Mode vs Trading Post Mode** -- When a user browses equipment for a fighter, they can toggle between "Equipment List" mode (showing only items from the fighter's equipment list) and the full Trading Post view (showing all equipment filtered by availability). Availability presets control the defaults for Trading Post mode.

**Can Buy Any** -- A flag on `ContentHouse` that, when enabled, gives all fighters in that house access to the full Trading Post by default rather than just their equipment list.

## Models

### `ContentFighterEquipmentListItem`

Represents a single entry on a fighter's equipment list. This is the primary model for defining which equipment items a fighter type can buy and at what price.

Each record links a `ContentFighter` to a `ContentEquipment` item, optionally specifying a particular weapon profile and an equipment list cost override. When a user views their fighter's equipment in "Equipment List" mode, these records determine what appears.

| Field | Type | Description |
|-------|------|-------------|
| `fighter` | ForeignKey to `ContentFighter` | The fighter type this equipment list entry belongs to |
| `equipment` | ForeignKey to `ContentEquipment` | The equipment item available to this fighter |
| `weapon_profile` | ForeignKey to `ContentWeaponProfile` (optional) | A specific weapon profile with its own cost override. Leave blank when setting the base equipment cost. |
| `cost` | Integer | The fighter-specific cost for this item. This overrides the equipment's base Trading Post cost. |

**Relationships:**

- Belongs to a `ContentFighter` and a `ContentEquipment`
- Optionally references a `ContentWeaponProfile` for profile-level cost overrides
- Referenced by the equipment views to build the "Equipment List" filter and to annotate fighter-specific costs

**Validation rules:**

- The combination of `fighter`, `equipment`, and `weapon_profile` must be unique
- If a `weapon_profile` is specified, it must belong to the specified `equipment`
- `equipment` is required

**Admin interface:**

- Searchable by fighter type, equipment name, and weapon profile name
- `fighter` and `equipment` use autocomplete fields for faster data entry
- The weapon profile dropdown is filtered to show only profiles belonging to the selected equipment, and only those with a cost greater than zero (since zero-cost profiles are "standard" and don't need overrides)
- Supports the "Copy to another Fighter" bulk action

**How equipment list cost overrides work:**

When you create a `ContentFighterEquipmentListItem` without a `weapon_profile`, the `cost` field overrides the base price of the equipment for that fighter type. When you include a `weapon_profile`, the `cost` field overrides the price of that specific profile. This allows you to set both an equipment-level override and individual profile-level overrides for the same weapon on the same fighter.

For example, for a Boltgun that costs 55 credits at the Trading Post:

- A record with fighter=Goliath Leader, equipment=Boltgun, weapon_profile=null, cost=45 means the Leader buys the base Boltgun for 45 credits
- A record with fighter=Goliath Leader, equipment=Boltgun, weapon_profile=Rapid Fire, cost=30 means the Leader buys the Rapid Fire profile for 30 credits

### `ContentFighterEquipmentListWeaponAccessory`

Defines which weapon accessories are available to a fighter type and at what cost. This works the same way as `ContentFighterEquipmentListItem` but for weapon accessories rather than equipment.

| Field | Type | Description |
|-------|------|-------------|
| `fighter` | ForeignKey to `ContentFighter` | The fighter type this accessory is available to |
| `weapon_accessory` | ForeignKey to `ContentWeaponAccessory` | The weapon accessory |
| `cost` | Integer | The fighter-specific cost for this accessory |

**Relationships:**

- Belongs to a `ContentFighter` and a `ContentWeaponAccessory`
- Referenced when a user adds accessories to an assigned weapon

**Validation rules:**

- The combination of `fighter` and `weapon_accessory` must be unique
- Cost cannot be negative

**Admin interface:**

- Searchable by fighter type and weapon accessory name
- `fighter` and `weapon_accessory` use autocomplete fields
- Supports the "Copy to another Fighter" bulk action

### `ContentFighterEquipmentListUpgrade`

Defines fighter-specific cost overrides for equipment upgrades. When an equipment item has upgrades (like cyberteknika upgrades or genesmithing options), this model lets you set different prices per fighter type.

| Field | Type | Description |
|-------|------|-------------|
| `fighter` | ForeignKey to `ContentFighter` | The fighter type this upgrade cost applies to |
| `upgrade` | ForeignKey to `ContentEquipmentUpgrade` | The specific equipment upgrade |
| `cost` | Integer | The fighter-specific cost for this upgrade |

**Relationships:**

- Belongs to a `ContentFighter` and a `ContentEquipmentUpgrade`
- Referenced when calculating upgrade costs on a fighter's equipment assignment

**Validation rules:**

- The combination of `fighter` and `upgrade` must be unique
- Cost cannot be negative

**Admin interface:**

- Searchable by fighter type, upgrade name, and parent equipment name
- `fighter` and `upgrade` use autocomplete fields
- Filterable by equipment upgrade mode (Single or Multi)
- Supports the "Copy to another Fighter" bulk action

### `ContentEquipmentCategoryFighterRestriction`

Controls which fighter categories can access equipment from a given equipment category. If no restrictions are set on a category, all fighter categories can access it. When one or more restrictions exist, only the listed fighter categories can see equipment from that category.

| Field | Type | Description |
|-------|------|-------------|
| `equipment_category` | ForeignKey to `ContentEquipmentCategory` | The equipment category being restricted |
| `fighter_category` | CharField (choices) | A fighter category that is allowed to access this equipment category |

**Relationships:**

- Belongs to a `ContentEquipmentCategory`
- Managed as an inline on the `ContentEquipmentCategory` admin page

**Validation rules:**

- The combination of `equipment_category` and `fighter_category` must be unique

**How restrictions work in practice:**

If the "Heavy Weapons" equipment category has two restriction records -- one for `LEADER` and one for `CHAMPION` -- then only Leaders and Champions will see Heavy Weapons when browsing equipment. Gangers, Juves, and other categories will not see that category at all.

If an equipment category has no restriction records, it is available to all fighter categories.

This model works in conjunction with `ContentFighterEquipmentCategoryLimit`, which can impose numeric limits on how many items from a restricted category a specific fighter type can take.

### `ContentFighterEquipmentCategoryLimit`

Sets per-fighter-type limits on how many items from a given equipment category can be assigned. This only works for categories that already have fighter category restrictions (via `ContentEquipmentCategoryFighterRestriction`).

| Field | Type | Description |
|-------|------|-------------|
| `fighter` | ForeignKey to `ContentFighter` | The specific fighter type this limit applies to |
| `equipment_category` | ForeignKey to `ContentEquipmentCategory` | The equipment category being limited |
| `limit` | PositiveInteger | Maximum number of items from this category the fighter can have (default: 1) |

**Relationships:**

- Belongs to a `ContentFighter` and a `ContentEquipmentCategory`
- Managed as an inline on both the `ContentEquipmentCategory` admin page and the `ContentFighter` admin page

**Validation rules:**

- The combination of `fighter` and `equipment_category` must be unique
- The equipment category must have at least one fighter category restriction before a limit can be set

**Admin interface:**

- On the `ContentEquipmentCategory` page, appears as an inline with fighters grouped by house
- On the `ContentFighter` page, appears as an inline with equipment categories filtered to only show those that have fighter restrictions, grouped by category group

### `ContentAvailabilityPreset`

Defines default availability filter settings for the Trading Post view. When a user opens the equipment browsing page in Trading Post mode, the system looks up the most specific matching preset to pre-populate the availability type checkboxes and maximum availability level.

Presets can be defined at three levels of specificity, and they stack: a preset for a specific fighter takes precedence over a preset for a fighter category, which takes precedence over one for a house.

| Field | Type | Description |
|-------|------|-------------|
| `fighter` | ForeignKey to `ContentFighter` (optional) | Specific fighter type this preset applies to |
| `category` | CharField (optional) | Fighter category (Leader, Champion, etc.) this preset applies to |
| `house` | ForeignKey to `ContentHouse` (optional) | House this preset applies to |
| `availability_types` | MultiSelectField | Which availability types to show by default (Common, Rare, Illegal, Exclusive, Unique) |
| `max_availability_level` | Integer (optional) | Maximum availability level (rarity roll). Leave blank for no limit. |
| `fighter_can_buy_any` | Boolean | If checked, this fighter defaults to showing all equipment (full Trading Post view) similar to the house-level `can_buy_any` flag |

**Specificity matching:**

When the system looks up a preset, it finds all presets where every non-null field matches the current fighter/category/house combination. It then picks the most specific match (the one with the most non-null fields). In case of a tie, the most recently created preset wins.

For example, with these presets:

1. Category=Leader, availability_types=[C, R, I]
2. Category=Leader, House=Goliath, availability_types=[C, R]
3. Fighter=Goliath Forge Boss, availability_types=[C, R, I], max_availability_level=9

A Goliath Forge Boss would match preset 3 (most specific). A Goliath Leader (who is not a Forge Boss) would match preset 2. An Escher Leader would match preset 1.

**Validation rules:**

- At least one of `fighter`, `category`, or `house` must be specified
- The combination of `fighter`, `category`, and `house` must be unique
- `max_availability_level` must be at least 1 if set

**Admin interface:**

- Searchable by fighter type and house name
- Filterable by category and house
- `fighter` and `house` use autocomplete fields

### `ContentEquipmentFighterProfile`

Links an equipment item to a fighter type for automatic fighter creation. When a user assigns the linked equipment to one of their fighters, the application automatically creates a new `ListFighter` of the specified type and links it as a child of the equipment assignment. This is used for Exotic Beasts and Vehicles -- equipment items that, when purchased, create an associated fighter on the list.

| Field | Type | Description |
|-------|------|-------------|
| `equipment` | ForeignKey to `ContentEquipment` | The equipment item that triggers fighter creation |
| `content_fighter` | ForeignKey to `ContentFighter` | The fighter type to create when this equipment is assigned |

**Relationships:**

- Belongs to a `ContentEquipment` and a `ContentFighter`
- Managed as an inline on the `ContentEquipment` admin page
- When the linked equipment is assigned to a `ListFighter`, the system automatically creates a new child `ListFighter`
- When the equipment assignment is deleted, the child fighter is also deleted

**Validation rules:**

- The combination of `equipment` and `content_fighter` must be unique
- Each equipment item should have at most one fighter profile (the system raises an error if multiple exist)
- The fighter profile must not point to the same fighter type as the one equipping it

**Admin interface:**

- Searchable by equipment name and fighter type
- `equipment` and `content_fighter` use autocomplete fields
- The fighter dropdown is grouped by house

### `ContentEquipmentEquipmentProfile`

Links an equipment item to another equipment item for automatic assignment. When the main equipment is assigned to a fighter, the linked equipment is automatically assigned as well. This is used for items that come bundled together, such as a weapon that includes specific ammunition types.

| Field | Type | Description |
|-------|------|-------------|
| `equipment` | ForeignKey to `ContentEquipment` | The main equipment item |
| `linked_equipment` | ForeignKey to `ContentEquipment` | The equipment item to auto-assign alongside the main item |

**Relationships:**

- Belongs to two `ContentEquipment` instances
- Managed as an inline on the `ContentEquipment` admin page
- The auto-assigned equipment is tracked as a "linked child" of the parent assignment
- When the parent equipment assignment is deleted, all linked child assignments are also deleted

**Validation rules:**

- The combination of `equipment` and `linked_equipment` must be unique
- An equipment item cannot link to itself
- The linked equipment cannot itself have equipment-equipment links (no chaining)

**Admin interface:**

- Searchable by both equipment names
- Both fields use autocomplete

## How It Works in the Application

### Equipment browsing

When a user navigates to the weapons or gear page for one of their fighters, the application builds the list of available equipment through several filtering stages:

1. **Base equipment query** -- All equipment is fetched (weapons or non-weapons depending on the page), annotated with fighter-specific costs from `ContentFighterEquipmentListItem`.

2. **Category restrictions** -- The system checks `ContentEquipmentCategoryFighterRestriction` records. Any equipment category that has restrictions but does not include the current fighter's category is excluded entirely. Categories with no restrictions remain available to all.

3. **Equipment list vs Trading Post mode** -- In Equipment List mode, only items that appear in `ContentFighterEquipmentListItem` records for the fighter are shown. In Trading Post mode, all equipment passing the category filter is shown, filtered by availability type and level.

4. **Availability presets** -- When in Trading Post mode, the system looks up a `ContentAvailabilityPreset` to determine default filter values. If the house has `can_buy_any` enabled or the preset has `fighter_can_buy_any` set, the view defaults to Trading Post mode with the preset's availability filters applied.

5. **Weapon profile filtering** -- For weapons, profiles are filtered by availability type and level. Profiles with zero cost (standard profiles) always appear. Profile-specific cost overrides from `ContentFighterEquipmentListItem` records with a `weapon_profile` set are applied.

### Cost display

Throughout the application, equipment costs displayed on fighter cards and equipment browsing pages reflect the fighter-specific override when one exists. The priority for cost resolution is:

1. Expansion cost override (from Equipment List Expansions, if applicable)
2. Equipment list cost override (from `ContentFighterEquipmentListItem`)
3. Base equipment cost (from `ContentEquipment.cost`)

The same priority applies to weapon profile costs and upgrade costs, using their respective override models.

### Auto-creation from equipment links

When a user assigns equipment that has a `ContentEquipmentFighterProfile`, the system automatically creates a new fighter on the list. For example, assigning an Exotic Beast equipment item creates the corresponding Exotic Beast fighter. The child fighter appears on the list and is linked to the equipment assignment -- removing the equipment also removes the fighter.

When a user assigns equipment that has `ContentEquipmentEquipmentProfile` links, the linked equipment items are automatically assigned to the same fighter. For example, assigning a weapon that comes with specific ammunition automatically adds that ammunition as a separate equipment assignment. These linked assignments are tracked and deleted together with the parent.

### Legacy fighters and combined equipment lists

When a `ListFighter` has a legacy content fighter assigned (via the `legacy_content_fighter` field), the system considers equipment lists from both the base content fighter and the legacy content fighter. Cost overrides are checked against both, and in Equipment List mode, items from both fighters' equipment lists are shown. This means legacy fighters effectively have access to a combined equipment list.

## Common Admin Tasks

### Setting up a new fighter's equipment list

1. Create the `ContentFighter` record with its house, category, and stats.
2. For each item on the fighter's equipment list in the rulebook, create a `ContentFighterEquipmentListItem` record linking the fighter to the equipment with the correct cost.
3. For weapons with non-standard profiles at different costs, create additional `ContentFighterEquipmentListItem` records with the `weapon_profile` field set.
4. For any weapon accessories available to this fighter, create `ContentFighterEquipmentListWeaponAccessory` records.
5. For equipment with upgrades that have fighter-specific pricing, create `ContentFighterEquipmentListUpgrade` records.

### Copying an equipment list to another fighter

When multiple fighter types share the same or similar equipment lists, use the "Copy to another Fighter" admin action:

1. Go to the Equipment List Items admin page.
2. Filter or search for the source fighter's equipment list items.
3. Select all the items you want to copy.
4. Choose "Copy to another Fighter" from the actions dropdown.
5. Select one or more target fighters and confirm.

This creates duplicate records for the target fighters. You can then edit individual costs as needed. The same action is available on `ContentFighterEquipmentListWeaponAccessory` and `ContentFighterEquipmentListUpgrade`.

### Copying a fighter to another house

When adding a new house that shares fighter types with an existing house, use the "Copy to another House" action on the `ContentFighter` admin page. This copies the fighter and all of its associated data -- equipment list items, weapon accessories, upgrades, default assignments, skills, and rules -- to the target house.

### Restricting an equipment category to certain fighter types

1. Go to the Equipment Categories admin page and select the category.
2. In the "Fighter Category Restrictions" inline section, add records for each fighter category that should have access.
3. Once restrictions are added, only the listed categories will see equipment from this category.

If you also need per-fighter limits (e.g. "Leaders can take at most 2 Heavy Weapons"), add `ContentFighterEquipmentCategoryLimit` records in the "Fighter Equipment Category Limits" inline on the same page, or from the fighter's own admin page.

### Configuring Trading Post defaults for a house

1. Determine what availability types and levels are appropriate for the house's fighter types.
2. Create `ContentAvailabilityPreset` records at the desired level of specificity:
   - House-level: set only `house` to apply defaults to all fighters in that house
   - Category-level: set `category` (and optionally `house`) to apply defaults to a fighter category
   - Fighter-level: set `fighter` for the most specific control
3. Set the `availability_types` (e.g. Common and Rare) and optionally `max_availability_level`.
4. If a specific fighter or category should default to showing all equipment, check `fighter_can_buy_any`.

### Setting up equipment that creates a fighter (Exotic Beasts, Vehicles)

1. Create the `ContentEquipment` record for the item (e.g. "Phyrr Cat").
2. Create the `ContentFighter` record for the fighter type it produces (e.g. the Phyrr Cat fighter with its stats).
3. On the equipment's admin page, add a `ContentEquipmentFighterProfile` inline record linking the equipment to the fighter type.
4. When a user assigns this equipment to one of their fighters, a new fighter of the linked type is automatically created on their list.

### Setting up equipment that auto-assigns other equipment

1. Create both `ContentEquipment` records (the main item and the linked item).
2. On the main equipment's admin page, add a `ContentEquipmentEquipmentProfile` inline record pointing to the linked equipment.
3. When a user assigns the main equipment, the linked equipment is automatically assigned to the same fighter.

Note that the linked equipment cannot itself have equipment-equipment links -- only one level of linking is supported.
