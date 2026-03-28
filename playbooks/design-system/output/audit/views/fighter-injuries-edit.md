# View Audit: Fighter Injuries Edit

## Metadata

| Field            | Value                                                        |
| ---------------- | ------------------------------------------------------------ |
| URL pattern      | `/list/<id>/fighter/<fid>/injuries`                          |
| Template         | `core/list_fighter_injuries_edit.html`                       |
| Extends          | `core/layouts/base.html`                                     |
| Includes         | `core/includes/list_common_header.html` (without fighter switcher) |
| Template tags    | `allauth`, `custom_tags`                                     |
| Form rendering   | No form on this page; it is a list/management view           |
| Has JS           | No                                                           |

## Components Found

### Navigation

- **Common header** (`list_common_header.html`): Included with `link_list="true"` but without `fighter` or `fighter_url_name` params, so no fighter switcher is rendered. This is an inconsistency with XP edit, narrative edit, and notes edit which do pass fighter switcher params.

### Cards

| Card                  | Classes                              | Content                                    |
| --------------------- | ------------------------------------ | ------------------------------------------ |
| Fighter state card    | `card` > `card-body`                 | State badge + "Update State" button        |
| Current injuries card | `card` > `card-header` + `card-body` | Table of injuries with remove links        |

### Badges

| Element         | Classes                                           | Context              |
| --------------- | ------------------------------------------------- | -------------------- |
| State badge     | `badge bg-warning` / `bg-danger` / `bg-success`   | Conditional on state |

Note: Uses `bg-*` instead of `text-bg-*` for badge colouring. The XP edit view uses `text-bg-primary` and `text-bg-secondary`. This is an inconsistency -- `text-bg-*` is the Bootstrap 5.3+ preferred pattern that automatically sets contrast text colour.

### Tables

- `table.table.table-sm.table-borderless` (no `table-responsive` wrapper, unlike stats edit)
- Columns: Injury name, Received date, Actions (with `visually-hidden` header)
- Notes rows use `rowspan="2"` on the injury name cell, with a second row for notes
- Notes cells: `ps-4 fs-7 text-muted` with `<em>` wrapper

### Alerts

| Type    | Classes            | Content                                          |
| ------- | ------------------ | ------------------------------------------------ |
| Info    | `alert alert-info` | "This fighter has no injuries" empty state        |

### Buttons

| Label                     | Element    | Classes                    | Notes                        |
| ------------------------- | ---------- | -------------------------- | ---------------------------- |
| Update Fighter State      | `a`        | `btn btn-secondary btn-sm` | Has pencil icon, correct `btn-sm` |
| Add Injury                | `a`        | `btn btn-primary`          | Has plus icon, no `btn-sm`   |
| Cancel                    | `a`        | `btn btn-link`             | Links to list detail with anchor |
| Remove (per injury)       | `a`        | `link-danger`              | Link style, not button       |

### Icons

| Icon                    | Class                   | Context                         |
| ----------------------- | ----------------------- | ------------------------------- |
| Pencil                  | `bi bi-pencil`          | Update state button             |
| Info circle             | `bi bi-info-circle`     | Empty state alert               |
| Plus                    | `bi bi-plus-lg`         | Add injury button               |

Note: Uses `bi bi-pencil` (two-class format) while other templates use `bi-` prefix only (single-class, e.g., `bi-plus-lg`). Both formats work, but it's an inconsistency.

## Typography Usage

| Element           | Tag      | Classes              | Text example                          |
| ----------------- | -------- | -------------------- | ------------------------------------- |
| Page heading      | `h1`     | `h3`                 | "Edit Injuries: {name}"              |
| Card header title | `h5`     | `mb-0`               | "Current Injuries"                   |
| State label       | `strong` | (none)               | "Fighter State:"                     |
| Injury notes      | `em`     | (none)               | Notes text in muted small font        |

## Colour Usage

| Purpose              | Colour token          | Bootstrap class           |
| -------------------- | --------------------- | ------------------------- |
| State: active        | Green                 | `bg-success`              |
| State: injured       | Yellow                | `bg-warning`              |
| State: dead          | Red                   | `bg-danger`               |
| Remove link          | Red                   | `link-danger`             |
| Empty state          | Blue info             | `alert alert-info`        |
| Notes text           | Muted                 | `text-muted`              |

## Spacing Values

| Location                   | Classes                                            |
| -------------------------- | -------------------------------------------------- |
| Outer column               | `col-lg-8 px-0 vstack gap-3`                      |
| State card inner           | `d-flex align-items-center justify-content-between` |
| Badge                      | `ms-2`                                             |
| Empty state icon           | `me-1`                                             |
| Notes cell                 | `ps-4 fs-7`                                        |
| Card body                  | `card-body mb-last-0`                              |

## Custom CSS

- `mb-last-0`: Custom utility from `styles.scss` that removes bottom margin from the last child. Used on `card-body` to prevent extra spacing after the table.
- `fs-7`: Custom font size (0.9 * base) defined in styles.scss. Used for injury notes.

## Inconsistencies

1. **Column width**: Uses `col-lg-8` while most other views in this group use `col-12 col-md-8 col-lg-6`. This makes the injuries view wider than sibling edit pages. Also missing `col-12` and `col-md-*` breakpoints.
2. **No fighter switcher**: Common header is included without fighter switcher params, unlike XP edit, narrative, and notes views.
3. **Badge colour format**: Uses `bg-warning`/`bg-danger`/`bg-success` instead of `text-bg-*` pattern used by XP edit badges.
4. **Icon format**: Mixes `bi bi-pencil` (two classes) and `bi-plus-lg` / `bi-info-circle` (single class with prefix).
5. **No `table-responsive`**: Table is not wrapped in `div.table-responsive`, unlike stats edit and advancements tables.
6. **Cancel link destination**: Uses `{% url 'core:list' list.id %}#{{ fighter.id }}` with a hash anchor, which is good for deep-linking but different from XP edit (no anchor) and stats/narrative/notes (uses `return_url`).
7. **`allauth` tag loaded but unused**: Same as stats edit.
8. **Uses `alert alert-info`** for empty state, which violates the convention to "Avoid `alert` classes".
9. **`btn-sm` inconsistency**: "Update Fighter State" correctly uses `btn-sm`, but "Add Injury" primary button does not.

## Accessibility Notes

- Actions column header uses `visually-hidden` span, which is good screen reader practice.
- State badge lacks explicit `aria-label`; the state text is visually present but screen readers will read the full badge text.
- Empty state alert has an icon (`bi-info-circle`) but no `role="status"` or `aria-live` attribute.
- "Remove" links have no confirmation mechanism or `aria-describedby` connecting them to the injury they remove.
- The info icon in the empty state has no `aria-hidden="true"`, so screen readers may announce "info circle" before the text.
