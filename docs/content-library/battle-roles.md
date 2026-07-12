# Battle Roles

## Overview

Battle roles are named participant roles that gangs take when they meet on the tabletop -- most commonly the classic "Attacker" and "Defender" pairing. The content library defines what roles are available and what options each role offers; campaign play then tags each participating gang with one of those options when a battle is set up. A list represents a user's collection of fighters (called a "gang" in Necromunda).

Roles are stored generically as a **role container** with a set of **role options**, so the same models can hold future asymmetric scenario roles (e.g. "Ambusher/Ambushed", "Rescuer/Rescued") without further schema changes. The default `Attacker/Defender` role and its two options are seeded automatically by a data migration.

Roles are picked at the battle level, not on the list itself. The same gang can be an Attacker in one battle and a Defender in the next, and role assignments are not carried over when a list is cloned.

## Key Concepts

**Battle Role** -- A named container for a set of mutually exclusive participant roles, such as "Attacker/Defender". Each role has one or more options.

**Battle Role Option** -- A single role a participant can take within a battle role, e.g. "Attacker" or "Defender". Options are the values actually assigned to a gang for a given battle.

**Battle Participant** -- The through-model row that links a `Battle` to a `List` in the core app. Each participant carries an optional `role_option` naming the role that gang plays in this battle. See [Fighters & Fighter Types](fighters.md) for how gangs and fighters are structured.

## Models

### `ContentBattleRole`

A named container for a set of mutually exclusive battle participant roles.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (max 100, unique) | The role's display name, such as "Attacker/Defender". Must be unique across all roles. |
| `description` | TextField (blank) | Optional description of the role and when it applies. |

**Ordering:** Roles are ordered alphabetically by `name`.

#### Relationships

- Has many `ContentBattleRoleOption` records through the `options` reverse relation.

#### Admin Interface

The list view shows `name`, `description`, and a count of the options attached to the role. The detail page includes an inline tabular section for editing each option's `name` and `description` directly on the role. Roles are searchable by `name` and `description`.

### `ContentBattleRoleOption`

A single option within a role. This is what actually gets assigned to a participating gang.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `role` | ForeignKey to `ContentBattleRole` | The parent role this option belongs to. Deleting the role cascades to delete its options. |
| `name` | CharField (max 100) | The option's display name, such as "Attacker" or "Defender". Must be unique within its parent role. |
| `description` | TextField (blank) | Optional description of what the option represents in the game. |

**Ordering:** Options are ordered by their parent role's name and then alphabetically by their own name.

**Constraints:** The combination of `role` and `name` must be unique -- you cannot have two options with the same name under the same role.

#### Relationships

- Belongs to a `ContentBattleRole` through `role`.
- Referenced by `BattleParticipant.role_option` in the core app through the `battle_participants` reverse relation. Deleting an option sets the referring participant rows' `role_option` to `NULL` rather than cascading, so existing battles keep their participants and simply show them as unassigned.

#### Admin Interface

Options can be managed in two ways. You can edit them inline on the parent `ContentBattleRole` page, where they appear as a tabular inline with `name` and `description` fields. You can also manage them through their own admin list, which shows name, parent role, and description, with search across the option name, description, and parent role name, and filtering by parent role.

## How It Works in the Application

### Seeded content

The migration that adds these models also seeds a default `Attacker/Defender` role with the options `Attacker` and `Defender`. Existing installations gain this content automatically; no admin action is required for the standard case. The seed is idempotent -- it uses `get_or_create`, so re-running the migration will not create duplicates.

### Assigning roles to a battle

Battles are a campaign feature. When a battle is created, its participants are added without a role (the participant row's `role_option` is `NULL`). Battle managers -- the battle owner, the campaign owner, and the owner of any participating gang -- then open the battle's **Assign roles** page (linked from the battle page) and pick an option for each gang. Saving persists the choice on the through-model row via `BattleParticipant.role_option`. Choosing "No role" clears an existing assignment.

### Display

The battle page groups its participants by their role option. Groups are ordered by option name, and any gangs without a role are shown last under an unassigned group. Participants inside each group are ordered by when they were added to the battle.

### Scope

- Roles are per-battle, not per-list. The same gang can hold a different role in every battle it plays.
- Role assignments are not part of the list clone flow. Cloning a gang (e.g. at campaign start) does not copy any battle participations.
- Winners are still tracked separately on the battle via `Battle.winners`; the role a gang held has no automatic bearing on who won.

## Common Admin Tasks

### Adding a new option to an existing role

1. Content → Battle Roles → open the role you want to extend (e.g. "Attacker/Defender").
2. In the inline options section, add a new row with a `name` (must be unique within the role) and an optional `description`.
3. Save the role.

The new option is immediately available on every battle's Assign roles page.

### Creating a new role type

1. Content → Battle Roles → Add.
2. Enter a `name` (e.g. "Ambusher/Ambushed") and an optional `description`.
3. Save.
4. Open the newly-created role and add each option (e.g. "Ambusher", "Ambushed") using the inline options section.

Once saved, the new options appear alongside the existing roles in the Assign roles picker. A gang can only hold one option at a time, so it is up to the players which role they pick per battle.

### Renaming or describing an existing option

1. Content → Battle Roles → open the parent role.
2. In the inline options section, edit the option's `name` or `description`.
3. Save.

The change is picked up wherever the option is displayed, including on battles that already reference it.

### Removing an option that is no longer needed

1. Content → Battle Roles → open the parent role.
2. Delete the option from the inline options section (or from the standalone Battle Role Options list).
3. Save.

Deleting an option does not delete any `BattleParticipant` rows that referenced it. Those participants are kept, with their `role_option` set to `NULL`, so they render in the unassigned group on their battle page.
