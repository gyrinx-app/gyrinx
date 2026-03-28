# View Audit: Home (Logged In)

## Metadata

- **URL:** `/`
- **Template:** `core/index.html`
- **Template chain:** `core/layouts/foundation.html` > `core/layouts/base.html` > `core/index.html`
- **Includes:** `core/includes/site_banner.html`, `core/includes/lists_filter.html` (compact mode)

## Components Found

### Buttons

| Text | Classes | Variant | Size | Icon | Notes |
|------|---------|---------|------|------|-------|
| Change Username | `btn btn-warning btn-sm ms-3` | Warning | Small | None | In username alert; only shown if username contains '@' |
| Search (gangs) | `btn btn-primary btn-sm` | Primary | Small | None | In search form input group |
| Search (campaigns) | `btn btn-primary btn-sm` | Primary | Small | None | In search form input group |
| Search (lists, via include) | `btn btn-primary btn-sm` | Primary | Small | None | Compact lists_filter.html include |
| Get started | `btn btn-primary` | Primary | Default | None | In new-list card form; no `btn-sm` -- inconsistent with other buttons |
| New Campaign (link) | `icon-link linked` | Link-style | N/A | `bi-plus-lg` | Uses custom `linked` class |
| New List (link) | `icon-link linked` | Link-style | N/A | `bi-plus-lg` | Uses custom `linked` class |
| Show all (gangs) | `link-secondary link-underline-opacity-25 link-underline-opacity-100-hover` | Link-style | N/A | None | Secondary colour link |
| Show all (campaigns) | `link-secondary link-underline-opacity-25 link-underline-opacity-100-hover` | Link-style | N/A | None | Secondary colour link |
| Show all (lists) | `link-secondary link-underline-opacity-25 link-underline-opacity-100-hover` | Link-style | N/A | None | Secondary colour link |

### Cards

| Element | Classes | Notes |
|---------|---------|-------|
| New list prompt card | `card card-body vstack gap-4` | Shown when user has no lists; acts as inline form |

### Navigation

None found (navigation is in base.html, audited separately in template chain).

### Forms

| Form ID | Action | Method | Classes | Notes |
|---------|--------|--------|---------|-------|
| search-gangs | `core:index` | GET | `vstack gap-2` | Hidden inputs for cachebuster and other search params |
| search-campaigns | `core:index` | GET | `vstack gap-2` | Hidden inputs for cachebuster and other search params |
| search-lists (via include) | `core:index` | GET | `vstack gap-2` | Compact version from lists_filter.html |
| (new list form) | `core:lists-new` | GET | `card card-body vstack gap-4` | Inline card-based form |

### Icons (Bootstrap Icons)

| Icon class | Context | Purpose |
|------------|---------|---------|
| `bi-exclamation-triangle` | Username alert | Warning indicator |
| `bi-search` | Search input groups (x3) | Search indicator |
| `bi-plus-lg` | New Campaign / New List links | Add action |
| `bi-award` | Campaign gang rows | Campaign membership indicator |
| `bi-chevron-right` | List/gang/campaign rows (mobile) | Forward navigation |

### Badges

| Text | Classes | Context |
|------|---------|---------|
| Credits value | `badge text-bg-primary` | Gang row, list row |
| Campaign status | `badge text-bg-success` / `badge text-bg-secondary` | Campaign row (via `get_status_display`) |

### Other Components

| Component | Classes | Notes |
|-----------|---------|-------|
| Hero banner | `hero` (custom) | Inline style with background-image linear-gradient overlay |
| Alert (username) | `alert alert-warning d-flex align-items-center` | Conditional username warning |
| Section dividers (logged-out) | `hr` with `col-1 my-4 align-self-center` | Used between marketing sections |
| vstack layout | `vstack gap-4` | Primary layout organiser |

## Typography Usage

| Element | Classes applied | Semantic role |
|---------|----------------|---------------|
| Hero heading | `h2` tag with `h1 fw-light text-light` | Main welcome message; uses `<h2>` but styled as `h1` |
| Column headers | `h2` tag with `h4 mb-0` | Section titles ("Campaign Gangs", "Campaigns", "Lists") |
| Item names (gangs/lists) | `h3` tag with `mb-0 h5` | List/gang names within each section |
| Item names (campaigns) | `h3` tag with `mb-0 h5` | Campaign names |
| Last edit metadata | `text-muted small` | Timestamp text |
| House name | plain `<div>` | No special typography classes |
| Campaign name (mobile) | `<span>` with `d-inline d-md-none` | Responsive show/hide |
| Campaign name (desktop) | `<a>` with `d-none d-md-inline` | Responsive show/hide |
| Logged-out marketing `<h2>` | plain `<h2>` | No additional classes |
| Logged-out lead text | `lead fs-2 text-center` | CTA paragraph |

