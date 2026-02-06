# Injuries

## Overview

Injuries represent lasting harm that fighters sustain during campaign play. When a fighter suffers a serious wound in a battle, the result is tracked as an injury on their fighter card. These injuries persist across battles and can affect a fighter's stats, availability, and long-term viability in a campaign. A list represents a user's collection of fighters (called a "gang" in Necromunda).

The injury system in the content library defines what injuries exist, how they are organized into groups, and what happens to a fighter when they receive each type of injury. Content administrators configure injury groups and individual injuries here; users then apply those injuries to their fighters during campaign play through the application's injury management interface.

Injuries are a campaign-mode feature. They cannot be added to fighters outside of campaign mode. Each injury can optionally carry stat modifiers that change a fighter's profile for as long as the injury is active, reflecting the lasting mechanical consequences of serious wounds.

## Key Concepts

**Injury Group** -- A named collection of related injuries. Groups control which fighter categories and houses can receive the injuries they contain. For example, a "Vehicle Damage" group might be restricted to vehicles only, while "Lasting Injuries" applies to most fighter types.

**Injury** -- A specific type of lasting harm, such as "Humiliated", "Eye Injury", or "Spinal Injury". Each injury belongs to a group and has a default outcome that determines what state the fighter should be placed into when the injury is applied.

**Default Outcome** -- The fighter state that an injury suggests when it is applied. For example, a minor injury might leave the fighter `Active`, while a critical injury might put them into `Convalescence` or mark them as `Dead`. The user can override this suggestion when adding the injury.

**Modifier** -- A stat modification attached to an injury. When a fighter has an active injury with modifiers, those modifiers are applied to the fighter's statline. For example, a leg injury might worsen the fighter's Movement stat.

**Fighter State** -- The availability status of a fighter in campaign mode. Injuries drive state changes, but the state is tracked on the fighter itself, not on the injury. See the "Fighter States and Availability" section below for details.

## Models

### `ContentInjuryGroup`

Represents a group of related injuries. Injury groups serve two purposes: they organize injuries into logical categories for display, and they control which fighters can receive the injuries in the group through category and house restrictions.

#### Fields

| Field | Type | Description |
|---|---|---|
| `name` | CharField (max 100, unique) | The display name for this group, such as "Lasting Injuries" or "Vehicle Damage". |
| `description` | TextField (blank) | Optional description of the group. |
| `restricted_to` | MultiSelectField | If set, only fighters with one of the selected categories can receive injuries from this group. When blank, all fighter categories are eligible. |
| `unavailable_to` | MultiSelectField | If set, fighters with any of the selected categories cannot receive injuries from this group, even if they match `restricted_to`. |
| `restricted_to_house` | ManyToManyField to `ContentHouse` | If set, only fighters belonging to one of the selected houses can receive injuries from this group. When empty, no house restriction applies. |

#### How Restrictions Work

The `restricted_to` and `unavailable_to` fields use the fighter category system. The available categories include Leader, Champion, Ganger, Juve, Crew, Exotic Beast, Hanger-on, Brute, Hired Gun, Bounty Hunter, House Agent, Hive Scum, Dramatis Personae, Prospect, Specialist, Stash, Vehicle, Ally, and Gang Terrain.

The restriction logic follows this order:

1. If `restricted_to` is set, the fighter's category must be in that list.
2. If `unavailable_to` is set, the fighter's category must not be in that list. This takes effect even if the category passes the `restricted_to` check.
3. If `restricted_to_house` has any entries, the fighter's house must be one of them.

When all restriction fields are left blank, the group's injuries are available to all fighters.

#### Admin Interface

The Injury Group admin page displays a list of groups with columns for name, description, restricted houses, restricted fighter categories, and unavailable fighter categories. Each group's detail page includes an inline table of all injuries belonging to that group, letting you manage injuries directly from the group page.

### `ContentInjury`

Represents an individual injury type that can be applied to a fighter.

