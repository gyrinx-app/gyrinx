# Houses & Factions

Houses are the core organisational unit in the Gyrinx content library. A list represents a user's collection of fighters (called a "gang" in Necromunda). Every list a user creates is associated with exactly one house, and that house determines which fighters can be hired, which equipment is available, and which skill categories are accessible. Houses represent the major factions from the Necromunda tabletop game -- Escher, Goliath, Orlock, Cawdor, Van Saar, Delaque, and many others.

When a user creates a new list, they choose a house. From that point on, the house acts as a filter across the entire application: the fighters shown in the "add fighter" form, the equipment lists available on weapon and gear pages, and the skill trees offered during advancement are all determined by the house. Getting house configuration right is essential because it shapes the entire user experience of building and managing a list.

The content library also supports house-level cost overrides for individual fighters through the `ContentFighterHouseOverride` model. This lets you set a different price for the same fighter type depending on which house is hiring them -- a common pattern in Necromunda where hired guns and hangers-on cost different amounts for different factions.

## Key Concepts

**House** -- A faction or house type (e.g., House Escher, House Goliath, Underhive Outcasts). Each user list belongs to exactly one house.

**Generic house** -- A special category of house whose fighters are available to all other houses. Used for mercenaries, hired guns, hangers-on, and other faction-neutral fighter types. Generic houses cannot be selected as the primary house when creating a list.

**Legacy house** -- An older or deprecated faction that still appears in the list creation form but is grouped separately under "Legacy House" to distinguish it from current factions.

**House override** -- A per-house cost adjustment for a specific fighter type. When a fighter has a house override, the overridden cost is used instead of the fighter's base cost whenever that fighter appears in a list belonging to the specified house.

**Gang-wide skills** -- An opt-in mode where the whole gang picks a ranked set of skill trees at creation and each fighter's primary/secondary trees are derived from those picks by rank. Used by factions like Venators where fighter templates do not have fixed primary/secondary trees.

## Models

### ContentHouse

`ContentHouse` represents a faction or house that fighters can belong to. It is the central model that ties together fighters, equipment access, and skill trees.

| Field | Type | Description |
|---|---|---|
| `name` | CharField (max 255) | The display name of the house (e.g., "House Escher", "Underhive Outcasts"). Indexed for search. |
| `description` | TextField (blank) | Free-form description of the house, shown on the pack detail page for content-pack houses. |
| `icon` | FileField (nullable) | Optional SVG icon rendered inline next to the house name via the `house_icon` template tag. The tag sanitises the stored SVG on render; do not embed untrusted SVG anywhere else. Content-pack houses that ship without their own icon receive the shared "custom gang" icon automatically. Icon display is gated to the "House Icons Alpha" group. |
| `generic` | BooleanField (default `False`) | When checked, fighters belonging to this house are available to lists of any other house. Generic houses cannot be selected as a primary house during list creation. |
| `legacy` | BooleanField (default `False`) | When checked, marks this house as a legacy/older faction. Legacy houses are grouped separately in the list creation form under a "Legacy House" heading. |
| `can_hire_any` | BooleanField (default `False`) | When checked, lists belonging to this house can hire any fighter from any house (except stash fighters). Used for factions like Underhive Outcasts that have unrestricted recruitment. |
| `can_buy_any` | BooleanField (default `False`) | When checked, lists belonging to this house can buy any equipment from any equipment list and the Trading Post. Equipment pages default to showing all available equipment rather than the fighter's own equipment list. |
| `skill_categories` | ManyToManyField | Links to `ContentSkillCategory` records. These are the "Unique Skill Categories" available to fighters in this house. They appear as a separate section on the skill advancement page alongside the standard (non-restricted) skill categories. |
| `gang_wide_skills` | BooleanField (default `False`) | When checked, gangs of this house pick a ranked set of skill trees at creation. Fighter templates' own primary/secondary skill trees are ignored; primary/secondary access is derived from the gang's picks via `ContentHouseSkillRankAccess`. |
| `gang_skill_tree_count` | PositiveSmallIntegerField (default `0`) | How many skill trees the gang ranks (e.g. `4` for Venators). Only used when `gang_wide_skills` is checked. |
| `gang_skill_tree_choices` | ManyToManyField (blank) | Optional pool of `ContentSkillCategory` records a gang of this house may pick from. Leave empty to allow any non-restricted skill tree; restricted trees can still be revealed via the picker's filter. Only used when `gang_wide_skills` is checked. |

**Relationships:**

