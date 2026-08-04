# Equipment List Expansions

## Overview

Equipment List Expansions allow you to define additional equipment that becomes available to fighters under specific conditions. In the base game, each fighter type has a fixed equipment list. A list represents a user's collection of fighters (called a "gang" in Necromunda). Expansions extend this by granting access to extra equipment when a list meets certain criteria -- such as having a particular affiliation, belonging to a specific house, or the fighter being a certain category.

This system is how Gyrinx handles conditional equipment access. For example, a Cawdor gang that has chosen the "Word-Keepers" alliance gains access to special devotional equipment that other Cawdor gangs do not have. Or Delaque vehicles might get access to house-specific vehicle upgrades. Expansions make this possible without duplicating equipment lists or creating separate fighter entries for every combination.

When an expansion applies, its equipment items appear alongside the fighter's normal equipment list in the equipment selection interface. Users see these items seamlessly integrated -- they may not even realise the equipment came from an expansion rather than the base equipment list. Expansion items can also override the base cost of equipment, allowing you to offer items at different prices depending on the context.

## Key Concepts

**Expansion**: A named collection of equipment items that becomes available when all of its rules are satisfied. An expansion has a name, a set of rules, and a set of equipment items.

**Rule**: A condition that must be met for an expansion to apply. Rules are evaluated against the context of a specific list and fighter. Multiple rules on an expansion use AND logic -- every rule must match for the expansion to activate.

**Rule Types**: There are three types of rules, each checking a different aspect of the list or fighter. You can combine rule types on a single expansion to create precise conditions.

**Expansion Item**: A piece of equipment (and optionally a specific weapon profile) that becomes available through an expansion, with an optional cost override.

**Expansion Cost Override**: An expansion item can specify a different cost than the equipment's base cost. This allows the same equipment to be available at different prices depending on the expansion context. If no cost override is set, the equipment's base cost is used.

**Cost Priority**: When a fighter has access to equipment through multiple sources, the cost resolution order is: expansion cost override (highest priority), then equipment list cost override (from `ContentFighterEquipmentListItem.cost`), then base equipment cost. This means expansion cost overrides always win over standard equipment list cost overrides.

## Models

### `ContentEquipmentListExpansion`

Represents a named expansion set. This is the top-level model that ties together a set of rules and a collection of equipment items.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (unique) | The name of this expansion, used to identify it in the admin interface and in string representations. Example: "Cawdor Word-Keepers Equipment" or "Delaque Vehicle Upgrades". |
| `rules` | ManyToManyField | The set of rules that must all match (AND logic) for this expansion to apply. Links to `ContentEquipmentListExpansionRule` instances. |

**Relationships:**

- Has many `ContentEquipmentListExpansionRule` instances via the `rules` many-to-many field. All rules must match for the expansion to apply.
- Has many `ContentEquipmentListExpansionItem` instances via the `items` reverse relation (ForeignKey from the item model).

**Admin interface:**

- Searchable by `name`.
- List view shows the expansion name, number of rules, and number of items.
- The `rules` field uses a horizontal filter widget, allowing you to select from all available rules.
- Equipment items are managed inline directly on the expansion's edit page.

### `ContentEquipmentListExpansionItem`

Represents a single piece of equipment that becomes available as part of an expansion. Each item links an expansion to a specific equipment entry and optionally a specific weapon profile.

| Field | Type | Description |
|-------|------|-------------|
| `expansion` | ForeignKey | The expansion this item belongs to. |
| `equipment` | ForeignKey | The `ContentEquipment` that becomes available. Uses autocomplete for selection. |
| `weapon_profile` | ForeignKey (nullable) | An optional specific weapon profile for this item. Use this when you want to make a particular variant available (such as a specific ammo type) rather than the entire equipment entry. Must belong to the selected equipment. |
| `cost` | IntegerField (nullable) | An override cost for this equipment within the expansion. Set to `null` to use the equipment's base cost. Set to `0` to make the item free. Any other value replaces the base cost. |

