# Custom CSS Audit

## 1. SCSS File Structure

Three SCSS files compose the stylesheet:

| File | Purpose | Lines |
|------|---------|-------|
| `styles.scss` | Bootstrap imports + all custom rules | 484 |
| `screen.scss` | Sets `$font-size-base: 0.875rem`, imports `styles` | 3 |
| `print.scss` | Sets `$font-size-base: 1rem`, imports `styles`, adds `body { zoom: 50% }` | 7 |

`screen.scss` and `print.scss` are thin wrappers that set `$font-size-base` before importing `styles.scss`. All custom CSS lives in `styles.scss`.

---

## 2. Bootstrap Variable Overrides (Pre-Import)

These appear before the Bootstrap `_variables.scss` import and configure Bootstrap's build.

| Variable | Value | Purpose |
|----------|-------|---------|
| `$enable-cssgrid` | `true` | Enables CSS Grid utilities (`g-col-*`, `grid`) |
| `$font-family-sans-serif` | `"mynor-variable", system-ui, ...` | Custom brand font with system fallbacks |
| `$font-family-base` | `$font-family-sans-serif` | Sets the body font |
| `$blue` | `#0771ea` | Brand blue |
| `$indigo` | `#5111dc` | Brand indigo |
| `$purple` | `#5d3cb0` | Brand purple |
| `$pink` | `#c02d83` | Brand pink |
| `$red` | `#cb2b48` | Brand red |
| `$orange` | `#ea5d0c` | Brand orange |
| `$yellow` | `#e8a10a` | Brand yellow |
| `$green` | `#1a7b49` | Brand green |
| `$teal` | `#1fb27e` | Brand teal |
| `$cyan` | `#10bdd3` | Brand cyan |

**Classification:** All are **design tokens** -- they configure Bootstrap's colour system at the source. These are well-placed and correctly implemented.

### Post-Variables Override

| Variable | Value | Purpose |
|----------|-------|---------|
| `$custom-font-sizes` | `(7: $font-size-base * 0.9)` | Adds `fs-7` to Bootstrap's font-size map |
| `$font-sizes` | `map-merge($font-sizes, $custom-font-sizes)` | Merges into Bootstrap's utility |

**Classification:** **Bootstrap extension** -- correctly extends the `fs-*` utility scale. `fs-7` is used 120+ times across templates, making it a critical custom token.

---

## 3. Complete Custom Rule Inventory

### 3.1 Hero Section

```scss
.hero {
    height: 25vh;
    background-size: cover;
    background-position: center;
    position: relative;
}
```

| Attribute | Value |
|-----------|-------|
| **Template usage** | `core/index.html` (1 file, 2 instances) |
| **Classification** | Component candidate |
| **Assessment** | Single-use component for the homepage hero banner. Legitimate component. |

---

### 3.2 Tooltip Cursor

```scss
[data-bs-toggle="tooltip"] { cursor: help; }
a[data-bs-toggle="tooltip"] { cursor: pointer; }
```

| Attribute | Value |
|-----------|-------|
| **Template usage** | Applied globally via attribute selector |
| **Classification** | Override/fix |
| **Assessment** | Bootstrap tooltips don't set cursor by default. This is a sensible global fix. Keep. |

---

### 3.3 Link Utilities

```scss
.linked {
    @extend .link-underline-opacity-25;
    @extend .link-underline-opacity-100-hover;
    @extend .link-offset-1;
}

.link-sm {
    @extend .link-underline-opacity-25;
    @extend .link-underline-opacity-100-hover;
    @extend .link-offset-1;
    @extend .fs-7;
}

.tooltipped {
    @extend .link-underline-opacity-50;
    @extend .link-underline-info;
    @extend .link-underline-opacity-100-hover;
    @extend .link-offset-1;
    @extend .text-decoration-underline;
}
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.linked` | 39 instances | 19 files |
| `.link-sm` | 4 instances | 2 files (`fighter_card_stash.html`, `design_system.html`) |
| `.tooltipped` | 11 instances | 9 files |

