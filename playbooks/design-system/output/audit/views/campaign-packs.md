# View Audit: Campaign Packs

## Metadata

| Field | Value |
|---|---|
| URL | `/campaign/<id>/packs` |
| Template | `core/campaign/campaign_packs.html` |
| Extends | `core/layouts/base.html` |
| Template tags loaded | `allauth`, `custom_tags` |
| Included templates | `core/includes/back.html` |
| Complexity | Medium -- two sections (current packs, add packs) with search and grid layouts |

## Components Found

### Buttons

| Element | Classes | Variant | Context |
|---|---|---|---|
| "Add to..." dropdown toggle | `btn btn-outline-primary btn-sm dropdown-toggle` | Outline primary small | Per-pack subscribe dropdown |
| Remove pack link | icon link (no btn class) | Danger link | Per-pack remove action |
| Search submit | `btn btn-primary` | Primary (no size) | Add packs search form |
| Clear search link | `btn btn-outline-secondary` | Outline secondary (no size) | Add packs search form (conditional) |
| Add pack submit | `btn btn-sm btn-outline-primary` | Outline primary small | Per-available-pack action |

**Observations:**

- Search submit is full-size `btn-primary` while add-pack buttons are `btn-sm btn-outline-primary` -- same sizing context mismatch as campaign-add-lists
- "Add to..." dropdown toggle uses `btn-outline-primary btn-sm dropdown-toggle` (outline variant for a dropdown), which is a unique pattern on campaign pages
- Remove icon is a link (`icon-link link-danger link-underline-opacity-25 link-underline-opacity-100-hover small`) without button classes -- icon-only action

### Cards

No Bootstrap `.card` components. Custom pack cards:

- `border rounded p-2 d-flex align-items-center justify-content-between` for both current packs and available packs

**Observations:**

- This "pack card" pattern is used identically for both the allowed packs and available packs sections
- Uses `p-2` (matching archive banner) but with `d-flex` layout for horizontal content + action arrangement

### Tables

No tables used.

### Navigation

| Element | Classes | Context |
|---|---|---|
| Back breadcrumb | `breadcrumb` / `breadcrumb-item active` | Top of page, "Back to Campaign" |

### Forms

| Form | Method | Classes | Context |
|---|---|---|---|
| Subscribe form | POST | (none, inside dropdown) | Per-pack, per-list subscribe action |
| Search form | GET | `mb-3 col-12 col-md-6 col-lg-4 px-0` | Pack search |
| Add pack form | POST | (none) | Per-available-pack add action |

**Observations:**

- Subscribe form is embedded inside a dropdown menu item -- form submission happens from dropdown
- Search form uses `col-12 col-md-6 col-lg-4` width constraint directly on the form element (not a wrapper)
- Search uses `input-group input-group-sm` (small size) unlike add-lists page which uses standard size

### Icons

| Icon class | Context |
|---|---|
| `bi-chevron-left` | Back breadcrumb (via include) |
| `bi-person` | Pack owner in both sections |
| `bi-trash` | Remove pack link |
| `bi-plus-circle` | Add pack button |

### Badges

No badges used.

### Dropdowns

| Trigger | Menu classes | Context |
|---|---|---|
| `btn btn-outline-primary btn-sm dropdown-toggle` | `dropdown-menu dropdown-menu-end` | Per-pack subscribe menu |

Dropdown contains:

- Form-based `<button class="dropdown-item">` for each subscribable list
- `dropdown-item-text text-muted small` for "All Gangs subscribed" state
- `dropdown-divider` separator
- `<a class="dropdown-item">` for "Other..." link

**Observations:**

- Uses `<button class="dropdown-item">` (inside form) alongside `<a class="dropdown-item">` -- mixing interactive patterns within the same dropdown. This is necessary for the form submission but notable.

### Other Components

| Component | Classes | Context |
|---|---|---|
| Input group (search) | `input-group input-group-sm` | Add packs search |
| Grid layout (packs) | `row g-2` with `col-12 col-md-6 col-lg-4` | Pack grid for both sections |

