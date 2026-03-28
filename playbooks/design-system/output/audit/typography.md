# Typography Audit

Cross-cutting typography analysis across 48 view audits, SCSS source, and template grep results.

---

## 1. SCSS Typography Definitions

### Font Stack

```scss
$font-family-sans-serif:
    "mynor-variable",
    system-ui, -apple-system, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, "Noto Sans", "Liberation Sans",
    sans-serif, "Apple Color Emoji", "Segoe UI Emoji",
    "Segoe UI Symbol", "Noto Color Emoji";
$font-family-base: $font-family-sans-serif;
```

Custom web font `mynor-variable` is the primary typeface.

### Base Font Sizes

| Context | `$font-size-base` | Effective Value |
|---------|-------------------|-----------------|
| Screen (`screen.scss`) | `0.875rem` | 14px |
| Print (`print.scss`) | `1rem` | 16px (then `zoom: 50%` = 8px visual) |

### Custom Font Size: `fs-7`

```scss
$custom-font-sizes: (
    7: $font-size-base * 0.9,
);
$font-sizes: map-merge($font-sizes, $custom-font-sizes);
```

| Context | Computed Size |
|---------|---------------|
| Screen | `0.875rem * 0.9 = 0.7875rem` (~12.6px) |
| Print | `1rem * 0.9 = 0.9rem` (then zoomed to ~7.2px visual) |

### Custom Text Classes

| Class | Definition | Composition |
|-------|-----------|-------------|
| `.caps-label` | `@extend .small; @extend .text-uppercase; @extend .text-muted; @extend .fw-semibold; letter-spacing: 0.03em` | Small, uppercase, muted, semibold, tracked |
| `.link-sm` | `@extend .link-underline-opacity-25; @extend .link-underline-opacity-100-hover; @extend .link-offset-1; @extend .fs-7` | Small link with underline |
| `fieldset legend` | `font-size: $font-size-base` | Resets legend to body size |

### Responsive Font Size Classes

```scss
@each $bp, $bp-value in $grid-breakpoints {
    .fs-#{$bp}-normal {
        font-size: $font-size-base !important;
    }
}
```

Generates: `.fs-xs-normal`, `.fs-sm-normal`, `.fs-md-normal`, `.fs-lg-normal`, `.fs-xl-normal`, `.fs-xxl-normal`

---

## 2. Complete Type Scale

### Bootstrap Font Sizes at `$font-size-base: 0.875rem`

| Class | Scale Factor | Computed (screen) | Computed (print) | Role |
|-------|-------------|-------------------|------------------|------|
| `fs-1` / `h1` | `$font-size-base * 2.5` | `2.1875rem` (~35px) | `2.5rem` | Display heading |
| `fs-2` / `h2` | `$font-size-base * 2` | `1.75rem` (~28px) | `2rem` | Page heading |
| `fs-3` / `h3` | `$font-size-base * 1.75` | `1.53125rem` (~24.5px) | `1.75rem` | Section heading |
| `fs-4` / `h4` | `$font-size-base * 1.5` | `1.3125rem` (~21px) | `1.5rem` | Sub-section |
| `fs-5` / `h5` | `$font-size-base * 1.25` | `1.09375rem` (~17.5px) | `1.25rem` | Card/component heading |
| `fs-6` / `h6` | `$font-size-base * 1` | `0.875rem` (14px) | `1rem` | Minor heading |
| (body) | `$font-size-base * 1` | `0.875rem` (14px) | `1rem` | Body text |
| `.fs-7` | `$font-size-base * 0.9` | `0.7875rem` (~12.6px) | `0.9rem` | Compact text |
| `.small` | `$font-size-base * 0.875` | `0.765625rem` (~12.25px) | `0.875rem` | Small text |
| `.lead` | `$font-size-base * 1.25` | `1.09375rem` (~17.5px) | -- | Lead paragraph (= h5) |

---

## 3. Typography Class Usage Across Templates

### Heading Tags (from template grep: 132 occurrences across 50 files)