| Attribute | Value |
|-----------|-------|
| **Classification** | Component candidates |
| **Assessment** | `.linked` is heavily used and well-established as the standard inline link style. `.link-sm` is a convenience that combines `.linked` + `.fs-7`. `.tooltipped` creates a distinct visual for tooltip-bearing links (info-blue underline). All three are legitimate shorthand for verbose Bootstrap utility combinations. |

**Note:** Some templates still spell out the raw utilities (`link-underline-opacity-25 link-underline-opacity-100-hover`) instead of using `.linked`. For example, the "Show all" links on the homepage and the "Copy from Campaign" link on the campaign detail page. These should use `.linked` instead.

---

### 3.4 Table Utilities

```scss
.table-group-divider {
    border-top: var(--bs-border-width) var(--bs-border-style)
        var(--bs-border-color) !important;
}

.table-fixed {
    table-layout: fixed;
    width: 100%;
    max-width: 100%;
}

.table-fixed .table-nowrap td,
.table-fixed .table-nowrap th {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 0;
}
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.table-group-divider` | 13 instances | 11 files |
| `.table-fixed` | 6 instances | 4 files |
| `.table-nowrap` | 5 instances | 4 files |

| Attribute | Value |
|-----------|-------|
| **Classification** | Bootstrap extensions |
| **Assessment** | `.table-group-divider` works around Bootstrap's `table-borderless` removing borders where a visual separator is still needed. `.table-fixed` and `.table-nowrap` provide layout control not available in Bootstrap's table utilities. All are well-used and should be kept. |

**Note:** Bootstrap 5.3 added its own `.table-group-divider` class. The custom version uses `!important` to override `table-borderless`. Verify whether Bootstrap's built-in version is sufficient or if the `!important` override is still needed.

---

### 3.5 Form Overrides

```scss
fieldset legend { font-size: $font-size-base; }
label { margin-bottom: 0.25rem; }
```

| Attribute | Value |
|-----------|-------|
| **Template usage** | Global element selectors, apply everywhere |
| **Classification** | Override/fix |
| **Assessment** | Bootstrap's default `legend` font size is larger; this normalises it to body size. Label margin is a global spacing adjustment. Both are reasonable global overrides. |

---

### 3.6 Dropdown Menu Width

```scss
.dropdown-menu-mw {
    min-width: 25em;
    width: 100%;
    max-width: 35em;
}
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.dropdown-menu-mw` | 5 instances | 5 files (filter dropdowns) |

| Attribute | Value |
|-----------|-------|
| **Classification** | Component candidate |
| **Assessment** | Bootstrap dropdowns have a fixed `min-width` that's too narrow for the filter dropdowns. This is a reusable component for wider dropdown menus. Keep. |

---

### 3.7 Fighter Switcher

```scss
.fighter-switcher-btn {
    padding: 0.25em 0.5em;
    border: none;
    background: transparent;
    &:hover, &:focus { background: transparent; text-decoration: underline; }
    &:active { background: transparent; }
}

.fighter-switcher-menu {
    max-height: 20em;
    overflow-y: auto;
}
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.fighter-switcher-btn` | 1 instance | `fighter_switcher.html` |
| `.fighter-switcher-menu` | 1 instance | `fighter_switcher.html` |

| Attribute | Value |
|-----------|-------|
| **Classification** | Component candidate |
| **Assessment** | Single-use component for the fighter name dropdown on edit pages. The button overrides Bootstrap's default dropdown toggle styling to look like a heading. The menu adds scroll overflow. Keep as a component. |

---

### 3.8 Spacing Utility

```scss
.mb-last-0 > :last-child {
    margin-bottom: 0 !important;
}
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.mb-last-0` | 16 instances | 14 files |

| Attribute | Value |
|-----------|-------|
| **Classification** | Bootstrap extension |
| **Assessment** | Removes trailing margin from the last child of a container. Used extensively on rich text containers (`|safe` output) where the last `<p>` has unwanted `margin-bottom`. Essential utility. Keep. |

