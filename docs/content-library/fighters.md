# Fighters & Fighter Types

## Overview

Fighters are the core building blocks of the Gyrinx content library. A list represents a user's collection of fighters (called a "gang" in Necromunda). Every fighter that a user can add to their list starts as a `ContentFighter` -- a template that defines the fighter's archetype, base statistics, default equipment, and available skill trees. When a user adds a fighter to their list, they are creating a `ListFighter` instance based on one of these content templates.

The content library separates fighter definitions from user data. As an administrator, you manage the archetypes (the "what exists in the game") while users manage their own instances (the "what's in my list"). Changes you make to a `ContentFighter` affect how new fighters are created and how existing fighters display their base characteristics.

This area also includes supporting models that control default equipment loadouts, category-specific terminology, and equipment carrying limits per fighter type.

## Key Concepts

**Fighter archetype**: A `ContentFighter` record that defines a type of fighter from the rulebooks. For example, "Gang Queen" or "Death Maiden" for House Escher. Users select from these archetypes when adding fighters to their lists.

**Fighter category**: A broad classification such as `LEADER`, `CHAMPION`, or `GANGER` that determines the fighter's role in the gang hierarchy. Categories control sorting order, which equipment a fighter can access, and how terminology is displayed.

**Fighter type**: The specific name of the fighter archetype within its category. For example, the category might be `CHAMPION` and the type might be "Death Maiden". The `type` field is the human-readable label users see when selecting a fighter.

**House**: The faction a fighter belongs to (see the Houses documentation area). Fighters are linked to a house, and users can only add fighters from their list's house -- plus fighters from generic houses that are available to everyone.

**Default assignment**: Equipment that comes with a fighter automatically when a user adds that fighter to their list. This represents the standard loadout described in the rulebooks.

**Legacy fighter**: A secondary fighter template that can be attached to certain fighters, representing a previous incarnation or inherited role. Controlled by the `can_take_legacy` and `can_be_legacy` flags.

## Models

### ContentFighter

The primary model in this area. Each record represents one fighter archetype from the game's rulebooks.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | CharField | The fighter's specific name (e.g. "Gang Queen", "Death Maiden", "Juve"). This is the label users see when selecting a fighter. |
| `category` | CharField (choices) | The fighter's role classification. See the full list of categories below. |
| `house` | ForeignKey to `ContentHouse` | The faction this fighter belongs to. Can be null for universal fighters. |
| `base_cost` | IntegerField | The credit cost to hire this fighter. Defaults to 0. |
| `skills` | ManyToMany to `ContentSkill` | Default skills the fighter starts with. |
| `primary_skill_categories` | ManyToMany to `ContentSkillCategory` | Skill trees the fighter can advance in as primary (cheaper XP cost). |
| `secondary_skill_categories` | ManyToMany to `ContentSkillCategory` | Skill trees available as secondary (more expensive XP cost). |
| `rules` | ManyToMany to `ContentRule` | Special rules that apply to this fighter type. |
| `can_take_legacy` | BooleanField | Whether user fighters of this type can have a legacy content fighter attached. Default: false. |
| `can_be_legacy` | BooleanField | Whether this fighter type can be assigned as someone else's legacy content fighter. Default: false. |
| `is_stash` | BooleanField | Whether this fighter represents a gang's stash rather than an actual fighter. Stash fighters only show gear/weapons and must have a `base_cost` of 0. Default: false. |
| `hide_skills` | BooleanField | Whether to hide the skills section on the fighter card in the application. Useful for fighter types that don't use skills. Default: false. |
| `hide_house_restricted_gear` | BooleanField | Whether to hide the house-restricted gear section on the fighter card. Default: false. |

#### Stat Fields

`ContentFighter` has twelve built-in stat fields that represent the traditional Necromunda statline. These are all `CharField` fields with a max length of 12, allowing values like `"4"`, `"2+"`, or `"-"`:

| Field | Verbose Name | Description |
|-------|-------------|-------------|
| `movement` | M | Movement distance |
| `weapon_skill` | WS | Weapon Skill |
| `ballistic_skill` | BS | Ballistic Skill |
| `strength` | S | Strength |
| `toughness` | T | Toughness |
| `wounds` | W | Wounds |
| `initiative` | I | Initiative |
| `attacks` | A | Attacks |
| `leadership` | Ld | Leadership |
| `cool` | Cl | Cool |
| `willpower` | Wil | Willpower |
| `intelligence` | Int | Intelligence |

These fields are stored as strings rather than integers because some stats use dice notation (e.g. `"2+"`) or may be left blank with `"-"`.

