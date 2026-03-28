# View Audit: Pack Lists

## Metadata

| Field         | Value                                                     |
|---------------|-----------------------------------------------------------|
| URL           | `/pack/<id>/lists/`                                       |
| Template      | `core/pack/pack_lists.html`                               |
| Extends       | `core/layouts/base.html` > `core/layouts/foundation.html` |
| Includes      | `core/includes/back.html`, `core/includes/lists_filter.html`, `core/includes/pagination.html` |
| Template tags | `allauth`, `custom_tags`, `tz`                            |

## Components Found

### Navigation

- **Back button:** `core/includes/back.html` with `url=pack.get_absolute_url` and `text=pack.name`
- **Tab navigation:** `ul.nav.nav-tabs.mb-4` with `li.nav-item` > `a.nav-link` (All / Lists / Campaign Gangs)
- **Pagination:** Standard `core/includes/pagination.html`

### Forms

- **Subscribe form:** Inline `<form method="post">` with hidden `list_id` + `return_url`, `.btn.btn-primary.btn-sm` "Add" button
- **Unsubscribe form:** Inline `<form method="post">` with hidden `list_id` + `return_url`, `.btn.btn-outline-danger.btn-sm` "Remove" button
- **Lists filter:** `core/includes/lists_filter.html` with `hide_toggles=True` -- full version with search input group, house dropdown filter, Update/Reset buttons

### Badges

- `.badge.text-bg-success` with `bi-award` icon for "Campaign: {name}"
- `.badge.text-bg-secondary` with `bi-list-ul` icon for "List" type

### Buttons

- `.btn.btn-primary.btn-sm` -- "Add" subscribe button
- `.btn.btn-outline-danger.btn-sm` -- "Remove" unsubscribe button
- `.btn.btn-primary` -- Search submit (full-size, from lists_filter include)
- `.btn.btn-outline-primary.btn-sm.dropdown-toggle` -- "House" filter dropdown trigger
- `.btn.btn-link.icon-link.btn-sm` -- "Update" filter
- `.btn.btn-link.text-secondary.icon-link.btn-sm` -- "Reset" filter

### Dropdowns

- House filter dropdown: `.dropdown-menu.shadow-sm.p-2.fs-7.dropdown-menu-mw` with checkboxes

### Lists

- Both subscribed and available lists use `div.vstack.gap-4` with `div.hstack.gap-3` rows
- List metadata uses `div.hstack.column-gap-2.row-gap-1.flex-wrap`

### Sections

- `<section>` elements for "Subscribed" and "Available" areas

### Icons

- `bi-award` (Campaign badge)
- `bi-list-ul` (List badge)
- `bi-search` (Search input)
- `bi-arrow-clockwise` (Update filter)

### Other

- **Subscribed section heading:** `h2.h5.mb-2`
- **Available section heading:** `h2.h5.mb-3` (different margin from subscribed)
- **Empty state:** `div.py-2.text-muted.small` for "No lists found."
- **Tab active state:** Uses `aria-current="page"` for active tab

## Typography Usage

| Element                 | Tag / Class                      | Notes                          |
|-------------------------|----------------------------------|--------------------------------|
| Page title              | `<h1 class="h3 mb-1">`          | Correct `.h3` override        |
| Subtitle                | `p.text-muted.small.mb-0`       | Muted small text               |
| Section headings        | `<h2 class="h5 mb-2">` / `<h2 class="h5 mb-3">` | Inconsistent margins |
| List names              | `<h3 class="mb-0 h5">`          | Semantic `h3` styled as `h5`  |
| Last edit timestamp     | `div.text-muted.small`          | Muted small                    |
| Filter labels           | `.form-check-label.fs-7`        | Custom `.fs-7`                 |

## Colour Usage

| Usage                | Class / Value            | Notes                          |
|----------------------|--------------------------|--------------------------------|
| Campaign badge       | `.text-bg-success`       | Green for campaign             |
| List badge           | `.text-bg-secondary`     | Grey for plain list            |
| Metadata text        | `.text-muted`            | Consistent muted               |
| Subscribe button     | `.btn-primary`           | Blue primary                   |
| Unsubscribe button   | `.btn-outline-danger`    | Red outline for destructive    |
| Empty state          | `.text-muted`            | Consistent                     |
| House filter dropdown| `.btn-outline-primary`   | Blue outline                   |

## Spacing Values

| Location                | Class(es)                         | Value              |
|-------------------------|-----------------------------------|--------------------|
| Outer container         | `.col-12.col-xl-8.px-0.vstack.gap-4` | 1.5rem vert gap |
| Subscribed list rows    | `.vstack.gap-4`                   | 1.5rem gap         |
| Available list rows     | `.vstack.gap-4`                   | 1.5rem gap         |
| List item row           | `.hstack.gap-3`                   | 1rem gap           |
| Metadata row            | `.hstack.column-gap-2.row-gap-1`  | 0.5rem / 0.25rem   |
| Filter grid             | `.grid.mb-3`                      | 1rem bottom        |
| Tabs                    | `.mb-4`                           | 1.5rem bottom      |
| Subscribed heading      | `.mb-2`                           | 0.5rem bottom      |
| Available heading       | `.mb-3`                           | 1rem bottom        |

## Custom CSS

| Class              | Source          | Description                          |
|--------------------|-----------------|--------------------------------------|
| `.fs-7`            | `styles.scss`   | Custom font size: `base * 0.9`       |
| `.dropdown-menu-mw`| `styles.scss`  | Min/max width for dropdown menus     |

## Inconsistencies

1. **Section heading margins differ:** "Subscribed" uses `.mb-2` while "Available" uses `.mb-3`. Both are `h2.h5` but have inconsistent bottom spacing.
2. **Subscribed and available list rows are structurally identical** but the subscribed section lacks the tab navigation and filter. This is intentional but the visual weight difference could confuse users.
3. **Search button in lists_filter is full-size `.btn.btn-primary`** without `.btn-sm`, matching the packs_filter inconsistency.
4. **Badge pattern uses `.text-bg-*`** (correct per design system) while the packs index uses `.bg-secondary` (without `.text-bg-` prefix). Cross-template inconsistency.
5. **The "Remove" button uses `.btn-outline-danger`** while the pack detail page uses `.link-danger` for archive actions. Different component types for similar destructive intent.
6. **List item layout is duplicated** between subscribed and available sections with near-identical markup. This could be extracted to a shared include.
7. **Empty state uses `div.py-2.text-muted.small`** while pack detail empty states use `p.text-center.text-secondary.mb-0`. Different element, alignment, colour class, and size for the same pattern.

## Accessibility Notes

- Back button inherits breadcrumb ARIA
- Tabs use `aria-current="page"` for active state
- Form checkboxes in house filter have associated `<label>` elements
- Subscribe/unsubscribe forms have clear button labels
- Dropdown has `aria-expanded` and `data-bs-auto-close`
- Missing: Tab panel content is not wrapped in a `role="tabpanel"` element
- Missing: No `aria-label` on subscribe/unsubscribe forms to distinguish them
- Missing: Hidden inputs `name="return_url"` expose internal routing names