---

### 3.9 Caps Label

```scss
.caps-label {
    @extend .small;
    @extend .text-uppercase;
    @extend .text-muted;
    @extend .fw-semibold;
    letter-spacing: 0.03em;
}
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.caps-label` | 57 instances | 12 files |

| Attribute | Value |
|-----------|-------|
| **Classification** | Token candidate / Component candidate |
| **Assessment** | Heavily used for section sub-headers, table column headers, and metadata labels. This is effectively a text style token. The `letter-spacing` is the only property not achievable via Bootstrap utilities. Formalise as a design token. |

---

### 3.10 Responsive Font Sizes

```scss
@each $bp, $bp-value in $grid-breakpoints {
    @include media-breakpoint-up($bp) {
        .fs-#{$bp}-normal {
            font-size: $font-size-base !important;
        }
    }
}
```

Generated classes: `.fs-sm-normal`, `.fs-md-normal`, `.fs-lg-normal`, `.fs-xl-normal`, `.fs-xxl-normal`

| Class | Template Usage | Files |
|-------|---------------|-------|
| `fs-*-normal` | 0 (grep found `fw-normal` but no `fs-*-normal`) | 0 files |

| Attribute | Value |
|-----------|-------|
| **Classification** | Dead code (potentially) |
| **Assessment** | Grep found zero template matches for `fs-sm-normal`, `fs-md-normal`, etc. The only match was `fw-normal` which is a Bootstrap class. **Candidate for removal** unless used in JavaScript or inline styles. |

---

### 3.11 Error List

```scss
.errorlist {
    @extend .list-unstyled;
    color: var(--bs-danger);
}
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.errorlist` | 0 explicit references | Generated by Django form rendering |

| Attribute | Value |
|-----------|-------|
| **Classification** | Override/fix |
| **Assessment** | Django generates `<ul class="errorlist">` for form validation errors. This override removes list bullets and applies danger colour. Necessary Django integration. Keep. |

---

### 3.12 Flash Animation

```scss
@keyframes flash-warn {
    from { background-color: var(--bs-warning-bg-subtle) !important; }
    to { background-color: inherit; }
}

.flash-warn,
.flash-warn td {
    animation: flash-warn 2s ease-in;
}
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.flash-warn` | 2 instances | 1 file (`design_system.html`) + applied dynamically |

| Attribute | Value |
|-----------|-------|
| **Classification** | Component candidate |
| **Assessment** | Used for highlighting recently changed items (e.g., after equipment assignment). The animation fades from warning yellow to transparent. Applied dynamically via URL hash fragment targeting. Keep. |

---

### 3.13 Image Utilities

```scss
img { max-width: 100%; height: auto; }

.img-link-transform img {
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    transform-style: preserve-3d;
    will-change: transform, box-shadow;
}
.img-link-transform:hover img { /* 3D tilt effect */ }
.img-link-transform:active img { /* pressed state */ }

.flatpage-content img {
    max-width: 100%;
    height: auto;
}
@include media-breakpoint-up(xl) {
    .flatpage-content img { max-width: 133%; }
}
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `img` (element) | Global | All images |
| `.img-link-transform` | 2 instances | `core/index.html` (homepage hero/marketing) |
| `.flatpage-content img` | Scoped | `flatpages/default.html` |

| Attribute | Value |
|-----------|-------|
| **Classification** | Override/fix (global `img`), Component candidate (`.img-link-transform`), Component (`.flatpage-content img`) |
| **Assessment** | The global `img` rule ensures responsive images. `.img-link-transform` provides a 3D hover effect used only on the homepage. `.flatpage-content img` allows images to bleed past container width on large screens (133%). All legitimate. |

---

### 3.14 Size Utilities (em-based)

```scss
// Square sizes
$em-sizes: (1: 1em, 2: 2em, 3: 4em, 4: 8em, 5: 16em);
.size-em-#{$size} { width: $value; height: $value; }
// Responsive: .size-em-#{$bp}-#{$size}

