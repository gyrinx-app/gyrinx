# Layout Audit

## 1. Page Layout Inventory

### Layout container hierarchy

Every page in the app follows this nesting:

```
foundation.html    <html><body>
  base.html          <nav.navbar> + <div#content.container.my-3.my-md-5>
    [page template]    <div class="col-* px-0 vstack gap-*">
```

The outermost content wrapper is a Bootstrap `.container` (max-width responsive container, not
fluid). All pages inherit this. Individual page templates then apply a column-width class to
constrain their content.

### Page width shells

Five distinct column-width patterns are in use:

| Shell | Classes | Max width (xl) | Count | Used by |
|-------|---------|---------------|------:|---------|
| **Narrow** | `col-12 col-md-8 col-lg-6` | ~50% | 84 | All forms, confirmations, edit pages |
| **Full** | `col-lg-12` (or bare `col-12`) | 100% | 16 | Index/listing pages, dice, archived fighters |
| **Wide** | `col-12 col-xl-8` | ~67% | 6 | Pack detail, pack activity, pack lists, campaign sub-pages |
| **Medium** | `col-12 col-lg-8` | ~67% at lg | 5 | Fighter injuries, fighter rules, fighter skills, fighter add-injury |
| **Medium-narrow** | `col-12 col-xl-6` | 50% at xl | 5 | Campaign sub-pages (assets, attributes) |
| **Sidebar** | `row g-*` with inner cols | varies | 10 | Campaign detail, user profile, home, attributes |

Additionally, the `page.html` layout provides a standard full-width shell:

```html
<div class="col-lg-12 px-0 vstack gap-4">
```

But only 1 template extends it (`list_credits_edit.html`), and most listing pages reimplement this
pattern manually.

### Detailed shell usage

#### Shell: Narrow (`col-12 col-md-8 col-lg-6 px-0 vstack gap-3`)

This is the dominant layout -- 84 templates use it. It covers:

- Fighter forms: edit, new, archive, delete, clone, kill, resurrect, restore, capture
- Fighter sub-forms: notes, narrative, xp, counters, advancements (delete), equipment
- List forms: edit, new, archive, clone
- Campaign forms: edit, new, start, log-action, resource-modify
- Pack forms: edit, new, item-add, item-edit, item-delete, weapon-profile, permissions
- Confirmation dialogs: assign-delete, upgrade-delete, equipment-list-item-remove
- Battle forms: edit, new, note-add

Variant: 6 templates use `col-12 col-md-8 col-lg-6 vstack gap-4` (no `px-0`, wider gap):
advancement-type, advancement-select, advancement-dice-choice, advancement-other,
advancement-confirm, equipment-sell.

#### Shell: Full (`col-lg-12 px-0 vstack gap-*`)

| Template | Gap | Notes |
|----------|-----|-------|
| `lists.html` (index) | `gap-4` | Via page.html layout |
| `campaigns.html` (index) | `gap-4` | Direct implementation |
| `packs.html` (index) | `gap-4` | Direct implementation |
| `dice.html` | `gap-3` | Single-page tool |
| `list_archived_fighters.html` | `gap-3` | Listing page |
| `design_system_debug.html` | `gap-5` | Debug page |
| `index.html` (home) | custom | Hero + container sections |

#### Shell: Wide (`col-12 col-xl-8 px-0 vstack gap-*`)

| Template | Gap |
|----------|-----|
| `pack.html` (detail) | `gap-5` |
| `pack_activity.html` | `gap-3` |
| `pack_lists.html` | `gap-4` |
| `campaign_actions.html` | `gap-5` |
| `campaign_resources.html` | `gap-5` |
| `campaign_packs.html` | `gap-5` |

#### Shell: Sidebar (`row g-*`)