#### Fields

| Field | Type | Description |
|---|---|---|
| `name` | CharField (max 255, unique) | The name of the injury, such as "Humiliated", "Eye Injury", or "Spinal Injury". |
| `description` | TextField (blank) | A text description of the injury and its effects. This is shown to users when they view injury details. |
| `phase` | CharField (labelled "Default Outcome") | The suggested fighter state when this injury is applied. Uses the `ContentInjuryDefaultOutcome` choices (see below). Defaults to `no_change`. |
| `injury_group` | ForeignKey to `ContentInjuryGroup` (nullable) | The group this injury belongs to. This determines which fighters can receive the injury based on the group's restrictions. |
| `group` | CharField (max 100, blank) | **Deprecated:** The `group` CharField is deprecated in favour of the `injury_group` ForeignKey. Do not use the `group` field for new injuries. |
| `modifiers` | ManyToManyField to `ContentMod` | Stat modifiers that are applied to a fighter's profile when this injury is active. See "Injury Modifiers and Stats" below. |

#### Admin Interface

The Injury admin page supports searching by `name` and `description`, and filtering by `phase` (Default Outcome). The list view shows columns for name, description, default outcome, and modifier count.

Each injury's detail page includes an inline section for managing the modifiers associated with that injury. You can add, edit, or remove modifiers directly from the injury detail page.

### `ContentInjuryDefaultOutcome`

An enumeration of the possible default outcomes for injuries. These values map to the fighter states used in campaign mode.

| Value | Display Name | Meaning |
|---|---|---|
| `no_change` | No Change | The injury does not suggest changing the fighter's current state. |
| `active` | Active | The fighter remains available for battles. |
| `recovery` | Recovery | The fighter is temporarily unavailable and must recover before participating in battles. |
| `convalescence` | Convalescence | The fighter is out for an extended period and cannot participate in battles. |
| `dead` | Dead | The fighter is killed. Dead fighters cannot participate in battles and their equipment is hidden from the fighter card. |
| `in_repair` | In Repair | Used for vehicles. The vehicle is damaged and must be repaired before it can be used again. |

When a user adds an injury to a fighter, the form automatically suggests the injury's default outcome as the new fighter state. The user can override this selection before confirming.

## How It Works in the Application

### Fighter States and Availability

Every fighter in campaign mode has an `injury_state` field that tracks their current availability. This state determines whether the fighter can participate in battles:

- **Active** -- The fighter is available and can participate in battles.
- **Recovery** and **Convalescence** -- The fighter is temporarily unavailable and cannot participate.
- **Dead** -- The fighter is permanently out. Dead fighters remain on the list but their wargear is hidden from the fighter card.
- **In Repair** -- Vehicles only. The vehicle is out of action until repaired.

The fighter's state is displayed as a colour-coded badge on their card: green for Active, yellow for Recovery/Convalescence/In Repair, and red for Dead.

### Adding an Injury

When a user (the list owner or the campaign arbitrator) adds an injury to a fighter, the application:

1. Presents a form showing only the injuries available to that fighter, filtered by the fighter's category and house against the injury group restrictions.
2. Groups the available injuries by their injury group in the dropdown.
3. Pre-selects the fighter state based on the chosen injury's default outcome (unless the outcome is `no_change`).
4. Creates a `ListFighterInjury` record linking the fighter to the content injury, along with the date and any notes.
5. Updates the fighter's `injury_state` to the selected state.
6. Logs the event to the campaign action log.

If the selected state is Dead, the user is redirected to a kill confirmation page.

### Injury Modifiers and Stats

When an injury has modifiers attached, those modifiers are applied to the fighter's calculated statline in campaign mode. For full details on how modifiers work and the different modifier types, see [Modifiers](modifiers.md). The modifier system supports several types of changes relevant to injuries:

- **Fighter Stat Modifiers** (`ContentModFighterStat`) -- Change a specific stat value. For example, an eye injury might worsen Ballistic Skill by 1, or a leg wound might worsen Movement.
- **Fighter Rule Modifiers** (`ContentModFighterRule`) -- Add or remove rules from the fighter.

Modifiers use a mode of `improve`, `worsen`, or `set` to determine how they change the stat value. The modifiers are applied in real time: as soon as the injury is added to the fighter, the stat changes appear on the fighter card. When the injury is removed, the modifiers are removed as well.

### Removing an Injury

Users can remove injuries from fighters when they recover. Removing an injury:

1. Deletes the `ListFighterInjury` record.
2. If the fighter has no remaining injuries, automatically resets the fighter's state to Active.
3. Logs the recovery to the campaign action log.
4. Immediately removes any stat modifiers that were applied by the injury.

### Injuries on Fighter Cards

In campaign mode, fighter cards display an "Injuries" row in the statline area. This row lists the names of all active injuries. If the list owner or campaign arbitrator is viewing the card, an "Edit" link appears next to the injuries, or an "Add" link if the fighter has no injuries yet. Outside of campaign mode, the injuries row is not shown.

### Custom Terminology

Different fighter categories may use different terminology for injuries. For example, vehicles use "Damage" instead of "Injury". The application handles this through the `term_injury_singular` and `term_injury_plural` properties on fighters, which pull from category-specific term configuration. All templates use these dynamic terms rather than hard-coding "Injury" or "Injuries".

## Common Admin Tasks

### Creating a New Injury Group

1. Go to the Injury Groups section in the admin.
2. Click "Add Injury Group".
3. Enter the group name (for example, "Lasting Injuries" or "Vehicle Lasting Damage").
4. Optionally add a description.
5. If this group should only apply to certain fighter types, select the appropriate categories in `restricted_to`. For vehicle damage, you would select "Vehicle".
6. If this group should be excluded from certain fighter types, select those categories in `unavailable_to`. For example, you might exclude "Exotic Beast" from standard lasting injuries.
7. If the group is house-specific, select the relevant houses in `restricted_to_house`.
8. Save the group.

### Adding Injuries to a Group

You can add injuries directly from the injury group's detail page using the inline injury table at the bottom.

1. Open the injury group.
2. In the inline injuries section, fill in the name, description, and default outcome for each injury.
3. Save the group.

Alternatively, you can create injuries individually through the Injuries admin section and assign them to a group using the `injury_group` dropdown.

### Attaching Modifiers to an Injury

1. Go to the Injuries section in the admin and open the injury you want to modify.
2. In the "Modifiers" inline section, click "Add another Modifier".
3. Select the appropriate modifier. These are shared `ContentMod` objects, so you need to have already created the modifier (for example, a Fighter Stat Modifier that worsens Movement by 1). See the Modifiers documentation for details on creating modifiers.
4. Save the injury.

The modifier will now be applied to any fighter who receives this injury during campaign play.

### Setting Up Vehicle Damage

Vehicles use a separate set of injuries with different terminology. To configure vehicle damage:

1. Create an injury group named something like "Vehicle Lasting Damage".
2. Set `restricted_to` to "Vehicle" so only vehicles can receive these injuries.
3. Add injuries with appropriate default outcomes. Use `in_repair` as the default outcome for damage that takes the vehicle out of action.
4. Attach any relevant stat modifiers (for example, worsening the vehicle's Handling or Movement).

### Migrating from the Deprecated Group Field

The `group` CharField on `ContentInjury` is a legacy text field that stored the group name as plain text. It has been replaced by the `injury_group` ForeignKey, which provides a proper relationship to `ContentInjuryGroup`.

If you encounter injuries that have a value in the `group` text field but no `injury_group` set, you should:

1. Find or create the appropriate `ContentInjuryGroup`.
2. Set the `injury_group` ForeignKey on the injury to point to that group.
3. The `group` text field can be left as-is; it is retained for backward compatibility but is not used by the application logic.
