# View Audit: Campaigns Index

## Metadata

- **URL:** `/campaigns/`
- **Template:** `core/campaign/campaigns.html`
- **Template chain:** `core/layouts/foundation.html` > `core/layouts/base.html` > `core/campaign/campaigns.html`
- **Includes:** `core/includes/campaigns_filter.html` (full mode), `core/includes/pagination.html`, `core/campaign/includes/status.html`

## Components Found

### Buttons

| Text | Classes | Variant | Size | Icon | Notes |
|------|---------|---------|------|------|-------|
| Search | `btn btn-primary` | Primary | Default | None | In full-mode campaigns_filter.html; no `btn-sm` |
| Status (dropdown toggle) | `btn btn-outline-primary btn-sm dropdown-toggle` | Outline Primary | Small | None | Status filter dropdown |
| Update (status dropdown) | `btn btn-link icon-link btn-sm` | Link | Small | `bi-arrow-clockwise` | Inside status dropdown |
| Reset (status dropdown) | `btn btn-link text-secondary icon-link btn-sm` | Link (secondary) | Small | None | Inside status dropdown |
| Update (main filters) | `btn btn-link icon-link btn-sm` | Link | Small | `bi-arrow-clockwise` | Main filter bar |
| Reset (main filters) | `btn btn-link text-secondary icon-link btn-sm` | Link (secondary) | Small | None | Main filter bar |
| Create a new Campaign (link) | plain `<a>` | Default link | N/A | None | Subtitle paragraph link |

### Cards

None found.

### Navigation

None found (no tabs unlike lists page).

### Forms

| Form ID | Action | Method | Classes | Notes |
|---------|--------|--------|---------|-------|
| search | `core:campaigns` + `#search` | GET | `grid g-col-12` | Full filter form |

### Form Controls

| Control | Type | Classes | Notes |
|---------|------|---------|-------|
| Search input | `search` | `form-control` | In input group |
| Status checkboxes | `checkbox` | `form-check-input` | Inside dropdown |
| Your Campaigns Only toggle | `checkbox` | `form-check-input` | `form-switch`, `data-gy-toggle-submit`; disabled for anon users |
| Participating Only toggle | `checkbox` | `form-check-input` | `form-switch`, `data-gy-toggle-submit`; disabled for anon users |
| Archived Only toggle | `checkbox` | `form-check-input` | `form-switch`, `data-gy-toggle-submit`; disabled for anon users |

### Icons (Bootstrap Icons)

| Icon class | Context | Purpose |
|------------|---------|---------|
| `bi-search` | Search input group | Search indicator |
| `bi-person` | Campaign owner | Owner indicator |
| `bi-archive` | Archived campaign | Archive indicator |
| `bi-chevron-right` | Mobile row action | Forward navigation |
| `bi-arrow-clockwise` | Update buttons | Refresh action |

### Badges

| Text | Classes | Context |
|------|---------|---------|
| "Pre-Campaign" | `badge bg-secondary` | Via status.html include |
| "In Progress" | `badge bg-success` | Via status.html include |
| "Post-Campaign" | `badge bg-secondary` | Via status.html include |

### Dropdowns

| Trigger | Menu classes | Notes |
|---------|-------------|-------|
| Status button | `dropdown-menu shadow-sm p-2 fs-7 dropdown-menu-mw` | Same pattern as lists house dropdown |

### Pagination

| Component | Classes | Notes |
|-----------|---------|-------|
| Pagination nav | `pagination justify-content-center` | Via pagination.html include |

### Tooltips

| Element | Tooltip | Notes |
|---------|---------|-------|
| Toggle wrappers (anon) | "Only available to signed-in users" | `data-bs-toggle="tooltip" data-bs-placement="top"` on parent `<div>` |

### Other Components

| Component | Classes | Notes |
|-----------|---------|-------|
| Campaign summary | `mb-last-0 text-secondary` | Uses custom `mb-last-0` class |
| Archived indicator | `text-muted` on icon + text | Inline text with archive icon |