// Width-only sizes
$width-em-sizes: (3: 3em, 4: 4em, 5: 5em, 6: 6em, 8: 8em, 10: 10em, 12: 12em);
.w-em-#{$size} { width: $value; }
// Responsive: .w-em-#{$bp}-#{$size}

// Square sizes (simple)
@each $size in (1, 2, 3, 4, 5, 6) {
    .sq-#{$size} { height: #{$size}em; width: #{$size}em; }
}
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `size-em-5` | 2 instances | 2 files (fighter lore images) |
| `size-em-md-5` | 1 instance | 1 file |
| `size-em-4` | 1 instance | 1 file |
| `w-em-5` | 7 instances | 4 files (list headers, stat tables) |
| `w-em-sm-12` | 2 instances | 1 file |
| `w-em-3` | 1 instance | 1 file |
| `w-em-10` | 1 instance | 1 file |
| `sq-6` | 1 instance | 1 file (QR code container) |

**Unused generated classes (dead code):**

- `size-em-1`, `size-em-2`, `size-em-3` and all responsive variants except `size-em-md-5`
- `w-em-4`, `w-em-6`, `w-em-8`, `w-em-12` and most responsive variants
- `sq-1` through `sq-5`
- All responsive `size-em-*-*` variants except `size-em-md-5`
- All responsive `w-em-*-*` variants except `w-em-sm-12`

| Attribute | Value |
|-----------|-------|
| **Classification** | Bootstrap extension (size utilities), significant dead code |
| **Assessment** | The utilities themselves are useful (em-based sizing not available in Bootstrap). However, the generated CSS includes dozens of unused classes. The `$em-sizes` map has a confusing numbering scheme where `size-em-5` is 16em, not 5em. Consider: (a) pruning to only generate used sizes, (b) using a linear naming scheme, or (c) replacing with one-off custom properties. |

**Overlap concern:** `.sq-*` and `.size-em-*` serve the same purpose (square sizing) with different APIs. `sq-6` = 6em square vs `size-em-3` = 4em square. The naming is confusing.

---

### 3.15 Responsive Border Utilities

```scss
@each $bp, $bp-value in $grid-breakpoints {
    @include media-breakpoint-up($bp) {
        .border-#{$bp}-0 { border: none !important; }
        .border-top-#{$bp}-0 { ... }
        .border-bottom-#{$bp}-0 { ... }
        .border-end-#{$bp}-0 { ... }
        .border-start-#{$bp}-0 { ... }
        .border-#{$bp} { border: ... }
        .border-top-#{$bp} { ... }
        .border-bottom-#{$bp} { ... }
        .border-end-#{$bp} { ... }
        .border-start-#{$bp} { ... }
        .rounded-#{$bp}-0 { ... }
        .rounded-top-#{$bp}-0 { ... }
        .rounded-bottom-#{$bp}-0 { ... }
        .rounded-start-#{$bp}-0 { ... }
        .rounded-end-#{$bp}-0 { ... }
    }
}
```

This generates 15 classes per breakpoint x 5 breakpoints = **75 classes**.

**Template usage (only `md` breakpoint used):**

| Class | Count |
|-------|-------|
| `border-start-md-0` | 3 |
| `border-end-md-0` | 3 |
| `rounded-start-md-0` | 3 |
| `rounded-end-md-0` | 3 |
| `border-start-md` | 4 |
| `border-end-md` | 3 |

**Unused:** All `sm`, `lg`, `xl`, `xxl` variants (60 classes), plus `border-top-md-0`, `border-bottom-md-0`, `border-md-0`, `border-top-md`, `border-bottom-md`, `rounded-md-0`, `rounded-top-md-0`, `rounded-bottom-md-0` (9 more classes).