**Validation rules:**

- The `weapon_profile`, if set, must belong to the selected `equipment`. The admin enforces this through model validation.
- The combination of `expansion`, `equipment`, and `weapon_profile` must be unique. You cannot add the same equipment/profile combination to the same expansion twice.

**Admin interface:**

- Managed as inline rows on the `ContentEquipmentListExpansion` edit page.
- Each row shows fields for equipment (autocomplete), weapon profile (autocomplete), and cost.
- One empty row is shown by default for adding new items.

### `ContentEquipmentListExpansionRule`

The base model for expansion rules. This uses Django's polymorphic model system, meaning each rule is actually one of the three specific rule types described below. You do not create base rules directly -- you always create one of the typed rule subclasses.

The parent rule admin page shows all rules of all types in a single list view, filterable by rule type. From there, you can click through to the specific rule type's edit page.

### `ContentEquipmentListExpansionRuleByAttribute`

A rule that matches based on a list's attribute values. This is the most common rule type, used for affiliations, alliances, alignments, and other list attributes configured through the [Gang Attributes](gang-attributes.md) system.

| Field | Type | Description |
|-------|------|-------------|
| `attribute` | ForeignKey | The `ContentAttribute` to check (e.g., "Affiliation", "Alliance"). Uses autocomplete for selection. |
| `attribute_values` | ManyToManyField (optional) | Specific `ContentAttributeValue` entries to match. If left empty, the rule matches any non-empty value for the attribute. If populated, the list must have at least one of the specified values assigned. |

**Matching behaviour:**

- The rule checks the list's active (non-archived) attribute assignments.
- If the list has no assignment for the specified attribute, the rule does not match.
- If `attribute_values` is empty, the rule matches any list that has any active value for that attribute.
- If `attribute_values` contains specific values, the rule matches if the list has at least one of those values assigned.
- Archived attribute assignments are ignored. If a list's attribute assignment is archived, expansions dependent on that attribute will stop applying.

**Admin interface:**

- The `attribute` field uses autocomplete, searchable by attribute name.
- The `attribute_values` field uses a horizontal filter widget.
- List view displays the rule's string representation and the attribute name.

### `ContentEquipmentListExpansionRuleByHouse`

A rule that matches based on the list's house.

| Field | Type | Description |
|-------|------|-------------|
| `house` | ForeignKey | The `ContentHouse` the list must belong to. Uses autocomplete for selection. |

**Matching behaviour:**

- The rule checks if the list's house matches the specified house exactly.

**Admin interface:**

- The `house` field uses autocomplete, searchable by house name.
- List view displays the rule's string representation and the house name.

### `ContentEquipmentListExpansionRuleByFighterCategory`

A rule that matches based on the fighter's category (Leader, Champion, Ganger, Vehicle, etc.).

| Field | Type | Description |
|-------|------|-------------|
| `fighter_categories` | MultiSelectField | One or more fighter categories that this rule matches. Uses the standard `FighterCategoryChoices` values: Leader, Champion, Ganger, Juve, Crew, Exotic Beast, Hanger-on, Brute, Hired Gun, Bounty Hunter, House Agent, Hive Scum, Dramatis Personae, Prospect, Specialist, Stash, Vehicle, Ally, Gang Terrain. |

**Matching behaviour:**

- The rule checks if the fighter's category is in the list of selected categories.
- If no fighter context is provided (for example, when evaluating at the list level only), the rule does not match.

**Admin interface:**

- The `fighter_categories` field is a multi-select widget.
- List view displays the rule's string representation and the selected categories (up to three shown).

## How It Works in the Application

When a user opens the equipment selection screen for a fighter, the application evaluates all expansions against the current context. The context includes the list, its house, its active attribute assignments, and the fighter's category. These inputs are bundled into an `ExpansionRuleInputs` structure that the rule system uses for evaluation.

For each expansion, every attached rule is checked. If all rules match (AND logic), the expansion applies. The equipment items from all applicable expansions are then merged into the fighter's available equipment. This happens transparently -- expansion equipment appears in the same list as the fighter's normal equipment.

