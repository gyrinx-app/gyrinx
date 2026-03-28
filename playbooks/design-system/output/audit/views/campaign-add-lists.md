# View Audit: Campaign Add Lists

## Metadata

| Field | Value |
|---|---|
| URL | `/campaign/<id>/lists/add` |
| Template | `core/campaign/campaign_add_lists.html` |
| Extends | `core/layouts/base.html` |
| Template tags loaded | `allauth`, `custom_tags`, `color_tags` |
| Included templates | `core/includes/back.html`, `core/campaign/includes/campaign_lists.html` (which includes `list_row.html`), `core/includes/pagination.html` |
| Complexity | High -- search form, filters, content pack confirmation modal, current gangs section, available gangs table |

## Components Found

### Buttons

| Element | Classes | Variant | Context |
|---|---|---|---|
| Search submit | `btn btn-primary` | Primary (no size) | Search form |
| Clear search link | `btn btn-outline-secondary` | Outline secondary (no size) | Search form (conditional) |
| Add Packs & Gang submit | `btn btn-primary btn-sm` | Primary small | Pack confirmation |
| Cancel (pack confirm) link | `btn btn-secondary btn-sm` | Secondary small | Pack confirmation |
| Add gang submit | `btn btn-outline-primary btn-sm` | Outline primary small | Available gangs table rows |
| Radio toggle labels | `btn btn-outline-primary btn-sm` | Outline primary small | Owner filter (All/Your/Others) |

**Observations:**

- Search submit uses full-size `btn-primary` while Add gang uses `btn-sm btn-outline-primary` -- different sizing contexts
- The `btn btn-outline-primary btn-sm` for "Add" is unique to this page; campaign_packs.html uses `btn btn-sm btn-outline-primary` (same classes, different order -- functionally identical but inconsistent source)
- Clear search uses `btn-outline-secondary` (no size) next to full-size search button

### Cards

No Bootstrap `.card` components. Custom card-like elements:

- `border border-danger rounded p-3 text-danger` for error messages
- `border border-warning rounded p-3` for pack confirmation prompt

**Observations:**

- Error uses `border-danger` + `p-3`, while the archive banner on campaign detail uses `border rounded p-2` -- different padding and border colour approach
- Pack confirmation uses `border-warning` -- a different border-colour pattern from the error state

### Tables

| Table | Classes | Context |
|---|---|---|
| Available gangs | `table table-sm mb-0 align-middle` | Available gangs listing |

**Observations:**

- This table uses `table-sm` but NOT `table-borderless`, making it bordered. This is different from the campaign detail tables which are all `table-borderless`. Since this is an actionable list (with add buttons per row), borders help distinguish rows -- but it's a conscious divergence from the campaign detail pattern.
- The campaign_lists.html include (current gangs section) uses `table-borderless` as on the detail page.

### Navigation

| Element | Classes | Context |
|---|---|---|
| Back breadcrumb | `breadcrumb` / `breadcrumb-item active` | Top of page, "Back to Campaign" |
| Pagination | `pagination justify-content-center` | Bottom of page (via include) |

### Forms

| Form | Method | Classes | Context |
|---|---|---|---|
| Search form | GET | `vstack gap-3` | Gang search with text input and filters |
| Pack confirm form | POST | (none) | Hidden form for adding packs + gang |
| Add gang forms | POST | (none) | Per-row inline form in available gangs table |

**Observations:**

- Search form uses `id="search"` for anchor linking (`#search`)
- Radio button group uses `data-gy-toggle-submit="search"` custom data attribute for auto-submit on change
- Form switch for pack filter uses `form-check form-switch` Bootstrap pattern

### Icons

| Icon class | Context |
|---|---|
| `bi-chevron-left` | Back breadcrumb (via include) |
| `bi-exclamation-triangle` | Error message |
| `bi-box-seam` | Content Packs in pack confirmation and gang pack list |
| `bi-search` | Search input group prepend |
| `bi-plus-circle` | Add Packs & Gang button |
| `bi-plus-lg` | Add gang button |

**Observations:**

- Two different "plus" icons: `bi-plus-circle` for "Add Packs & Gang" and `bi-plus-lg` for individual "Add" buttons. Elsewhere in the project, `bi-plus-circle` is the standard for add actions.

### Badges

No badges used directly in this template (campaign_lists.html include uses `badge text-bg-warning` for "Pending").

### Dropdowns

No dropdowns in the main template (campaign_lists.html include has per-row dropdowns).

### Other Components

| Component | Classes | Context |
|---|---|---|
| Input group (search) | `input-group` with `input-group-text` prepend | Search form |
| Radio button group | `btn-group` with `btn-check` inputs | Owner filter |
| Form switch | `form-check form-switch` with `form-check-input` / `form-check-label` | Matching packs filter |
| Section headings | `h2.h5.mb-2` | "Campaign Gangs", "Available Gangs" |
| Flash highlight | `{% flash "search" %}` custom template tag | Available gangs section wrapper |

