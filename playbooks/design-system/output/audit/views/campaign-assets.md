# View Audit: Campaign Assets

## Metadata

| Field | Value |
|---|---|
| URL | `/campaign/<id>/assets` |
| Template | `core/campaign/campaign_assets.html` |
| Extends | `core/layouts/base.html` |
| Template tags loaded | `allauth`, `custom_tags`, `color_tags` |
| Included templates | `core/includes/back.html` |
| Complexity | Medium-high -- dynamic list of asset types with per-type asset tables, responsive desktop/mobile action patterns |

## Components Found

### Buttons

| Element | Classes | Variant | Context |
|---|---|---|---|
| Mobile dropdown trigger (asset type) | `btn btn-sm btn-link text-secondary p-0` | Link small, custom padding | Asset type actions (mobile only, `d-sm-none`) |
| Mobile dropdown trigger (asset row) | `btn btn-sm btn-link text-secondary p-0` | Link small, custom padding | Per-asset actions (mobile only, `d-sm-none`) |

**Observations:**

- No primary action buttons on this page -- all actions are links
- The mobile dropdown trigger pattern (`btn btn-sm btn-link text-secondary p-0`) is consistent between asset type and asset row levels
- This page uses a responsive dual pattern: expanded inline links on `sm+` screens, dropdown on mobile

### Cards

No card components used.

### Tables

| Table | Classes | Context |
|---|---|---|
| Asset table (per type) | `table table-sm table-borderless mb-0 align-middle` | Per-asset-type listing |

**Observations:**

- Consistent with campaign detail asset table styling
- Has explicit `<thead>` with column headers (Name, Holder, Actions) unlike the campaign detail which has no thead for assets
- Uses custom width classes `w-em-10 w-em-sm-12` and `w-em-3 w-em-sm-12` for column sizing

### Navigation

| Element | Classes | Context |
|---|---|---|
| Back breadcrumb | `breadcrumb` / `breadcrumb-item active` | Top of page, "Back to Campaign" |

### Forms

No forms on this page -- all actions are links.

### Icons

| Icon class | Context |
|---|---|
| `bi-chevron-left` | Back breadcrumb |
| `bi-plus-circle` | Add Asset Type link, Add [asset] link |
| `bi-box-arrow-in-down` | Copy from another Campaign link |
| `bi-pencil` | Edit Type link, Edit asset link |
| `bi-trash` | Remove Type link, Remove asset link |
| `bi-arrow-left-right` | Transfer asset link |
| `bi-three-dots-vertical` | Mobile dropdown triggers |

**Observations:**

- Uses `bi-three-dots-vertical` for mobile dropdowns while campaign detail uses `bi-three-dots` (horizontal). Inconsistent dot-menu icon direction.
- Full icon-text pairs for expanded links; icon-only for mobile dropdown is handled by having text inside dropdown items.

### Badges

No badges used.

### Dropdowns

| Trigger | Menu classes | Context |
|---|---|---|
| Asset type mobile dropdown | `dropdown-menu dropdown-menu-end` | Edit Type / Remove Type |
| Asset row mobile dropdown | `dropdown-menu dropdown-menu-end` | Transfer / Edit / Remove |

Both use `dropdown d-sm-none` to show only on mobile, paired with `d-none d-sm-inline` expanded links.

**Observations:**

- This is a responsive action pattern: inline links on desktop, dropdown on mobile
- Danger items in dropdown use `dropdown-item text-danger` pattern
- This responsive pattern is unique to the assets page; other campaign sub-pages show all links at all sizes

### Other Components

| Component | Classes | Context |
|---|---|---|
| Section heading wrapper | `d-flex justify-content-between align-items-center mb-2` | Per-asset-type section heading |
| Header action bar | `hstack gap-3 ms-md-auto fs-7` | Page-level actions (Add Type, Copy) |
| Type-level action bar | `hstack gap-3` | Per-type actions (Add, Edit, Remove) |
| Description text | `text-muted small mb-3 mb-last-0` | Asset type description |

## Typography Usage

| Element | Classes | Usage |
|---|---|---|
| Page heading | `h1` with `mb-2` | "Campaign Assets" |
| Campaign name | `p.text-muted.mb-0` | Subtitle |
| Section headings (per type) | `h2.h5.mb-0` | Asset type name |
| Table headers | `.caps-label` with `ps-0` | Name, Holder, Actions columns |
| Asset name | `fw-semibold` | Asset table cells |
| Asset description | `small text-muted mb-last-0` | Below asset name, rendered with `|safe` |
| Property labels | `small text-muted` | Asset properties and sub-asset counts |
| Header actions | `fs-7` | "Add Asset Type" and "Copy" links |
| Empty state | `text-muted small mb-0` | No assets message |
| Holder "Unowned" | `text-muted` | When asset has no holder |
| Expanded action links | `link-secondary link-underline-opacity-25 link-underline-opacity-100-hover small` | Transfer, Edit, Remove |