| Template | Gutter | Left col | Right col | Notes |
|----------|--------|----------|-----------|-------|
| `campaign.html` (detail) | `g-5` | `col-lg-8` | `col-lg-4` | Main + sidebar |
| `user.html` (profile) | `g-3` | `col-lg-4` | `col-lg-8` | Sidebar + main (reversed) |
| `index.html` (home, logged in) | `g-4` | `col-lg-8` | `col-lg-4` | Main + sidebar |
| `list_attribute_edit.html` | `g-3` | `col-lg-8` | implicit | Form + context |
| `campaign_attributes.html` | `g-2` | inner cols | inner cols | Attribute value cards |
| `campaign_actions.html` | `g-2` | inner cols | inner cols | Action form fields |
| `campaign_packs.html` | `g-2` | inner cols | inner cols | Pack grid |

## 2. Layout Method Inventory

### Method frequency across all templates

| Method | Count | Role |
|--------|------:|------|
| `vstack` | 302 | Primary vertical stacking -- used in nearly every template |
| `row` (Bootstrap grid) | 165 | Two-column layouts, form grids, footer |
| `d-flex` | 163 | Inline flex layouts (headers, button rows, metadata lines) |
| `hstack` | 147 | Horizontal stacking (metadata, button groups, icon+text) |
| `grid` (CSS Grid) | 23 | Fighter card grids, filter forms |
| `container` | 17 | Base layout wrapper, footer |
| `d-grid` | 2 | Rare, used in filter forms |

### vstack + gap combinations

| Pattern | Count | Semantic role |
|---------|------:|---------------|
| `vstack gap-3` | 170 | Default vertical layout: forms, page sections |
| `vstack gap-2` | 37 | Tight vertical: cards, metadata groups |
| `vstack gap-4` | 32 | Section layout: page-level content areas |
| `vstack gap-1` | 29 | Very tight: inline item groups, stacked badges |
| `vstack gap-5` | 13 | Major section: detail pages |
| `vstack gap-0` | 8 | No gap: header title + subtitle |

### hstack + gap combinations

| Pattern | Count | Semantic role |
|---------|------:|---------------|
| `hstack gap-2` | 55 | Standard horizontal: metadata, badges, icons |
| `hstack gap-3` | 39 | Wide horizontal: page header rows, list item rows |
| `hstack gap-1` | 6 | Tight horizontal: icon+label |

### CSS Grid usage

