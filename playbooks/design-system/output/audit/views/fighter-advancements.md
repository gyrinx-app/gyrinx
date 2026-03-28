# View Audit: Fighter Advancements

## Metadata

| Field            | Value                                                        |
| ---------------- | ------------------------------------------------------------ |
| URL pattern      | `/list/<id>/fighter/<fid>/advancements/`                     |
| Template         | `core/list_fighter_advancements.html`                        |
| Extends          | `core/layouts/base.html`                                     |
| Includes         | `core/includes/list_common_header.html` (with fighter switcher) |
| Template tags    | `allauth`                                                    |
| Form rendering   | No form; this is a list/management view                      |
| Has JS           | No                                                           |

## Components Found

### Navigation

- **Common header** (`list_common_header.html`): Included with `link_list="true"`, `fighter=fighter`, `fighter_url_name="core:list-fighter-advancements"`. Fighter switcher is active.
- **"Add XP" link**: Inline link in the XP summary section, visible only to the list owner.

### Badges

| Element           | Classes                   | Context           |
| ----------------- | ------------------------- | ----------------- |
| Current XP        | `badge text-bg-primary`   | Inside list item  |
| Total XP          | `badge text-bg-secondary` | Inside list item  |

### Lists

- `ul.fs-5.mb-3.list-group.list-group-flush` containing two `li.list-group-item` elements for XP display. This is identical to the XP edit view's XP summary.

### Tables

- `table.table.table-borderless.table-sm` inside `div.table-responsive`
- Columns: Type, Advancement, XP, Rating, Actions (conditionally, with `visually-hidden` header)
- Owner-only column for actions using `{% if list.owner_cached == user %}`

### Links

| Element         | Classes                                                                        | Context            |
| --------------- | ------------------------------------------------------------------------------ | ------------------ |
| Add XP          | `fs-7 link-secondary link-underline-opacity-25 link-underline-opacity-100-hover ms-2` | Inline in XP list  |
| Remove          | `link-secondary icon-link link-underline-opacity-25 link-underline-opacity-100-hover` | Per-advancement    |

### Buttons

| Label            | Element | Classes            | Notes                      |
| ---------------- | ------- | ------------------ | -------------------------- |
| Add Advancement  | `a`     | `btn btn-primary`  | Has `bi-plus-lg` icon      |
| Cancel           | `a`     | `btn btn-link`     | Links to list with anchor  |

### Icons

| Icon       | Class          | Context                    |
| ---------- | -------------- | -------------------------- |
| Plus       | `bi-plus-lg`   | Add Advancement button     |
| Trash      | `bi-trash`     | Remove advancement link    |

## Typography Usage

| Element           | Tag    | Classes        | Text example                    |
| ----------------- | ------ | -------------- | ------------------------------- |
| Page heading      | `h2`   | (none)         | "Advancements for {name}"     |
| Table headers     | `th`   | (none)         | "Type", "Advancement", etc.    |
| Empty state       | `p`    | `text-muted`   | "No advancements yet."        |
| XP link           | `a`    | `fs-7` + links | "Add XP"                       |
| Remove link       | `a`    | `fs-7` + links | "Remove"                       |

### Inconsistency

- Uses `<h2>` with no classes (like XP edit), not `<h1 class="h3">` like stats/injuries/narrative/notes views.

## Colour Usage

| Purpose             | Colour token       | Bootstrap class                    |
| ------------------- | ------------------ | ---------------------------------- |
| Current XP badge    | Primary            | `text-bg-primary`                  |
| Total XP badge      | Secondary          | `text-bg-secondary`                |
| Empty state text    | Muted              | `text-muted`                       |
| Remove link         | Secondary          | `link-secondary`                   |
| Action cells        | (default)          | `text-end fs-7`                    |

## Spacing Values

| Location                | Classes                                       |
| ----------------------- | --------------------------------------------- |
| Outer column            | `col-12 col-md-8 col-lg-6 px-0 vstack gap-3` |
| XP list                 | `fs-5 mb-3 list-group list-group-flush`       |
| Add XP link             | `ms-2`                                        |
| Action cell             | `text-end fs-7`                               |
| Bottom button area      | `d-flex align-items-center`                   |

## Custom CSS

- `fs-7`: Custom font size class used for the "Add XP" link and action cells.
- No other custom classes.

## Inconsistencies

1. **Heading level**: Uses `<h2>` (no class), same as XP edit, but different from `<h1 class="h3">` used by stats/injuries/narrative/notes. Semantic and visual mismatch.
2. **Permission check pattern**: Uses `{% if list.owner_cached == user %}` to conditionally show owner-only columns. This works but means the table structure (number of columns) changes based on ownership, which could affect layout.
3. **Empty state style**: Uses `p.text-muted` ("No advancements yet.") while injuries uses `div.alert.alert-info` with an icon. Different empty state patterns within the same feature area.
4. **Button container**: Uses `div.d-flex.align-items-center` while XP edit uses `div.hstack.gap-2.mt-3.align-items-center` and stats/narrative/notes use `div.mt-3`. Three different patterns for the same conceptual container.
5. **Cancel link destination**: Uses `{% url 'core:list' list.id %}#{{ fighter.id }}` (with hash anchor, like injuries) rather than `return_url` (like stats/narrative/notes) or plain list URL (like XP edit).
6. **Remove link**: Uses `link-secondary` while injuries uses `link-danger` for the same "Remove" action. Inconsistent colour semantics for destructive actions.
7. **Icon class format**: Uses `bi-trash` and `bi-plus-lg` (single-class prefix format), consistent within this template but inconsistent with injuries' `bi bi-pencil`.
8. **XP summary duplicated**: The XP badges/list-group is nearly identical between this view and XP edit. This is presentation logic duplication that could be extracted to a shared include.

## Accessibility Notes

- Actions column uses `visually-hidden` text header, good for screen readers.
- "Remove" link has a `title` attribute ("Remove advancement") providing additional context.
- `icon-link` class used on the remove link, which is Bootstrap's built-in icon link pattern.
- Table uses proper `<thead>`/`<tbody>` structure.
- No `aria-label` on the table itself.
- Archived advancements hide the remove link but still render the table cell, maintaining consistent layout.
