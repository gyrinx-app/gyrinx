# Spacing Audit

## 1. Template Spacing Inventory

Every Bootstrap spacing utility class found across all templates (`gyrinx/core/templates/`,
`gyrinx/content/templates/`, `gyrinx/pages/templates/`), sorted by frequency.

### Margin-bottom (`mb-*`)

| Class | Count | Bootstrap value |
|-------|------:|-----------------|
| `mb-0` | 337 | 0 |
| `mb-2` | 128 | 0.5rem |
| `mb-3` | 104 | 1rem |
| `mb-1` | 47 | 0.25rem |
| `mb-4` | 16 | 1.5rem |
| `mb-5` | 1 | 3rem |

**Observation:** `mb-0` dominates because it is the standard heading reset (`h1.mb-0`, `h2.mb-0`, `p.mb-0`).
`mb-2` and `mb-3` are the workhorse spacers. `mb-4` and `mb-5` are rare.

### Margin-top (`mt-*`)

| Class | Count | Bootstrap value |
|-------|------:|-----------------|
| `mt-3` | 90 | 1rem |
| `mt-1` | 21 | 0.25rem |
| `mt-2` | 20 | 0.5rem |
| `mt-4` | 5 | 1.5rem |
| `mt-5` | 2 | 3rem |

**Observation:** `mt-3` is overwhelmingly the top-margin default (button rows below forms, section separators).
`mt-1` and `mt-2` are secondary adjusters.

### Gap (`gap-*`)

| Class | Count | Bootstrap value |
|-------|------:|-----------------|
| `gap-3` | 220 | 1rem |
| `gap-2` | 182 | 0.5rem |
| `gap-1` | 70 | 0.25rem |
| `gap-4` | 32 | 1.5rem |
| `gap-5` | 13 | 3rem |
| `gap-0` | 9 | 0 |

**Observation:** `gap-3` (1rem) is the dominant gap -- used in `vstack gap-3` (170 occurrences), the
single most common layout pattern. `gap-2` (0.5rem) is the secondary gap for tighter spacing.
`gap-5` (3rem) is used for major section separation on detail pages.

### Padding (`p-*`, `px-*`, `py-*`, `ps-*`, `pe-*`, `pt-*`, `pb-*`)

| Class | Count | Bootstrap value |
|-------|------:|-----------------|
| `px-0` | 137 | 0 |
| `p-2` | 78 | 0.5rem |
| `p-0` | 36 | 0 |
| `p-3` | 35 | 1rem |
| `py-1` | 32 | 0.25rem |
| `px-2` | 27 | 0.5rem |
| `ps-0` | 22 | 0 |
| `py-2` | 17 | 0.5rem |
| `pe-0` | 17 | 0 |
| `ps-3` | 16 | 1rem |
| `py-0` | 11 | 0 |
| `px-1` | 5 | 0.25rem |
| `pt-3` | 5 | 1rem |
| `pt-2` | 5 | 0.5rem |
| `py-4` | 3 | 1.5rem |
| `pb-3` | 3 | 1rem |
| `pb-2` | 3 | 0.5rem |
| `py-3` | 2 | 1rem |
| `pt-1` | 2 | 0.25rem |
| `pb-5` | 2 | 3rem |
| `pb-1` | 2 | 0.25rem |
| `p-1` | 2 | 0.25rem |
| `px-3` | 1 | 1rem |
| `pt-4` | 1 | 1.5rem |
| `ps-4` | 1 | 1.5rem |
| `pb-4` | 1 | 1.5rem |
| `pb-0` | 1 | 0 |

**Observation:** `px-0` is the second-most-used spacing class overall -- it is the standard column
padding reset applied to page-level wrappers. `p-2` is the standard inline container padding
(section header bars, cards, compact containers). `py-1` is the standard tight vertical padding
(section headers, list items).

### Margin-start/end (`ms-*`, `me-*`)

| Class | Count | Bootstrap value |
|-------|------:|-----------------|
| `ms-2` | 29 | 0.5rem |
| `me-1` | 17 | 0.25rem |
| `ms-1` | 14 | 0.25rem |
| `me-2` | 11 | 0.5rem |
| `ms-3` | 2 | 1rem |