| Attribute | Value |
|-----------|-------|
| **Classification** | Bootstrap extension, major dead code |
| **Assessment** | Bootstrap 5 lacks responsive border utilities, so this fills a real gap. However, generating for all breakpoints and all sides produces 75 classes when only 6 are used (all `md`). Consider generating only for `md` breakpoint, or only generating the specific classes needed. |

---

### 3.16 Colour Radio (Color Picker)

```scss
.color-radio-label:hover { transform: scale(1.1); z-index: 1; }
.color-radio-input:checked + .color-radio-label {
    box-shadow: 0 0 0 3px rgba(13, 110, 253, 0.5);
    transform: scale(1.05);
}
.color-radio-input:focus + .color-radio-label {
    box-shadow: 0 0 0 3px rgba(13, 110, 253, 0.25);
}
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.color-radio-label` | 2 instances | `widgets/color_radio_option.html` |
| `.color-radio-input` | 2 instances | `widgets/color_radio_option.html` |

| Attribute | Value |
|-----------|-------|
| **Classification** | Component candidate |
| **Assessment** | Custom widget for colour selection (gang/group colour picker). Single-use but well-encapsulated. The `rgba(13, 110, 253, ...)` is hardcoded Bootstrap primary blue rather than using `var(--bs-primary-rgb)`. Should use CSS variables for theme compatibility. |

---

### 3.17 Flatpage Navigation

```scss
@include media-breakpoint-up(md) {
    .flatpage-heading .stickyboi { top: 1em; }
}

.flatpage-content .list-unstyled a {
    &:hover { background-color: var(--bs-secondary-bg-subtle); }
}

// Flatpage heading link icons (bi-link-45deg hover reveal)
.flatpage-content a > h1, ..., a > h6 {
    position: relative;
    display: inline-block;
    .bi-link-45deg { /* positioned absolutely, hidden by default */ }
}
.flatpage-content a:hover > h1, ... {
    .bi-link-45deg { opacity: 1; }
}
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.flatpage-heading` | 1 instance | `flatpages/default.html` |
| `.stickyboi` | 1 instance | `flatpages/default.html` |
| `.flatpage-content` | 1 instance | `flatpages/default.html` |

| Attribute | Value |
|-----------|-------|
| **Classification** | Component candidate |
| **Assessment** | Flatpage-specific styles for the Help and About pages. The sticky sidebar navigation and heading anchor links are a coherent component. `.stickyboi` could use a more descriptive name (e.g., `.flatpage-sidebar-sticky`). |

---

### 3.18 Grid Utility

```scss
.auto-flow-dense { grid-auto-flow: row dense; }
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.auto-flow-dense` | 3 instances | 3 files (list, fighter card stash, blank cards) |

| Attribute | Value |
|-----------|-------|
| **Classification** | Bootstrap extension |
| **Assessment** | Bootstrap's CSS Grid utilities don't include `grid-auto-flow` control. This enables dense packing for fighter card grids. Keep. |

---

### 3.19 Print Utility

```scss
.break-inside-avoid { break-inside: avoid; }
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.break-inside-avoid` | 7 instances | 7 files (fighter cards, list groups) |

| Attribute | Value |
|-----------|-------|
| **Classification** | Bootstrap extension |
| **Assessment** | Bootstrap lacks print-specific break utilities. Used to prevent fighter cards from splitting across print pages. Essential for the print view. Keep. |

---

### 3.20 Stat Input Cell

```scss
.stat-input-cell { width: 4rem; }
```

| Class | Template Usage | Files |
|-------|---------------|-------|
| `.stat-input-cell` | 3 instances | 3 files (pack fighter stat forms) |

| Attribute | Value |
|-----------|-------|
| **Classification** | Component candidate |
| **Assessment** | Controls the width of stat input cells in pack fighter forms. Simple but necessary for the form layout. Keep. |

---

### 3.21 Print SCSS (`print.scss`)

```scss
$font-size-base: 1rem;
@import "./styles";
body { zoom: 50%; }
```