When a user toggles the "Equipment List" filter (which shows only equipment from the fighter's designated equipment list), expansion items are included alongside the fighter's standard equipment list items. Both sources of equipment are treated equally in this filtered view.

Cost overrides from expansions take the highest priority. If a piece of equipment appears both on a fighter's standard equipment list (with its own equipment list cost override) and in an applicable expansion (with a different expansion cost override), the expansion's cost is used. This priority order ensures that special conditions like affiliations can grant discounted or premium pricing that supersedes the default fighter-specific pricing.

Weapon profiles are also supported. An expansion item can specify a particular weapon profile, making only that profile available rather than the whole equipment entry. Profile-specific cost overrides follow the same priority rules.

## Common Admin Tasks

### Creating an Expansion for a Gang Affiliation

This is the most common scenario: a gang with a specific affiliation (like "Malstrain Corrupted" or "Water Guild") gains access to additional equipment for certain fighter types.

1. **Create the attribute rule.** Go to the Expansion Rules section and create a new "Expansion Rule by Attribute". Select the attribute (e.g., "Affiliation") and then select the specific values that should trigger this expansion (e.g., "Malstrain Corrupted"). If you want the expansion to apply for any value of the attribute, leave the attribute values empty.

2. **Create the fighter category rule** (if applicable). If only certain fighter categories should get the equipment, create a new "Expansion Rule by Fighter Category" and select the relevant categories (e.g., Leader, Champion).

3. **Create the expansion.** Go to Equipment List Expansions and create a new expansion. Give it a descriptive name (e.g., "Malstrain Leader/Champion Equipment"). In the rules section, add both rules you created. Remember, all rules must match -- adding both an attribute rule and a fighter category rule means the expansion only applies when both conditions are met.

4. **Add equipment items.** In the inline section at the bottom of the expansion form, add equipment entries. For each item, select the equipment and optionally set a cost override. Leave the cost blank to use the equipment's base cost.

### Creating a House-Specific Expansion

For equipment that should only be available to lists of a specific house:

1. **Create the house rule.** Create a new "Expansion Rule by House" and select the target house (e.g., "Delaque").

2. **Optionally create a fighter category rule** to further restrict which fighters get access.

3. **Create the expansion** and add both rules.

4. **Add the equipment items** with optional cost overrides.

### Adding a Weapon Profile to an Expansion

Sometimes you want to make a specific weapon variant available rather than the base equipment:

1. On the expansion's edit page, add a new item row in the inline section.
2. Select the equipment first.
3. Then select the specific weapon profile. The weapon profile must belong to the selected equipment -- the system validates this.
4. Optionally set a cost override for this specific profile.

This is useful for making specific ammo types or weapon configurations available through an expansion.

### Changing an Expansion Item's Cost

When you change the cost of an expansion item, affected user data is automatically marked for recalculation. See the cost propagation section in [Equipment & Weapons](equipment-and-weapons.md) for details.

Simply edit the cost field on the expansion item and save. The cost propagation happens automatically.

### Reusing Rules Across Expansions

Rules are standalone objects that can be shared across multiple expansions. For example, if you have an attribute rule for "Malstrain Corrupted" and a fighter category rule for "Leader, Champion", you can attach these same rules to multiple expansions. This avoids duplicating rule definitions and makes it easy to manage conditions that apply to several different equipment sets.

When browsing the rules list, you can see which expansions reference each rule. If you modify a rule (for example, adding a new fighter category), the change affects all expansions that use that rule.

### Verifying an Expansion Works

After creating an expansion, you can verify it by:

1. Creating (or using an existing) list of the appropriate house.
2. Setting the relevant attribute values on the list (if the expansion uses attribute rules).
3. Selecting a fighter of the correct category.
4. Opening the equipment selection screen and toggling the "Equipment List" filter.
5. Checking that the expansion equipment appears in the list with the correct costs.
