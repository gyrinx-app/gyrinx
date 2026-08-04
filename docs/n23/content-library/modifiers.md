# Modifiers

## Overview

Modifiers are the content library's mechanism for expressing how equipment, upgrades, weapon accessories, and injuries change a fighter's characteristics. Rather than hard-coding the effects of every item into application logic, modifiers let you declare effects as data: "this piece of equipment improves Movement by 1" or "this injury removes the Infiltrate skill."

The modifier system uses a polymorphic architecture. There is a single base model, `ContentMod`, and several specialized child types that each handle a different kind of modification -- weapon stats, fighter stats, weapon traits, fighter rules, fighter skills, skill tree access, and psyker discipline access. When you create a modifier in the admin, you choose which type of modifier you need, then fill in the details specific to that type.

These modifiers are then attached to equipment, equipment upgrades, weapon accessories, or injuries through many-to-many relationships. When a user views a fighter on their list -- a list represents a user's collection of fighters (called a "gang" in Necromunda) -- the system collects all modifiers from the fighter's equipment (including accessories and upgrades) and any active injuries, then applies them to produce the final fighter statline, weapon profiles, rules, and skills the user sees.

## Key Concepts

### Polymorphic Modifiers

All modifier types share a single database table hierarchy rooted in `ContentMod`. This means you can attach any type of modifier to any item that accepts modifiers -- the system does not restrict which modifier types can go on which items. In the admin interface, the main Modifications list shows all modifier types together, and you can filter by type.

### Mode

Every modifier has a `mode` field that controls how the modifier takes effect. The available modes vary by modifier type:

- **Stat modifiers** (`ContentModStat`, `ContentModFighterStat`): `improve`, `worsen`, or `set`
- **Trait, rule, and skill modifiers**: `add` or `remove`
- **Skill tree access modifiers**: `add_primary`, `add_secondary`, `remove_primary`, `remove_secondary`, or `disable`
- **Psyker discipline access modifiers**: `add` or `remove`

### Improve vs. Worsen

For stat modifiers, `improve` and `worsen` are relative to the game meaning of the stat, not the raw number. Some stats are "inverted" -- a lower number is better (for example, Ballistic Skill 3+ is better than 4+). The modifier system handles this automatically: `improve` always makes the stat better for the fighter, and `worsen` always makes it worse, regardless of the underlying number direction.

### Attachment Points

Modifiers can be attached to four types of content:

- **Equipment** (`ContentEquipment.modifiers`) -- for fighter-level effects like stat changes, rules, and skills
- **Equipment Upgrades** (`ContentEquipmentUpgrade.modifiers`) -- for effects that come from upgrading equipment
- **Weapon Accessories** (`ContentWeaponAccessory.modifiers`) -- for effects that modify weapon statlines and traits
- **Injuries** (`ContentInjury.modifiers`) -- for lasting effects from campaign injuries

### Virtual Weapon Profile

When a weapon has accessories attached, the application creates a `VirtualWeaponProfile` -- a computed wrapper around the base weapon profile that applies all relevant weapon stat and trait modifiers. This means users see the final modified weapon stats rather than the base stats plus a separate list of changes.

## Models

### `ContentMod`

The base polymorphic model for all modifications. You do not create `ContentMod` instances directly; instead, you create one of the specific child types listed below.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Auto-generated primary key |

In the admin, the main Modifications list shows all modifier types together. You can filter by modifier type using the polymorphic type filter in the sidebar.

### `ContentModStat`

Modifies a weapon's statline values (range, accuracy, strength, etc.). These modifiers are applied through the `VirtualWeaponProfile` system and affect how weapon stats are displayed.

| Field | Type | Description |
|-------|------|-------------|
| `stat` | Choice | The weapon stat to modify. Options: `strength`, `range_short`, `range_long`, `accuracy_short`, `accuracy_long`, `armour_piercing`, `damage`, `ammo` |
| `mode` | Choice | How to apply the change: `improve` (make the stat better), `worsen` (make the stat worse), or `set` (replace the stat value entirely) |
| `value` | String (max 5 chars) | The modification value. For `improve`/`worsen`, this is the amount to change by. For `set`, this is the new value |

**Stat display format:** The `value` field should contain a plain number. The system automatically handles the correct display format based on the stat type -- adding `"` for range stats, `+` prefix for accuracy/AP, and `+` suffix for ammo rolls.

**Example:** A modifier with `stat=strength`, `mode=improve`, `value=1` applied to a weapon with Strength 4 produces Strength 5. The same modifier with `mode=worsen` would produce Strength 3.

### `ContentModFighterStat`

Modifies a fighter's statline values (movement, toughness, wounds, etc.). These modifiers are collected from all of a fighter's equipment and injuries and applied to the fighter's base statline.

