# Houses & Factions

Houses are the core organisational unit in the Gyrinx content library. A list represents a user's collection of fighters (called a "gang" in Necromunda). Every list a user creates is associated with exactly one house, and that house determines which fighters can be hired, which equipment is available, and which skill categories are accessible. Houses represent the major factions from the Necromunda tabletop game -- Escher, Goliath, Orlock, Cawdor, Van Saar, Delaque, and many others.

When a user creates a new list, they choose a house. From that point on, the house acts as a filter across the entire application: the fighters shown in the "add fighter" form, the equipment lists available on weapon and gear pages, and the skill trees offered during advancement are all determined by the house. Getting house configuration right is essential because it shapes the entire user experience of building and managing a list.

The content library also supports house-level cost overrides for individual fighters through the `ContentFighterHouseOverride` model. This lets you set a different price for the same fighter type depending on which house is hiring them -- a common pattern in Necromunda where hired guns and hangers-on cost different amounts for different factions.

## Key Concepts

**House** -- A faction or house type (e.g., House Escher, House Goliath, Underhive Outcasts). Each user list belongs to exactly one house.

**Generic house** -- A special category of house whose fighters are available to all other houses. Used for mercenaries, hired guns, hangers-on, and other faction-neutral fighter types. Generic houses cannot be selected as the primary house when creating a list.

**Legacy house** -- An older or deprecated faction that still appears in the list creation form but is grouped separately under "Legacy House" to distinguish it from current factions.

**House override** -- A per-house cost adjustment for a specific fighter type. When a fighter has a house override, the overridden cost is used instead of the fighter's base cost whenever that fighter appears in a list belonging to the specified house.

**Gang-wide skills** -- An opt-in mode for a house in which the gang as a whole picks a ranked set of skill trees at list level, and each fighter then derives its primary/secondary skill trees from those picks by rank rather than from the fighter template's own primary/secondary skill tree fields. Enabled per-house and governed by per-house "rank rules" (see [`ContentHouseSkillRankAccess`](#contenthouseskillrankaccess)).

## Models

### ContentHouse

`ContentHouse` represents a faction or house that fighters can belong to. It is the central model that ties together fighters, equipment access, and skill trees.