| Pattern | Frequency | Views | Purpose |
|---------|-----------|-------|---------|
| `<h1 class="h3">` | ~18 views | Fighter edit, list edit, campaign edit/new, pack edit, design system | **Standard page title** |
| `<h1>` (no class) | ~6 views | Campaign detail, packs index, flatpage, login, pack detail | Full-size page title |
| `<h1 class="mb-0">` | ~3 views | Campaign detail, pack detail, pack activity | Full-size, no margin |
| `<h1 class="mb-1">` | ~3 views | Lists index, campaigns index, packs index | Full-size, tight margin |
| `<h1 class="h3 mb-0">` | ~2 views | Pack activity | Downsized, no margin |
| `<h1 class="h3 mb-1">` | ~1 view | Pack lists | Downsized, tight margin |
| `<h1 class="h2 mb-0">` | ~1 view | User profile | Non-standard sizing |
| `<h1>` visually-hidden | 1 view | Dice | Screen-reader only |
| No `<h1>` at all | ~5 views | List about, list notes, list credits edit, account home, list print | Accessibility gap |

### Heading Class Overrides

| Tag + Class | Rendered As | Frequency | Purpose |
|-------------|------------|-----------|---------|
| `h1.h3` | h3 visual size | ~18 views | Sub-page titles |
| `h1.h2` | h2 visual size | 1 view | User profile |
| `h2.h3` | h3 visual size | ~5 views | Gang name in common header |
| `h2.h4` | h4 visual size | ~4 views | Section titles (home, user, about/notes) |
| `h2.h5` | h5 visual size | ~20 views | Section headings (very common) |
| `h3.h4` | h4 visual size | ~3 views | About/notes section titles |
| `h3.h5` | h5 visual size | ~15 views | Fighter names, category headings |
| `h3.h6` | h6 visual size | ~2 views | Embed fighter name, stash |
| `h4.h6` | h6 visual size | ~2 views | Gear items, stash sub-headers |
| `h4` (card-title) | h4 default | ~2 views | Advancement dice cards |
| `h5.card-title` | h5 default | ~2 views | Stats edit card |
| `h5.mb-0` | h5 default | ~3 views | Injuries card header |
| `h6.mb-0` | h6 default | ~1 view | Stash credits header |
| `<h2>` (no class) | h2 default | ~3 views | XP edit, advancements, credits edit |

### Font Size Utility Classes

| Class | Template Files | Total Occurrences | Primary Purpose |
|-------|----------------|-------------------|-----------------|
| `fs-7` | ~35 | ~80+ | Compact text: tabs, stats, metadata, filter labels, weapon tables, button text |
| `fs-5` | ~8 | ~20 | Print stat values, credits list, subtitle text, XP badges wrapper |
| `fs-6` | ~2 | ~3 | Common header stat values |
| `fs-3` | ~2 | ~3 | Dice icon display, print cost wrapper |
| `fs-2` | ~1 | ~1 | Logged-out marketing lead text |
| `fs-1` | ~1 | ~1 | Dice grid (`h1` class on div) |
| `.small` | ~25 | ~50+ | Metadata, timestamps, action links, empty states |
| `.lead` | ~1 | ~2 | Home page marketing text |

### Font Weight Classes

| Class | Template Files | Total Occurrences | Purpose |
|-------|----------------|-------------------|---------|
| `fw-semibold` | ~3 | ~5 | Custom in `.caps-label`, form label, attribute label |
| `fw-medium` | ~3 | ~5 | Pack name, list pack name, content packs label |
| `fw-normal` | ~3 | ~4 | Print badge, attribute badge, house name |
| `fw-bold` | ~1 | ~1 | Design system demo |
| `fw-light` | ~2 | ~3 | Hero heading, private notes label, design system demo |

### Text Transform Classes

| Class | Template Files | Total Occurrences | Purpose |
|-------|----------------|-------------------|---------|
| `text-uppercase` | ~8 | ~15 | Via `.caps-label`, group headers, dropdown headers, private notes label |

### Other Typography Classes