| Field | Type | Description |
|-------|------|-------------|
| `stat` | String (max 50 chars) | The fighter stat to modify. Choices are dynamically generated from `ContentStat` objects, ensuring all defined stats are available |
| `mode` | Choice | How to apply the change: `improve`, `worsen`, or `set` |
| `value` | String (max 5 chars) | The modification value |

**Validation:** The system prevents duplicate `ContentModFighterStat` records. If a modifier with the same `stat`, `mode`, and `value` already exists, validation will reject the new entry. This means you can reuse the same modifier across multiple items.

**Admin form:** The `stat` field uses a dropdown populated from `ContentStat` objects. This ensures consistency with the statline system and means the available fighter stats update automatically when new stats are defined.

### `ContentModTrait`

Adds or removes weapon traits from a weapon profile.

| Field | Type | Description |
|-------|------|-------------|
| `trait` | FK to `ContentWeaponTrait` | The weapon trait to add or remove |
| `mode` | Choice | `add` (give the weapon this trait) or `remove` (take the trait away) |

**Example:** A weapon accessory that grants the Knockback trait would have a `ContentModTrait` with `trait=Knockback` and `mode=add`.

### `ContentModFighterRule`

Adds or removes rules from a fighter.

| Field | Type | Description |
|-------|------|-------------|
| `rule` | FK to `ContentRule` | The rule to add or remove |
| `mode` | Choice | `add` or `remove` |

The `rule` field uses autocomplete in the admin for easier searching across the full rule catalogue.

### `ContentModFighterSkill`

Adds or removes skills from a fighter.

| Field | Type | Description |
|-------|------|-------------|
| `skill` | FK to `ContentSkill` | The skill to add or remove |
| `mode` | Choice | `add` or `remove` |

The admin form groups skills by their skill category for easier selection.

### `ContentModSkillTreeAccess`

Modifies which skill trees a fighter has access to. This affects which skills the fighter can choose when advancing.

| Field | Type | Description |
|-------|------|-------------|
| `skill_category` | FK to `ContentSkillCategory` | The skill category (tree) to modify access to |
| `mode` | Choice | `add_primary` (grant primary access), `add_secondary` (grant secondary access), `remove_primary` (revoke primary access), `remove_secondary` (revoke secondary access), `disable` (remove all access to this category) |

**How modes interact:** The `disable` mode removes a skill category from both primary and secondary access. The `add_primary` and `add_secondary` modes are additive -- they add the category without affecting existing access through other sources. The `remove_primary` and `remove_secondary` modes only remove the specific access level.

### `ContentModPsykerDisciplineAccess`

Modifies which psyker disciplines a fighter has access to.

| Field | Type | Description |
|-------|------|-------------|
| `discipline` | FK to `ContentPsykerDiscipline` | The psyker discipline to grant or revoke |
| `mode` | Choice | `add` (grant access to this discipline) or `remove` (revoke access) |

### `ContentModStatApplyMixin`

This is not a model but a shared mixin class used by both `ContentModStat` and `ContentModFighterStat`. It contains the `apply()` method that handles the arithmetic of stat modifications. Understanding this logic is helpful when verifying that modifiers produce the expected results.

**How `apply()` works:**

1. If the mode is `set`, the method returns the modifier's value directly, replacing whatever was there before.
2. For `improve` or `worsen`, the method determines the direction of change. For `improve`, the value increases; for `worsen`, it decreases.
3. For inverted stats (where lower is better, such as BS 3+), the direction is reversed -- `improve` decreases the number and `worsen` increases it.
4. The method parses the current stat value, handling the various display formats:
   - `"-"` or empty string is treated as 0
   - Values ending in `"` are inch measurements (e.g., `12"`)
   - Values ending in `+` are target rolls (e.g., `4+`)
   - Values starting with `+` are modifiers (e.g., `+1`)
   - Values containing `S` are strength-linked (e.g., `S`, `S+1`, `S-1`)
   - Plain numbers are treated as-is
5. The modifier value is added (or subtracted) and the result is formatted back into the appropriate display format.

**Stat categories:** The system classifies each stat using four properties from `ContentStat`:

| Property | Meaning | Example Stats |
|----------|---------|---------------|
| `is_inverted` | Lower number is better | WS, BS, Int, Ld, Cl, Wil, Init, Save, Ammo, AP, Handling |
| `is_inches` | Displayed with `"` suffix | Range Short, Range Long, Movement |
| `is_modifier` | Displayed with `+` prefix | Accuracy Short, Accuracy Long, AP |
| `is_target` | Displayed with `+` suffix | Ammo, WS, BS, Int, Ld, Cl, Wil, Init, Save, Handling |

## How It Works in the Application

### Fighter Statline Modifications

When a user views a fighter, the application computes the final statline through several steps:

1. The fighter's base statline comes from the `ContentFighter` definition.
2. Any manual overrides from the user (stat advancements) are applied.
3. All modifiers from the fighter's equipment, upgrades, and active injuries are collected.
4. Each stat in the statline is run through the relevant modifiers using the `apply()` method.
5. If the final value differs from the base, the stat is visually marked as modified in the UI, so users can see at a glance which stats have been changed.

