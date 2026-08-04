# Skills, Rules & Psyker Powers

## Overview

Skills, rules, and psyker powers are the three categories of special abilities that define what a fighter can do beyond their base statistics and equipment. In Gyrinx, a list represents a user's collection of fighters (called a "gang" in Necromunda). Together, these abilities capture the narrative and mechanical identity of each fighter archetype in the content library.

Skills represent trained abilities grouped into themed categories (called skill trees) such as Agility, Brawn, or Combat. Rules represent special rules and abilities inherent to certain fighter types -- things like "Psyker", "Gang Fighter", or faction-specific traits. Psyker powers are supernatural abilities available only to fighters with one of the psyker rules, organised into thematic disciplines.

Content configured in this area flows directly into what users see on their fighter cards. When a user views a fighter in their list, the card displays the fighter's rules, skills, and (for psykers) powers. Users can also add, remove, enable, or disable these abilities on their own fighters, with the content library providing both the defaults and the full catalogue of available options.

## Key Concepts

**Skill tree** -- A category of skills (e.g., Agility, Brawn, Combat). Referred to as "Skill Tree" in the admin interface. Each skill belongs to exactly one tree.

**Primary skill tree** -- A skill tree that a fighter type has full access to. During advancement, primary skills are typically easier or cheaper to acquire.

**Secondary skill tree** -- A skill tree that a fighter type has limited access to. Secondary skills are typically harder to acquire during advancement.

**Default skill** -- A skill that comes pre-assigned to a fighter type by the content library. Users can disable but not permanently remove default skills.

**Rule** -- A named special ability or trait assigned to a fighter type. Rules are simpler than skills -- they have no category hierarchy, just a name.

**Psyker** -- A fighter who possesses one of the psyker rules ("Psyker", "Non-Sanctioned Psyker", or "Sanctioned Psyker"). Psyker status is derived automatically from the fighter's rules, not set as a separate flag.

**Discipline** -- A thematic grouping of psyker powers, such as Telekinesis or Pyromancy.

**Generic discipline** -- A discipline that any psyker can access, regardless of their fighter type. Generic disciplines cannot be directly assigned to a `ContentFighter` -- they are available to all psykers automatically.

## Models

### `ContentSkillCategory` (Skill Tree)

Represents a category or tree of skills. Skill trees organise individual skills into themed groups and determine which fighter types can access them.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (unique) | The name of the skill tree (e.g., "Agility", "Brawn", "Combat"). |
| `restricted` | BooleanField | If checked, this skill tree is only available to specific lists. Unrestricted trees are available to all fighters. |

**Admin interface:** The admin page for a skill tree shows its skills as an inline table, so you can manage the tree and all its skills in one place. You can search by name and see the `restricted` flag in the list view.

### `ContentSkill`

Represents an individual skill within a skill tree.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField | The name of the skill (e.g., "Catfall", "Iron Jaw"). |
| `category` | ForeignKey to `ContentSkillCategory` | The skill tree this skill belongs to. Displayed as "tree" in the admin. |

**Constraints:** A skill name must be unique within its tree (`unique_together` on `name` and `category`).

**Admin interface:** Skills can be searched by name or tree name, and filtered by tree. Skills are also shown inline when editing a skill tree.

### `ContentRule`

Represents a named special rule or ability from the game system.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField | The name of the rule (e.g., "Psyker", "Gang Fighter", "Mounted"). |

Rules are intentionally simple -- just a name. The game semantics of each rule are understood by the players and the application; the content library just needs to track which rules exist and which fighters have them.

Certain rule names have special significance in the application. The names `Psyker`, `Non-Sanctioned Psyker`, and `Sanctioned Psyker` (case-insensitive) determine whether a fighter is considered a psyker, which unlocks the psyker powers section of their fighter card.

**Admin interface:** Rules have a simple admin with search by name.

### `ContentPsykerDiscipline`

Represents a discipline (themed grouping) of psyker powers.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (unique) | The name of the discipline (e.g., "Telekinesis", "Pyromancy"). |
| `generic` | BooleanField | If checked, this discipline is available to any psyker fighter, not just those with an explicit assignment. |

**The `generic` flag:** Generic disciplines serve as a shared pool of powers available to all psykers. Because they are universally available, they cannot be assigned to individual fighter types via `ContentFighterPsykerDisciplineAssignment` -- attempting to do so will raise a validation error. Non-generic disciplines must be explicitly assigned to fighter types that should have access to them.