## Typography Usage

| Element | Classes | Usage |
|---|---|---|
| Page heading | `h1` with `mb-2` | "Content Packs" |
| Campaign name | `p.text-muted.mb-0` | Subtitle |
| Section headings | `h2.h5.mb-3` | "Allowed Packs", "Add Packs" |
| Pack name | `fw-semibold` (with link) | Both sections |
| Pack owner | `text-muted small` | Both sections |
| Empty state text | `text-muted small mb-3` or `text-muted small mb-0` | No packs messages |
| Dropdown disabled text | `dropdown-item-text text-muted small` | "All Gangs subscribed" |

**Observations:**

- Section headings use `h2.h5.mb-3` -- differs from campaign detail (`h2.h5.mb-0` inside header bar) and campaign-add-lists (`h2.h5.mb-2`). Three different `mb-*` values across campaign pages.
- Empty state for allowed packs uses `mb-3` while empty state for available packs uses `mb-0` -- inconsistent trailing margin.

## Colour Usage

| Colour | Bootstrap class | Context |
|---|---|---|
| Primary blue | `btn-primary`, `btn-outline-primary`, link defaults | Search, add buttons, pack name links |
| Secondary grey | `btn-outline-secondary` | Clear search |
| Danger red | `link-danger` | Remove pack icon |
| Muted grey | `text-muted` | Owner text, empty states |

## Spacing Values

| Spacing class | Context |
|---|---|
| `gap-5` | Main page vstack |
| `g-2` | Grid gutters for pack cards |
| `gap-2` | Pack card d-flex actions area |
| `mb-0` | Campaign name subtitle |
| `mb-2` | Page heading h1 |
| `mb-3` | Section headings; pack grid; search form; allowed packs empty state |
| `p-2` | Pack card padding |
| `px-0` | Main column; search form |

## Custom CSS

| Class | Source | Usage |
|---|---|---|
| `linked` | `styles.scss` | Not used directly in this template |
| `link-underline-opacity-25 link-underline-opacity-100-hover` | Bootstrap utilities | Pack name links and remove icon |

## Inconsistencies

1. **Section heading mb value**: Uses `h2.h5.mb-3` while campaign detail uses `h2.h5.mb-0` (inside header bar) and add-lists uses `h2.h5.mb-2`. Should standardize section heading spacing.

2. **Search input sizing**: Uses `input-group-sm` here but the add-lists search uses standard `input-group` size. Both are search inputs in the same feature area.

3. **Search form width**: Constrained to `col-12 col-md-6 col-lg-4` on the form element itself, while add-lists search is full width. Different width approaches for the same pattern.

4. **Empty state mb inconsistency**: `text-muted small mb-3` for allowed packs empty state vs `text-muted small mb-0` for available packs empty state.

5. **Pack card pattern is repeated**: The `border rounded p-2 d-flex align-items-center justify-content-between` pattern is copy-pasted between allowed packs and available packs sections. Could be extracted to a shared include.

6. **No section header bar**: Unlike campaign detail's sections, this page uses plain `h2.h5` headings without the `bg-body-secondary rounded px-2 py-1` header bar. This is consistent with other sub-pages (add-lists, assets, resources, attributes) but creates a visual hierarchy difference between the detail and sub-pages.

7. **Link style for pack names**: Uses `link-underline-opacity-25 link-underline-opacity-100-hover fw-semibold` directly rather than the `linked` custom class, even though `linked` provides the same underline behaviour.

## Accessibility Notes

- Back link uses breadcrumb ARIA semantics
- Dropdown trigger has `aria-expanded="false"` attribute
- Search input has `placeholder` but no explicit `<label>` element or `aria-label` -- the placeholder alone is insufficient for screen readers
- Remove pack icon (`bi-trash`) is a link with no text content -- relies solely on the icon, which is not accessible. Needs `aria-label` or visually hidden text.
- Form buttons inside dropdown items may confuse screen readers expecting links in menu context
