# View Audit: Fighter XP Edit

## Metadata

| Field            | Value                                                        |
| ---------------- | ------------------------------------------------------------ |
| URL pattern      | `/list/<id>/fighter/<fid>/xp`                                |
| Template         | `core/list_fighter_xp_edit.html`                             |
| Extends          | `core/layouts/base.html`                                     |
| Includes         | `core/includes/list_common_header.html` (with fighter switcher) |
| Template tags    | `custom_tags`                                                |
| Form rendering   | `{{ form.as_div }}`                                          |
| Has JS           | No                                                           |

## Components Found

### Navigation

- **List common header** (`list_common_header.html`): Full gang header with stats table, owner link, campaign link, and refresh button. Passed `link_list="true"` and `fighter_url_name` for fighter switcher.
- **Fighter switcher** (`fighter_switcher.html`): Dropdown to switch between fighters, rendered via the common header.
- **No back button**: Unlike other views in this group, this view relies solely on the common header for navigation context. No breadcrumb-style back button.

### Badges

| Element                      | Classes                    | Context          |
| ---------------------------- | -------------------------- | ---------------- |
| Current XP badge             | `badge text-bg-primary`    | Inside list item |
| Total XP badge               | `badge text-bg-secondary`  | Inside list item |

### Lists

- `ul.fs-5.mb-3.list-group.list-group-flush` containing two `li.list-group-item` elements for current and total XP display.

### Forms

- `form.vstack.gap-3` with `method="post"`
- `{{ form.as_div }}` -- uses Django's default div-based rendering (no custom field layout)
- CSRF token included

### Buttons

| Label      | Element    | Classes                 | Notes                    |
| ---------- | ---------- | ----------------------- | ------------------------ |
| Update XP  | `button`   | `btn btn-primary`       | Submit button, no `btn-sm` |
| Cancel     | `a`        | `btn btn-link`          | Links to list detail     |

### Icons

- None in the primary template (icons come from the common header include).

## Typography Usage

| Element | Tag    | Classes    | Text example              |
| ------- | ------ | ---------- | ------------------------- |
| Heading | `h2`   | (none)     | "Edit XP for {name}"     |
| XP text | `span` | `badge`    | "{n} XP"                 |
| Labels  | inline | (none)     | "Current", "Total"       |

### Inconsistencies in Typography

- The heading uses a plain `h2` with no utility class, while sibling views (`stats_edit`, `injuries_edit`, `narrative_edit`, `notes_edit`) use `h1.h3` -- a significant inconsistency in heading level and visual size.
- Title block: `"XP - {{ fighter.fully_qualified_name }}"` uses `fully_qualified_name` while other views use `fighter.name` or `form.instance.name`.

## Colour Usage

| Purpose             | Colour token          | Bootstrap class        |
| ------------------- | --------------------- | ---------------------- |
| Current XP badge    | Primary (blue)        | `text-bg-primary`      |
| Total XP badge      | Secondary (grey)      | `text-bg-secondary`    |

No custom colours. All colour is delivered through Bootstrap contextual classes.

## Spacing Values

| Location                  | Classes                              |
| ------------------------- | ------------------------------------ |
| Outer column              | `col-12 col-md-8 col-lg-6 px-0 vstack gap-3` |
| XP list                   | `fs-5 mb-3 list-group list-group-flush` |
| Form                      | `vstack gap-3`                       |
| Button row                | `hstack gap-2 mt-3 align-items-center` |

## Custom CSS

No custom CSS classes used beyond what the common header introduces (e.g., `fighter-switcher-btn`, `fighter-switcher-menu`, `linked`).

## Inconsistencies

1. **Heading level**: Uses `<h2>` while sibling edit views use `<h1 class="h3">`. This is both a semantic and visual inconsistency.
2. **No `btn-sm` on submit button**: Convention from CLAUDE.md states primary buttons should use `btn btn-primary btn-sm`, but this view uses `btn btn-primary` (full size). Other views in this batch also omit `btn-sm`, but the convention mismatch is notable.
3. **Form rendering**: Uses `{{ form.as_div }}` (Django default rendering) while sibling views render fields manually with `form-label`, `form-text`, etc. This means error display, help text, and label styling are inconsistent with other edit views.
4. **Column widths**: Uses `col-12 col-md-8 col-lg-6` matching some peers, but the injuries view uses `col-lg-8` -- inconsistent max widths within the same feature group.
5. **Title meta**: Uses `fighter.fully_qualified_name` in `<title>` while other views use `fighter.name`.
6. **Cancel link**: Points to list detail page, not a `return_url` variable as used in stats/narrative/notes views. This means cancel from this page always goes to the list, not where the user came from.

## Accessibility Notes

- No `aria-label` on the form element.
- Badge text ("XP") is adjacent to the label text ("Current"/"Total"), which is readable by screen readers.
- The common header provides tooltip `aria-label` attributes on stat abbreviations.
- Cancel link is a plain anchor styled as a button (`btn btn-link`), which is acceptable for navigation.