**Observations:**

- Uses `fs-7` for the header action links, which is the same custom font size (0.9rem) seen in the campaign detail assets section
- Section headings use `mb-0` (no bottom margin) since the content follows directly or the description provides spacing
- The `Actions` header column shows text on `sm+` (`d-none d-sm-inline`) -- responsive column header hiding

## Colour Usage

| Colour | Bootstrap class | Context |
|---|---|---|
| Primary blue | `link-primary` | Add Asset Type, Add [asset] links |
| Secondary grey | `link-secondary`, `text-secondary` | Copy link, Edit links, Transfer links, mobile dropdown triggers |
| Danger red | `link-danger`, `text-danger` | Remove links (both inline and dropdown) |
| Muted grey | `text-muted` | Campaign name, descriptions, empty states, "Unowned" |

**Observations:**

- "Add" actions use `link-primary` while "Edit" and "Transfer" actions use `link-secondary` -- consistent semantic colour hierarchy
- "Remove" actions consistently use `link-danger` or `text-danger`

## Spacing Values

| Spacing class | Context |
|---|---|
| `gap-5` | Main page vstack between sections |
| `gap-3` | Action link hstacks |
| `gap-2` | Header d-flex layout |
| `mb-0` | Section headings; tables; empty states |
| `mb-2` | Page heading h1; section heading wrapper |
| `mb-3` | Asset type description |
| `px-0` | Main column; table cells (ps-0); Actions header (pe-0) |
| `pe-0` | Action column cells and header |
| `ps-0` | Name column cells and header |

## Custom CSS

| Class | Source | Usage |
|---|---|---|
| `caps-label` | `styles.scss` | Table headers |
| `mb-last-0` | `styles.scss` | Asset description containers |
| `w-em-10`, `w-em-sm-12`, `w-em-3` | `styles.scss` | Table column width constraints |
| `{% property_nowrap_class %}` | Template tag | Asset property spans |
| `{% list_with_theme %}` | Template tag | Holder gang name rendering |

## Inconsistencies

1. **Mobile dropdown icon direction**: Uses `bi-three-dots-vertical` while campaign detail header uses `bi-three-dots` (horizontal). Should standardize dot-menu icon across the project.

2. **Section heading pattern divergence**: Uses `d-flex justify-content-between align-items-center mb-2` without the `bg-body-secondary rounded px-2 py-1` background bar used on campaign detail. This is consistent with other sub-pages but means the visual hierarchy differs between detail and management pages.

3. **Responsive action pattern uniqueness**: The dual desktop-links/mobile-dropdown pattern is only used on this page and not on campaign-resources or campaign-attributes, which show inline links at all viewport sizes. Larger link sets on resources/attributes could overflow on mobile.

4. **Header action font size**: Uses `fs-7` class on header action links, which is only applied here and on the assets section of campaign detail. Other pages (resources, attributes) do not apply `fs-7` to their equivalent header actions, making the text slightly larger on those pages.

5. **Asset table has thead**: This management table includes `<thead>` with column headers, while the same asset table on the campaign detail page has no `<thead>` -- just `<tbody>`. Different table structures for the same data.

6. **Description safe filter**: Uses `{{ asset_type.description|safe }}` and `{{ asset.description|safe }}` -- raw `|safe` rather than `|safe_rich_text|safe` used for campaign summary/narrative on the detail page. If these descriptions contain user-generated HTML, the lack of `safe_rich_text` sanitization could be a security concern.

## Accessibility Notes

- Back link uses breadcrumb ARIA semantics
- Mobile dropdown triggers have `aria-expanded="false"`
- Responsive hiding (`d-none d-sm-inline` / `d-sm-none`) ensures content is not duplicated for screen readers at any viewport -- however, both the expanded links and the dropdown are in the DOM simultaneously, meaning screen readers may announce both sets of actions
- The "Actions" column header is visually hidden on mobile via `d-none d-sm-inline` but the `<th>` itself remains, which is correct for table structure
- Missing: Tables lack `<caption>` elements
- Missing: `<section>` elements per asset type have no `aria-label` connecting them to their h2 headings
- Good: Transfer links include `return_url` parameter for proper navigation flow