## Typography Usage

| Element | Classes | Usage |
|---|---|---|
| Page heading | `h1` with `mb-1` | "Add Gangs" |
| Campaign name | `p.text-muted.mb-0` | Subtitle |
| Section headings | `h2.h5.mb-2` | "Campaign Gangs", "Available Gangs" |
| Pack confirm heading | `h5.mb-2` | "Content Packs Required" |
| Gang name | `fw-semibold` (with link) | Available gangs table |
| House name | `text-muted fw-normal` | Adjacent to gang name |
| Gang metadata | `small text-muted` | Owner, stats, packs |
| Filter label | `form-check-label small` | "Matching Content Packs" |
| Empty state | `text-muted small mb-0` | No gangs found |

**Observations:**

- Section headings use `h2.h5.mb-2` here vs `h2.h5.mb-0` in campaign detail section headers. The `mb-2` is used because these sections lack the `bg-body-secondary rounded` header bar, so they need bottom margin on the heading itself.
- Pack confirmation heading is `h5` (not `h2.h5`), which is a different semantic level.

## Colour Usage

| Colour | Bootstrap class | Context |
|---|---|---|
| Primary blue | `btn-primary`, `btn-outline-primary`, `link-primary` | Search, add buttons |
| Secondary grey | `btn-secondary`, `btn-outline-secondary` | Cancel, clear buttons |
| Danger red | `border-danger`, `text-danger` | Error message border and text |
| Warning yellow | `border-warning`, `text-warning` | Pack confirmation border, icon colour |
| Muted grey | `text-muted` | Metadata, subtitles, empty states |

## Spacing Values

| Spacing class | Context |
|---|---|
| `gap-5` | Main page vstack |
| `gap-3` | Search form vstack |
| `gap-2` | Header gap; filter hstack; pack confirm buttons d-flex |
| `mb-0` | Campaign name p; empty state p |
| `mb-1` | Page heading h1 |
| `mb-2` | Section headings; pack confirm h5; ul in pack confirm |
| `mb-3` | Pack confirm paragraph |
| `p-3` | Error and pack confirm containers |
| `px-0` | Main column; table cells (ps-0) |
| `ms-2` | Pack filter switch margin |

## Custom CSS

| Class | Source | Usage |
|---|---|---|
| `linked` | `styles.scss` | Gang name link in campaign_lists.html |
| `caps-label` | `styles.scss` | Table header in campaign_lists.html |
| `{% flash "..." %}` | `custom_tags` | Flash animation class on available gangs section |
| `flash-warn` | `styles.scss` | Animation applied by flash tag |
| `{% list_with_theme %}` | Template tag | Gang name rendering |
| `{% credits %}` | Template tag | Credit value formatting |
| `data-gy-toggle-submit` | Custom JS data attribute | Auto-submit on radio/checkbox change |

## Inconsistencies

1. **Plus icon variants**: Uses `bi-plus-lg` for the individual "Add" button but `bi-plus-circle` elsewhere for add actions. Should standardize.

2. **Error/warning containers**: Error uses `border border-danger rounded p-3 text-danger`, pack warning uses `border border-warning rounded p-3`. Neither uses Bootstrap's `alert` component (consistent with project convention of avoiding `alert` for inline content), but the pattern could be extracted into a shared include.

3. **Section heading pattern**: Uses `h2.h5.mb-2` without the `bg-body-secondary rounded px-2 py-1` header bar pattern used on campaign detail. This is because the add-lists page is a management sub-page, but it means section headers look visually different from the detail page.

4. **Table border pattern**: Available gangs table has borders (`table-sm` only) while campaign_lists.html uses `table-borderless`. This is arguably intentional (different interaction pattern) but creates visual inconsistency within the same page.

5. **Search button sizing**: Full-size `btn-primary` for Search but `btn-sm` for Clear -- visually mismatched adjacent buttons. Both should use the same size.

## Accessibility Notes

- Search input has `aria-label="Search"` and `type="search"` for proper semantics
- Radio buttons use proper `<input>` + `<label>` associations with `for`/`id` attributes
- Form switch uses `form-check-input` / `form-check-label` pattern
- Hidden inputs use `type="hidden"` correctly
- Pagination uses `<nav aria-label="Page navigation">`
- Concern: `data-gy-toggle-submit` auto-submits on change -- users with assistive technology may not expect immediate navigation on radio/checkbox interaction. Consider adding `aria-live` region or status message.
- Concern: Gang links in available gangs table open in `target="_blank"` with `rel="noopener"` (good security) but no visual indicator or ARIA note that link opens in new tab.