- Each `ContentFighter` has a foreign key to `ContentHouse`, establishing which house a fighter template belongs to.
- Each user `List` has a foreign key to `ContentHouse`, establishing the house for the entire list.
- Skill categories linked via `skill_categories` appear on the fighter skill advancement page as house-specific skill trees.
- When `gang_wide_skills` is on, `ContentHouseSkillRankAccess` rows (see below) define the per-rank mapping from ranked slot to primary/secondary role. A user list stores its ranked picks in `ListSkillTreeAssignment` (in the core app).

**Admin interface:**

The `ContentHouse` admin page displays all fields for the house, uses `filter_horizontal` widgets for both `skill_categories` and `gang_skill_tree_choices`, and includes two inlines: `ContentHouseSkillRankAccess` (the per-rank mapping rules) and the list of `ContentFighter` records belonging to the house. You can search houses by name.

### ContentHouseSkillRankAccess

`ContentHouseSkillRankAccess` maps a fighter rank (category) to a ranked gang skill-tree slot and role. One row means: "in this house, a fighter of category `fighter_category` gets the skill tree the gang ranked at `slot` as `role` (primary or secondary)." These rules are only consulted for houses with `gang_wide_skills` enabled.

| Field | Type | Description |
|---|---|---|
| `house` | ForeignKey (`ContentHouse`) | The house this rule applies to. Related name `skill_rank_rules`. |
| `fighter_category` | CharField (max 255, choices) | The fighter rank this rule applies to. Uses `FighterCategoryChoices`. |
| `slot` | PositiveSmallIntegerField | 1-based rank of the gang skill tree this rule refers to. Must be `>= 1`. |
| `role` | CharField (max 16, choices) | Whether the tree at `slot` is `primary` or `secondary` for this rank. |

**Constraints:**

- The combination of `house`, `fighter_category`, and `slot` must be unique. A single rank cannot have two rules for the same slot.
- Rows are ordered by house name, fighter category, then slot.

**Admin interface:**

Skill rank rules are managed as an inline on the `ContentHouse` change page and via a standalone admin filtered by house, fighter category, and role. Searching by house name is supported.

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

### Gang-Wide Skills

Houses with `gang_wide_skills` enabled work differently. Instead of each fighter template declaring its own primary and secondary skill trees, the whole gang picks a ranked set of trees at creation and every fighter derives its primary/secondary from those picks via the house's `ContentHouseSkillRankAccess` rules.

At gang creation, the user is redirected to a picker where they rank `gang_skill_tree_count` skill trees. When `gang_skill_tree_choices` is populated, the picker's dropdowns are restricted to that pool; when it is empty, any non-restricted tree is available and restricted trees can be revealed via the same `?include_restricted=1` filter used elsewhere in the app. The picks are saved on the list as `ListSkillTreeAssignment` rows and can be edited later via **Manage Skill Trees** on the list page.

When rendering a fighter, the application looks up `ContentHouseSkillRankAccess` rows for the fighter's house and category, uses each rule's `slot` to find the tree the gang ranked at that position, and adds it as primary or secondary according to the rule's `role`. Fighter promotions (e.g. Ganger → Leader) resolve against the promoted category, so a rank change automatically swaps to the appropriate rules. Fighter templates' own `primary_skill_categories` / `secondary_skill_categories` M2Ms are ignored in this mode. If the gang has not picked yet, the fighter's primary/secondary lists are empty until the picker is completed.

Equipment-modifier overlays (`ContentModSkillTreeAccess`) still apply on top of the gang-wide resolution -- see [Modifiers](modifiers.md).

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

### Configuring a Gang-Wide-Skills House

For factions like Venators where the gang picks skill trees rather than each fighter template declaring its own:

1. Open the house in the admin and check `gang_wide_skills`.
2. Set `gang_skill_tree_count` to the number of trees the gang should rank (e.g. `4`).
3. Optionally populate `gang_skill_tree_choices` with the pool of skill categories the gang may pick from. Leave empty to allow any non-restricted tree.
4. In the **House Skill Rank Rules** inline, add one row for each `(fighter category, slot, role)` combination that describes how ranks map onto ranked slots. For example: `Leader → slot 1 → primary`, `Leader → slot 2 → secondary`, `Ganger → slot 3 → primary`, and so on. The exact mapping is a content-data decision and should match the rulebook.
5. Save. New lists created for this house will be redirected to the skill-tree picker after creation and existing lists will show a **Manage Skill Trees** panel.

Because the mapping is entirely data-driven, no code change is required to add or adjust a gang-wide-skills house.
