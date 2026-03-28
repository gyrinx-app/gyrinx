# View Audit: Lists Index

## Metadata

- **URL:** `/lists/`
- **Template:** `core/lists.html`
- **Template chain:** `core/layouts/foundation.html` > `core/layouts/base.html` > `core/lists.html`
- **Includes:** `core/includes/lists_filter.html` (full mode), `core/includes/pagination.html`

## Components Found

### Buttons

| Text | Classes | Variant | Size | Icon | Notes |
|------|---------|---------|------|------|-------|
| Search | `btn btn-primary` | Primary | Default | None | In full-mode lists_filter.html input group; no `btn-sm` |
| House (dropdown toggle) | `btn btn-outline-primary btn-sm dropdown-toggle` | Outline Primary | Small | None | Filter dropdown trigger |
| Update (house dropdown) | `btn btn-link icon-link btn-sm` | Link | Small | `bi-arrow-clockwise` | Inside house dropdown |
| Reset (house dropdown) | `btn btn-link text-secondary icon-link btn-sm` | Link (secondary) | Small | None | Inside house dropdown |
| Update (main filters) | `btn btn-link icon-link btn-sm` | Link | Small | `bi-arrow-clockwise` | Main filter bar |
| Reset (main filters) | `btn btn-link text-secondary icon-link btn-sm` | Link (secondary) | Small | None | Main filter bar |
| Create a new List (link) | plain `<a>` | Default link | N/A | None | Subtitle paragraph link, unstyled |

### Cards

None found.

### Navigation

| Component | Classes | Notes |
|-----------|---------|-------|
| Tabs (All / Lists / Campaign Gangs) | `nav nav-tabs` | Bootstrap nav tabs; active state uses `nav-link active` with `aria-current="page"` |

### Forms

| Form ID | Action | Method | Classes | Notes |
|---------|--------|--------|---------|-------|
| search | `core:lists` + `#search` | GET | `grid g-col-12` | Full filter form with CSS grid layout |

### Form Controls

| Control | Type | Classes | Notes |
|---------|------|---------|-------|
| Search input | `search` | `form-control` | In input group |
| House checkboxes | `checkbox` | `form-check-input` | role="switch"; inside dropdown |
| Your Lists Only toggle | `checkbox` | `form-check-input` | `form-switch`, `data-gy-toggle-submit` |
| Archived Only toggle | `checkbox` | `form-check-input` | `form-switch`, `data-gy-toggle-submit` |

### Icons (Bootstrap Icons)

| Icon class | Context | Purpose |
|------------|---------|---------|
| `bi-search` | Search input group | Search indicator |
| `bi-person` | List owner | Owner indicator |
| `bi-award` | Campaign gang badge | Campaign indicator |
| `bi-list-ul` | List badge | List type indicator |
| `bi-chevron-right` | Mobile row action | Forward navigation |
| `bi-arrow-clockwise` | Update buttons | Refresh action |

### Badges

| Text | Classes | Context |
|------|---------|---------|
| Credits value | `badge text-bg-primary` | List row metadata |
| "Campaign: {name}" | `badge text-bg-success` | Campaign-mode list indicator |
| "List" | `badge text-bg-secondary` | Standard list indicator |

### Dropdowns

| Trigger | Menu classes | Notes |
|---------|-------------|-------|
| House button | `dropdown-menu shadow-sm p-2 fs-7 dropdown-menu-mw` | Custom min/max width via `dropdown-menu-mw`; `data-bs-auto-close="outside"` |

### Pagination

| Component | Classes | Notes |
|-----------|---------|-------|
| Pagination nav | `pagination justify-content-center` | Standard Bootstrap pagination |
| Page items | `page-item` / `page-item active` / `page-item disabled` | Standard states |
| Page links | `page-link` | Standard Bootstrap page-link |

### Other Components

| Component | Classes | Notes |
|-----------|---------|-------|
| Page header `<h1>` | `mb-1` | Proper semantic `<h1>` |
| Subtitle | `fs-5 col-12 col-md-6 mb-0` | Constrained width paragraph |

## Typography Usage