| Field | Type | Description |
|---|---|---|
| `name` | CharField | The display name of the house (e.g., "House Escher", "Underhive Outcasts"). Indexed for search. |
| `generic` | BooleanField | When checked, fighters belonging to this house are available to lists of any other house. Generic houses cannot be selected as a primary house during list creation. Defaults to `false`. |
| `legacy` | BooleanField | When checked, marks this house as a legacy/older faction. Legacy houses are grouped separately in the list creation form under a "Legacy House" heading. Defaults to `false`. |
| `can_hire_any` | BooleanField | When checked, lists belonging to this house can hire any fighter from any house (except stash fighters). Used for factions like Underhive Outcasts that have unrestricted recruitment. Defaults to `false`. |
| `can_buy_any` | BooleanField | When checked, lists belonging to this house can buy any equipment from any equipment list and the Trading Post. Equipment pages default to showing all available equipment rather than the fighter's own equipment list. Defaults to `false`. |
| `skill_categories` | ManyToManyField | Links to `ContentSkillCategory` records. These are the "Unique Skill Categories" available to fighters in this house. They appear as a separate section on the skill advancement page alongside the standard (non-restricted) skill categories. |
| `gang_wide_skills` | BooleanField (default `False`) | When checked, gangs of this house pick a ranked set of skill trees at list level; those picks become each fighter's primary/secondary skill trees by rank (via the house's [skill rank rules](#contenthouseskillrankaccess)). The fighter template's own primary/secondary skill tree fields are ignored in this mode. |
| `gang_skill_tree_count` | PositiveSmallIntegerField (default `0`) | How many skill trees the gang ranks (e.g. 4 for Venators). Only consulted when `gang_wide_skills` is checked. |
| `gang_skill_tree_choices` | ManyToManyField | Optional pool of skill trees a gang may pick from (labelled "Gang Skill Tree Pool"). Leave empty to allow any non-restricted skill tree -- restricted trees can still be revealed in the picker via the `?include_restricted=1` filter. |

**Relationships:**

- Each `ContentFighter` has a foreign key to `ContentHouse`, establishing which house a fighter template belongs to.
- Each user `List` has a foreign key to `ContentHouse`, establishing the house for the entire list.
- Skill categories linked via `skill_categories` appear on the fighter skill advancement page as house-specific skill trees.
- Each `ContentHouseSkillRankAccess` row points back to a `ContentHouse` via the `skill_rank_rules` related name. These rules are only consulted when `gang_wide_skills` is checked.

**Admin interface:**

The `ContentHouse` admin page displays all fields for the house and includes two inlines: a `ContentFighter` listing and a `ContentHouseSkillRankAccess` ("House Skill Rank Rules") listing for the gang-wide skills mode. The `skill_categories` and `gang_skill_tree_choices` many-to-many fields use the horizontal filter widget. You can search houses by name.

### ContentFighterHouseOverride

`ContentFighterHouseOverride` captures cases where a fighter has a different cost when being hired by a specific house. This is a common pattern for faction-neutral fighters (bounty hunters, hangers-on, dramatis personae) whose hiring cost varies by faction.

| Field | Type | Description |
|---|---|---|
| `fighter` | ForeignKey | The `ContentFighter` whose cost is being overridden. |
| `house` | ForeignKey | The `ContentHouse` for which this override applies. |
| `cost` | IntegerField | The overridden cost in credits. Nullable -- if left blank, the fighter's base cost is used. |

**Constraints:**

- The combination of `fighter` and `house` must be unique. You cannot create two overrides for the same fighter-house pair.
- Overrides are ordered by house name, then fighter type.

**Admin interface:**

The `ContentFighterHouseOverride` admin page provides autocomplete fields for both `fighter` and `house`, making it quick to find the correct records. You can search by fighter type or house name, and filter by fighter type or house.

### ContentHouseSkillRankAccess

`ContentHouseSkillRankAccess` (verbose name: "House Skill Rank Rule") is a per-house rule that maps a fighter rank (category) to one of the gang's ranked skill-tree slots and assigns it a role of primary or secondary. These rules are only consulted for houses with `gang_wide_skills` enabled; they are how a gang's ranked picks become each fighter's primary/secondary skill trees.

One row means: "in this House, a fighter of category `fighter_category` gets the skill tree the gang ranked at `slot` as `role` (primary or secondary)."

| Field | Type | Description |
|---|---|---|
| `house` | ForeignKey | The `ContentHouse` this rule applies to. Reverse-accessed via `house.skill_rank_rules`. |
| `fighter_category` | CharField (choices from `FighterCategoryChoices`) | The fighter rank this rule applies to (e.g., Leader, Champion, Ganger, Juve). |
| `slot` | PositiveSmallIntegerField (min `1`) | 1-based rank of the gang's chosen skill tree this rule refers to (1 = the gang's highest-ranked pick). Slots beyond the house's `gang_skill_tree_count` will simply never resolve to a pick. |
| `role` | CharField (choices: `primary`, `secondary`) | Whether the tree at this slot is primary or secondary for this rank. |

**Constraints:**

- The combination of `house`, `fighter_category`, and `slot` must be unique. A given rank can only have one role per slot in a given house.
- Rows are ordered by house name, then fighter category, then slot.

**Admin interface:**

`ContentHouseSkillRankAccess` rows are typically managed as inlines on the parent `ContentHouse` change page, where the columns shown are `fighter_category`, `slot`, and `role`. There is also a standalone admin with filters on `house`, `fighter_category`, and `role`, and search by house name.

## How It Works in the Application

### List Creation