### Margin x/y (`mx-*`, `my-*`)

| Class | Count | Bootstrap value |
|-------|------:|-----------------|
| `my-3` | 5 | 1rem |
| `my-4` | 4 | 1.5rem |
| `my-2` | 1 | 0.5rem |
| `m-2` | 1 | 0.5rem |

### Grid gutters (`g-*`)

| Class | Count | Bootstrap value |
|-------|------:|-----------------|
| `g-2` | 8 | 0.5rem |
| `g-3` | 4 | 1rem |
| `g-5` | 2 | 3rem |
| `g-4` | 2 | 1.5rem |
| `g-0` | 1 | 0 |

### Responsive spacing

| Class | Count | Bootstrap value |
|-------|------:|-----------------|
| `p-sm-2` | 14 | 0.5rem at sm |
| `my-md-5` | 3 | 3rem at md |
| `py-sm-2` | 2 | 0.5rem at sm |
| `py-sm-1` | 2 | 0.25rem at sm |
| `py-md-5` | 2 | 3rem at md |
| `px-sm-2` | 2 | 0.5rem at sm |
| `p-sm-0` | 2 | 0 at sm |
| `mt-md-0` | 2 | 0 at md |
| `mb-lg-0` | 2 | 0 at lg |
| `gap-md-0` | 2 | 0 at md |
| `px-lg-2` | 1 | 0.5rem at lg |
| `ps-md-2` | 1 | 0.5rem at md |
| `my-md-4` | 1 | 1.5rem at md |
| `ms-md-0` | 1 | 0 at md |
| `me-sm-1` | 1 | 0.25rem at sm |
| `gap-sm-1` | 1 | 0.25rem at sm |

**Observation:** Responsive spacing is lightly used. The main responsive pattern is the content container
`my-3 my-md-5` in `base.html` and a few `p-sm-2` adjustments for fighter cards.

## 2. SCSS Custom Spacing

From `gyrinx/core/static/core/scss/styles.scss`:

| Declaration | Value | Context |
|-------------|-------|---------|
| `label { margin-bottom: 0.25rem }` | 0.25rem | Form labels -- matches Bootstrap `1` scale |
| `.fighter-switcher-btn { padding: 0.25em 0.5em }` | 0.25em / 0.5em | Fighter dropdown trigger -- uses `em` not `rem` |
| `.mb-last-0 > :last-child { margin-bottom: 0 !important }` | 0 | Reset pattern for rich text containers |
| `.flatpage-content a > h* .bi-link-45deg { margin-inline-start: 0.25em }` | 0.25em | Link icon offset -- uses `em` not `rem` |
| `.stat-input-cell { width: 4rem }` | 4rem | Pack fighter stat inputs |

**No custom spacing scale is defined.** The project relies entirely on Bootstrap's default `$spacers` map.

## 3. Implicit Spacing Scale

The project uses only Bootstrap 5 default spacing values:

| Scale | Value | Template usage | Role in Gyrinx |
|------:|------:|---------------:|----------------|
| 0 | 0 | 232 | Resets (mb-0, px-0, p-0, gap-0) |
| 1 | 0.25rem | 214 | Tight: list items, icon gaps, small adjustments |
| 2 | 0.5rem | 496 | Standard: inline spacing, hstack gaps, small containers |
| 3 | 1rem | 525 | Default: vstack gaps, form spacing, section margins |
| 4 | 1.5rem | 62 | Section: page-level gaps, tabs margin |
| 5 | 3rem | 20 | Major: page-level section separation |

**The full Bootstrap scale is in active use**, with usage concentrated at scales 2 and 3.

## 4. Inconsistencies

### 4.1 Outer container gap varies by page type without a clear rule

| Page type | Outer gap | Examples |
|-----------|-----------|---------|
| Forms | `gap-3` (1rem) | fighter-edit, list-edit, campaign-new, pack-edit |
| Index/listing pages | `gap-4` (1.5rem) | lists-index, campaigns-index, pack-lists, page.html layout |
| Detail pages | `gap-5` (3rem) | campaign-detail, pack-detail, list-about |
| Advancement flow | `gap-4` (1.5rem) | advancement-type, advancement-select, advancement-dice-choice |
| Mixed/inconsistent | varies | pack-activity uses `gap-3`, pack-lists uses `gap-4`, pack-detail uses `gap-5` |

