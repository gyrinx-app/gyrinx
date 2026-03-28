# View Audit: Campaign Attributes

## Metadata

| Field | Value |
|---|---|
| URL | `/campaign/<id>/attributes` |
| Template | `core/campaign/campaign_attributes.html` |
| Extends | `core/layouts/base.html` |
| Template tags loaded | `allauth`, `custom_tags`, `color_tags` |
| Included templates | `core/includes/back.html` |
| Complexity | Medium-high -- group-by selector form, dynamic attribute types with value cards grid, and per-type gang assignment tables |

## Components Found

### Buttons

| Element | Classes | Variant | Context |
|---|---|---|---|
| Group-by noscript submit | `btn btn-sm btn-primary` | Primary small | Noscript fallback for group-by form |

**Observations:**

- Only one actual button on the page, and it is hidden behind `<noscript>` -- the `<select>` auto-submits via `onchange`
- All other actions are links

### Cards

No Bootstrap `.card` components. Custom value cards:

- `border rounded p-2 d-flex align-items-center justify-content-between` for attribute value items

**Observations:**

- Same card pattern as campaign-packs pack cards
- Contains colour dot, value name, and edit/remove action links

### Tables

| Table | Classes | Context |
|---|---|---|
| Assignment table (per type) | `table table-sm table-borderless mb-0 align-middle` | Per-attribute-type gang assignment listing |

**Observations:**

- Consistent table pattern with other campaign pages
- Three columns: Gang, Assigned values, (action column with no header text)

### Navigation

| Element | Classes | Context |
|---|---|---|
| Back breadcrumb | `breadcrumb` / `breadcrumb-item active` | Top of page, "Back to Campaign" |

### Forms

| Form | Method | Classes | Context |
|---|---|---|---|
| Group-by form | POST | `d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2` | Group attribute type selector |

**Observations:**

- Form uses `onchange="this.form.submit()"` for JS auto-submit with `<noscript>` fallback button
- Form action is a dedicated endpoint (`campaign-set-group-attribute`)
- Layout uses responsive flex pattern (column on mobile, row on desktop)

### Icons

| Icon class | Context |
|---|---|
| `bi-chevron-left` | Back breadcrumb |
| `bi-plus-circle` | Add Attribute type, Add value links |
| `bi-pencil` | Edit attribute type, Edit value links |
| `bi-trash` | Remove attribute type, Remove value links |

### Badges

| Classes | Context |
|---|---|
| `badge fw-normal text-bg-light border d-inline-flex align-items-center gap-1` | Assigned attribute value tags in assignment table |

**Observations:**

- Same badge pattern as campaign detail's campaign_lists.html attribute badges
- Includes colour dot (`10px` circle) -- note this is the same size as group headers on campaign detail (10px) but different from the 8px dots in campaign_lists.html badges. Yet the 16px dots appear in the value cards above the table.

### Dropdowns

No dropdowns used.

### Other Components

| Component | Classes | Context |
|---|---|---|
| Header layout | `d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2` | Page header with responsive stacking |
| Header actions | `hstack gap-3 ms-md-auto` | Add Attribute type link |
| Section heading wrapper | `d-flex justify-content-between align-items-center mb-2` | Per-type heading with action links |
| Type-level action bar | `hstack gap-3` | Per-type Add value/Edit/Remove links |
| Value action bar | `hstack gap-2` | Per-value Edit/Remove links |
| Description text | `text-muted small mb-3 mb-last-0` | Attribute type description |
| Form select | `form-select form-select-sm w-auto` | Group-by dropdown |
| Form label | `form-label mb-0 text-nowrap fw-semibold` | "Group gangs by" |
| Grid layout (values) | `row g-2 mb-3` with `col-12 col-md-6 col-lg-4` | Attribute value cards |
| Colour dots (large) | `d-inline-block rounded-circle` at `16px` | Value cards |
| Colour dots (small) | `d-inline-block rounded-circle` at `10px` | Assignment badge dots |

## Typography Usage

| Element | Classes | Usage |
|---|---|---|
| Page heading | `h1` with `mb-2` | "Campaign Attributes" |
| Campaign name | `p.text-muted.mb-0` | Subtitle |
| Section headings (per type) | `h2.h5.mb-0` | Attribute type name |
| Table headers | `.caps-label` with `ps-0` | Gang, Assigned values columns |
| Value name | `strong` | Inside value cards |
| Group-by label | `form-label mb-0 text-nowrap fw-semibold` | "Group gangs by" |
| Group-by description | `text-muted small` | Explanatory text after select |
| Action links | `icon-link link-primary/secondary/danger link-underline-opacity-25 link-underline-opacity-100-hover small` | Various action links |
| "Not assigned" text | `text-muted small` | When gang has no assigned values |
| Empty state | `text-muted small mb-0` | No values/types messages |