## Colour Usage

| Element | Property | Source | Semantic purpose |
|---------|----------|-------|-----------------|
| Hero overlay | background-image | Inline style: `linear-gradient(rgba(0,0,0,0.1), rgba(0,0,0,0.7))` | Darken hero image for text readability |
| Hero text | color | `text-light` (Bootstrap) | Light text on dark background |
| Hero username link | color | `link-light link-underline-opacity-25 link-underline-opacity-100-hover` | Light link variant |
| Username alert | background | `alert-warning` (Bootstrap) | Warning state |
| Credits badge | background | `text-bg-primary` (Bootstrap) | Primary highlight |
| Campaign status badge | background | `text-bg-success` / `text-bg-secondary` (Bootstrap) | Status indicator |
| "Show all" links | color | `link-secondary` (Bootstrap) | De-emphasised action |
| Empty state text | color | `text-secondary` (Bootstrap) | Muted informational text |
| Last edit text | color | `text-muted` (Bootstrap) | De-emphasised metadata |
| Search icon | color | inherited (via `input-group-text`) | Neutral |

## Spacing Values

| Element | Property | Source class | Notes |
|---------|----------|-------------|-------|
| Content wrapper | margin-bottom, padding-bottom | `mb-5 pb-5` | Extra bottom space |
| Main vstack | gap | `vstack gap-4` | 1.5rem gap between sections |
| Row gutters | gap | `g-4` | 1.5rem Bootstrap grid gap |
| Section headers | margin-bottom | `mb-3` | Below header row |
| Column vstack items | gap | `vstack gap-3` | Within each column |
| Gang/list row | gap | `hstack gap-3` | Horizontal gap in each row |
| Metadata badges | gap | `hstack column-gap-2 row-gap-1 flex-wrap` | Inline metadata items |
| Chevron right link | padding | `p-3` | Touch target for mobile |
| New-list card | gap | `vstack gap-4` | Within card body |
| Logged-out marketing | margin-top | `mt-4` | Top of logged-out content |
| Marketing HRs | margin | `my-4` | Vertical separator space |

## Custom CSS

| Class name | Defined in | Properties | Used on elements |
|------------|-----------|------------|-----------------|
| `hero` | `styles.scss` | `height: 25vh; background-size: cover; background-position: center; position: relative` | Hero banner div |
| `linked` | `styles.scss` | Extends `link-underline-opacity-25`, `link-underline-opacity-100-hover`, `link-offset-1` | New Campaign, New List links |
| `mb-last-0` | `styles.scss` | `> :last-child { margin-bottom: 0 !important }` | Not used in this template directly |

## Inconsistencies

| Issue | Elements involved | Description | Severity |
|-------|-------------------|-------------|----------|
| Button size inconsistency | "Get started" vs all Search buttons | "Get started" uses `btn btn-primary` (default size) while all other action buttons use `btn-sm`. | Medium |
| Heading semantics vs visual | Hero `<h2>` styled as `h1` | The hero uses an `<h2>` tag but applies `.h1` class; the actual semantic `<h1>` is absent from the logged-in page. | Medium |
| Inconsistent heading hierarchy | Section `<h2 class="h4">` then item `<h3 class="h5">` | Semantic levels used correctly but visual sizing is overridden, creating a visual-semantic mismatch. | Low |
| `text-muted` vs `text-secondary` | "Last edit" vs empty-state paragraphs | "Last edit" uses `text-muted` while empty states use `text-secondary`. These are equivalent in BS5 but mixing them is inconsistent. | Low |
| Campaign name link vs span | Desktop vs mobile campaign names | Desktop shows campaign name as an `<a>` link, mobile shows it as a `<span>` -- mobile users cannot tap to navigate to the campaign. | Medium |
| Inline hero background | Hero div | Uses inline `style=""` for the background-image gradient and URL rather than a class. | Low |
| `{% load tz %}` loaded twice | Lines 97 and 209 | Template tag library loaded redundantly inside the loop sections. | Low |

## Accessibility Notes

- Hero heading semantics: The logged-in page has no `<h1>` element; the hero uses `<h2>` visually styled as `h1`.
- Search inputs have `aria-label` attributes ("Search campaign gangs", "Search campaigns", "Search lists").
- Username alert has `role="alert"`.
- Mobile chevron-right links lack `aria-label` in gangs and campaigns columns (only the lists page version has one).
- Campaign award icon uses `data-bs-toggle="tooltip"` with `data-bs-title` for screen reader context.
- The "Get started" card form input has an `id` matching its `<label>` (`id_name`).