When a user creates a new list, they see a dropdown of all available houses. The form filters out generic houses (since those exist only to provide shared fighters) and groups the remaining houses into two sections: "House" for current factions and "Legacy House" for older ones. The user's selection becomes the `content_house` for their list and cannot be changed after creation.

### Fighter Selection

When a user adds a fighter to their list, the available fighters are determined by the list's house:

- **Standard houses** (`can_hire_any` is `false`): The form shows fighters belonging to the list's own house plus fighters from all generic houses. Exotic beasts, vehicles, and stash fighters are excluded from the dropdown (exotic beasts and vehicles are added through equipment assignments instead).
- **Unrestricted houses** (`can_hire_any` is `true`): The form shows all fighters from every house, except stash fighters. This allows factions like Underhive Outcasts to recruit from any house.

Fighter costs in the dropdown reflect house-specific pricing. If a `ContentFighterHouseOverride` exists for the fighter-house combination, that override cost is displayed. Otherwise, the fighter's standard `base_cost` is shown.

### Equipment Access

The `can_buy_any` flag controls how equipment pages behave:

- **Standard houses** (`can_buy_any` is `false`): Equipment pages default to showing only items from the fighter's own equipment list.
- **Unrestricted houses** (`can_buy_any` is `true`): Equipment pages automatically redirect to show all equipment from every equipment list and the Trading Post. Users can still switch back to the equipment list view manually.

### Skill Advancement

Each house can have unique skill categories linked via the `skill_categories` field. When a user advances a fighter's skills, the skill page shows:

1. Standard (non-restricted) skill categories available to all fighters.
2. House-specific skill categories from the fighter's house, displayed in a separate section.

This allows houses like Escher to have access to faction-specific skill trees alongside the universal ones.

### Gang-wide Skill Trees

If a house has `gang_wide_skills` checked, the gang as a whole picks a ranked set of skill trees rather than each fighter type carrying its own primary/secondary skill tree configuration. This is the mechanism behind factions like Venators, where the rulebook specifies that the gang chooses N skill trees in rank order and every fighter draws its primary/secondary access from those picks based on rank.

The flow is:

1. **List creation redirects to the picker.** When a user creates a list whose house has `gang_wide_skills` set, they are redirected to the gang skill-tree picker (`/list/<id>/skill-trees`). The selection can be deferred -- the list is created without picks, and fighters resolve gracefully until picks exist.
2. **Picking trees.** The picker (`/list/<id>/skill-trees/edit`) renders N ranked dropdowns, where N is the house's `gang_skill_tree_count`. Each dropdown is filtered to the house's `gang_skill_tree_choices` pool, or to all non-restricted skill trees if the pool is empty. Picks must be distinct across slots. A `?include_restricted=1` query parameter reveals restricted trees in the dropdowns.
3. **Per-fighter resolution.** When the application asks for a fighter's primary or secondary skill categories, it looks up the rank rules (`ContentHouseSkillRankAccess`) for the fighter's current category, finds the slots assigned the requested role, and returns the trees the gang ranked at those slots. The fighter template's own `primary_skill_categories` and `secondary_skill_categories` are ignored in this mode. Promotions are respected because resolution uses the fighter's current `get_category()`.
4. **Cloning a list** copies the gang's skill-tree picks alongside its attributes.

If a house with `gang_wide_skills` is missing rank rules (or rules for some categories), affected fighters simply get no primary/secondary trees from the gang picks for that role -- the system fails open rather than raising. Equipment-driven skill-tree access modifiers continue to apply on top in the same way as for non-gang-wide houses.

The gang picks are stored on the list as `ListSkillTreeAssignment` records (one per slot).

### Lists Browsing and Filtering

On the public lists page, users can filter lists by house. The house filter shows all houses (not just non-generic ones), and the search also matches against house names.

### Cost Recalculation

When a `ContentFighterHouseOverride` cost changes, the system automatically marks all affected `ListFighter` records as "dirty" -- meaning their cached cost data needs recalculation. This ensures that user-facing list totals stay accurate after content changes. The dirty fighters are recalculated the next time their list is viewed.

