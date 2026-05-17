# Content Packs

## Overview

Content Packs are user-created collections of custom game content. They allow users to group together custom houses, fighters, equipment, and other content items into a named, shareable package. A list represents a user's collection of fighters (called a "gang" in Necromunda). A pack might represent homebrew content for a list, a fan-made expansion, or a collection of house rules with associated game data.

The content pack system is designed around a key principle: pack content is hidden from normal queries by default. When a user browses fighters, equipment, or other content in the application, they only see the official base content. Pack content only appears when a user explicitly opts in to a specific pack. This keeps the default experience clean while still allowing custom content to coexist in the same database.

Content packs are available to all authenticated users. Any logged-in user can access the packs interface, create packs, and browse community packs.

## Key Concepts

**Base content** is the standard game content that ships with the application -- all the official houses, fighters, equipment, and so on. Base content is visible to all users by default.

**Pack content** is any content item that has been added to at least one content pack. Pack content is automatically excluded from normal content queries throughout the application.

**Listed vs unlisted** packs control public visibility. A listed pack appears in search results and the community packs index. An unlisted pack can still be shared via its direct URL, but it will not show up when other users browse packs.

**Featured packs** are admin-curated promotions. A featured, listed, non-archived pack appears in a showcase at the top of the [Customisation page](#the-customisation-page) and on the front page (`/`) for both signed-out and signed-in users. The `featured` flag is set in the admin only; pack owners cannot set it themselves.

**Editor permissions.** A pack has a single owner but can also grant editor access to other users through `CustomContentPackPermission`. Editors can modify the pack and its items just like the owner, but cannot change permissions or transfer ownership.

**Content types** refer to the different kinds of game content that can be included in a pack. The system is built using Django's `ContentType` framework, and a pack can contain any of the following content models: `ContentHouse`, `ContentAttribute`, `ContentAttributeValue`, `ContentFighter` (including vehicles and exotic beasts), `ContentRule` (special rules), `ContentSkillCategory` (skill trees), `ContentSkill`, `ContentPsykerDiscipline`, `ContentPsykerPower`, `ContentEquipment` (gear and weapons), `ContentWeaponTrait`, `ContentWeaponAccessory`, and `ContentModApplication` (pack house-rule modifiers; see [Pack house rules](#pack-house-rules) below). Custom weapon profiles, equipment-list entries, default assignments, and equipment upgrades for pack-owned items are also captured automatically because their parent records belong to the pack.

**Archive semantics.** Archiving a `CustomContentPack` or `CustomContentPackItem` is a pack-owner soft-delete: it hides the record from the owner's pack admin/editor and prevents new subscribers from picking it up, but it does **not** retract content from lists/gangs already subscribed. See [Archive semantics](#archive-semantics) for the full rule and the queryset helper that enforces it.

## Models

### `CustomContentPack`

Represents a named collection of custom content items. Each pack is owned by a single user.

`CustomContentPack` inherits from `AppBase`, which provides UUID primary keys, owner tracking, archive functionality, and history tracking.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (max 255) | The display name of the pack. Packs are ordered alphabetically by name. |
| `summary` | TextField (blank) | A brief description shown on the packs index page. Supports rich text. |
| `description` | TextField (blank) | A longer description shown on the pack detail page. Supports rich text. |
| `listed` | BooleanField (default `False`) | Whether the pack appears in public search results and the community index. |
| `featured` | BooleanField (default `False`) | Whether the pack appears in the admin-curated showcase on the front page and the Customisation page. Only meaningful when the pack is also `listed=True` and not archived. Set in the Django admin. |
| `featured_description` | TextField (blank) | A short description shown on the featured-pack card in place of the regular summary. Falls back to `summary` when blank. |
| `owner` | ForeignKey (User) | The user who created and owns the pack. Inherited from `AppBase`. |

History tracking is enabled via `HistoricalRecords`, so all changes to a pack are recorded with timestamps and the user who made the change.

#### Admin interface

- **List display:** `name`, `listed`, `owner`, `created`
- **Search:** By pack name or owner username
- **Filters:** By `listed` status and creation date
- **Editable fields:** `name`, `summary`, `description`, `listed`, `featured`, `featured_description`, `owner`

### `CustomContentPackItem`

A through model that links a content object to a pack. Uses Django's `ContentType` framework to support polymorphic references -- a single `CustomContentPackItem` can point to a `ContentHouse`, a `ContentFighter`, a `ContentEquipment`, or any other content model.

| Field | Type | Description |
|-------|------|-------------|
| `pack` | ForeignKey (`CustomContentPack`) | The pack this item belongs to. Deleting a pack cascades to delete all its items. |
| `content_type` | ForeignKey (`ContentType`) | The Django content type of the linked object. Limited to models in the `content` app. |
| `object_id` | UUIDField | The primary key of the linked content object. |
| `content_object` | GenericForeignKey | A convenience accessor that resolves to the actual content object. Not a database column. |
| `owner` | ForeignKey (User) | The user who added this item. Inherited from `AppBase`. |

#### Constraints and validation

- **Unique together:** The combination of `pack`, `content_type`, and `object_id` must be unique among non-archived rows. The uniqueness constraint is conditional on `archived=False`, so an archived item does not prevent re-adding the same content object to the same pack. You cannot have two non-archived rows with the same triple.
- **Cross-pack sharing:** The same content item can belong to multiple different packs. The uniqueness constraint is scoped to a single pack.
- **Object existence:** The `clean()` method validates that the referenced content object actually exists. It uses `all_content()` for this check, so it can find objects that are themselves pack content.
- **Cascade delete:** Deleting a pack deletes all its `CustomContentPackItem` records. Deleting a `ContentType` also cascades, though this is unlikely in practice.
- **Index:** A composite index on `content_type` and `object_id` ensures efficient lookups when determining which packs a content item belongs to.

#### Admin interface

- **List display:** `pack`, `content_type`, a clickable link to the content object, and `owner`
- **Search:** By pack name or owner username
- **Filters:** By pack and content type
- **Editable fields:** `pack`, `content_type`, `object_id`, and a read-only link to the content object

The content object link in the admin navigates directly to the Django admin change page for the referenced content item.

### `CustomContentPackPermission`

Grants a non-owner user a role on a pack. The only role currently defined is `editor`, which allows the user to edit the pack and its items as if they were the owner.

| Field | Type | Description |
|-------|------|-------------|
| `pack` | ForeignKey (`CustomContentPack`) | The pack the permission applies to. Cascades on delete. |
| `user` | ForeignKey (User) | The user being granted the role. Cascades on delete. |
| `role` | CharField (max 20, choices: `editor`; default `editor`) | The role granted. |
| `owner` | ForeignKey (User) | Who created the permission. Inherited from `AppBase`. |

#### Constraints

- **Unique together:** Each `(pack, user)` pair can have at most one permission row.

The `CustomContentPack.can_edit(user)` method returns `True` if the user is the owner or has an editor permission row. `can_view(user)` returns `True` if the pack is listed, the user is the owner, or the user has any permission row on the pack. Unlisted packs return 404 to users who lack viewing rights.

### `ContentModApplication`

A pack-scoped wrapper that applies an existing `ContentMod` to a specific library item (typically a weapon profile or fighter). `ContentModApplication` is itself a `Content` model and is attached to a pack via `CustomContentPackItem`, so it follows the same pack-filtering and archive rules as any other pack-owned content. See [Pack house rules](#pack-house-rules) below for the runtime behaviour, and [Modifiers](modifiers.md#contentmodapplication) for the field reference.

## Pack Filtering System

The pack filtering system is the mechanism that keeps pack content separate from base content in application queries. It is built into the `ContentManager` and `ContentQuerySet` classes that all content models use.

### How default filtering works

Every content model (such as `ContentFighter`, `ContentEquipment`, `ContentWeaponProfile`) uses `ContentManager` as its default manager. The manager's `get_queryset()` method automatically calls `exclude_pack_content()`, which adds a subquery filter that excludes any content object linked to a `CustomContentPackItem`.

This means that any code using `ContentFighter.objects.all()` or `ContentFighter.objects.filter(...)` will never return pack content. This is intentional -- pack content should not appear in the normal application flow unless explicitly requested.

### Query methods

The `ContentManager` provides three ways to query content:

| Method | What it returns |
|--------|----------------|
| `.all()` / `.filter(...)` | Base content only. Pack content is excluded. This is the default behaviour. |
| `.all_content()` | All content, including pack content. Bypasses the pack filter entirely. |
| `.with_packs(packs)` | Base content plus content from the specified packs. Content from other packs is still excluded. |

The `with_packs()` method accepts a list of `CustomContentPack` instances. It returns a queryset containing all base content (items not in any pack) combined with items that belong to any of the specified packs. Items belonging to other, non-specified packs remain excluded.

`with_packs()` also accepts an `include_archived_items` keyword. Subscriber read paths (anything driven by `list.packs` or `campaign.packs`) **must** pass `include_archived_items=True` so that archived items and items inside an archived pack still surface to subscribed lists. Owner-side callers (pack admin, gallery, write paths) should leave it at the default to keep archived items out of pickers and listings. See [Archive semantics](#archive-semantics) below for the full rule.

### How the admin handles pack content

The `ContentAdmin` base class in the content admin overrides `get_queryset()` to use `all_content()`. This ensures that when you view content models in the Django admin, you see all items including pack content. Without this override, pack content would be invisible in the admin.

The same override is applied to `ContentTabularInline` and `ContentStackedInline`, so inline content displays in the admin also show pack content.

### The `packs_display` column

Every content model's admin list view includes a "Packs" column at the end. This column shows which packs (if any) a content item belongs to. If the item is not in any pack, the column displays a dash. If the item belongs to one or more packs, it displays their names separated by commas.

This column also appears as a read-only field on each content item's detail/edit page in the admin.

## Archive semantics

Archiving a `CustomContentPack` or `CustomContentPackItem` is a **pack-owner soft-delete**. It hides the pack/item from the owner's pack admin/editor and prevents new subscribers from picking it up -- but it does **not** retract content from lists/gangs already subscribed.

Once a list or campaign holds a pack in its `packs` M2M, every item in that pack stays visible to that list -- even items where `archived=True`, and even if the whole pack has been archived. This applies to fighters, equipment, default assignments, weapon profiles, accessories, skills, rules, psyker disciplines, psyker powers, attributes, mod applications, and any other pack-aware content.

**Rules of thumb when querying packs / pack items:**

- **Subscriber read paths** (anything driven by `list.packs` or `campaign.packs`) MUST NOT filter `archived=False` on `CustomContentPack` or `CustomContentPackItem`. This applies to both directions: the M2M lookup that finds *which* packs a list/campaign is subscribed to, and the pack-item lookup that resolves content within those packs. The canonical join is `ContentQuerySet.with_packs(packs, include_archived_items=True)` -- subscriber paths **must** pass `include_archived_items=True`; the default excludes archived items so owner-side callers don't surface them.
- **Pack-owner library views, gallery/featured listings, list-creation pack pickers, and campaign pack-add UIs** -- these are pack-discovery/write paths. Filtering `archived=False` is correct here so archived packs don't appear as new options. For `with_packs([pack])` calls on owner-side, leave the default -- archived items stay hidden.
- **Form validation and unique-constraint lookups** are also fine to filter `archived=False`; the unique constraint on `CustomContentPackItem` is conditional on `archived=False` and code that looks up the "live" item must match.

The same rule is documented in the project root `CLAUDE.md` under "Domain Rules → Content packs: archive semantics".

## Pack house rules

Pack authors can declare modifications to existing library content (weapons, weapon profiles, gear, fighters) without forking the underlying record. When a list subscribes to the pack, the modifications are applied automatically wherever the targeted item appears on that list.

### How it works

- A `ContentModApplication` row pairs an existing `ContentMod` with a target object via `GenericForeignKey`. The target must be a `ContentWeaponProfile` or a `ContentFighter`.
- The application is owned by a pack via the polymorphic `CustomContentPackItem` table, so it is pack-filtered like any other pack item and follows the same archive semantics.
- At runtime, `List.pack_mods_by_target` builds a `(content_type_id, object_id) → [ContentMod]` dict in a single query per list. This dict is consumed at three injection points:
  - `ListFighterEquipmentAssignment._mods` -- per-equipment scope.
  - `ListFighter._mods` -- per-fighter scope.
  - `VirtualWeaponProfile` construction -- per-profile scope. For default assignments, `VirtualListFighterEquipmentAssignment` rebuilds profiles with pack mods unioned in.
- The "modified" tooltip on a stat now reads "Modified by equipment, accessories, upgrades, a pack house rule, or manually."

### Validation

`ContentModApplication.clean()` cross-validates the modifier subclass against the target type:

- `ContentModStat` and `ContentModTrait` -- must target a `ContentWeaponProfile`.
- `ContentModFighterStat`, `ContentModFighterRule`, `ContentModFighterSkill`, `ContentModSkillTreeAccess`, `ContentModPsykerDisciplineAccess` -- must target a `ContentFighter`.

The target object must exist; the check uses `all_content()` so pack-owned targets are also valid.

### UX scope

The pack detail page exposes a "House Rules" section with a picker → form flow plus edit and archive routes. The v1 form scope covers stat mods only -- `ContentModStat` for weapon targets and `ContentModFighterStat` for fighter/gear targets. Other `ContentMod` subclasses remain valid model-side and accessible via the admin.

Modding `ContentWeaponAccessory`, `ContentEquipmentUpgrade`, or `ContentWeaponTrait` directly is not yet supported. There is also no per-pack tooltip attribution (which pack caused the change) and no conflict-resolution UI when two packs target the same item -- mods stack in pack-iteration order.

### Admin

`ContentModApplication` has its own admin (registered under the Content app):

- **List display:** the human-readable string (the modifier and target), `target_content_type`, the linked `modifier`, and `packs_display`.
- **Filter:** by `target_content_type`.
- **Raw id field:** `modifier` (use the lookup widget to find polymorphic mods).

## Campaign required packs

A campaign can mark any of its associated content packs as **required**. Required packs are a hard compatibility constraint: every list in the campaign must already be subscribed to every required pack.

### Model

`Campaign.packs` routes through `CampaignContentPack`, a through-model with a `required` boolean. The through-model lives in `gyrinx/core/models/campaign.py` and shares the `core_campaign_packs` table with the original implicit M2M (the migration is state-only, so existing rows backfill to `required=False`).

| Field | Type | Description |
|-------|------|-------------|
| `campaign` | ForeignKey (`Campaign`) | The campaign. Cascades on delete. |
| `pack` | ForeignKey (`CustomContentPack`) | The pack. Cascades on delete. The DB column is named `customcontentpack_id` for backwards compatibility. |
| `required` | BooleanField (default `False`) | When `True`, every list in this campaign must subscribe to this pack. |

`Campaign.required_packs` returns the queryset of packs flagged as required; `Campaign.pack_links` is the reverse accessor for the through-model rows.

### Behaviour

- Joining a campaign -- whether before or during it -- is blocked when the list is missing any of the campaign's required packs. The error names the missing packs.
- A list owner cannot unsubscribe from a pack that is required by any of their campaigns. Optional packs still unsubscribe normally.
- Arbitrators can flip a campaign pack to required at any time before POST_CAMPAIGN, but the flip is rejected if any joined list lacks the pack. Demoting a required pack back to optional is unconditional and takes effect immediately.
- The invitation pack-setup flow validates required packs server-side: a POST that omits one of the campaign's required packs is rejected.
- Removing a pack from a campaign does not unsubscribe the lists; their `list.packs` membership is independent.
- Copying a campaign carries the `required` flag onto the target through-row.

The required-flag flip and the join path both take a row lock on the through-row so a concurrent flip cannot sneak in between `validate_list_required_packs` and the join.

## How It Works in the Application

### The Customisation page

Authenticated users access content packs through the Customisation page at `/packs/`. This page shows a searchable, paginated list of content packs.

By default, authenticated users see only their own packs (the "My packs only" toggle is on). Turning the toggle off shows all publicly listed packs from the community. Full-text search covers pack names, summaries, and author usernames.

Each pack in the list shows its name, author, summary, and an "Unlisted" badge if the pack is not publicly listed.

### Featured packs

Featured packs are surfaced in two places:

- **The front page (`/`)** -- up to three featured packs appear at the top of the marketing area for signed-out users and below the dashboard row for signed-in users. The section disappears entirely when no pack is currently featured.
- **The Customisation page (`/packs/`)** -- the same featured-pack cards appear at the top of the index.

The featured card markup lives in `core/includes/featured_pack_card.html` and is shared by both pages. A pack appears when `featured=True`, `listed=True`, and the pack is not archived. The card shows the pack name, owner, and `featured_description` (falling back to `summary` when blank); clicking through navigates to `/pack/<id>`. Toggling `featured=False` in the admin removes the pack from both showcases.

### Pack detail page

Clicking a pack opens its detail page at `/pack/<id>`. This page shows:

- The pack name, author, and public/unlisted status
- The summary and description (if provided)
- A content section for each supported content type, in display order: Houses, Gang Attributes, Fighters & Vehicles, Special Rules, Skill Trees, Skills, Psyker Disciplines, Psyker Powers, Gear, Weapons, Weapon Traits, Weapon Accessories, and House Rules (pack mod applications)
- Quick-add buttons in each section ("Add gear", "Add a special rule", etc.) and a global quick-add panel for fast iteration
- A recent activity feed showing the last 5 changes, with a link to the full activity history

The Special Rules section was previously labelled "Rules"; it was renamed to disambiguate from the House Rules section, which holds pack mod applications. Slug, URL, and model names are unchanged.

Pack owners and users with editor permissions see edit controls. Unlisted packs return a 404 for users who can neither view (via the listed flag or a permission row) nor edit the pack.

### Creating and editing packs

Users create packs at `/packs/new/`. The form includes fields for name, summary (rich text), description (rich text), and the listed toggle. The pack is automatically owned by the current user.

Editing a pack at `/pack/<id>/edit/` uses the same form. Only the pack owner can edit it.

### Activity history

Each pack has a full activity history at `/pack/<id>/activity/`. This combines history records from both the pack itself and its items into a single chronological feed. The activity feed shows:

- Who made a change and when
- Whether the change was to the pack or to an item
- For items: the name and type of the affected content object
- For updates: which fields changed and their new values (text fields just show "updated" rather than the full content diff)

Activity is paginated at 50 entries per page.

### Pack content visibility in lists and fighters

When users build lists and add fighters or equipment, they interact with the normal content queries that exclude pack content by default. Pack content does not appear in fighter selection dropdowns, equipment lists, or any other content-driven interface unless the application explicitly uses `with_packs()` to include specific packs.

Subscriber views call `with_packs(list.packs.all(), include_archived_items=True)` so that archived items and items in archived packs remain visible to lists already subscribed. See [Archive semantics](#archive-semantics).

### Pack mod applications

When a list subscribes to a pack, any `ContentModApplication` rows owned by the pack are surfaced into the list's `pack_mods_by_target` cache. The cache is keyed by `(content_type_id, object_id)` so that fighter and equipment-assignment code paths can look up applicable mods in O(1). Modifiers from pack house rules stack with modifiers from equipment, accessories, upgrades, and injuries; the resulting "modified" tooltip notes the pack-house-rule source.

## Common Admin Tasks

### Creating a pack via the admin

While users typically create packs through the application interface, you can also create them directly in the admin:

1. Navigate to Custom Content Packs in the admin
2. Click "Add Custom Content Pack"
3. Fill in the name, optional summary and description, set the listed flag, and choose an owner
4. Save

### Adding content to a pack via the admin

To add a content item to a pack:

1. Navigate to Custom Content Pack Items in the admin
2. Click "Add Custom Content Pack Item"
3. Select the pack, the content type (e.g., "content | content house"), and paste the UUID of the content object into the `object_id` field
4. Set the owner and save

The content object link will appear as a read-only field after saving, confirming the item was linked correctly.

### Checking which packs a content item belongs to

When viewing any content model in the admin (houses, fighters, equipment, etc.), look at the "Packs" column on the right side of the list view. This shows the pack names for items that belong to packs, or a dash for base content.

You can also see this information on the detail page of any content item, where "Packs" appears as a read-only field at the bottom.

### Making a pack publicly listed

By default, new packs are unlisted. To make a pack visible in community search results:

1. Navigate to Custom Content Packs in the admin
2. Find the pack and click to edit it
3. Check the `listed` checkbox
4. Save

Alternatively, the pack owner can toggle the "Listed" checkbox when editing their pack through the application interface.

### Featuring a pack on the front page and Customisation page

To promote a listed pack into the homepage and `/packs/` showcase:

1. Navigate to Custom Content Packs in the admin.
2. Confirm `listed` is checked and the pack is not archived; otherwise the showcase will skip it.
3. Check the `featured` checkbox.
4. Optionally fill in `featured_description` with a short pitch to display in place of the regular summary on the featured card.
5. Save.

Toggling `featured` is admin-only. The front-page showcase displays up to three featured packs; if more than three are featured at once, the application chooses which three to show.

### Granting editor permissions on a pack

Editor permissions let a non-owner user modify the pack and its items.

1. Navigate to Content Pack Permissions in the admin.
2. Click "Add Content Pack Permission".
3. Select the pack and the user; leave `role` at `editor` (the only role currently defined).
4. Save.

The user can now view and edit the pack from the application interface even if the pack is unlisted. Removing the permission revokes their access.

### Marking a campaign pack as required

To make one of a campaign's content packs required for every list joining the campaign, use the campaign packs page in the application or the through-row admin:

1. Open the campaign in the application and navigate to the Packs tab.
2. Toggle "Required" on the pack you want to make required.
3. If any joined list lacks the pack, the toggle is rejected with an error naming the missing lists; ensure all lists subscribe before flipping the flag.

Demoting a required pack back to optional is unconditional and takes effect immediately. The flag can also be flipped via `CampaignContentPack` in the Django admin, which exposes `campaign`, `pack`, and `required` directly.

### Adding a house-rule modifier to a pack

To attach a stat modifier to a library weapon profile or fighter through a pack:

1. Open the pack in the application and scroll to the **House Rules** section.
2. Click the picker entry for the kind of modifier you want (weapon stat or fighter stat).
3. Choose the target (a library `ContentWeaponProfile` or `ContentFighter`), the stat, the mode (`improve` / `worsen` / `set`), and the value.
4. Save. A new `ContentMod` and a `ContentModApplication` are created and attached to the pack via `CustomContentPackItem`.

Subscribed lists immediately pick up the modifier wherever the target appears. To remove or change the rule, return to the House Rules section and use the edit or archive controls on the row.

### Reviewing pack activity

To review the history of changes to a pack, navigate to the pack's detail page in the application and scroll to the Activity section. For the full history, click "View all". This shows a chronological feed of all pack and item changes.

In the admin, you can also review history by navigating to the historical records for `CustomContentPack` or `CustomContentPackItem` through the History link on any record.