**Problem:** Three different gap values are used for page-level section spacing, with no documented
convention for when to use each. The pack pages are a clear example: three sibling pages use three
different gaps.

### 4.2 Section heading margin varies

| Pattern | Count | Context |
|---------|------:|---------|
| `h2.h5.mb-0` | common | Section headings inside section header bars |
| `h2.h5.mb-2` | occasional | Pack lists "Subscribed" section |
| `h2.h5.mb-3` | occasional | Pack lists "Available" section |

The same page (pack-lists) uses both `mb-2` and `mb-3` for sibling section headings.

### 4.3 Form button row margin varies

| Pattern | Count | Context |
|---------|------:|---------|
| `div.mt-3` | majority | Standard form button row (campaign-edit, pack-edit, fighter-edit) |
| `div.mt-2` | occasional | Some fighter forms |
| no margin | rare | Buttons inline in the form vstack |

### 4.4 Page title bottom margin varies

| Pattern | Context |
|---------|---------|
| `h1.mb-0` | Pack detail, campaign detail (no subtitle) |
| `h1.mb-1` | Lists index, campaigns index, packs index (with subtitle) |
| `h1.mb-2` | Campaign sub-pages (assets, attributes, resources) |

### 4.5 vstack gap-3 vs gap-4 for form layouts

Most forms use `vstack gap-3` (1rem between fields), but advancement flow pages use `vstack gap-4`
(1.5rem). This creates inconsistent field spacing across forms.

### 4.6 Empty state padding varies

| Pattern | Context |
|---------|---------|
| `div.py-2` | Packs index, user profile |
| `div.py-2.text-muted.small` | Pack lists |
| `p.text-muted.small.mb-0` | Pack detail activity |
| `p.text-center.text-secondary.mb-0` | Pack detail content sections |
| `div.text-muted.fst-italic` | List about (no lore) |

No single empty state spacing pattern.

## 5. Consolidation Recommendations

### 5.1 Confirm the Bootstrap default scale

The project should continue using Bootstrap's default spacing scale without modification. All six
values (0 through 5) are actively used and map cleanly to distinct semantic roles.

### 5.2 Standardise outer container gaps by page type

Define three named gap conventions:

| Convention | Gap | When to use |
|------------|-----|-------------|
| **Form gap** | `gap-3` (1rem) | All form/edit pages, confirmation dialogs |
| **List gap** | `gap-4` (1.5rem) | Index pages, listing pages, multi-section browsing pages |
| **Detail gap** | `gap-5` (3rem) | Detail/show pages with distinct sections |

**Action:** Normalise pack-activity from `gap-3` to `gap-4` or `gap-5` depending on whether it is
treated as a listing or detail page. Normalise advancement flow pages to `gap-3` (they are forms).

### 5.3 Standardise page title bottom margin

| Convention | Margin | When to use |
|------------|--------|-------------|
| Title with subtitle | `mb-1` | When followed by a `p.fs-5` subtitle |
| Title without subtitle | `mb-0` | When wrapped in a vstack that provides gap |
| Title on sub-page | `mb-2` | Campaign sub-pages with campaign name subtitle |

### 5.4 Standardise form button row

All form button rows should use `div.mt-3`. Remove `mt-2` variants.

### 5.5 Standardise section heading margin

Section headings (`h2.h5`) inside section header bars should use `mb-0` (the bar provides its own
padding). Standalone section headings should use `mb-3` consistently.

### 5.6 Standardise empty state spacing

Adopt a single empty state pattern: `<p class="text-muted mb-0">Message.</p>` with no additional
padding. The parent vstack's gap handles spacing. This eliminates `py-2`, `text-center`,
`text-secondary`, `small`, and `fst-italic` variants.

### 5.7 Custom SCSS spacing

The two `em`-based spacing values in the fighter-switcher and flatpage link icons are intentional
(they scale with font size). No change needed.

The `label { margin-bottom: 0.25rem }` override aligns with Bootstrap's scale-1 and should be retained.