| Class | Occurrences | Purpose |
|-------|-------------|---------|
| `fst-italic` | ~3 | Empty state text (lore/notes overview) |
| `font-monospace` | ~3 | Debug banners |
| `text-center` | ~20+ | Tables, empty states, badges |
| `text-decoration-underline` | ~3 | `.tooltipped` class, current sidebar item |
| `text-decoration-line-through` | ~3 | Disabled skills/rules |
| `text-decoration-none` | ~5 | Sub-page links, badge links |
| `text-nowrap` | ~3 | Form labels, metadata |

---

## 4. Implicit Type Scale in Use

Sorting all actually-used font sizes (screen context):

| Rank | Size | Source | Usage |
|------|------|--------|-------|
| 1 | `2.1875rem` (35px) | `h1` / `fs-1` | Full-size page titles (6 views), dice display |
| 2 | `1.75rem` (28px) | `h2` / `fs-2` | Marketing lead text, XP/advancements heading (3 views) |
| 3 | `1.53125rem` (24.5px) | `h3` / `fs-3` | Standard page title via `h1.h3`, gang name via `h2.h3` (~23 views) |
| 4 | `1.3125rem` (21px) | `h4` / `fs-4` | Section titles via `h2.h4`, `h3.h4` (~7 views) |
| 5 | `1.09375rem` (17.5px) | `h5` / `fs-5` | Section headings via `h2.h5`, `h3.h5`, credits display, print stat values (~35 views) |
| 6 | `0.875rem` (14px) | `h6` / body / `fs-6` | Body text, minor headings via `h4.h6` |
| 7 | `0.7875rem` (12.6px) | `.fs-7` | Compact UI: tabs, stats, weapons tables, filter labels (~35 files) |
| 8 | `0.765625rem` (12.25px) | `.small` | Metadata, timestamps, action links (~25 files) |

**Key observation:** Ranks 7 and 8 (`fs-7` at 12.6px and `.small` at 12.25px) are only 0.35px apart. They serve overlapping purposes (compact metadata text) and are often used interchangeably. This creates visual near-duplicates.

---

## 5. Pattern Analysis

### Page Title Patterns (h1)

Three distinct patterns with no clear rule for when to use which:

| Pattern | Count | Examples |
|---------|-------|---------|
| `<h1 class="h3">` | ~18 | All edit/new form pages, design system debug |
| `<h1>` (full size) | ~9 | Campaign detail, index pages, flatpages, login |
| No `<h1>` | ~5 | List about/notes, list credits, account home, print |

**Implicit rule (not documented):** Form pages and sub-pages use `h1.h3`; top-level entity pages and index pages use full `h1`.

### Section Heading Patterns

| Pattern | Count | Context |
|---------|-------|---------|
| `h2.h5.mb-0` | ~15 | Inside section header bars (`bg-body-secondary rounded px-2 py-1`) |
| `h2.h5.mb-2` | ~5 | Standalone section headings (campaign sub-pages) |
| `h2.h5.mb-3` | ~3 | Standalone section headings (campaign packs, pack lists) |
| `h2.h4` | ~4 | About/notes section titles, home section headers |
| `h2.h4.mb-3` | ~2 | Design system debug sub-sections |
| `h3.h5.mb-0` | ~12 | Card headers (skills, weapons, gear categories) |
| `h3.h4` | ~3 | About/notes fighter names |
| `h3.h5` | ~8 | Fighter names in cards, list item names |

### Compact Text Pattern (`fs-7`)

`fs-7` is the most-used custom class. Primary uses:

| Context | Pattern | Frequency |
|---------|---------|-----------|
| Fighter card tabs | `nav-link fs-7 px-2 py-1` | Every list detail page |
| Stat headers/values | `fs-7` (screen), `fs-5` (print) | Every fighter card |
| Weapons/gear tables | `table ... fs-7` | Every weapon/gear display |
| Filter labels | `form-check-label fs-7 mb-0` | All filter forms |
| Filter dropdowns | `.dropdown-menu ... fs-7` | List/campaign/pack filters |
| Action button text | `btn btn-link icon-link fs-7` | Skills/rules toggle buttons |
| Metadata (header) | `fs-7 text-muted` | Common header owner/house |
| Activity links | `fs-7` | Campaign assets header |