**Admin interface:** Disciplines are listed with search by name and a filter on the `generic` flag. Editing a discipline shows its powers as an inline table.

### `ContentPsykerPower`

Represents a specific power within a psyker discipline.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField | The name of the power. |
| `discipline` | ForeignKey to `ContentPsykerDiscipline` | The discipline this power belongs to. |

**Constraints:** A power name must be unique within its discipline (`unique_together` on `name` and `discipline`).

**Admin interface:** Powers are primarily managed inline when editing their parent discipline. They can also be managed via the standalone admin, which groups powers by discipline name in the selection dropdown.

### `ContentFighterPsykerDisciplineAssignment`

Links a `ContentFighter` to a `ContentPsykerDiscipline`, indicating that fighters of this type have access to powers from this discipline.

| Field | Type | Description |
|-------|------|-------------|
| `fighter` | ForeignKey to `ContentFighter` | The fighter type receiving discipline access. |
| `discipline` | ForeignKey to `ContentPsykerDiscipline` | The discipline being granted. |

**Validation rules:**

- You cannot assign a generic discipline to a fighter. Generic disciplines are automatically available to all psykers and should not be assigned individually. Attempting this raises a validation error.

**Constraints:** Each fighter-discipline combination must be unique (`unique_together` on `fighter` and `discipline`).

**Admin interface:** Discipline assignments are managed as inline rows when editing a `ContentFighter`. They can also be managed through a standalone admin page with autocomplete for both fighter and discipline, plus search and filter capabilities.

### `ContentFighterPsykerPowerDefaultAssignment`

Assigns a specific psyker power as a default for a fighter type. Default powers are automatically available to users' fighters of this type.

| Field | Type | Description |
|-------|------|-------------|
| `fighter` | ForeignKey to `ContentFighter` | The fighter type that starts with this power. |
| `psyker_power` | ForeignKey to `ContentPsykerPower` | The power assigned by default. |

**Validation rules:**

- You cannot assign a default power to a non-psyker fighter. The fighter must have one of the psyker rules for this assignment to be valid.

**Constraints:** Each fighter-power combination must be unique (`unique_together` on `fighter` and `psyker_power`).

**Admin interface:** Default power assignments are managed as inline rows when editing a `ContentFighter`, with powers grouped by discipline name in the dropdown. They can also be managed through a standalone admin page with search and filter by fighter type and discipline.

## Fighter Relationships to Skills, Rules & Powers

The `ContentFighter` model ties all of these systems together through several fields:

| Field | Type | Description |
|-------|------|-------------|
| `skills` | ManyToManyField to `ContentSkill` | Default skills that come with this fighter type (labelled "Default Skills" in the admin). |
| `primary_skill_categories` | ManyToManyField to `ContentSkillCategory` | Skill trees where this fighter has primary access (labelled "Primary Skill Trees"). |
| `secondary_skill_categories` | ManyToManyField to `ContentSkillCategory` | Skill trees where this fighter has secondary access (labelled "Secondary Skill Trees"). |
| `rules` | ManyToManyField to `ContentRule` | Special rules assigned to this fighter type. |
| `hide_skills` | BooleanField | If checked, the skills section is hidden on the fighter card. Useful for fighter types where skills are not relevant, such as exotic beasts or similar. |

**Psyker detection:** A fighter is considered a psyker if any of its rules (case-insensitive) match "Psyker", "Non-Sanctioned Psyker", or "Sanctioned Psyker". This check is performed automatically -- there is no separate "is psyker" checkbox.

## How It Works in the Application

### Fighter Cards

When a user views a fighter in their list, the fighter card displays:

- **Rules** -- Always shown. Lists the fighter's rules, including defaults from the content library, custom user-added rules, and any rules added or removed by equipment modifiers. Users with edit access see an "Edit" or "Add" link to manage rules.
- **Skills** -- Shown unless the `hide_skills` flag is set on the fighter's `ContentFighter`. Lists default skills and user-added skills, with equipment modifiers applied. Users with edit access can add or edit skills.
- **Powers** -- Only shown if the fighter is a psyker. Lists default powers and user-assigned powers, with a link to manage them.

### Editing Skills

The skills editing page for a fighter shows three sections:

1. **Default Skills** -- Skills that come from the `ContentFighter` template. Users can disable these (shown with strikethrough styling) or re-enable them, but cannot permanently remove them.
2. **User-added Skills** -- Skills the user has manually added. These can be fully removed.
3. **Skill Categories** -- A browsable grid of all available skill trees and their skills. Each tree is labelled as "Primary" or "Secondary" based on the fighter's content configuration. The page supports filtering by primary/secondary status and searching by skill name.

### Editing Rules

The rules editing page shows:

1. **Default Rules** -- Rules from the `ContentFighter` template. These can be disabled or re-enabled.
2. **User-added Rules** -- Rules manually added by the user, which can be removed.
3. **Add Rules** -- A searchable, paginated list of all available rules that can be added to the fighter.

### Editing Psyker Powers

Only available for fighters with a psyker rule. The powers editing page shows:

1. **Current Psyker Powers** -- All currently assigned powers, with each marked as "Default" if it comes from the content library. Default powers can be disabled; user-added powers can be removed.
2. **Available Disciplines** -- A browsable grid of disciplines and their powers. This includes both the fighter's explicitly assigned disciplines and any generic disciplines. Powers can be searched and added from here.

### Skill Tree Access and Equipment Modifiers

The skill trees a fighter can access are not fixed -- they can be modified by equipment. The modifier system includes `ContentModSkillTreeAccess`, which can add or remove primary/secondary skill tree access, and `ContentModPsykerDisciplineAccess`, which can add or remove psyker discipline access. This means equipping certain items can grant a fighter access to new skill trees or psyker disciplines. See [Modifiers](modifiers.md) for details on how `ContentModSkillTreeAccess` and `ContentModPsykerDisciplineAccess` work.

Similarly, `ContentModFighterRule` can add or remove rules from a fighter via equipment, and `ContentModFighterSkill` can add or remove specific skills. These modifiers are applied automatically when the user equips or unequips items.

## Common Admin Tasks

### Adding a new skill tree

1. Open the Skill Trees admin.
2. Click "Add Skill Tree".
3. Enter the tree name (e.g., "Savant").
4. Set `restricted` if this tree should only be available to certain lists.
5. Save, then use the inline table to add individual skills to the tree.

### Assigning skill trees to a fighter type

1. Open the Fighters admin and find the fighter type.
2. In the "Primary Skill Trees" and "Secondary Skill Trees" fields, select the appropriate trees.
3. Save. Users creating fighters of this type will now see those trees labelled as primary or secondary on the skills editing page.

### Adding default skills to a fighter type

1. Open the Fighters admin and find the fighter type.
2. In the "Default Skills" field, select the skills that should come pre-assigned.
3. Save. These skills will appear automatically on every user's fighter of this type.

### Adding a new rule

1. Open the Rules admin.
2. Click "Add Rule".
3. Enter the rule name exactly as it appears in the game system.
4. Save. The rule is now available for assignment to fighter types or for users to add to their fighters.

Be careful with the names "Psyker", "Non-Sanctioned Psyker", and "Sanctioned Psyker" -- assigning any of these rules to a fighter type causes the application to treat that fighter as a psyker, which enables the powers section on the fighter card.

### Setting up a new psyker discipline

1. Open the Psyker Disciplines admin.
2. Click "Add Psyker Discipline".
3. Enter the discipline name.
4. Set `generic` if this discipline should be available to all psykers. Leave unchecked if it should only be available to specifically assigned fighter types.
5. Save, then use the inline table to add individual powers to the discipline.

### Assigning a discipline to a fighter type

1. Open the Fighters admin and find the fighter type.
2. In the inline section "Fighter Psyker Disciplines", add a new row and select the discipline.
3. You cannot assign generic disciplines here -- they are available to all psykers automatically.
4. Save.

### Assigning default psyker powers to a fighter type

1. Open the Fighters admin and find the fighter type.
2. The fighter must have a psyker rule (e.g., "Psyker") in its rules. If it does not, you will get a validation error.
3. In the inline section for default psyker power assignments, add rows and select powers. Powers are grouped by discipline in the dropdown.
4. Save. Users' fighters of this type will start with these powers pre-assigned.

### Hiding the skills section for a fighter type

Some fighter types (such as exotic beasts or vehicles) do not use skills. To hide the skills section from their fighter cards:

1. Open the Fighters admin and find the fighter type.
2. Check the `hide_skills` flag.
3. Save. The skills row will no longer appear on fighter cards of this type.