**Observations:**

- Attribute type description uses plain `{{ attribute_type.description }}` -- no `|safe` or `|safe_rich_text|safe` filter, unlike campaign-assets/resources which use `|safe`. This means HTML in descriptions will be escaped and shown as raw text. Inconsistent with other sub-pages.

## Colour Usage

| Colour | Bootstrap class | Context |
|---|---|---|
| Primary blue | `link-primary`, `btn-primary` | Add links, noscript submit |
| Secondary grey | `link-secondary` | Edit links, value card edit icons |
| Danger red | `link-danger` | Remove links, value card remove icons |
| Muted grey | `text-muted` | Campaign name, descriptions, not-assigned text |
| Light | `text-bg-light` | Attribute value assignment badges |
| Inline colour | `style="background-color: {{ value.colour }}"` | Value dots at 16px and 10px sizes |

## Spacing Values

| Spacing class | Context |
|---|---|
| `gap-5` | Main page vstack between sections |
| `gap-3` | Type action link hstacks |
| `gap-2` | Header d-flex; value card d-flex actions; badge hstack; form layout |
| `gap-1` | Badge dot-to-text gap |
| `g-2` | Value cards grid gutters |
| `mb-0` | Section headings; form label; campaign name; tables; empty states |
| `mb-2` | Page heading h1; section heading wrapper |
| `mb-3` | Description; value cards grid wrapper |
| `p-2` | Value card padding |
| `px-0` | Main column |
| `ps-0` | Gang column and header |
| `pe-0` | Action column and header |

## Custom CSS

| Class | Source | Usage |
|---|---|---|
| `caps-label` | `styles.scss` | Table headers |
| `mb-last-0` | `styles.scss` | Attribute type description containers |
| `{% list_with_theme %}` | Template tag | Gang name rendering |
| `{% lookup %}` | Template filter | Nested dictionary lookups for assignments |

## Inconsistencies

1. **Colour dot size inconsistency across the project**: This page uses `16px` for value cards and `10px` for assignment badge dots. Campaign detail uses `10px` for group headers and `8px` for attribute badges in campaign_lists.html. Three different sizes for conceptually similar colour indicators.

2. **Description rendering**: Uses `{{ attribute_type.description }}` with NO `|safe` filter, while campaign-assets and campaign-resources use `|safe`. This means HTML will be escaped here but rendered as HTML on other pages. If the data can contain HTML, this is a rendering bug; if it cannot, the other pages have unnecessary `|safe` calls.

3. **Value card action link gap**: Uses `hstack gap-2` for value card actions while type-level actions use `hstack gap-3`. The tighter spacing for value actions is appropriate for the smaller context but not explicitly documented as a pattern.

4. **Assignment table action column header empty**: The third `<th>` has `caps-label text-end pe-0` but no text content -- it is a blank header for the "Assign" action column. Campaign-resources explicitly labels its action column "Actions". Inconsistent header labelling.

5. **Group-by form uses onchange**: Relies on JavaScript `onchange="this.form.submit()"` for usability. While `<noscript>` provides a fallback, this pattern is not used elsewhere in campaign pages (add-lists uses `data-gy-toggle-submit` data attribute for similar auto-submit behaviour). Two different JS auto-submit patterns.

6. **No header action for "Copy from another Campaign"**: Campaign-assets and campaign-resources both offer "Copy from another Campaign" as a header action. Campaign-attributes does not, even though attributes can presumably be copied between campaigns.

## Accessibility Notes

- Back link uses breadcrumb ARIA semantics
- Form has proper label-select association via `for`/`id` attributes
- `<noscript>` fallback ensures the form works without JavaScript
- Badge colour dots have adjacent text (value name) providing non-colour information
- Missing: Tables lack `<caption>` elements
- Missing: `<section>` elements per attribute type have no `aria-label`
- Concern: `onchange="this.form.submit()"` can be disorienting for screen reader users as the page reloads unexpectedly when changing a select value
- Good: The `form-select` uses Bootstrap's accessible select styling
- Missing: The empty third `<th>` has no `aria-label` or hidden text explaining the column purpose