### Label Patterns

Two competing label patterns for section metadata:

| Pattern | Properties | Usage |
|---------|-----------|-------|
| `.caps-label` (custom) | `small + text-uppercase + text-muted + fw-semibold + letter-spacing: 0.03em` | Campaign detail, list detail, campaign sub-pages: ~15 uses |
| Manual caps label | `text-secondary text-uppercase small` + sometimes `strong` or `fw-light` | Pack detail house groups, list notes private label: ~5 uses |

The manual pattern is missing `fw-semibold` and `letter-spacing` from `.caps-label`, creating visual inconsistency.

### Private Notes Label Anti-Pattern

List notes uses `text-uppercase fs-7 fw-light text-secondary mb-1` for the "Private" label. This is the **opposite** of `.caps-label`:

- `fw-light` vs `fw-semibold`
- `fs-7` vs `.small` (different size)
- `text-secondary` vs `text-muted`

---

## 6. Inconsistencies

### 6.1 Page Title Heading Level (Critical)

5 views have no `<h1>` at all:

- **List About** and **List Notes**: Gang name is `h2.h3`, no h1
- **List Credits Edit**: Uses `<h2>` for page title
- **Account Home**: No visible heading
- **List Print**: No h1 (gang name is h2.h3)

3 views use `<h2>` where `<h1>` is expected:

- **XP Edit**: `<h2>` with no class
- **Advancements**: `<h2>` with no class
- **Credits Edit**: `<h2>` with no class

### 6.2 Full `h1` vs `h1.h3` (Medium)

No documented rule for when to use which. Current implicit pattern:

- **Full h1**: Campaign detail, packs index, lists index, campaigns index, flatpages, login, campaign add-lists
- **h1.h3**: All edit/new forms, fighter sub-pages, pack sub-pages, design system debug

Exceptions that break the implicit pattern:

- **Pack detail**: Full `h1` (should be `h1.h3` if it is a sub-page of packs index?)
- **Campaign detail**: Full `h1` (consistent -- entity detail pages use full h1)
- **User profile**: `h1.h2` (unique, not h1 or h1.h3)

### 6.3 `fs-7` vs `.small` Confusion (Medium)

Both used for "smaller than body" text with different sizes:

- `fs-7` = `0.7875rem` (12.6px)
- `.small` = `0.765625rem` (12.25px)

Templates mix them arbitrarily:

- Filter labels: `fs-7`
- Activity metadata: `.small`
- Action links: `.small`
- Stat headers: `fs-7`
- Owner name: `fs-7 text-muted`
- Timestamps: `small text-muted` or `text-muted small`

The 0.35px difference is visually imperceptible, making the distinction pointless.

### 6.4 Caps Label vs Manual Uppercase (Low)

Three approaches to uppercase section labels:

1. `.caps-label` custom class (correct)
2. `text-secondary text-uppercase small` (missing semibold + tracking)
3. `text-uppercase fs-7 fw-light text-secondary` (opposite weight)

### 6.5 Section Heading Margin Inconsistency (Low)

The same `h2.h5` pattern used with different bottom margins:

- `mb-0`: Inside section header bars
- `mb-1`: TOC heading
- `mb-2`: Campaign add-lists, campaign assets/resources sections
- `mb-3`: Campaign packs, pack lists available section

### 6.6 Print Typography Mismatch (Low)

Print mode switches `fs-7` to `fs-5` for stat values, creating a different visual hierarchy. The switch only applies to stats -- weapon tables stay at `fs-7` in print, creating an inconsistency within the printed card.

### 6.7 `h1` Used for Font Sizing (Low)

The dice page applies `h1` class to a `<div>` purely for font-size effect. Should use `fs-1` instead.

---

## 7. Consolidation Recommendation

### Proposed Type Scale

Reduce the effective scale from 8 levels to 6 by merging `fs-7` and `.small`:

| Token | Size | CSS | Usage |
|-------|------|-----|-------|
| `$gy-display` | `h1` default | `fs-1` | Full-width page titles (index pages, entity details) |
| `$gy-page-title` | `h3` default | `.h3` on `h1` | Sub-page titles (edit/new forms, management pages) |
| `$gy-section` | `h5` default | `.h5` on `h2` | Section headings |
| `$gy-body` | `0.875rem` | body default | Body text |
| `$gy-compact` | `0.8125rem` | new `.fs-7` value | Merge current fs-7 and .small |
| `$gy-micro` | `0.75rem` | new scale level | Reserved for extreme density (future) |

### Specific Changes

#### 1. Merge `fs-7` and `.small` into a single compact size

Change the `fs-7` definition to match `.small` exactly (`0.875 * base`), or create a new token that replaces both:

```scss
$custom-font-sizes: (
    7: $font-size-base * 0.875,  // Align with .small = 0.765625rem
);
```

This eliminates the meaningless 0.35px difference. All `.small` usage and `fs-7` usage would then produce identical results, allowing gradual migration to whichever class is preferred. Recommendation: use `fs-7` as the utility class (it is more explicit) and `.small` only when inside Bootstrap components that expect it.

Alternatively, bump `fs-7` to `$font-size-base * 0.8125` (13px at base 16px, ~11.4px at base 14px) to create a more distinct step. This would require visual review.

#### 2. Standardise page title pattern

Document the rule explicitly:

| Page Type | Heading Pattern | Example |
|-----------|----------------|---------|
| Top-level index | `<h1 class="mb-1">` | Lists, Campaigns, Packs |
| Entity detail | `<h1 class="mb-0">` | Campaign detail, Pack detail |
| Sub-page / form | `<h1 class="h3">` | All edit/new pages |
| Wizard step | `<h3 class="h5 mb-0">` under progress `<h2>` | Advancement flow |

Fix the 5 views with no `<h1>` and 3 views using `<h2>` as page title.

#### 3. Standardise section headings

| Context | Pattern |
|---------|---------|
| Inside section header bar | `<h2 class="h5 mb-0">` |
| Standalone section heading | `<h2 class="h5 mb-2">` |
| Card header heading | `<h3 class="h5 mb-0">` |
| Sub-section label | `.caps-label` |

Remove all manual uppercase label patterns and replace with `.caps-label`.

#### 4. Fix Private Notes label

Replace `text-uppercase fs-7 fw-light text-secondary mb-1` with `caps-label mb-1`.

#### 5. Standardise heading semantic levels

Document the heading hierarchy convention:

```
h1 — Page title (one per page, always present)
  h2 — Major sections
    h3 — Cards, items within sections
      h4 — Sub-items (advancement cards, gear items)
        h5 — Card titles (only used by Bootstrap card-title internally)
          h6 — Rare sub-sub-items
```

Current violations:

- `h2.h3` for gang name + `h2` for page title on same page (credits edit)
- `h2` reused for both section headers and list items (user profile)
- `h3.h5` used for both gang name AND section headers (list detail)

#### 6. Document print typography

Create explicit print size overrides rather than relying on scattered `{% if print %}fs-5{% else %}fs-7{% endif %}` conditionals. Consider a print-specific class like `.gy-stat-value` that handles the size switch via media query or SCSS entry point.

### Proposed Type Scale Table (Visual Reference)

```
35px  ████████████████████████████████████  h1 (Display)
28px  ████████████████████████████████      h2
24.5px ███████████████████████████          h3 (h1.h3 page titles)
21px  ██████████████████████████            h4
17.5px █████████████████████                h5 (h2.h5 sections)
14px  ██████████████████                    h6 / body
12.6px ████████████████                     fs-7 (compact)
12.25px ███████████████                     .small (nearly identical to fs-7)
```

After consolidation:

```
35px  ████████████████████████████████████  Display (index pages)
24.5px ███████████████████████████          Page title (sub-pages)
17.5px █████████████████████                Section heading
14px  ██████████████████                    Body
12.25px ███████████████                     Compact (merged fs-7 + small)
```
