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

### `CustomContentPackAttachment`

A supplementary file attached to a pack -- for example a scenario PDF, campaign rules document, or a reference image. Unlike `CustomContentPackItem`, this is **not** a polymorphic link to a content model; it stores an uploaded file directly. This lets a pack ship a full campaign package (rules + scenarios + reference sheets) alongside its structured content.

| Field | Type | Description |
|-------|------|-------------|
| `pack` | ForeignKey (`CustomContentPack`) | The pack this file belongs to. Deleting a pack cascades to delete its attachments. |
| `file` | FileField | The uploaded file. Stored with a UUID filename via the shared `upload_to` helper (local filesystem in dev, GCS in production). |
| `original_filename` | CharField | The filename as uploaded, shown to users. |
| `file_size` | PositiveIntegerField | Size in bytes, used for display and quota accounting. |
| `content_type` | CharField | The MIME type, captured from the upload. |
| `title` | CharField (optional) | A display title. Falls back to `original_filename` when blank (`display_name`). |
| `description` | TextField (optional) | A short caption shown beside the file. |
| `order` | PositiveIntegerField | Sort order within the pack's file list. |
| `owner` | ForeignKey (User) | The user who uploaded the file. Inherited from `AppBase`. |

#### Constraints and validation

- **Allowed types:** PDF and raster images only (`application/pdf`, JPEG, PNG, GIF, WebP). Validated in `clean()`.
- **SVG is deliberately excluded.** Attachments are served from a public CDN via direct links (no `Content-Disposition: attachment`), so a file served as `image/svg+xml` would render as a document and execute any embedded `<script>` -- a stored-XSS vector. Raster images render inert and PDFs open in the viewer.
- **Extension is validated too.** The stored object keeps the user-supplied extension and the CDN derives the served `Content-Type` from it, so a file named `evil.svg` uploaded with a spoofed `image/png` content type would still be served as SVG. `clean()` rejects any extension outside `{pdf, jpg, jpeg, png, gif, webp}`, closing that spoofing path.
- **Size cap:** 20 MB per file (`PACK_ATTACHMENT_MAX_FILE_SIZE`).
- **Per-pack cap:** at most 5 active attachments per pack (`PACK_ATTACHMENT_MAX_PER_PACK`), enforced in the upload view.
- **Daily quota:** a per-user 100 MB/day upload budget (`PACK_ATTACHMENT_DAILY_QUOTA`), tracked separately from the image-upload quota on `UploadedFile`.
- **Soft delete:** removing a file archives it (`archived=True`) rather than hard-deleting; archived files are hidden from everyone.

#### Permissions

Uploading and removing files requires pack **edit** permission (`pack.can_edit` -- owner or an editor). Downloading is available to anyone who can **view** the pack (`pack.can_view`), matching the rest of the pack detail page.

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
- A **Files** section listing any attachments as download links (with filename, size, and optional caption). Anyone who can view the pack sees the downloads; pack editors additionally see an "Add" control and a "Remove" link per file. The section is hidden for non-editors when the pack has no files.
- A recent activity feed showing the last 5 changes, with a link to the full activity history

Pack owners see an "Edit" button. Unlisted packs return a 404 for users who are not the owner.

Editors upload files at `/pack/<id>/attachments/add/` (a standard multipart form, capped at 5 files per pack) and remove them at `/pack/<id>/attachment/<attachment_id>/delete/`. See [`CustomContentPackAttachment`](#customcontentpackattachment) above for the validation and storage rules.

### Creating and editing packs

Users create packs at `/packs/new/`. The form includes fields for name, summary (rich text), description (rich text), and the listed toggle. The pack is automatically owned by the current user.

Editing a pack at `/pack/<id>/edit/` uses the same form. Only the pack owner can edit it.

### Editing pack content items

When pack editors author content items inside a pack (special rules, gear, weapons, weapon traits, weapon accessories, skills, gang attribute values, houses, psyker disciplines and psyker powers), the **description** field uses the TinyMCE rich-text editor with text formatting, links, and lists. Image insertion is deliberately disabled in these per-item description editors -- the descriptions are short and sit in a dense listing -- so the image toolbar button, insert-menu entry, plugin, and quick-insert bar are all removed. The main pack summary/description editor at the pack level still supports images. Descriptions are stored as HTML and rendered as sanitised rich text on the pack detail page (any legacy embedded images are visually capped to a small thumbnail).

The `PackAttachment` caption is intentionally left as a plain textarea.

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
