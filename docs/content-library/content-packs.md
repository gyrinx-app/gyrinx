# Content Packs

## Overview

Content Packs are user-created collections of custom game content. They allow users to group together custom houses, fighters, equipment, and other content items into a named, shareable package. A list represents a user's collection of fighters (called a "gang" in Necromunda). A pack might represent homebrew content for a list, a fan-made expansion, or a collection of house rules with associated game data.

The content pack system is designed around a key principle: pack content is hidden from normal queries by default. When a user browses fighters, equipment, or other content in the application, they only see the official base content. Pack content only appears when a user explicitly opts in to a specific pack. This keeps the default experience clean while still allowing custom content to coexist in the same database.

Content packs are available to all authenticated users. Any logged-in user can access the packs interface, create packs, and browse community packs.

## Key Concepts

**Base content** is the standard game content that ships with the application -- all the official houses, fighters, equipment, and so on. Base content is visible to all users by default.

**Pack content** is any content item that has been added to at least one content pack. Pack content is automatically excluded from normal content queries throughout the application.

**Listed vs unlisted** packs control public visibility. A listed pack appears in search results and the community packs index. An unlisted pack can still be shared via its direct URL, but it will not show up when other users browse packs.

**Content types** refer to the different kinds of game content that can be included in a pack. Currently, the supported content type is Houses (`ContentHouse`). The system is built using Django's `ContentType` framework, so extending it to additional content models is straightforward.

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
| `owner` | ForeignKey (User) | The user who created and owns the pack. Inherited from `AppBase`. |

History tracking is enabled via `HistoricalRecords`, so all changes to a pack are recorded with timestamps and the user who made the change.

#### Admin interface

- **List display:** `name`, `listed`, `owner`, `created`
- **Search:** By pack name or owner username
- **Filters:** By `listed` status and creation date
- **Editable fields:** `name`, `summary`, `description`, `listed`, `owner`

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

- **Unique together:** The combination of `pack`, `content_type`, and `object_id` must be unique. You cannot add the same content item to the same pack twice.
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

### How the admin handles pack content

The `ContentAdmin` base class in the content admin overrides `get_queryset()` to use `all_content()`. This ensures that when you view content models in the Django admin, you see all items including pack content. Without this override, pack content would be invisible in the admin.

The same override is applied to `ContentTabularInline` and `ContentStackedInline`, so inline content displays in the admin also show pack content.

### The `packs_display` column

Every content model's admin list view includes a "Packs" column at the end. This column shows which packs (if any) a content item belongs to. If the item is not in any pack, the column displays a dash. If the item belongs to one or more packs, it displays their names separated by commas.

This column also appears as a read-only field on each content item's detail/edit page in the admin.

## How It Works in the Application

### The Customisation page

Authenticated users access content packs through the Customisation page at `/packs/`. This page shows a searchable, paginated list of content packs.

By default, authenticated users see only their own packs (the "My packs only" toggle is on). Turning the toggle off shows all publicly listed packs from the community. Full-text search covers pack names, summaries, and author usernames.

Each pack in the list shows its name, author, summary, and an "Unlisted" badge if the pack is not publicly listed.

### Pack detail page

Clicking a pack opens its detail page at `/pack/<id>`. This page shows:

- The pack name, author, and public/unlisted status
- The summary and description (if provided)
- A content section for each supported content type (currently Houses), listing the items in the pack
- A recent activity feed showing the last 5 changes, with a link to the full activity history

Pack owners see an "Edit" button. Unlisted packs return a 404 for users who are not the owner.

### Creating and editing packs

Users create packs at `/packs/new/`. The form includes fields for name, summary (rich text), description (rich text), and the listed toggle. The pack is automatically owned by the current user.

Editing a pack at `/pack/<id>/edit/` uses the same form. Only the pack owner can edit it.

### Editing pack gear and weapons: the Modifiers tab

When a pack owner edits a custom gear or weapon item, the item editor is split into two tabs:

- **Details** -- the item's base fields (name, cost, statline, and so on).
- **Modifiers** -- a picker for attaching fighter-level modifiers to the item.

The Modifiers tab (at `/pack/<id>/item/<item_id>/modifiers/`) lets the owner attach three kinds of modifier:

- **Stat modifiers** -- improve, worsen, or set a fighter stat. At most one modifier may be set per stat. Improve and worsen require a whole-number value; set accepts any value.
- **Special rule modifiers** -- add or remove a fighter rule.
- **Skill modifiers** -- add or remove a fighter skill.

These map to `ContentModFighterStat`, `ContentModFighterRule`, and `ContentModFighterSkill` records, which are attached to the equipment's `modifiers` relationship. The picker finds or reuses matching modifier records rather than creating duplicates. It manages only these three fighter-level modifier kinds; any other modifiers set on a library item (for example skill-tree or psyker-discipline access modifiers configured through the admin) are preserved on save. The rule and skill pickers are pack-aware, so a pack's own custom rules and skills are selectable alongside the base library.

The Modifiers tab is available only for gear and weapon items; other content types do not have it. When adding a new gear or weapon, only the Details fields are shown, with a hint pointing to the Modifiers tab -- which becomes available once the item has been saved. When a list subscribes to the pack and a fighter is equipped with the item, these modifiers surface on the fighter through the normal equipment-modifier runtime path (`ListFighterEquipmentAssignment._mods`). See [Modifiers](modifiers.md) for the underlying modifier model details.

### Pack house rules

A pack can define **house rules** -- pack-scoped modifications applied to a target through a `ContentModApplication`. Each house rule targets either a weapon profile or a fighter (or vehicle), and a *kind* selector controls what is modified. The available kinds depend on the target:

| Target | Available kinds |
|--------|-----------------|
| Weapons | **Stat** (adjust a value on the weapon statline) or **Trait** (add or remove a weapon trait). |
| Fighters & Vehicles | **Stat** (adjust a value on the fighter statline) or **Special rule** (add or remove a fighter rule). |

The mode options follow the kind: stat modifications use `improve`, `worsen`, or `set` (improve and worsen require a whole-number value); trait and special-rule modifications use `add` or `remove`. The trait and rule selectors are pack-aware, so the pack's own custom traits and rules are offered alongside the base library.

House rules are managed from the pack at `/pack/<id>/house-rule/`. When a list or campaign subscribes to the pack, a stat house rule adjusts the relevant statline, a weapon trait house rule surfaces through the weapon's trait line (`VirtualWeaponProfile.traits`), and a fighter special-rule house rule surfaces through the fighter's rule line (`ListFighter.ruleline`). See [Modifiers](modifiers.md) for the modifier types these house rules apply.

### Activity history

Each pack has a full activity history at `/pack/<id>/activity/`. This combines history records from both the pack itself and its items into a single chronological feed. The activity feed shows:

- Who made a change and when
- Whether the change was to the pack or to an item
- For items: the name and type of the affected content object
- For updates: which fields changed and their new values (text fields just show "updated" rather than the full content diff)

Activity is paginated at 50 entries per page.

### Pack content visibility in lists and fighters

When users build lists and add fighters or equipment, they interact with the normal content queries that exclude pack content by default. Pack content does not appear in fighter selection dropdowns, equipment lists, or any other content-driven interface unless the application explicitly uses `with_packs()` to include specific packs.

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

### Reviewing pack activity

To review the history of changes to a pack, navigate to the pack's detail page in the application and scroll to the Activity section. For the full history, click "View all". This shows a chronological feed of all pack and item changes.

In the admin, you can also review history by navigating to the historical records for `CustomContentPack` or `CustomContentPackItem` through the History link on any record.
