# View Audit: Fighter Stats Edit

## Metadata

| Field            | Value                                                    |
| ---------------- | -------------------------------------------------------- |
| URL pattern      | `/list/<id>/fighter/<fid>/stats`                         |
| Template         | `core/list_fighter_stats_edit.html`                      |
| Extends          | `core/layouts/base.html`                                 |
| Includes         | `core/includes/back.html`                                |
| Template tags    | `allauth`, `custom_tags`                                 |
| Form rendering   | Manual per-field inside a table                          |
| Has JS           | No                                                       |

## Components Found

### Navigation

- **Back button** (`core/includes/back.html`): Breadcrumb-style back link using `return_url`. Text is "Back".
- **No common header**: Unlike XP edit, injuries, narrative, notes, and advancements views, this view does NOT include `list_common_header.html`. It only has a simple back link. No fighter switcher.
- **No fighter switcher**: Not included because the common header is absent.

### Cards

| Card               | Classes                | Content                                       |
| ------------------- | ---------------------- | --------------------------------------------- |
| Stat overrides card | `card` > `card-body`   | Title, help text, table of stat override fields |

### Tables

- `table.table.table-borderless.table-sm` inside a `div.table-responsive`
- Columns: Stat, Short, Base Value, Override
- Rows use `align-middle` and conditionally `border-top` via `field.field.is_first_of_group`
- Base value cells use `text-muted`

### Forms

- `form.vstack.gap-3` with explicit `action` attribute pointing to the named URL
- Hidden `return_url` input for redirect after save
- CSRF token
- Error display: per-field `div.invalid-feedback.d-block` and a page-level `div.alert.alert-danger`
- Card-title: `h5.card-title.mb-3`
- Help text: `p.text-muted.mb-3` (not `form-text` class -- inconsistency)

### Buttons

| Label         | Element    | Classes            | Notes                      |
| ------------- | ---------- | ------------------ | -------------------------- |
| Save Changes  | `button`   | `btn btn-primary`  | No `btn-sm`                |
| Cancel        | `a`        | `btn btn-link`     | Links to `return_url`      |

### Icons

- None in the primary template.

## Typography Usage

| Element          | Tag    | Classes              | Text example                       |
| ---------------- | ------ | -------------------- | ---------------------------------- |
| Page heading     | `h1`   | `h3`                 | "Edit Stats: {name}"              |
| Card title       | `h5`   | `card-title mb-3`    | "Stat Overrides"                  |
| Help text        | `p`    | `text-muted mb-3`    | "Leave fields empty to use..."    |
| Table headers    | `th`   | (none)               | "Stat", "Short", "Base Value"     |
| Base values      | `td`   | `text-muted`         | Stat default values                |

### Notes

- `h1.h3` pattern is used for the page heading (semantic h1 styled as h3), which is the correct pattern per the codebase conventions for edit pages.

## Colour Usage

| Purpose           | Colour token         | Bootstrap class     |
| ----------------- | -------------------- | ------------------- |
| Help text         | Muted                | `text-muted`        |
| Base stat values  | Muted                | `text-muted`        |
| Error alert       | Danger               | `alert alert-danger` |
| Error feedback    | Danger (via BS)      | `invalid-feedback`  |

## Spacing Values

| Location                  | Classes                                     |
| ------------------------- | ------------------------------------------- |
| Outer column              | `col-12 col-md-8 col-lg-6 px-0 vstack gap-3` |
| Card title                | `card-title mb-3`                           |
| Help text                 | `text-muted mb-3`                           |
| Button wrapper            | `mt-3`                                      |

## Custom CSS

- `border-top` conditionally applied via `is_first_of_group` to separate stat groups in the table. This is template logic, not a custom class.

## Inconsistencies

1. **No common header**: This is the only edit view in this group that uses `back.html` instead of `list_common_header.html`. XP, injuries, narrative, notes, and advancements all include the common header. This means the user loses the gang stats bar and fighter switcher on this page.
2. **Help text class**: Uses `p.text-muted.mb-3` for help text in the card, rather than the Bootstrap `form-text` class used consistently in other forms (notes, narrative, advancement select).
3. **Error alert uses `alert` class**: The convention from CLAUDE.md says "Avoid `alert` classes - use `border rounded p-2` instead", but this view uses `alert alert-danger` for `error_message`. The advancement flow also uses `alert` extensively, so this is a systemic inconsistency with the stated convention.
4. **Button container**: Uses `div.mt-3` (no flex), whereas XP edit uses `div.hstack.gap-2.mt-3.align-items-center`. The button and cancel link are just inline elements inside a plain div.
5. **Submit label**: "Save Changes" vs "Update XP" (XP edit) vs "Save" (narrative/notes). Three different labels for the same action class across this group.
6. **`allauth` tag loaded**: The `allauth` template tag library is loaded but not used in this template. Unnecessary import.

## Accessibility Notes

- Table uses proper `<thead>` and `<th>` elements.
- Error messages use `role="alert"` on the page-level alert.
- Per-field errors use `invalid-feedback` which is visually associated but not programmatically linked to inputs via `aria-describedby`.
- The form has no `aria-label`.
- Back button is rendered as a breadcrumb with `aria-label="breadcrumb"` and `aria-current="page"`.
