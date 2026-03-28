# View Audit: Dice

## Metadata

- **URL:** `/dice/`
- **Template:** `core/dice.html`
- **Template chain:** `core/layouts/foundation.html` > `core/layouts/base.html` > `core/dice.html`
- **Includes:** `core/includes/home.html` (breadcrumb)

## Components Found

### Buttons

| Text | Classes | Variant | Size | Icon | Notes |
|------|---------|---------|------|------|-------|
| Roll D6 | `btn btn-primary` or `btn btn-outline-secondary` | Primary (active) / Outline Secondary (inactive) | Default | None | Mode toggle; no `btn-sm` |
| Roll D3 | `btn btn-primary` or `btn btn-outline-secondary` | Primary (active) / Outline Secondary (inactive) | Default | None | Mode toggle |
| Reset | `btn btn-outline` | Outline (no variant!) | Default | None | Reset link; `btn-outline` alone is not a valid Bootstrap class |
| Minus (per group) | `btn btn-outline-secondary` | Outline Secondary | Default | `bi-dash-lg` | Remove one die; `disabled` class when count=1 |
| "1" (per group) | `btn btn-outline-secondary` | Outline Secondary | Default | None | Reset to 1 die; `disabled` when count=1 |
| Plus (per group) | `btn btn-outline-primary` | Outline Primary | Default | `bi-plus-lg` | Add one die |
| Remove group | `btn btn-outline-danger` | Outline Danger | Default | `bi-x-lg` | Remove dice group; only shown for groups after the first |
| New dice group | `btn btn-primary` | Primary | Default | `bi-plus-lg` | Add new dice group |

### Cards

None found.

### Navigation

| Component | Classes | Notes |
|-----------|---------|-------|
| Breadcrumb | `breadcrumb` / `breadcrumb-item active` | Via home.html include |

### Forms

None found (all interactions via links).

### Icons (Bootstrap Icons)

| Icon class | Context | Purpose |
|------------|---------|---------|
| `bi-chevron-left` | Breadcrumb | Back indicator |
| `bi-dash-lg` | Minus button | Decrease count |
| `bi-plus-lg` | Plus button, New dice group | Increase count / Add group |
| `bi-x-lg` | Remove group | Delete group |
| `bi-dice-{1-6}` | Dice results | Dice face display |

### Badges

None found.

### Button Groups

| Context | Classes | Notes |
|---------|---------|-------|
| Mode toggles | `d-grid gap-2 d-md-block` | Not a proper `btn-group`; uses grid on mobile, inline on desktop |
| Dice controls (per group) | `btn-group` | Standard Bootstrap button group |

### Other Components

| Component | Classes | Notes |
|-----------|---------|-------|
| Dice grid | `row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4 h1` | Responsive grid with `h1` font size for dice icons |
| Dice display | `hstack gap-2 flex-wrap` | Inline dice icons |

## Typography Usage

| Element | Classes applied | Semantic role |
|---------|----------------|---------------|
| Page heading | `<h1>` with `visually-hidden` | Screen reader only; no visible heading |
| Dice icons | Inherited `h1` from parent `div` | Large dice display; `h1` class on a `<div>` for sizing |
| Button text | Default button text | "Roll D6", "Roll D3", "Reset", "1" |

## Colour Usage

| Element | Property | Source | Semantic purpose |
|---------|----------|-------|-----------------|
| Active mode button | background | `btn-primary` | Selected state |
| Inactive mode button | border/text | `btn-outline-secondary` | Unselected state |
| Plus button | border/text | `btn-outline-primary` | Positive action |
| Remove group button | border/text | `btn-outline-danger` | Destructive action |
| Reset button | border | `btn-outline` (invalid!) | Neutral reset |
| New dice group | background | `btn btn-primary` | Primary action |

## Spacing Values

| Element | Property | Source class | Notes |
|---------|----------|-------------|-------|
| Outer wrapper | padding | `px-0` | Removes horizontal padding |
| Outer vstack | gap | `vstack gap-3` | 1rem gap |
| Mode button grid (mobile) | gap | `d-grid gap-2` | 0.5rem gap on mobile |
| Dice result grid | gap | `g-4` | 1.5rem column/row gap |
| Each dice group | gap | `vstack gap-2` | Within group |
| Each dice group | padding | `py-3` | Vertical padding |
| Dice row | gap | `hstack gap-2` | Between dice icons |
| Remove group button | margin | `ms-auto ms-md-0` | Right-aligned on mobile, no margin on desktop |
| New dice group wrapper | margin | `mt-3` | Top margin |
| New dice group wrapper | alignment | `hstack justify-content-center` | Centered |

## Custom CSS

None used in this template directly.

## Inconsistencies

| Issue | Elements involved | Description | Severity |
|-------|-------------------|-------------|----------|
| Invalid Bootstrap class | Reset button `btn btn-outline` | `btn-outline` is not a valid Bootstrap 5 button variant. Should be `btn-outline-secondary` or similar. This will render without proper styling. | High |
| `h1` used for font sizing | Dice grid wrapper `row ... h1` | Using `h1` class on a `<div>` purely for font-size is a misuse of heading utility classes. Should use `fs-1` or a custom size class. | Medium |
| Button size inconsistency | All buttons use default size | This page uses default-sized buttons while most other pages prefer `btn-sm`. However, for a touch-focused dice roller, larger buttons may be intentional. | Low |
| Remove group margin inconsistency | `ms-auto ms-md-0` | On mobile, the remove button is right-aligned (`ms-auto`), but on desktop it is part of the button group with no margin. This creates different visual grouping at breakpoints. | Low |
| `rel="nofollow"` on all links | All dice action links | Every link uses `rel="nofollow"` -- correct for SEO but notable as a pattern. | Low |

## Accessibility Notes

- The `<h1>` is `visually-hidden` ("Roll some dice") -- good for screen readers.
- Minus/plus buttons have `aria-label` ("Remove one die", "Add one die", "Remove dice group").
- Disabled minus button has `aria-label="Remove one die (disabled)"`.
- Dice icons have `aria-label="Dice showing {n}"` -- good accessibility.
- Mode toggle buttons lack `aria-pressed` or equivalent active-state ARIA attribute.
- All links use `<a>` elements rather than `<button>` -- semantically, these are navigation actions (they change URL query params), so `<a>` is appropriate.