## Typography Usage

| Element | Classes applied | Semantic role |
|---------|----------------|---------------|
| Page title | `<h1>` with `mb-1` | Page heading |
| Subtitle | `<p>` with `fs-5 col-12 col-md-6 mb-0` | Page description |
| Campaign name | `<h2>` with `mb-0 h5` | Item heading |
| Owner name | plain `<div>` with icon | Metadata |
| Campaign summary | `<div>` with `mb-last-0 text-secondary` | Description text |
| Archived text | `<div>` with `fs-7 text-secondary` | Small metadata |
| Toggle labels | `form-check-label fs-7 mb-0` | Form labels |

## Colour Usage

| Element | Property | Source | Semantic purpose |
|---------|----------|-------|-----------------|
| Status badges | background | `bg-success` / `bg-secondary` | Status indicator |
| Campaign summary | color | `text-secondary` | De-emphasised text |
| Archive icon | color | `text-muted` | De-emphasised indicator |
| Archived row text | color | `fs-7 text-secondary` | Metadata |
| Reset links | color | `text-secondary` | De-emphasised action |

## Spacing Values

| Element | Property | Source class | Notes |
|---------|----------|-------------|-------|
| Outer wrapper | padding | `px-0` | Removes horizontal padding |
| Outer vstack | gap | `vstack gap-4` | 1.5rem gap |
| Header | margin-bottom | `mb-1` | Tight bottom margin |
| Campaign rows | gap | `hstack gap-3` | Row items |
| Campaign row inner | gap | `d-flex flex-column gap-1` | Vertical items |
| Metadata | gap | `hstack column-gap-2 row-gap-1 flex-wrap` | Inline badges/text |
| Filter bar | gap | `hstack gap-3 flex-wrap` | Filter controls |
| Chevron right | padding | `p-3` | Touch target |
| Empty state | padding | `py-2` | Vertical padding |

## Custom CSS

| Class name | Defined in | Properties | Used on elements |
|------------|-----------|------------|-----------------|
| `dropdown-menu-mw` | `styles.scss` | `min-width: 25em; width: 100%; max-width: 35em` | Status filter dropdown |
| `mb-last-0` | `styles.scss` | `> :last-child { margin-bottom: 0 !important }` | Campaign summary div |
| `fs-7` | `styles.scss` | `font-size: 0.7875rem` | Toggle labels, dropdown menu, archived text |

## Inconsistencies

| Issue | Elements involved | Description | Severity |
|-------|-------------------|-------------|----------|
| Badge class inconsistency | Status badges vs list/home badges | Status.html uses `badge bg-secondary` / `badge bg-success` while lists use `badge text-bg-primary` / `badge text-bg-secondary`. The `bg-*` pattern is older Bootstrap; `text-bg-*` is the recommended utility. | Medium |
| No tabs unlike Lists page | Campaigns page vs Lists page | Lists has tab navigation (All/Lists/Campaign Gangs) but Campaigns has no equivalent, despite both using filters. Not necessarily wrong, but inconsistent in page structure. | Low |
| Missing `aria-label` on chevron | Mobile chevron link | No `aria-label` on the mobile chevron-right stretched-link, unlike the lists page which has one. | Medium |
| "Create a new Campaign" link style | Plain `<a>` in subtitle | Same as lists page -- plain link without utility classes, different from homepage `icon-link linked` pattern. | Low |

## Accessibility Notes

- Disabled toggles for anonymous users have tooltip explanation via `data-bs-toggle="tooltip"`.
- Search input has `aria-label="Search campaigns"`.
- Status dropdown has `aria-expanded="false"`.
- Toggle switches use `role="switch"`.
- Mobile chevron link lacks `aria-label` (accessibility gap).
- Pagination uses semantic `<nav>` with `aria-label`.
