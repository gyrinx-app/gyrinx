# Battle Roles

## Overview

Battle roles let administrators define the roles that gangs can take when they meet in a battle -- for example, the classic **Attacker** and **Defender** split used by most Necromunda scenarios. A list represents a user's collection of fighters (called a "gang" in Necromunda), and when several lists are recorded as participants in a battle, each one can be tagged with a role option that says which side of the fight they were on.

The system is intentionally generic. A **role** is a named axis of choice (like "Attacker/Defender") and its **options** are the mutually exclusive picks within that axis (like "Attacker" and "Defender"). This shape leaves room for scenarios beyond the standard two-sided fight -- a three-way axis, for example, or a scenario-specific role set -- without changing the models.

Battle roles are content data. They are configured through the Django admin and referenced by user-created battles through the `BattleParticipant` through model. The default **Attacker/Defender** role is seeded automatically by migration, so the standard case works out of the box.

## Key Concepts

**Battle Role** -- A named container of participant roles, such as "Attacker/Defender". Roles group together the options a participant can pick from for a given scenario or family of scenarios.

**Battle Role Option** -- A single pickable role within a battle role, such as "Attacker" or "Defender". Options belong to exactly one role and are mutually exclusive within it.

**Participant Role Assignment** -- The link between a gang and the role option they took in a specific battle. This is stored on the `BattleParticipant` through model in the core app; the role option itself lives in the content library.

**Seeded Default** -- The migration ships with a single default role, "Attacker/Defender", containing the "Attacker" and "Defender" options. Deployments start with a working role set even if no administrator has touched the section.

## Models

### `ContentBattleRole`

A named set of battle participant roles.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (max 100), unique | The role's display name, e.g. "Attacker/Defender". Must be unique across all battle roles. |
| `description` | TextField (blank) | Optional explanation shown in the admin, useful for noting which scenarios a role is intended for. |

**Ordering:** Battle roles are ordered alphabetically by `name`.

#### Relationships

- Has many `ContentBattleRoleOption` records through the `options` reverse relation. Deleting a role cascades to delete all of its options.

#### Admin Configuration

The list view shows `name`, `description`, and a count of the role's options. `ContentBattleRoleOption` records are edited inline on the role's detail page with `name` and `description` fields, so an administrator can define a role and its options in one place. The `id`, `created`, and `modified` fields are shown as read-only.

### `ContentBattleRoleOption`

A single role a participant can take within a `ContentBattleRole` -- for example, "Attacker" or "Defender".

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `role` | ForeignKey to `ContentBattleRole` | The parent role this option belongs to. Deleting the role cascades to delete its options. |
| `name` | CharField (max 100) | The option's display name, e.g. "Attacker". Must be unique within its parent role. |
| `description` | TextField (blank) | Optional explanation of what the option means. |

**Ordering:** Options are ordered first by their parent role's `name`, then alphabetically by their own `name`.

**Constraints:** The combination of `role` and `name` must be unique -- you cannot have two options with the same name under the same role.

#### Relationships

- Belongs to a `ContentBattleRole` through the `role` foreign key.
- Referenced by `BattleParticipant.role_option` (in the core app) through the `battle_participants` reverse relation. When an option is deleted, the participant rows keep their history but the role reference is set to `NULL`.

#### Admin Configuration

The list view shows `name`, `role`, and `description`, filterable by `role`. Search covers `name`, `description`, and the parent role's `name`. Options can be created inline from their parent role or through their own admin list.

## How It Works in the Application

### Assigning roles to a battle

When a user creates a battle inside an in-progress campaign, participants are added as gangs first and tagged with roles afterwards. Each `BattleParticipant` (a through row between the battle and a participating `List`) carries an optional `role_option` foreign key pointing at a `ContentBattleRoleOption`. Leaving the field blank means the gang has no role assigned for that battle.

The battle owner or a campaign arbitrator opens the **Assign roles** page from the battle view to set or change these role options. All options across all battle roles are available, so a scenario that expects a non-default role picks up admin-defined options without further wiring.

### Grouping participants on the battle page

The battle page groups its participants by role option so an "Attacker vs Defender" battle renders each side under its own heading. Gangs without a role assigned are shown last under an unassigned group. The grouping is stable: participants are ordered by role option name, then by creation time, so the layout does not shuffle between visits.

### Default seeding

The `0179_seed_battle_roles` migration creates the "Attacker/Defender" role and its two options on first migrate. This runs automatically, so administrators do not need to configure anything to record standard scenarios. Reversing the migration removes the seeded rows.

## Common Admin Tasks

### Creating a new battle role

1. Open the Battle Roles section in the admin.
2. Click "Add Battle Role".
3. Enter the role `name` (e.g. "Ambush").
4. Optionally fill in the `description` to note which scenarios use this role.
5. In the Battle Role Options inline section, add each option with a `name` and optional `description` (e.g. "Ambusher" and "Ambushed").
6. Save the role.

The new role's options are immediately available on the **Assign roles** page for any battle.

### Adding an option to an existing role

1. Open the Battle Roles section and click the role you want to extend.
2. Scroll to the inline options section.
3. Add a new row with the option `name` and optional `description`.
4. Save.

The unique constraint prevents adding an option whose name already exists on that role. Rename the existing one first if you need to replace it.

### Renaming an option

1. Open the option through either the Battle Role Options list or the parent role's inline section.
2. Change the `name` and save.

Existing `BattleParticipant` rows keep their reference to the option by ID, so the rename is reflected everywhere the role option is displayed. Historical rows in the battle audit trail continue to point at the same option.

### Removing an option

Deleting an option through the admin sets `role_option` to `NULL` on every `BattleParticipant` that was using it. The battle history is preserved, but affected gangs will render under the unassigned group until a new role option is picked. Prefer to rename an option to something similar rather than delete it when past battles reference it.

### Removing the default Attacker/Defender role

The seeded role behaves like any other content and can be removed if a deployment does not want it. Deleting the role cascades to its options, which in turn nulls out `role_option` on any `BattleParticipant` rows that referenced them. Re-running the seed migration would recreate the role, so archive or delete the migration if you truly want the role gone.
