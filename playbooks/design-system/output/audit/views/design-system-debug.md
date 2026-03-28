# View Audit: Design System Debug

## Metadata

| Field         | Value                                                     |
|---------------|-----------------------------------------------------------|
| URL           | `/_debug/design-system/`                                  |
| Template      | `core/debug/design_system.html`                           |
| Extends       | `core/layouts/base.html` > `core/layouts/foundation.html` |
| Includes      | None                                                      |
| Template tags | None (no `{% load %}` beyond base)                        |
| Lint override | `{# djlint:off H021 #}` (allows inline styles)           |

## Components Found

### Navigation

- None (no back button, no breadcrumb -- top-level debug page)

### Sections (documented design system components)

The page documents 10 component categories:

1. **Colours** -- theme overrides, semantic colours, subtle backgrounds, text colours
2. **Typography** -- headings, heading utility classes, font sizes, font weights, custom text styles
3. **Links** -- default, `.linked`, `.link-sm`, secondary pattern, danger pattern, `.tooltipped`
4. **Buttons** -- standard (btn-sm), outline, full-size
5. **Badges** -- all `text-bg-*` variants
6. **Containers and surfaces** -- `border rounded p-3`, `border rounded p-2`, warning block, error block, card
7. **Form elements** -- text input, small input, select, checkbox, number (cost pattern), search input
8. **Tables** -- weapon stat table pattern
9. **Icons** -- commonly used Bootstrap Icons
10. **Flash highlight** -- `.flash-warn` animation
11. **Spacing scale** -- Bootstrap spacing levels 0-5

### Tables

- Headings table: `.table.table-sm.table-borderless.mb-4` with computed font sizes via JS
- Font sizes table: same pattern
- Weapon stat demo table: `.table.table-sm.table-borderless.mb-0.fs-7`

### Forms (demo)

- `.form-control`, `.form-control-sm`
- `.form-select`
- `.form-check` with `.form-check-input`, `.form-check-label`
- Number input: `.form-control.form-control-sm.text-center.p-0.w-auto`
- Search input: `.form-control.form-control-sm` with placeholder

### Buttons (demo)

- Standard: `.btn.btn-primary.btn-sm` through all variants (primary, secondary, success, danger, warning, info, light, dark, link)
- Outline: `.btn.btn-outline-primary.btn-sm` through subset (primary, secondary, success, danger)
- Full-size: `.btn.btn-primary`, `.btn.btn-success`, `.btn.btn-link`

### Badges (demo)

- All variants: `.badge.text-bg-primary` through `.text-bg-dark`

### Containers (demo)

- `.border.rounded.p-3` (standard)
- `.border.rounded.p-2` (compact)
- `.border.border-warning.rounded.p-3.bg-warning.bg-opacity-10` (warning)
- `.border.border-danger.rounded.p-2.text-danger` (error)
- `.card` > `.card-header.p-2` + `.card-body.p-2`

### Other

- **Flash animation demo:** `div.flash-warn.border.rounded.p-3`
- **Spacing scale visualization:** Coloured bars with `.bg-primary.rounded`
- **Inline JS:** Script to compute and display rendered font sizes

## Typography Usage

| Element                | Tag / Class              | Notes                           |
|------------------------|--------------------------|---------------------------------|
| Page title             | `<h1 class="h3">`       | Correct `.h3` override         |
| Section headings       | `<h2 class="h4 mb-3">`  | `h2` styled as `h4`            |
| Sub-section headings   | `<h3 class="h6 caps-label mb-2">` | `h3` styled as `h6` with `.caps-label` |
| Description text       | `p.text-secondary`       | Uses `.text-secondary` (not `.text-muted`) |
| Code samples           | `<code>`, `<code class="small text-secondary">` | Inline code |
| Heading demos          | `h1`-`h6` with `.mb-0`  | Raw heading elements            |
| Font weight demos      | `p.fw-light` through `p.fw-bold` | All weight classes      |

## Colour Usage

