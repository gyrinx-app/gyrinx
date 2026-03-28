# View Audit: List Print

## Metadata

- **URL**: `/list/<id>/print`
- **Template**: `core/list_print.html`
- **Extends**: `core/layouts/base_print.html` -> `core/layouts/foundation.html`
- **Template tags loaded**: `static`, `allauth`, `custom_tags`
- **Stylesheet**: `core/css/print.css` (from `print.scss`, base font 1rem, body zoom 50%)
- **Key includes**:
  - `core/includes/list.html` (with `print=True`, `print_config=print_config`)
  - All sub-includes from list.html in print mode
- **Auto-print**: JavaScript triggers `window.print()` on DOMContentLoaded

## Components Found

### Buttons

No interactive buttons rendered in print mode. All `{% if not print %}` blocks suppress buttons, links, and forms.

### Cards

| Pattern | Classes | Location |
|---------|---------|----------|
| Fighter card (print) | `card g-col-12 g-col-sm-6 g-col-md-3 g-col-xl-2 break-inside-avoid` | fighter_card_content.html (print default classes) |
| Blank fighter card | `card g-col-12 g-col-sm-6 g-col-md-3 g-col-xl-2 break-inside-avoid` | blank_fighter_card.html |
| Fighter card header | `card-header p-2 hstack align-items-start` | fighter_card_content.html |
| Fighter card body | `card-body p-0` | fighter_card_content.html |

### Tables

| Pattern | Classes | Location |
|---------|---------|----------|
| Stats summary | `table table-sm table-borderless table-responsive text-center mb-0` | list_common_header.html |
| Fighter statline | `table table-sm table-borderless table-fixed mb-0` | fighter_card_content_inner.html |
| Weapons table | `table table-sm table-borderless mb-0 fs-7` | list_fighter_weapons.html |
| Attributes table | `table table-sm table-borderless mb-0 fs-7` | list_attributes.html |
| Blank fighter statline | `table table-sm table-borderless table-fixed mb-0` | blank_fighter_card.html |
| Blank weapons table | `table table-sm table-borderless mb-0 fs-7` | blank_fighter_card.html |

### Badges

| Pattern | Classes | Context |
|---------|---------|---------|
| Cost (print) | `badge text-body border fw-normal` | fighter_card_cost.html |
| Cost (print, overridden) | `badge text-body border fw-normal` | fighter_card_cost.html (same in print) |
| Injury state | `badge ms-2 bg-warning` / `badge ms-2 bg-danger` | fighter_card_content.html |
| Captured | `badge ms-2 bg-warning text-dark` | fighter_card_content.html |
| Campaign status | `badge bg-secondary` / `badge bg-success` | campaign status.html |
| Blank cost | `badge text-body border fw-normal` | blank_fighter_card.html |

### Icons

In print mode, icons are rendered but many are suppressed inside `{% if not print %}` blocks. Remaining icons:

- `bi-award` - Campaign link (text only, no link)
- `bi-box-seam` - Pack icon on fighters
- `bi-dash` - Weapon sub-items
- `bi-crosshair` - Weapon accessories
- `bi-arrow-up-circle` - Weapon upgrades
- `bi-person` - Owner name

### Other Components

| Pattern | Classes | Location |
|---------|---------|----------|
| QR code | `hstack h-100 ms-2 mb-2 align-items-start justify-content-end` wrapper, `sq-6` for QR SVG | list.html (print mode) |
| CSS grid | `grid auto-flow-dense gap-2` | list.html (print mode adds `gap-2`) |
| Fighter groups | `grid h-100 gap-2 gap-md-0 border rounded p-2 bg-secondary-subtle` | list.html |
| Content wrapper | `p-2` (id="content") | list_print.html |

## Typography Usage

| Element | Classes | Size | Context |
|---------|---------|------|---------|
| Gang name | `h2.mb-0.h3` | h3 at 1rem base | list_common_header.html |
| Owner name | `fs-7 text-muted` | 0.9rem | list_common_header.html |
| Fighter name | `h3.h5.mb-0` | h5 at 1rem base | fighter_card_content.html |
| Fighter type | default | 1rem base | fighter_card_content.html |
| Stat headers | `fs-5` (print override) | ~1.25rem | fighter_card_content_inner.html |
| Stat values | `fs-5` (print override) | ~1.25rem | list_fighter_statline.html |
| Detail rows | `fs-7` | 0.9rem | fighter_card_content_inner.html |
| Weapons table | `fs-7` | 0.9rem | list_fighter_weapons.html |
| Cost badge (print) | `fs-3` wrapper | ~1.75rem | fighter_card_content.html (print cost section) |
| Blank card stats | `fs-5` | ~1.25rem | blank_fighter_card.html |
| Blank card details | `fs-7` | 0.9rem | blank_fighter_card.html |