CSS Grid (Bootstrap's `$enable-cssgrid: true` module) is used exclusively for fighter card grids
and filter form layouts:

| g-col pattern | Count | Context |
|---------------|------:|---------|
| `g-col-12` | 54 | Mobile-first full width |
| `g-col-md-6` | 23 | Two-column at md |
| `g-col-sm-6` | 8 | Two-column at sm |
| `g-col-xl-4` | 7 | Three-column at xl |
| `g-col-xl-2` | 6 | Six-column at xl (compact fighter cards) |
| `g-col-md-3` | 6 | Four-column at md (compact fighter cards) |
| `g-col-xl-6` | 4 | Two-column at xl |
| `g-col-lg-6` | 4 | Two-column at lg |
| `g-col-md-12` | 3 | Full width at md |
| `g-col-xl-8` | 1 | Wide column at xl |

Fighter cards use two distinct grid patterns:

- **Compact cards** (print, stash): `g-col-12 g-col-sm-6 g-col-md-3 g-col-xl-2`
- **Full cards** (normal view): `g-col-12 g-col-md-6 g-col-xl-4`

## 3. Responsive Breakpoint Usage

### Breakpoints in column classes

| Breakpoint | Column uses | Display uses | Spacing uses |
|------------|------------:|-------------:|-------------:|
| (none/xs) | 200+ (`col-12`) | base defaults | heavy |
| `sm` | 32 | 8 (`d-sm-*`) | 22 (`p-sm-*`, etc.) |
| `md` | 158 | 10 (`d-md-*`) | 11 |
| `lg` | 147 | 4 (`d-lg-*`) | 2 |
| `xl` | 48 | 0 | 0 |
| `xxl` | 0 | 0 | 0 |

**Key observations:**

- `xxl` breakpoint is never used
- `sm` is used sparingly, mostly for fighter card grid columns
- `md` and `lg` are the primary layout breakpoints
- `xl` is used for wider detail pages and fighter card columns
- The navbar collapses at `lg` (`navbar-expand-lg`)

### Flexbox utilities

| Utility | Count | Notes |
|---------|------:|-------|
| `align-items-center` | 127 | Dominant vertical alignment |
| `justify-content-between` | 63 | Standard header pattern (title + actions) |
| `flex-wrap` | 50 | Metadata rows that wrap on mobile |
| `align-items-start` | 33 | Card content, form layouts |
| `flex-column` | 31 | Responsive column stacking |
| `flex-grow-1` | 28 | Fill remaining space |
| `align-items-md-center` | 14 | Responsive alignment |
| `align-items-baseline` | 14 | Text alignment |
| `justify-content-center` | 8 | Pagination, centered content |
| `align-items-end` | 7 | Button alignment |
| `justify-content-end` | 6 | Right-aligned actions |
| `flex-shrink-0` | 6 | Prevent icon/badge shrinking |

## 4. Standard Page Shells

Based on the data, the app has **four recurring page shells** plus one composite pattern:

### Shell A: Form Page

**Pattern:** `col-12 col-md-8 col-lg-6 px-0 vstack gap-3`

Used by ~84 templates. The most common layout in the app. Narrows from full-width on mobile to
roughly half-width on desktop. Contains a `vstack gap-3` for consistent 1rem spacing between
form fields and sections.

**Structure:**

```
container (my-3 my-md-5)
  col-12 col-md-8 col-lg-6 px-0 vstack gap-3
    back button
    h1.h3
    form.vstack.gap-3
      fields...
      div.mt-3 (button row)
```

**Views using this shell:** fighter-edit, fighter-new, list-edit, list-new, campaign-edit,
campaign-new, pack-edit, pack-new, and ~70 more confirmation/edit pages.

### Shell B: Listing Page

**Pattern:** `col-lg-12 px-0 vstack gap-4`

Used by ~16 templates. Full-width content with `gap-4` section spacing. The `page.html` layout
provides this as a reusable base.

**Structure:**

```
container (my-3 my-md-5)
  col-lg-12 px-0 vstack gap-4
    header (h1 + subtitle)
    filter/search (optional)
    list items (vstack gap-2 or gap-3)
    pagination (optional)
```

**Views using this shell:** lists-index, campaigns-index, packs-index, dice, archived-fighters.

### Shell C: Detail Page

**Pattern:** `col-12 col-xl-8 px-0 vstack gap-5`

Used by ~6 templates. Constrained width with generous `gap-5` (3rem) section spacing for
content-heavy detail pages.

**Structure:**

```
container (my-3 my-md-5)
  col-12 col-xl-8 px-0 vstack gap-5
    back button
    header (h1 + metadata)
    section 1
    section 2
    ...
```

**Views using this shell:** pack-detail, campaign-actions, campaign-resources, campaign-packs.

Variant: `col-12 col-xl-8 px-0 vstack gap-3` (pack-activity) and `gap-4` (pack-lists) -- these
should be normalised.

### Shell D: Sidebar Page

**Pattern:** `row g-3` (or `g-4`, `g-5`) with `col-lg-8` + `col-lg-4`

Used by ~4 templates. Two-column layout with main content and sidebar. The sidebar position
(left/right) and gutter size vary.

**Structure:**

```
container (my-3 my-md-5)
  px-0
    header row
    row g-* (gutter)
      col-lg-8 (main)
      col-lg-4 (sidebar)
```

**Views using this shell:** campaign-detail (`g-5`), home-logged-in (`g-4`), user-profile (`g-3`).

### Shell E: Medium Form Page (uncommon)

**Pattern:** `col-12 col-lg-8 px-0 vstack gap-3`

Used by ~5 templates. Wider than Shell A for forms that need more horizontal space (tables, injuries).

**Views:** fighter-injuries-edit, fighter-rules-edit, fighter-skills-edit, fighter-add-injury,
fighter-remove-injury.

## 5. Layout Inconsistencies

### 5.1 Inconsistent outer gap values for similar page types

The pack pages use three different gaps:

- `pack.html` (detail): `gap-5`
- `pack_lists.html`: `gap-4`
- `pack_activity.html`: `gap-3`

The campaign sub-pages are more consistent (`gap-5`) but campaign-detail itself uses a sidebar
layout with `g-5` gutters.

### 5.2 Advancement flow uses wrong shell

The advancement flow pages (type, select, dice-choice, other, confirm) use `col-12 col-md-8 col-lg-6
vstack gap-4` -- missing `px-0` and using `gap-4` instead of `gap-3`. These are functionally
form pages and should use Shell A.

### 5.3 page.html layout is underutilised

The `page.html` layout provides a clean Shell B implementation, but only 1 template extends it.
All other listing pages reimplement the same structure manually.

### 5.4 Sidebar gutter varies

| Page | Gutter |
|------|--------|
| campaign-detail | `g-5` |
| home-logged-in | `g-4` |
| user-profile | `g-3` |

Three sidebar pages, three different gutter values.

### 5.5 CSS Grid vs Bootstrap row/col mixing

Fighter card grids use CSS Grid (`grid` + `g-col-*`), while page-level layouts use Bootstrap
row/col. This is intentional (CSS Grid handles the auto-flow dense pattern for fighter cards),
but the `g-col-*` classes are only used in this one context.

### 5.6 Inconsistent `px-0` application

Most Shell A templates include `px-0`, but 6 advancement flow templates omit it. Some templates
use `px-0` on the outer div and also on inner elements, creating redundant resets.

### 5.7 `container` vs `container-fluid`

The app uses only `.container` (never `.container-fluid`). This is consistent. The single
container breakpoint set is: 540px (sm), 720px (md), 960px (lg), 1140px (xl), 1320px (xxl).

## 6. Consolidation Recommendations

### 6.1 Name and document four standard shells

| Shell name | Classes | Use when |
|------------|---------|----------|
| **form-page** | `col-12 col-md-8 col-lg-6 px-0 vstack gap-3` | Any form, edit, confirmation, or action page |
| **list-page** | `col-lg-12 px-0 vstack gap-4` | Index, listing, search results, browsing pages |
| **detail-page** | `col-12 col-xl-8 px-0 vstack gap-5` | Detail/show pages with multiple content sections |
| **sidebar-page** | `px-0` + `row g-4` + `col-lg-8` + `col-lg-4` | Pages with main content and a sidebar |

Retire Shell E (medium form). The 5 templates using `col-12 col-lg-8` should move to either
**form-page** (if the content fits) or **detail-page** (if it needs width for tables).

### 6.2 Extend page.html or create shell templates

Create layout templates for each shell:

```
core/layouts/page.html         -> list-page (already exists, expand usage)
core/layouts/form_page.html    -> form-page (new)
core/layouts/detail_page.html  -> detail-page (new)
core/layouts/sidebar_page.html -> sidebar-page (new)
```

This would eliminate the 84 duplicate `col-12 col-md-8 col-lg-6 px-0 vstack gap-3` wrapper divs.

### 6.3 Normalise advancement flow

Change the 6 advancement flow templates from `col-12 col-md-8 col-lg-6 vstack gap-4` to the
standard form-page shell (`col-12 col-md-8 col-lg-6 px-0 vstack gap-3`).

### 6.4 Normalise pack page gaps

- `pack_activity.html`: change `gap-3` to `gap-5` (it is a detail sub-page)
- `pack_lists.html`: change `gap-4` to `gap-5` (it is a detail sub-page)

Or if these are considered listing pages, change both to `gap-4`.

### 6.5 Normalise sidebar gutters

Standardise all sidebar pages to `g-4`:

- campaign-detail: change `g-5` to `g-4`
- user-profile: change `g-3` to `g-4`

### 6.6 Retire `xxl` planning

The `xxl` breakpoint is not used anywhere. If a future need arises, apply it consistently, but
there is no current need to add it.

### 6.7 Consolidate CSS Grid usage

Document that CSS Grid (`grid` + `g-col-*`) is reserved for fighter card grids and dense
auto-flow layouts. All other multi-column layouts should use Bootstrap row/col.