Modifiers from different sources stack. If a fighter has two pieces of equipment that each improve Movement by 1, the fighter's Movement increases by 2 total.

### Weapon Profile Modifications

Weapon stat and trait modifiers work through the `VirtualWeaponProfile` system:

1. When a fighter's equipment assignment includes weapon accessories (or the equipment itself has weapon-level modifiers), the system wraps each weapon profile in a `VirtualWeaponProfile`.
2. The `VirtualWeaponProfile` applies all `ContentModStat` modifiers to each weapon stat value on initialization.
3. Trait modifiers (`ContentModTrait`) are applied when the trait list is accessed -- adding traits the weapon does not have, or removing traits it does.
4. The modified statline and trait list are displayed to the user. Modified stat values are visually highlighted.

### Rules and Skills

`ContentModFighterRule` and `ContentModFighterSkill` modifiers are collected alongside stat modifiers. The application maintains separate lists of rule mods and skill mods and applies them when displaying a fighter's rules and skills. An `add` modifier grants the rule or skill; a `remove` modifier takes it away.

### Skill Tree and Psyker Discipline Access

When a fighter advances, the application determines which skill trees are available as primary or secondary. `ContentModSkillTreeAccess` modifiers adjust these lists. Similarly, `ContentModPsykerDisciplineAccess` modifiers control which psyker disciplines a fighter can access. These modifiers are checked at the point of advancement.

### Equipment vs. Weapon Modifiers

It is important to understand which modifier types belong where:

- **On equipment** (`ContentEquipment.modifiers`): Use fighter-level modifiers -- `ContentModFighterStat`, `ContentModFighterRule`, `ContentModFighterSkill`, `ContentModSkillTreeAccess`, `ContentModPsykerDisciplineAccess`. The admin form for equipment automatically filters the modifier list to show only these types.
- **On weapon accessories** (`ContentWeaponAccessory.modifiers`): Use weapon-level modifiers -- `ContentModStat` and `ContentModTrait` -- to change weapon profiles. You can also use fighter-level modifiers if the accessory affects the fighter directly.
- **On equipment upgrades** (`ContentEquipmentUpgrade.modifiers`): Can use any modifier type depending on whether the upgrade affects the weapon or the fighter.
- **On injuries** (`ContentInjury.modifiers`): Typically use fighter-level modifiers, since injuries affect the fighter rather than individual weapons.

## Common Admin Tasks

### Creating a Weapon Stat Modifier

1. Navigate to the Modifications list and click "Add Modification."
2. Select "Weapon Stat Modifier" as the type.
3. Choose the `stat` you want to modify (e.g., Strength).
4. Set the `mode` to `improve`, `worsen`, or `set`.
5. Enter the `value` -- for `improve`/`worsen`, this is the numeric amount (e.g., `1` to improve by one step). For `set`, this is the replacement value.
6. Save the modifier.
7. Go to the relevant weapon accessory or equipment upgrade and add this modifier to its `modifiers` field.

### Creating a Fighter Stat Modifier

1. Navigate to the Modifications list and click "Add Modification."
2. Select "Fighter Stat Modifier" as the type.
3. Choose the `stat` from the dropdown (populated from `ContentStat` definitions).
4. Set the `mode` and `value`.
5. Save the modifier.
6. Attach it to the relevant equipment, equipment upgrade, or injury.

Note: If you try to create a fighter stat modifier that duplicates an existing one (same stat, mode, and value), validation will reject it. Search for the existing modifier and reuse it instead.

### Adding a Trait to a Weapon via an Accessory

1. Create a `ContentModTrait` with `mode=add` and the desired `trait`.
2. Go to the weapon accessory and add this modifier to its `modifiers` field.
3. When a user attaches this accessory to a weapon, the trait will appear in the weapon's trait list.

### Modelling an Injury That Reduces a Stat

1. Create a `ContentModFighterStat` with the target `stat`, `mode=worsen`, and the appropriate `value`.
2. Go to the injury and add this modifier to its `modifiers` field.
3. When the injury is applied to a fighter in a campaign, the stat reduction will appear on the fighter's statline.

### Modelling Equipment That Grants Skill Tree Access

1. Create a `ContentModSkillTreeAccess` with the target `skill_category` and `mode=add_primary` (or `add_secondary`).
2. Go to the equipment item and add this modifier to its `modifiers` field.
3. When a fighter has this equipment, they will gain access to the specified skill tree during advancement.

### Reviewing All Modifiers Attached to an Item

From any equipment, equipment upgrade, weapon accessory, or injury admin page, the `modifiers` field shows all attached modifiers. Each modifier displays a human-readable string describing its effect (e.g., "Improve weapon Strength by 1" or "Add Knockback"). You can click through to edit any modifier directly.

To see all items that use a particular modifier, navigate to the main Modifications list, find the modifier, and check its usage through the related objects.