There is also a custom statline system (via `ContentStatline`) that allows fighters to use an entirely different set of stats. When a fighter has a custom statline attached, it takes precedence over these built-in fields. This is used for fighter types like vehicles that have different stat categories (e.g. Front Armour, Handling, etc.). For full details on configuring stats and custom statlines, see [Stats & Statlines](stats-and-statlines.md).

#### Fighter Categories

The `category` field uses the `FighterCategoryChoices` enum. Fighters are sorted in lists by category in this order:

| Category | Label | Typical Use |
|----------|-------|-------------|
| `LEADER` | Leader | Gang leader, one per gang |
| `CHAMPION` | Champion | Experienced gang members |
| `PROSPECT` | Prospect | Fighters working toward full membership |
| `SPECIALIST` | Specialist | Fighters with specialised roles |
| `GANGER` | Ganger | Standard gang members |
| `JUVE` | Juve | Young/inexperienced gang members |
| `CREW` | Crew | Vehicle crew members |
| `EXOTIC_BEAST` | Exotic Beast | Companion creatures, added via equipment rather than directly |
| `BRUTE` | Brute | Large hired muscle |
| `HANGER_ON` | Hanger-on | Non-combat gang associates |
| `HIRED_GUN` | Hired Gun | Mercenaries for hire |
| `BOUNTY_HUNTER` | Bounty Hunter | Independent bounty hunters |
| `HOUSE_AGENT` | House Agent | Faction agents |
| `HIVE_SCUM` | Hive Scum | Underhive mercenaries |
| `DRAMATIS_PERSONAE` | Dramatis Personae | Named special characters |
| `ALLY` | Ally | Allied fighters |
| `VEHICLE` | Vehicle | Vehicles, which use a different statline |
| `STASH` | Stash | Special category for the gang's equipment stash |
| `GANG_TERRAIN` | Gang Terrain | Gang-specific terrain pieces |

Fighters with categories `EXOTIC_BEAST`, `VEHICLE`, and `STASH` are excluded from the normal fighter selection dropdown when users add fighters to their lists. Exotic beasts and vehicles are added through equipment assignments instead. Stash fighters are handled automatically.

#### How Base Cost Works

The `base_cost` field defines the default credit cost to hire a fighter of this type. When a user adds a fighter to their list, this is the cost they pay.

However, the cost can be overridden per house using `ContentFighterHouseOverride` records (documented in the Houses area). This is used when a fighter type costs different amounts depending on which house is hiring them. When a house override exists, the application uses `cost_for_house()` to look up the overridden cost for the specific house.

Stash fighters must always have a `base_cost` of 0. The application enforces this through validation.

#### Admin Interface

The `ContentFighter` admin page provides:

- **Search**: by `type`, `category`, and `house__name`
- **Filters**: by `category`, `house`, and `psyker_disciplines__discipline`
- **Autocomplete**: on the `house` field
- **Inlines**:
  - **Fighter Statline**: attach a custom statline type (max one per fighter)
  - **Equipment Category Limits**: set per-category equipment limits (see `ContentFighterEquipmentCategoryLimit` below)
  - **Psyker Discipline Assignments**: assign psyker disciplines to this fighter
  - **Psyker Power Default Assignments**: assign default psyker powers
- **Actions**: "Copy selected to house" -- duplicates selected fighters (with all their equipment lists, default assignments, and relationships) into a different house

### ContentFighterDefaultAssignment

Defines the equipment that comes with a fighter by default. When a user adds a fighter to their list, the application creates equipment assignments based on these records.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `fighter` | ForeignKey to `ContentFighter` | The fighter archetype this default equipment belongs to. |
| `equipment` | ForeignKey to `ContentEquipment` | The piece of equipment included by default. |
| `weapon_profiles_field` | ManyToMany to `ContentWeaponProfile` | Specific weapon profiles to include. If a weapon has multiple profiles (e.g. different firing modes), this controls which non-standard profiles are included by default. Standard profiles (cost 0) are always included. |
| `weapon_accessories_field` | ManyToMany to `ContentWeaponAccessory` | Weapon accessories included with this default assignment. |
| `cost` | IntegerField | Cost override for this assignment. You typically should not change this from 0, as default equipment is included in the fighter's `base_cost`. |

#### How Default Assignments Work

Each `ContentFighterDefaultAssignment` record represents one piece of equipment that a fighter starts with. For example, a Gang Queen might have default assignments for a Laspistol and a Stiletto Knife.

