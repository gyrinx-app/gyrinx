# Stage 2: Cross-Cutting Audit Summary

## Palette Health

- **10 Bootstrap colour overrides** in SCSS, but **5 are unused** ($indigo, $purple, $pink, $orange, $teal)
- **`text-muted` (~120 uses) vs `text-secondary` (~60 uses)** — interchangeable, needs canonical choice
- **Badge format split**: `bg-*` (~25 uses) vs `text-bg-*` (~30 uses) — standardise on `text-bg-*`
- **Dynamic colour dots**: 3 different inline sizes (8px, 10px, 16px) for the same concept
- **Proposed consolidation**: 13 semantic `$gy-color-*` tokens, remove unused overrides

## Typography Health

- **`fs-7` (12.6px) and `.small` (12.25px) are 0.35px apart** — used interchangeably across ~60 files, merge them
- **5 views have no `<h1>`** (accessibility gap), 3 views use `<h2>` where `<h1>` expected
- **3 competing uppercase label patterns**: `.caps-label` (correct), manual `text-uppercase` (missing properties), inverted `fw-light` variant
- **Section heading margins** vary: `mb-0`, `mb-1`, `mb-2`, `mb-3` for the same `h2.h5` pattern
- **Proposed consolidation**: Reduce 8-level effective scale to 5 levels

## Spacing Health

- **Bootstrap's 6-level scale used exclusively** — no custom values needed
- **Outer container gaps inconsistent**: forms `gap-3`, listings `gap-4`, detail pages `gap-5` — not documented
- **Section heading margins** and **form button row margins** vary across similar pages
- **Proposed consolidation**: Document gap conventions per page type, standardise heading margins

## Component Health

- **21 component types** catalogued across 48 views
- **Buttons**: 18 variants, canonical is `btn btn-primary btn-sm` for toolbars, full-size for forms
- **Cards**: 8 variants, several violate "cards only for fighters in grids" convention
- **Callouts/Alerts**: **13 distinct feedback patterns** — the most fragmented area
- **Empty states**: 5 different approaches, no unified component
- **5 missing template components** identified: section header bar, error box, warning callout, info note, empty state

### Component Classification Summary

| Classification | Count | Action |
|---------------|-------|--------|
| Canonical | ~15 | Encode in spec |
| Acceptable Variant | ~20 | Encode as named variants |
| Drift | ~30 | Migrate to canonical |
| Bespoke | ~10 | Design decision needed |
| Anti-pattern | ~5 | Fix during migration |

## Icon Health

- **414 icon instances**, 80+ distinct classes
- **Two syntax formats**: `bi-*` (392) vs `bi bi-*` (22) — standardise on hyphenated
- **Same concept, different icons**: Add (3 icons), Confirm (3), Back (3), More Options (2)
- **97.8% of icons lack accessibility attributes** — only 9 of 414 have `aria-hidden` or `aria-label`
- **No standard sizing** — ad-hoc `fs-3`, `fs-4`, `fs-5`, `fs-6`

## Custom CSS Health

- **21 custom rule groups** in `styles.scss`
- **~147 generated CSS classes never referenced** in any template (unused responsive variants)
- **`.linked` (39 uses) and `.caps-label` (57 uses)** are the most important custom classes
- **Hardcoded colour** in colour-radio component
- **Classification**: 3 token candidates, 4 component candidates, 6 Bootstrap extensions, 4 overrides/fixes, 4 dead code groups

## Layout Health

- **4 distinct page shells**: form-page (`col-12 col-md-8 col-lg-6`), list-page (`col-lg-12`), detail-page (`col-12 col-xl-8`), sidebar-page (`row g-*`)
- **`page.html` layout exists but only 1 template uses it** — 16 templates manually reimplement the same structure
- **CSS Grid used exclusively for fighter card grids**, everything else uses row/col or vstack/hstack
- **`xxl` breakpoint never used**

---

## Biggest Wins (by frequency x severity)

1. **Standardise `text-muted` vs `text-secondary`** — 180+ instances, one search-replace. Pick `text-secondary` (Bootstrap 5.3 recommendation) or keep `text-muted` (more common currently).

2. **Merge `fs-7` and `.small`** — ~60 files affected. They're 0.35px apart. Pick one, alias the other.

3. **Extract 5 missing template components** — section header bar, error callout, warning callout, info note, empty state. Each is repeated 10-20+ times inline. Extract once, include everywhere.

4. **Standardise badge format to `text-bg-*`** — ~25 instances to migrate from `bg-*`. Mechanical find-replace.

5. **Add `aria-hidden="true"` to decorative icons** — 400+ icons, most are decorative. Bulk migration.

## Biggest Risks

1. **Fighter card template chain** — 7 levels deep, used everywhere. Changes here ripple across every view. Must test all modes (interactive, print, compact, gear-edit).

2. **Feedback pattern consolidation** — 13 distinct patterns across error/warning/info/success. Changing these affects user-facing error flows. Needs careful testing per-form.

3. **Alert → callout migration** — CLAUDE.md says "avoid alerts" but 30+ templates use `alert-*`. Migration requires verifying each one works correctly with the replacement pattern.

4. **Print styles** — `print.scss` + `base_print.html` + `zoom: 50%` (non-standard). Any design system changes must preserve print output.

5. **Allauth templates** — Separate template chain with its own panel/card/error patterns. Must be migrated separately and tested with auth flows.

## Estimated Scope

| Category | Templates Affected | Estimated Changes |
|----------|-------------------|-------------------|
| `text-muted` → canonical | ~60 | Low risk, mechanical |
| `fs-7`/`.small` merge | ~60 | Low risk, mechanical |
| Badge `bg-*` → `text-bg-*` | ~15 | Low risk, mechanical |
| Icon format `bi bi-*` → `bi-*` | ~10 | Low risk, mechanical |
| Extract section header component | ~20 | Medium risk, structural |
| Extract callout components (5) | ~40 | Medium risk, must test flows |
| Card → `border rounded` migration | ~10 | Medium risk, visual change |
| Heading hierarchy fixes | ~8 | Low risk |
| Alert → callout migration | ~30 | High risk, must test each |
| Icon accessibility | ~400 instances | Low risk, bulk add |
| Dead CSS removal | ~147 classes | Low risk, verify first |
| **Total unique templates** | **~120** | |

---

## Dimension Reports

| Dimension | File | Key Finding |
|-----------|------|-------------|
| Colour | `colours.md` | `text-muted` vs `text-secondary` is the #1 issue |
| Typography | `typography.md` | `fs-7` and `.small` are functionally identical |
| Spacing | `spacing.md` | Bootstrap scale is correct, gap conventions undocumented |
| Components | `components.md` | 13 feedback patterns, 5 missing components |
| Icons | `icons.md` | 97.8% lack accessibility attributes |
| Layout | `layouts.md` | 4 page shells, `page.html` underused |
| Custom CSS | `custom-css.md` | ~147 dead CSS classes |