## Common Admin Tasks

### Adding a New House

1. Open the Houses admin page and click "Add House".
2. Enter the house `name` (e.g., "House Escher").
3. Set the flags as appropriate:
   - Leave `generic` unchecked for a standard selectable house.
   - Leave `legacy` unchecked unless this is an older faction you want to separate visually in the list creation form.
   - Leave `can_hire_any` unchecked unless this faction can recruit from any other house.
   - Leave `can_buy_any` unchecked unless this faction has unrestricted equipment access.
4. Optionally link skill categories in the `skill_categories` field if the house has unique skill trees.
5. Save the house. It will now appear in the list creation form.

### Adding a Generic House for Shared Fighters

Generic houses hold fighters that should be available across all factions (e.g., hired guns, hangers-on, dramatis personae).

1. Create a new house and check the `generic` flag.
2. Add fighters to this house as you normally would.
3. These fighters will automatically appear in the "add fighter" dropdown for lists belonging to any house.

Users will not see generic houses in the list creation form -- they exist only as containers for shared content.

### Setting a House-Specific Fighter Cost

Some fighters cost different amounts depending on which house hires them. To configure this:

1. Open the Fighter-House Overrides admin page and click "Add Fighter-House Override".
2. Use the autocomplete fields to select the `fighter` and the `house`.
3. Enter the override `cost` in credits.
4. Save. The next time a user views a list belonging to that house, the fighter's cost will reflect the override.

You can also search for existing overrides by fighter type or house name and filter by house to see all overrides for a particular faction.

### Marking a House as Legacy

If a house is being retired or replaced but existing lists still reference it:

1. Open the house in the admin.
2. Check the `legacy` flag.
3. Save. The house will continue to work for existing lists but will appear in the "Legacy House" group in the list creation form, visually separated from current factions.

### Configuring Unrestricted Recruitment

For factions that can hire from any house (e.g., Underhive Outcasts):

1. Open the house in the admin.
2. Check the `can_hire_any` flag.
3. Save. Lists belonging to this house will now show all fighters from every house in the "add fighter" form (excluding stash fighters).

### Configuring Unrestricted Equipment Access

For factions that can buy from any equipment list (e.g., Venators):

1. Open the house in the admin.
2. Check the `can_buy_any` flag.
3. Save. Equipment pages for fighters in this house will default to showing all available equipment rather than just the fighter's equipment list.

### Linking Unique Skill Categories to a House

If a house has faction-specific skill trees:

1. Open the house in the admin.
2. In the `skill_categories` (labelled "Unique Skill Categories") field, select the relevant `ContentSkillCategory` entries.
3. Save. These skill categories will now appear in a dedicated section on the skill advancement page for fighters belonging to this house.

### Configuring Gang-wide Skill Trees for a House

For factions where the gang as a whole picks a ranked set of skill trees and every fighter draws its primary/secondary access from those picks (e.g., Venators):

1. Open the house in the admin.
2. Check the `gang_wide_skills` flag.
3. Set `gang_skill_tree_count` to the number of skill trees the gang ranks (e.g., 4).
4. Optionally populate `gang_skill_tree_choices` ("Gang Skill Tree Pool") to restrict the pool of trees the gang may choose from. Leave it empty to allow any non-restricted skill tree.
5. In the "House Skill Rank Rules" inline, add one row per `(fighter category, slot, role)` mapping required by the rulebook. For example, "Champion gets slot 1 as primary" plus "Champion gets slot 2 as primary" plus "Champion gets slot 3 as secondary". Each rank/slot pair must be unique within the house.
6. Save. New lists belonging to this house will now be redirected to the gang skill-tree picker at creation, and existing lists gain a "Manage" link to set or change their picks.

Until rank rules exist for a given fighter category, fighters of that category will have no primary/secondary trees from the gang picks. Configure the rules before turning users loose on the house.
