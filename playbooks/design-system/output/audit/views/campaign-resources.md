# View Audit: Campaign Resources

## Metadata

| Field | Value |
|---|---|
| URL | `/campaign/<id>/resources` |
| Template | `core/campaign/campaign_resources.html` |
| Extends | `core/layouts/base.html` |
| Template tags loaded | `allauth`, `custom_tags`, `color_tags` |
| Included templates | `core/includes/back.html` |
| Complexity | Medium -- dynamic list of resource types with per-type gang/amount tables |

## Components Found

### Buttons

No button elements on this page. All actions are styled as links.

### Cards

No card components used.

### Tables

| Table | Classes | Context |
|---|---|---|
| Resource table (per type) | `table table-sm table-borderless mb-0 align-middle` | Per-resource-type gang listing |

**Observations:**

- Consistent table pattern with campaign detail and campaign assets
- Three column headers: Gang, Amount, Actions
- "Actions" column always visible (no responsive hiding like campaign-assets)

### Navigation

| Element | Classes | Context |
|---|---|---|
| Back breadcrumb | `breadcrumb` / `breadcrumb-item active` | Top of page, "Back to Campaign" |

### Forms

No forms on this page.

### Icons

| Icon class | Context |
|---|---|
| `bi-chevron-left` | Back breadcrumb |
| `bi-box-arrow-in-down` | Copy from another Campaign link |
| `bi-plus-circle` | Add Resource Type link |
| `bi-pencil` | Edit resource type link, Modify resource link |
| `bi-trash` | Remove resource type link |

### Badges

No badges used.

### Dropdowns

No dropdowns used.

### Other Components

| Component | Classes | Context |
|---|---|---|
| Header layout | `d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2` | Page header with responsive stacking |
| Header actions | `hstack gap-3 ms-md-auto` | Copy and Add links (no `fs-7`) |
| Section heading wrapper | `d-flex justify-content-between align-items-center mb-2` | Per-type heading with action links |
| Type-level action bar | `hstack gap-3` | Per-type Edit/Remove links |
| Description text | `text-muted small mb-3 mb-last-0` | Resource type description |

## Typography Usage

| Element | Classes | Usage |
|---|---|---|
| Page heading | `h1` with `mb-2` | "Campaign Resources" |
| Campaign name | `p.text-muted.mb-0` | Subtitle |
| Section headings (per type) | `h2.h5.mb-0` | Resource type name |
| Table headers | `.caps-label` with `ps-0` | Gang, Amount, Actions columns |
| Action links | `icon-link link-secondary link-underline-opacity-25 link-underline-opacity-100-hover small` | Edit, Remove, Modify |
| Add type link | `icon-link link-primary link-underline-opacity-25 link-underline-opacity-100-hover small` | Header "Add Resource Type" |
| Copy link | `icon-link link-secondary link-underline-opacity-25 link-underline-opacity-100-hover small` | Header "Copy from another Campaign" |
| Empty state | `text-muted small mb-0` | No resources messages |
| Pre-campaign notice | `text-muted small` | "Campaign not started" in action column |

**Observations:**

- Header action links do NOT use `fs-7` unlike campaign-assets header actions. This means the text is slightly different in size from the assets page equivalent.
- Uses `icon-link` class on action links, which campaign-assets also uses for its expanded links but not consistently across all link types.

## Colour Usage

| Colour | Bootstrap class | Context |
|---|---|---|
| Primary blue | `link-primary` | Add Resource Type link |
| Secondary grey | `link-secondary` | Copy, Edit, Modify links |
| Danger red | `link-danger` | Remove resource type link |
| Muted grey | `text-muted` | Campaign name, descriptions, empty states, pre-campaign notice |

Identical colour semantics to campaign-assets.

## Spacing Values

| Spacing class | Context |
|---|---|
| `gap-5` | Main page vstack between sections |
| `gap-3` | Action link hstacks |
| `gap-2` | Header d-flex |
| `mb-0` | Section headings; tables; campaign name; empty states |
| `mb-2` | Page heading h1; section heading wrapper |
| `mb-3` | Resource type description |
| `px-0` | Main column |
| `ps-0` | Gang column cells and header |
| `pe-0` | Actions column cells and header |

## Custom CSS

| Class | Source | Usage |
|---|---|---|
| `caps-label` | `styles.scss` | Table headers |
| `mb-last-0` | `styles.scss` | Resource type description containers |
| `{% list_with_theme %}` | Template tag | Gang name rendering in tables |

## Inconsistencies

1. **No `fs-7` on header actions**: Campaign-assets uses `fs-7` on its header action links; this page does not. The visual result is slightly larger text for "Add Resource Type" and "Copy from another Campaign" compared to the equivalent links on the assets page.

2. **No responsive action pattern**: Unlike campaign-assets which has desktop-expanded/mobile-dropdown, this page shows all action links at all viewport sizes. The `icon-link` Edit/Remove links could overflow on narrow screens when text is long.

3. **Header action order**: "Copy from another Campaign" appears BEFORE "Add Resource Type" in the DOM/visual order. On campaign-assets, the "Add Asset Type" appears FIRST, then "Copy from another Campaign". Inconsistent ordering of the same conceptual action pair.

4. **Table Actions column**: Always shows "Actions" header text with no responsive hiding, unlike campaign-assets which uses `d-none d-sm-inline` for the header and `d-none d-sm-inline` for expanded links. Since this page has no responsive pattern, the explicit "Actions" text is always visible.

5. **Modify vs Edit naming**: Resource amounts use "Modify" as the action verb while assets use "Edit". The different verbs for similar actions (changing a value) is a microcopy inconsistency.

6. **Description safe filter**: Uses `{{ resource_type.description|safe }}` -- same raw `|safe` concern as campaign-assets. Should use `|safe_rich_text|safe` if content is user-generated.

## Accessibility Notes

- Back link uses breadcrumb ARIA semantics
- Tables have proper `<thead>` structure
- Missing: Tables lack `<caption>` elements
- Missing: `<section>` elements per resource type have no `aria-label`
- Good: Modify links include `return_url` parameter for navigation flow
- Concern: The conditional display of "Campaign not started" text in the Actions column replaces interactive elements -- screen reader users may not understand why "Modify" is sometimes absent