For weapons, the assignment automatically includes all "standard" weapon profiles (those with a cost of 0). If a weapon has additional profiles that cost extra -- for example, special ammunition types -- you can add those specific profiles through the `weapon_profiles_field` to include them in the default loadout.

The `cost` field on a default assignment is typically 0 because the equipment cost is already factored into the fighter's `base_cost`. Only set a non-zero cost if the equipment should add cost beyond the base fighter cost.

#### Admin Interface

The `ContentFighterDefaultAssignment` admin page provides:

- **Search**: by `fighter__type`, `equipment__name`, and `weapon_profiles_field__name`
- **Autocomplete**: on `fighter` and `equipment` fields
- **Actions**: "Copy selected to fighter" -- duplicates selected default assignments to a different fighter

### ContentFighterCategoryTerms

Controls the terminology used in the application for different fighter categories. This allows the application to use context-appropriate language -- for example, referring to a vehicle's "Damage" instead of "Injuries", or calling it "The stash" instead of "This fighter".

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `categories` | MultiSelectField | One or more fighter categories that use these terms. Each category can only appear in one terms record. |
| `singular` | CharField | The singular noun for this type. Default: "Fighter". Examples: "Vehicle", "Beast". |
| `proximal_demonstrative` | CharField | How the application refers to "this" entity. Default: "This fighter". Examples: "The vehicle", "The stash". |
| `injury_singular` | CharField | Singular form for injuries. Default: "Injury". Examples: "Damage", "Glitch". |
| `injury_plural` | CharField | Plural form for injuries. Default: "Injuries". Examples: "Damage". |
| `recovery_singular` | CharField | Singular form for recovery. Default: "Recovery". Examples: "Repair". |

#### When to Use

You only need to create `ContentFighterCategoryTerms` records for categories that use non-standard terminology. If a category should use the defaults ("Fighter", "This fighter", "Injury", etc.), you do not need to create a record for it.

Common examples:

- Vehicles might use "Vehicle" / "The vehicle" / "Damage" / "Damage" / "Repair"
- The stash might use "Stash" / "The stash" with the injury/recovery fields left at defaults since they are not displayed

#### Admin Interface

The `ContentFighterCategoryTerms` admin page shows all fields in the default list view. The `categories` field enforces uniqueness -- each combination of categories can only have one terms record.

### ContentFighterEquipmentCategoryLimit

Sets a maximum number of items from a specific equipment category that a fighter type can carry. Note the distinction: restrictions control which fighter categories can access an equipment category; limits control how many items from that category a fighter can carry. This is used to enforce game rules like "a fighter can carry at most 3 grenades" or "a vehicle can mount at most 2 heavy weapons".

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `fighter` | ForeignKey to `ContentFighter` | The fighter type this limit applies to. |
| `equipment_category` | ForeignKey to `ContentEquipmentCategory` | The equipment category being limited. |
| `limit` | PositiveIntegerField | The maximum number of items from this category the fighter can have. Default: 1. |

#### Validation Rules

- The `fighter` and `equipment_category` combination must be unique -- you can only set one limit per category per fighter.
- The equipment category must have at least one `ContentEquipmentCategoryFighterRestriction` before limits can be set. This means the category must already be configured with fighter category restrictions (see Equipment Categories documentation).

#### Admin Interface

Equipment category limits can be managed in two places:

1. **From the `ContentFighter` admin page**: an inline at the bottom of each fighter's edit page lets you add limits for that fighter. The equipment category dropdown is filtered to only show categories that have fighter restrictions configured.

2. **From the `ContentEquipmentCategory` admin page**: an inline shows all fighter limits for that category. The fighter dropdown is grouped by house for easier navigation.

## How It Works in the Application

### Adding a Fighter to a List

When a user clicks "Add Fighter" on their list, the application shows a form with a dropdown of available fighter types. This dropdown is populated by the `available_for_house()` method, which returns:

- All `ContentFighter` records belonging to the list's house
- All `ContentFighter` records from generic houses (houses with `generic=True`), which represent universally available fighters like Hired Guns
- If the house has `can_hire_any=True`, all fighters from all houses are shown (except stash fighters)

Fighters with categories `EXOTIC_BEAST`, `VEHICLE`, and `STASH` are excluded from this dropdown. Exotic beasts and vehicles are added through equipment assignments, and the stash is managed automatically.

The dropdown groups fighters by house, so the user sees their house's fighters first, followed by generic fighters.

### Fighter Cost Calculation

When a user selects a fighter type, the cost shown is determined by:

1. First checking for a `ContentFighterHouseOverride` matching this fighter and the list's house
2. If no override exists, using the fighter's `base_cost`