| Attribute | Value |
|-----------|-------|
| **Classification** | Override/fix |
| **Assessment** | Increases base font size for print (compensating for 50% zoom) to get more content per page while maintaining readability. Unconventional approach -- `zoom` is not a standard CSS property (WebKit/Blink only). Works for Chrome-based printing but may not work in Firefox. |

---

## 4. Classification Summary

### Token Candidates

| Class/Variable | Current | Recommendation |
|----------------|---------|----------------|
| `$blue` through `$cyan` | Bootstrap variable overrides | Formalise as brand colour tokens |
| `$font-size-base` (screen/print) | Set in wrapper files | Document as typography tokens |
| `fs-7` (0.9x base) | Custom font-size utility | Formalise as a typography token |
| `.caps-label` | Composite of utilities + `letter-spacing` | Formalise as a text style token |

### Component Candidates

| Class | Usage | Recommendation |
|-------|-------|----------------|
| `.hero` | 1 file | Keep as homepage component |
| `.linked` | 19 files | Formalise; migrate raw utility spellings to use this class |
| `.link-sm` | 2 files | Keep; it's `.linked` + `.fs-7` |
| `.tooltipped` | 9 files | Formalise as distinct link variant |
| `.dropdown-menu-mw` | 5 files | Keep as dropdown component modifier |
| `.fighter-switcher-btn` / `-menu` | 1 file | Keep as fighter-switcher component |
| `.flash-warn` | Dynamic use | Keep as animation component |
| `.img-link-transform` | 1 file | Keep as homepage component |
| `.color-radio-label` / `-input` | 1 file | Keep as colour picker component; fix hardcoded colour |
| `.flatpage-heading` / `.flatpage-content` / `.stickyboi` | 1 file | Rename `.stickyboi` to `.flatpage-sidebar-sticky` |
| `.stat-input-cell` | 3 files | Keep as form component |

### Bootstrap Extensions

| Class | Usage | Recommendation |
|-------|-------|----------------|
| `fs-7` | 120+ instances | Keep; critical utility |
| `.table-group-divider` | 11 files | Keep; verify against Bootstrap 5.3 built-in |
| `.table-fixed` / `.table-nowrap` | 4 files | Keep |
| `.mb-last-0` | 14 files | Keep; essential for rich text |
| `.auto-flow-dense` | 3 files | Keep |
| `.break-inside-avoid` | 7 files | Keep |
| `.size-em-*` | 2 files (4 classes used) | Prune to used sizes only |
| `.w-em-*` | 4 files (4 classes used) | Prune to used sizes only |
| `.sq-*` | 1 file (1 class used) | Prune to `sq-6` only, or merge into `size-em-*` |
| `.border-*-md-*` / `.rounded-*-md-*` | 4 files (6 classes used) | Prune to `md` breakpoint only |
| `.fs-*-normal` | 0 files | Remove (dead code) |

### Overrides/Fixes

| Rule | Recommendation |
|------|----------------|
| Tooltip cursor (`[data-bs-toggle="tooltip"]`) | Keep |
| `fieldset legend` font size | Keep |
| `label` margin-bottom | Keep |
| `img` max-width | Keep |
| `.errorlist` | Keep |
| `print.scss` zoom | Keep, but document limitation |

### Dead Code

| Rule | Generated Classes | Used | Recommendation |
|------|-------------------|------|----------------|
| `.fs-*-normal` | 5 classes | 0 | **Remove** |
| `.size-em-*` unused sizes | ~25 classes | 0 | **Prune** |
| `.w-em-*` unused sizes | ~40 classes | 0 | **Prune** |
| `.sq-*` unused sizes | 5 classes | 0 | **Prune** |
| `.border-*-{sm,lg,xl,xxl}-*` | ~60 classes | 0 | **Prune** to `md` only |
| `.border-{top,bottom,md}-0` etc unused md variants | ~9 classes | 0 | **Prune** |
| `.rounded-{top,bottom,md}-0` unused md variants | ~3 classes | 0 | **Prune** |