| Usage              | Class / Value        | Notes                              |
|--------------------|----------------------|------------------------------------|
| Description text   | `.text-secondary`    | Not `.text-muted` -- this is the reference |
| Colour swatches    | Inline `style="background:{{ hex }}"` | Dynamic from view context |
| Semantic swatches  | `.bg-{{ name }}`     | Dynamic Bootstrap semantic classes |
| Subtle swatches    | `.bg-{{ name }}-subtle` | Dynamic subtle variants         |
| Code labels        | `.text-secondary`    | Consistent muted code labels      |
| Spacing bars       | `.bg-primary`        | Primary colour for visualization  |

### Theme colours defined (from view context)

These are the custom SCSS colour overrides documented:

- `$blue: #0771ea`
- `$indigo: #5111dc`
- `$purple: #5d3cb0`
- `$pink: #c02d83`
- `$red: #cb2b48`
- `$orange: #ea5d0c`
- `$yellow: #e8a10a`
- `$green: #1a7b49`
- `$teal: #1fb27e`
- `$cyan: #10bdd3`

## Spacing Values

| Location              | Class(es)                   | Value           |
|-----------------------|-----------------------------|-----------------|
| Outer container       | `.col-12.px-0.vstack.gap-5.pb-5` | 3rem gap, 3rem bottom pad |
| Section spacing       | `.mb-3` on headings         | 1rem            |
| Sub-section spacing   | `.mb-2` on sub-headings     | 0.5rem          |
| Content blocks        | `.mb-4` on most sections    | 1.5rem          |
| Demo elements         | `.gap-2` in flex containers | 0.5rem          |
| Colour swatches       | Inline `width:5rem; height:3.5rem` | Fixed size |

## Custom CSS

| Class            | Source          | Description                                  |
|------------------|-----------------|----------------------------------------------|
| `.caps-label`    | `styles.scss`   | Small, uppercase, muted, semibold, tracked   |
| `.linked`        | `styles.scss`   | Link with underline opacity pattern          |
| `.link-sm`       | `styles.scss`   | Small link with underline opacity            |
| `.tooltipped`    | `styles.scss`   | Info underline, cursor: help                 |
| `.flash-warn`    | `styles.scss`   | Warning background fade animation (2s)       |
| `.fs-7`          | `styles.scss`   | Custom font size 0.9 * base                 |

## Inconsistencies

1. **Colour swatch rendering uses inline styles** (`style="background:{{ hex }}"`) which contradicts the Bootstrap-first approach. This is acceptable for a debug/reference page.
2. **The page itself uses `.text-secondary` for descriptions** but many actual app templates use `.text-muted`. The design system documents both but doesn't prescribe which to use in which context.
3. **Missing documentation of several patterns** used across the app:
   - Section header bar (`.bg-body-secondary.rounded.px-2.py-1`) used in pack detail
   - Empty state patterns (varies across pages)
   - Stretched link pattern
   - Activity item / list-group-item pattern
   - Filter form pattern (search + toggles)
   - Tab navigation pattern
4. **Cards section note says** "used for fighter grids and category groups" but cards appear nowhere in the pack pages. The border/rounded containers documented here are also absent from pack templates, which use a different section header pattern.
5. **The "cost pattern" number input** (`.form-control.form-control-sm.text-center.p-0.w-auto`) is documented but its usage context is not explained.
6. **No responsive behaviour documentation.** The design system shows static components but doesn't document breakpoint conventions (e.g., when to use `col-xl-8` vs `col-lg-6` vs `col-md-8`).

## Accessibility Notes

- The page has no `aria-label` on sections
- Heading hierarchy is well-structured: `h1` > `h2` > `h3`
- Form demos include `<label>` elements but lack `for` attributes in some cases (checkbox demo does have `for`)
- `data-measure` / `data-measure-target` attributes are used for JS enhancement only, not for accessibility
- Inline styles on colour swatches have no text alternative describing the colour values (partially covered by adjacent text)
- The page uses `djlint:off H021` to suppress inline style linting, which is appropriate for a reference page