In campaign mode, this cost is deducted from the list's available credits when the fighter is hired. If the list does not have enough credits, the hire is rejected.

### Default Equipment

After a fighter is created, the application looks up all `ContentFighterDefaultAssignment` records for that fighter's content type. Each default assignment creates an equipment assignment on the user's `ListFighter`. This means the fighter immediately appears with their standard loadout.

### Fighter Display

On the list view, each fighter card shows:

- The fighter's name (user-assigned) and type (from `ContentFighter.type`)
- The fighter's category label (e.g. "Leader", "Champion")
- The statline -- either from the custom statline system or the built-in stat fields
- Equipment, including default assignments and any user-added gear
- Skills (hidden if `hide_skills` is true)
- House-restricted gear section (hidden if `hide_house_restricted_gear` is true)
- Special rules from the `rules` relationship

### Category Terminology

Throughout the application, when displaying text about a fighter, the system checks for `ContentFighterCategoryTerms` matching the fighter's category. If found, it uses the custom terminology. For example, a vehicle's injury table heading would say "Damage" instead of "Injuries".

### Sorting

Fighters in a list are sorted by category in a defined order: Stash first (if present), then Leaders, Champions, Prospects, Specialists, Gangers, Juves, with other categories in the middle, and Gang Terrain last. Within the same category, fighters are sorted by their type name.

## Common Admin Tasks

### Adding a New Fighter Type

1. Open the Fighters admin page and click "Add Fighter"
2. Fill in the `type` field with the fighter's name as it appears in the rulebooks (e.g. "Gang Queen")
3. Select the appropriate `category` (e.g. `LEADER`)
4. Select the `house` this fighter belongs to
5. Set the `base_cost` in credits
6. Fill in the stat fields (M, WS, BS, S, T, W, I, A, Ld, Cl, Wil, Int) with values from the rulebooks. Use `"-"` or leave blank for stats that don't apply.
7. Add any default skills, primary/secondary skill categories, and rules
8. Set the boolean flags as needed (`can_take_legacy`, `hide_skills`, etc.)
9. Save the fighter

After saving, you can add a custom statline, equipment category limits, and psyker disciplines using the inline forms.

### Setting Up Default Equipment

1. Navigate to the Default Equipment Assignments admin page
2. Click "Add Default Equipment Assignment"
3. Select the `fighter` (the content fighter archetype)
4. Select the `equipment` (the piece of gear or weapon)
5. If the equipment is a weapon with multiple profiles, optionally select the specific `weapon_profiles_field` entries that should be included beyond the standard (free) profiles
6. Leave `cost` at 0 unless you have a specific reason to override it
7. Save

Repeat for each piece of equipment the fighter starts with.

### Copying a Fighter to Another House

Some fighter types exist across multiple houses with the same or similar stats. Rather than creating each one from scratch:

1. Go to the Fighters admin page
2. Select the fighter(s) you want to copy using the checkboxes
3. Choose the "Copy selected to house" action from the dropdown
4. Select the target house
5. Execute the action

This copies the fighter along with all its equipment lists, default assignments, skill categories, rules, and other relationships. You can then edit the copy to adjust any house-specific differences like cost or stat variations.

### Configuring Equipment Category Limits

1. Open the fighter you want to restrict in the Fighters admin page
2. Scroll down to the "Equipment Category Limits" inline section
3. Select an equipment category from the dropdown (only categories with fighter restrictions are shown)
4. Set the `limit` value
5. Save

For example, to limit a Ganger to carrying 3 grenades, you would select the "Grenades" equipment category and set the limit to 3.

### Setting Up Custom Terminology

1. Go to the Fighter Category Terms admin page
2. Click "Add Fighter Category Terms"
3. Select the categories this terminology applies to (e.g. `VEHICLE`)
4. Fill in the custom terms:
   - `singular`: "Vehicle"
   - `proximal_demonstrative`: "The vehicle"
   - `injury_singular`: "Damage"
   - `injury_plural`: "Damage"
   - `recovery_singular`: "Repair"
5. Save

### Creating a Stash Fighter

Each house typically needs one stash fighter to represent the gang's equipment stash:

1. Add a new fighter with `type` set to something like "Stash"
2. Set the `category` to `STASH`
3. Set the `house` to the relevant house
4. Ensure `base_cost` is 0 (this is enforced by validation)
5. Check the `is_stash` flag
6. You can usually check `hide_skills` and `hide_house_restricted_gear` since a stash does not need these sections
7. Stat fields can be left blank
8. Save