**Note**: Print SCSS sets `$font-size-base: 1rem` (vs screen's `0.875rem`), then `body { zoom: 50% }`. This effectively halves everything visually but uses larger base calculations.

## Colour Usage

| Colour | Bootstrap Class | Context |
|--------|----------------|---------|
| Warning subtle | `bg-warning-subtle` | Stat highlights, captured/injured card headers |
| Danger subtle | `bg-danger-subtle` | Dead card headers |
| Secondary subtle | `bg-secondary-subtle` | Fighter group background |
| Body secondary | `bg-body-secondary` | Section headers |
| Warning | `bg-warning` | Injury badge |
| Danger | `bg-danger` | Dead badge |
| Dark text on warning | `text-dark` | Captured badge |
| Body text with border | `text-body border` | Cost badge (print variant) |

## Spacing Values

| Property | Values Used | Context |
|----------|-------------|---------|
| Content padding | `p-2` | #content wrapper |
| Grid gap | `gap-2` (print-specific) | fighter grid |
| Card header | `p-2` | fighter cards |
| Card body | `p-0` | fighter cards (print mode) |
| Section header | `px-2 py-1` | section headers |
| QR code margin | `ms-2 mb-2` | QR wrapper |

## Custom CSS

| Class | Definition | Used In |
|-------|-----------|---------|
| `break-inside-avoid` | `break-inside: avoid` | All cards, prevents page breaks mid-card |
| `auto-flow-dense` | `grid-auto-flow: row dense` | Fighter grid |
| `sq-6` | `height: 6em; width: 6em` | QR code |
| `table-fixed` | `table-layout: fixed` | Fighter statlines |
| `table-group-divider` | Border-top override | Table sections |
| `flash-warn` | Flash animation | (suppressed in print via no JS interaction) |

### Print-specific SCSS

```scss
// print.scss
$font-size-base: 1rem;
@import "./styles";
body { zoom: 50%; }
```

No dedicated print media queries in the SCSS. The print layout is achieved through:

1. Different SCSS entry point (`print.scss` vs `screen.scss`)
2. Different base template (`base_print.html` -- no navbar, no footer)
3. Template conditionals (`{% if print %}` / `{% if not print %}`)
4. Different grid column classes in print mode

## Inconsistencies

1. **No print-specific `@media print` rules**: The print stylesheet is loaded as the main stylesheet (replacing screen.css), rather than using `@media print` queries. This means the print page looks like a print layout even when viewed in a browser before the print dialog opens. There's no screen fallback.

2. **Zoom approach**: Using `body { zoom: 50% }` is a non-standard CSS property (WebKit/Blink only). Firefox does not support `zoom`. This could cause layout issues for Firefox users printing the page.

3. **Font size escalation in print**: Print mode uses `fs-5` for stat values (equivalent to ~1.25rem at 1rem base = 1.25rem, then halved by zoom to ~0.625rem visual), while screen uses `fs-7` (~0.79rem). After zoom, print stats are actually smaller visually than screen stats.

4. **Cost badge sizing inconsistency**: In print mode, the cost is wrapped in `<div class="fs-3">` (the entire cost include), making costs visually much larger than other content. This wrapper is only added in print mode -- screen mode has no size wrapper.

5. **Blank card hardcoded stats**: The blank_fighter_card.html hardcodes 12 stat columns (M, WS, BS, S, T, W, I, A, Ld, Cl, Wil, Int). If a content fighter has a different statline length, the blank card won't match. The hardcoded `colspan="4"` and `colspan="8"` for detail rows also assumes 12 columns.

6. **Print config optionality**: `print_config` controls whether actions, assets, attributes, and stash are included. But fighter cards themselves are always included -- there's no option to exclude specific fighter types in print.

7. **Grid classes change entirely**: Screen uses `g-col-12 g-col-xl-8` for the outer wrapper, while print uses `g-col-12 g-col-sm-6 g-col-md-6 g-col-xl-4`. These are completely different responsive breakpoints.

## Accessibility Notes

1. **No navigation or skip links**: `base_print.html` extends `foundation.html` directly without the navbar or skip link from `base.html`. This is appropriate for print but means the printed page has no navigation at all.

2. **Auto-print**: The JavaScript auto-triggers `window.print()`, which may be unexpected for screen reader users or users with assistive technology. There's no way to preview the page without the print dialog appearing.

3. **QR code**: The QR SVG is rendered via `{% qr_svg %}` template tag. It's unclear if the SVG includes an accessible `<title>` or `aria-label`. The QR code links to the list's print URL.

4. **No page title visible**: The page has a `<title>` element but no visible `<h1>`. The gang name appears as `h2.h3` in the header, but there's no explicit page heading.

5. **Table accessibility**: Stat tables use `<th scope="col">` which is correct. The weapons table also uses `<th scope="col">`. Detail rows use `<th scope="row">` for labels.