| Element | Classes applied | Semantic role |
|---------|----------------|---------------|
| Page title | `<h1>` with `mb-1` | Page heading |
| Subtitle | `<p>` with `fs-5 col-12 col-md-6 mb-0` | Page description |
| List name | `<h2>` with `mb-0 h5` | Item heading; semantic `<h2>` styled as `h5` |
| Owner name | plain `<div>` with icon | Metadata |
| House name | plain `<div>` | Metadata |
| Last edit | `text-muted small` | Timestamp |
| Toggle labels | `form-check-label fs-7 mb-0` | Form labels; uses custom `fs-7` size |
| House dropdown labels | `form-check-label` | Form labels; no `fs-7` -- inconsistent with toggle labels |
| Dropdown content | `fs-7` on menu | Smaller text for dropdown content |

## Colour Usage

| Element | Property | Source | Semantic purpose |
|---------|----------|-------|-----------------|
| Credits badge | background | `text-bg-primary` | Primary highlight |
| Campaign badge | background | `text-bg-success` | Campaign status |
| List badge | background | `text-bg-secondary` | List type |
| Owner link | color | default link colour | Navigational |
| Last edit | color | `text-muted` | De-emphasised |
| "Create a new List" link | color | default `<a>` styling | CTA |
| Reset links | color | `text-secondary` | De-emphasised action |

## Spacing Values

| Element | Property | Source class | Notes |
|---------|----------|-------------|-------|
| Outer wrapper | padding | `px-0` | Removes horizontal padding |
| Outer vstack | gap | `vstack gap-4` | 1.5rem gap |
| Page header | margin-bottom | `mb-1` | Tight bottom margin |
| List rows | gap | `hstack gap-3` | Horizontal gap between items |
| List row inner | gap | `d-flex flex-column gap-1` | Vertical gap within row |
| Metadata line | gap | `hstack column-gap-2 row-gap-1 flex-wrap` | Inline items |
| Filter bar | gap | `hstack gap-3 flex-wrap` | Filter controls |
| Filter input group | gap | `hstack gap-2 align-items-end` | Search and button |
| Chevron right | padding | `p-3` | Touch target |
| Empty state | padding | `py-2` | Vertical padding |

## Custom CSS

| Class name | Defined in | Properties | Used on elements |
|------------|-----------|------------|-----------------|
| `dropdown-menu-mw` | `styles.scss` | `min-width: 25em; width: 100%; max-width: 35em` | House filter dropdown menu |
| `fs-7` | `styles.scss` (via `$custom-font-sizes`) | `font-size: 0.7875rem` (0.9 * 0.875rem base) | Toggle labels, dropdown menu, filter area |

## Inconsistencies

| Issue | Elements involved | Description | Severity |
|-------|-------------------|-------------|----------|
| Search button size | Full-mode search `btn btn-primary` vs compact `btn btn-primary btn-sm` | The full-mode lists_filter omits `btn-sm` on the search button while the compact version uses it. Also inconsistent with homepage search buttons. | Medium |
| `<h2>` for list items | Item headings use `<h2>` | Multiple `<h2>` elements used for list items, same semantic level as section headings on other pages, but visually styled as `h5`. | Low |
| House dropdown label style | `form-check-label` without `fs-7` | Toggle labels outside dropdown use `fs-7` but house checkbox labels inside the dropdown do not; the dropdown itself has `fs-7` on the container. | Low |
| Link styling for "Create a new List" | Plain `<a>` without any link utility classes | Other navigational links on the homepage use `link-secondary` or `linked` classes; this one is unstyled. | Low |
| Chevron link aria-label | Present in lists template | Lists template has `aria-label="View {{ list.name }} details"` while home and campaigns templates omit it. | Low |

## Accessibility Notes

- Tab navigation uses `aria-current="page"` for the active tab.
- Search input has `aria-label="Search lists"`.
- House filter dropdown has `aria-expanded="false"`.
- Toggle switches use `role="switch"` on checkbox inputs.
- Mobile chevron links have `aria-label` with list name.
- Pagination uses `<nav aria-label="Page navigation">`.