**Estimated dead CSS classes: ~147 generated classes never referenced in any template.**

---

## 5. Recommendations

### R1: Prune Generated Utilities

The responsive breakpoint loops and size maps generate approximately 147 unused CSS classes. Replace the loops with explicit declarations for only the classes that are actually used.

**Before (75 generated classes, 6 used):**

```scss
@each $bp, $bp-value in $grid-breakpoints {
    @include media-breakpoint-up($bp) {
        .border-#{$bp}-0 { ... }
        // ... 14 more classes per breakpoint
    }
}
```

**After (6 generated classes, 6 used):**

```scss
@include media-breakpoint-up(md) {
    .border-start-md-0 { border-left: none !important; }
    .border-end-md-0 { border-right: none !important; }
    .border-start-md { border-left: var(--bs-border-width) var(--bs-border-style) var(--bs-border-color); }
    .border-end-md { border-right: var(--bs-border-width) var(--bs-border-style) var(--bs-border-color); }
    .rounded-start-md-0 { border-top-left-radius: 0 !important; border-bottom-left-radius: 0 !important; }
    .rounded-end-md-0 { border-top-right-radius: 0 !important; border-bottom-right-radius: 0 !important; }
}
```

Similarly, replace size utility loops with explicit declarations for used sizes only.

### R2: Remove Dead Code

Remove `.fs-*-normal` entirely -- zero template usage found.

### R3: Consolidate Size Utilities

Three overlapping sizing systems exist: `.size-em-*`, `.w-em-*`, and `.sq-*`. Consolidate:

| Current | Used Values | Proposed |
|---------|-------------|----------|
| `.sq-6` (6em square) | `sq-6` | Keep `.sq-6` only |
| `.size-em-4` (8em), `.size-em-5` (16em) | 2 values | Rename to descriptive names or keep as-is |
| `.w-em-3`, `.w-em-5`, `.w-em-10`, `.w-em-sm-12` | 4 values | Keep these 4 only |

The `.size-em-*` numbering is confusing (5 = 16em). Consider renaming to literal values: `.size-8em`, `.size-16em`.

### R4: Formalise Token/Component Boundary

Create clear documentation separating:

1. **Design tokens** -- colour variables, `fs-7`, `caps-label` (text style)
2. **Utility extensions** -- `mb-last-0`, `auto-flow-dense`, `break-inside-avoid`, `table-*` classes, border responsive classes
3. **Components** -- `hero`, `linked`/`tooltipped`/`link-sm`, `dropdown-menu-mw`, `fighter-switcher-*`, `flash-warn`, `color-radio-*`, `flatpage-*`, `img-link-transform`, `stat-input-cell`
4. **Overrides** -- tooltip cursor, form element selectors, `errorlist`, `img` max-width

### R5: Fix Hardcoded Colours

`.color-radio-input:checked + .color-radio-label` uses `rgba(13, 110, 253, 0.5)` -- hardcoded Bootstrap default blue. Replace with `rgba(var(--bs-primary-rgb), 0.5)` to respect the custom `$blue: #0771ea` override.

### R6: Rename `.stickyboi`

Rename to `.flatpage-sidebar-sticky` for clarity and consistency with the `flatpage-*` namespace.

### R7: Migrate Raw Link Utility Strings

Templates that spell out `link-underline-opacity-25 link-underline-opacity-100-hover` (e.g., "Show all" links, error page back links) should use `.linked` instead. This would reduce template verbosity and ensure consistent link styling.

Affected files include:

- `core/index.html` -- "Show all" links
- `campaign/campaign.html` -- "Copy from Campaign" link
- `errors/error.html` -- "Go Back" link
- Various other templates using the raw utilities

### R8: Verify `table-group-divider` Against Bootstrap 5.3

Bootstrap 5.3+ ships its own `.table-group-divider`. Test whether the built-in version works with `.table-borderless` tables. If it does, remove the custom override. If not, add a comment explaining why the custom version is needed.
