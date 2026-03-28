# Cross-Cutting Component Audit

Aggregated from 48 per-view audits, the SCSS source, and template grep analysis. This report inventories every UI component variant, classifies each as canonical/drift/anti-pattern, and identifies missing components that should be encoded in the design system.

---

## 1. Buttons

**Total instances:** ~120+
**Distinct variants:** 18

### Variant Table

| Classes | Frequency | Views | Classification | Notes |
|---------|-----------|-------|----------------|-------|
| `btn btn-primary btn-sm` | ~20 | list-detail, campaign-detail, pack-detail, list-packs, pack-lists, campaign-add-lists | **Canonical** | Standard primary action in toolbars and data views |
| `btn btn-secondary btn-sm` | ~10 | list-detail, campaign-detail, list-edit, injuries-edit | **Canonical** | Secondary action in toolbars |
| `btn btn-primary` (no btn-sm) | ~25 | fighter-edit, fighter-new, xp-edit, stats-edit, narrative-edit, notes-edit, list-edit, list-new, campaign-edit, campaign-new, pack-edit, home (Get started), lists-index (search), campaigns-index (search), weapons-edit (search), skills-edit (search), advancement-type, advancement-other, dice | **Acceptable Variant** | Full-size on form pages for submit buttons |
| `btn btn-link` (no btn-sm) | ~15 | fighter-edit, fighter-new, xp-edit, stats-edit, narrative-edit, notes-edit, campaign-edit, campaign-new, list-edit, list-new, list-credits | **Acceptable Variant** | Cancel link on form pages |
| `btn btn-outline-primary btn-sm` | ~10 | weapons-edit, gear-edit, skills-edit, rules-edit, campaign-add-lists, campaign-packs, pack-lists | **Canonical** | Add/subscribe action in data views |
| `btn btn-outline-secondary btn-sm` | ~8 | list-detail (fighter edit), list-about, list-notes, dice | **Canonical** | Edit action on content items |
| `btn btn-secondary btn-sm dropdown-toggle` | ~6 | list-detail, campaign-detail, pack-detail | **Canonical** | Overflow menu trigger |
| `btn btn-outline-primary btn-sm dropdown-toggle` | ~6 | lists-index, campaigns-index, weapons-edit, gear-edit, campaign-packs, pack-lists | **Canonical** | Filter dropdown trigger |
| `btn btn-link btn-sm p-0 text-secondary` | ~4 | list-common-header (refresh), campaign-detail (row dropdown), campaign-assets (mobile dropdown) | **Acceptable Variant** | Inline icon-only action |
| `btn btn-link icon-link btn-sm` | ~6 | lists-index, campaigns-index, weapons-edit, gear-edit, packs-index, pack-lists | **Canonical** | Update filter action |
| `btn btn-link text-secondary icon-link btn-sm` | ~6 | lists-index, campaigns-index, weapons-edit, gear-edit, packs-index, pack-lists | **Canonical** | Reset filter action |
| `btn btn-success btn-sm` | 2 | campaign-detail (Start, Reopen) | **Acceptable Variant** | State-change positive action |
| `btn btn-danger btn-sm` | 1 | campaign-detail (End) | **Acceptable Variant** | State-change destructive action |
| `btn btn-success` (no btn-sm) | 1 | advancement-select (Confirm) | **Acceptable Variant** | Final confirmation in wizard |
| `btn btn-info text-bg-info btn-sm` | 1 | list-detail (Invitations) | **Bespoke** | Only instance of btn-info |
| `btn btn-warning btn-sm` | 1 | home (Change Username) | **Bespoke** | Only instance of btn-warning |
| `btn btn-outline-danger btn-sm` | 2 | list-packs (Remove), pack-lists (Remove) | **Acceptable Variant** | Destructive outline button |
| `btn btn-outline` (no variant) | 1 | dice (Reset) | **Anti-pattern** | Invalid Bootstrap class; renders unstyled |
| `btn btn-outline-secondary dropdown-toggle` (no btn-sm) | 2 | flatpage-about (mobile nav), account-home (Menu) | **Drift** | Missing btn-sm on dropdown toggles |

### Canonical Definition

**Toolbar/data view buttons:** `btn btn-{variant} btn-sm`

- Primary action: `btn btn-primary btn-sm`
- Secondary action: `btn btn-secondary btn-sm`
- Add/subscribe: `btn btn-outline-primary btn-sm`
- Edit: `btn btn-outline-secondary btn-sm`
- Destructive: `btn btn-danger btn-sm` or `btn btn-outline-danger btn-sm`

**Form page buttons:** `btn btn-{variant}` (full size, no btn-sm)

- Submit: `btn btn-primary`
- Cancel: `btn btn-link`

**Filter buttons:**

- Update: `btn btn-link icon-link btn-sm`
- Reset: `btn btn-link text-secondary icon-link btn-sm`

### Migration Targets

| Current | Target | Views |
|---------|--------|-------|
| `btn btn-outline` | `btn btn-outline-secondary` | dice |
| `btn btn-outline-secondary dropdown-toggle` (no btn-sm) | Add `btn-sm` | flatpage-about, account-home |
| Search buttons (full-size in filter bars) | Consider `btn-sm` or document as intentional | lists-index, campaigns-index, weapons-edit, gear-edit, skills-edit, rules-edit |

---

## 2. Cards

**Total instances:** ~40+
**Distinct variants:** 8

### Variant Table

| Classes | Frequency | Views | Classification | Notes |
|---------|-----------|-------|----------------|-------|
| `card {grid_classes} break-inside-avoid` with `card-header p-2` + `card-body p-0` | ~30+ | list-detail, list-print, list-about, list-notes | **Canonical** | Fighter cards in grids |
| `card g-col-12 g-col-md-6` with `card-header p-2` + `card-body vstack gap-2 p-0 p-sm-2` | ~10 | weapons-edit, gear-edit | **Canonical** | Equipment category cards in edit views |
| `card g-col-12 g-col-md-6` with `card-header p-2` + `card-body p-0 p-sm-2` | ~10 | skills-edit, rules-edit | **Canonical** | Skill/rule category cards |
| `card` with `card-body` only (no header) | 3 | stats-edit, state (injuries-edit), user-profile | **Drift** | Convention says "cards only for fighters in grids"; these should be `border rounded p-3` |
| `card h-100 shadow-sm` | 2 | advancement-dice-choice | **Bespoke** | Only cards with shadow; wizard-specific |
| `card card-body vstack gap-4` | 1 | home (new list prompt) | **Bespoke** | Inline card-form, unique to home page |
| `nav card card-body flex-column mb-3 p-2` | 2 | list-about, list-notes (TOC sidebar) | **Bespoke** | Navigation card; could be a dedicated component |
| `card` with `card-header` + `card-body mb-last-0` | 1 | injuries-edit (current injuries) | **Drift** | Should be `border rounded p-3` per convention |

### Card Body Padding Variants (Sub-inconsistency)

| Padding | Views | Classification |
|---------|-------|----------------|
| `p-0` | Fighter card (interactive, print) | **Canonical** (print/compact) |
| `p-0 p-sm-2` | Fighter card sections, skills/rules | **Canonical** (screen) |
| `p-0 p-sm-2 pt-2` | Stash card, fighter gear card | **Drift** -- extra `pt-2` |
| `p-0 px-sm-2 py-sm-1` | Gear edit categories | **Drift** -- different vertical padding |
| `p-2` | Pack equipment categories, rules add card | **Acceptable Variant** (compact) |
| `card-body` (default ~1rem) | Stats edit, state edit, user profile | **Drift** -- non-fighter cards using default |
| `card-body vstack gap-3` | Advancement dice choice | **Bespoke** |

### Canonical Definition

**Fighter card in grid:**

```html
<div class="card {grid_classes} break-inside-avoid">
  <div class="card-header p-2 hstack align-items-start">...</div>
  <div class="card-body p-0">...</div>
</div>
```

**Equipment/skill category card in grid:**

```html
<div class="card g-col-12 g-col-md-6">
  <div class="card-header p-2">...</div>
  <div class="card-body vstack gap-2 p-0 p-sm-2">...</div>
</div>
```

### Migration Targets

| Current | Target | Views |
|---------|--------|-------|
| `card` + `card-body` (standalone, no grid) | `border rounded p-3` | stats-edit, injuries-edit (state), user-profile |
| Inconsistent `pt-2` additions | Standardize on `p-0 p-sm-2` | stash card, fighter gear card |

---

## 3. Tables

**Total instances:** ~30+
**Distinct variants:** 6

### Variant Table

| Classes | Frequency | Views | Classification | Notes |
|---------|-----------|-------|----------------|-------|
| `table table-sm table-borderless mb-0` | ~15 | campaign-detail, campaign-assets, campaign-resources, campaign-attributes, stash card | **Canonical** | Data tables with `align-middle` |
| `table table-sm table-borderless table-fixed mb-0` | ~5 | fighter statline (list-detail, print, about, weapons-edit, gear-edit) | **Canonical** | Fixed-layout stat tables |
| `table table-sm table-borderless mb-0 fs-7` | ~8 | weapons table, attributes table, resources table | **Canonical** | Compact data tables |
| `table table-sm table-borderless table-responsive text-center mb-0` | ~5 | list-common-header stats summary | **Canonical** | Centered summary stats |
| `table table-sm mb-0` (with borders) | 2 | captured fighters, campaign-add-lists available gangs | **Drift** | Missing `table-borderless`; intentional for actionable rows but inconsistent |
| `table table-borderless table-sm` (different class order) | 2 | list-attributes fighter type summary, advancements | **Drift** | Class order inconsistency (no functional difference) |

### Canonical Definition

**Standard data table:** `table table-sm table-borderless mb-0 align-middle`
**Stat table (fixed):** `table table-sm table-borderless table-fixed mb-0`
**Compact table:** `table table-sm table-borderless mb-0 fs-7`
**Summary table:** `table table-sm table-borderless table-responsive text-center mb-0`

All tables should be wrapped in `div.table-responsive` for horizontal scroll safety.

### Migration Targets

| Current | Target | Views |
|---------|--------|-------|
| `table table-sm mb-0` (bordered) | Add `table-borderless` or document as "actionable table" variant | captured fighters, campaign-add-lists |
| Missing `align-middle` | Add `align-middle` | captured fighters |
| Missing `table-responsive` wrapper | Add wrapper | injuries-edit, advancements |

---

## 4. Navigation

**Total instances:** ~25
**Distinct variants:** 7

### Variant Table

| Classes | Frequency | Views | Classification | Notes |
|---------|-----------|-------|----------------|-------|
| Back breadcrumb via `back.html` | ~20 | stats-edit, campaign-edit, campaign-new, campaign-detail, list-edit, list-new, list-packs, pack-detail, pack-edit, pack-activity, pack-lists, campaign-assets, campaign-resources, campaign-attributes, campaign-packs, all campaign sub-pages | **Canonical** | Standard back navigation |
| `nav nav-tabs` (page tabs) | 4 | lists-index, list-about, list-notes, pack-lists | **Canonical** | Tab navigation between related pages |
| `nav nav-tabs flex-grow-1 px-1` (in-card tabs) | 1 | fighter-card-content (fighter card) | **Canonical** | Tabs within fighter cards |
| `nav hstack gap-1 flex-nowrap` | 1 | list-detail (toolbar) | **Canonical** | Toolbar navigation |
| `nav btn-group flex-nowrap` | 2 | campaign-detail, pack-detail (action bar) | **Canonical** | Button group in header |
| Fighter switcher dropdown | ~10 | weapons-edit, gear-edit, skills-edit, rules-edit, narrative-edit, notes-edit, xp-edit, advancements | **Canonical** | Fighter context switching |
| Home breadcrumb via `home.html` | 3 | user-profile, dice | **Acceptable Variant** | Simple "Home" breadcrumb |

### Canonical Definition

**Back navigation:** `{% include "core/includes/back.html" with url=target_url text="Back Text" %}`
**Page tabs:** `ul.nav.nav-tabs.mb-4` with `li.nav-item` > `a.nav-link`
**Fighter card tabs:** `ul.nav.nav-tabs.flex-grow-1.px-1` with tab buttons using `fs-7 px-2 py-1`

---

## 5. Forms

**Total instances:** ~40+
**Distinct variants:** 5 rendering approaches

### Variant Table

| Rendering Approach | Frequency | Views | Classification | Notes |
|-------------------|-----------|-------|----------------|-------|
| `{{ form }}` (Django default) | ~8 | fighter-new, list-edit, list-new, campaign-edit, campaign-new, pack-edit | **Canonical** | Full Django form rendering |
| `{{ form.as_div }}` | 1 | list-credits-edit | **Drift** | Different from `{{ form }}` used elsewhere |
| Manual per-field with `form-label` + `form-text` + `invalid-feedback d-block` | ~10 | fighter-edit, narrative-edit, stats-edit, advancement forms | **Acceptable Variant** | Custom field layout for complex forms |
| `{% include "core/includes/form_field.html" %}` | ~5 | campaign form includes | **Acceptable Variant** | Shared field rendering include |
| Inline form elements (tables, hstacks) | ~10 | skills-edit, rules-edit, weapons-edit, gear-edit | **Acceptable Variant** | Action forms within data views |

### Form Container Pattern

| Pattern | Frequency | Classification |
|---------|-----------|----------------|
| `form.vstack.gap-3` | ~15 | **Canonical** |
| `form.vstack.gap-4` | 3 | **Drift** (advancement wizard only) |
| `form` (no class) | 2 | **Drift** |

### Button Group Pattern (form submit area)

| Pattern | Frequency | Views | Classification |
|---------|-----------|-------|----------------|
| `div.mt-3` | ~8 | stats-edit, narrative-edit, notes-edit, list-edit, list-new, pack-edit | **Canonical** |
| `div.hstack.gap-2.mt-3.align-items-center` | 2 | xp-edit, list-credits | **Drift** |
| `div.d-flex.align-items-center` | 1 | advancements | **Drift** |
| `div.hstack.gap-3.mt-4` | 1 | login (allauth) | **Bespoke** |

### Canonical Definition

**Form page:**

```html
<form class="vstack gap-3" method="post" action="...">
  {% csrf_token %}
  {{ form }}
  <div class="mt-3">
    <button type="submit" class="btn btn-primary">Save</button>
    <a href="..." class="btn btn-link">Cancel</a>
  </div>
</form>
```

### Migration Targets

| Current | Target |
|---------|--------|
| `{{ form.as_div }}` | `{{ form }}` |
| `hstack gap-2 mt-3` button groups | `div.mt-3` |
| `form.vstack.gap-4` | `form.vstack.gap-3` (unless wizard-specific variant documented) |

---

## 6. Badges

**Total instances:** ~30+
**Distinct variants:** 12

### Variant Table

| Classes | Frequency | Views | Classification | Notes |
|---------|-----------|-------|----------------|-------|
| `badge text-bg-primary` | ~8 | xp badge, credits badge, list rows | **Canonical** | Primary value badge |
| `badge text-bg-secondary` | ~5 | total xp, list type, cost badge | **Canonical** | Secondary/neutral badge |
| `badge text-bg-success` | ~3 | campaign "In Progress", staff badge, campaign gang badge | **Canonical** | Positive status badge |
| `badge text-bg-warning` | 1 | advancement-other (XP cost) | **Acceptable Variant** | Warning value badge |
| `badge text-bg-light border` | 2 | campaign attribute values | **Acceptable Variant** | Neutral tag badge with border |
| `badge bg-primary` | 2 | skills-edit (primary badge), list-packs (count) | **Drift** | Missing `text-` prefix |
| `badge bg-secondary` | 4 | campaign status, packs-index (unlisted), list-new (pack name), skills-edit | **Drift** | Missing `text-` prefix; older BS pattern |
| `badge bg-success` | 2 | campaign status (via status.html) | **Drift** | Missing `text-` prefix |
| `badge bg-warning` | 2 | injuries-edit (injured state), list-detail (injury badge) | **Drift** | Missing `text-` prefix |
| `badge bg-danger` | 2 | list-detail (dead badge) | **Drift** | Missing `text-` prefix |
| `badge bg-warning text-dark` | 2 | list-detail (captured), campaign-detail (captured) | **Drift** | Old pattern with manual text colour |
| `badge bg-info` | 1 | list-detail (invitation count) | **Drift** | Missing `text-` prefix |
| `badge bg-primary-subtle` | 1 | pack-detail (count inside button) | **Bespoke** | Subtle badge inside a primary button |
| `badge text-body border fw-normal` | 1 | fighter card cost (print) | **Acceptable Variant** | Print-specific neutral badge |

### Canonical Definition

All badges should use the `text-bg-*` pattern: `badge text-bg-{variant}`

Variants: `primary`, `secondary`, `success`, `danger`, `warning`, `info`, `light`

### Migration Targets

All `badge bg-*` instances (without `text-` prefix) should migrate to `badge text-bg-*`:

- `badge bg-secondary` -> `badge text-bg-secondary` (4 instances)
- `badge bg-success` -> `badge text-bg-success` (2 instances)
- `badge bg-primary` -> `badge text-bg-primary` (2 instances)
- `badge bg-warning` -> `badge text-bg-warning` (2 instances)
- `badge bg-danger` -> `badge text-bg-danger` (2 instances)
- `badge bg-info` -> `badge text-bg-info` (1 instance)
- `badge bg-warning text-dark` -> `badge text-bg-warning` (2 instances)

---

## 7. Icons (Bootstrap Icons)

**Total instances:** 400+ across 130 template files
**Distinct icon classes:** ~50+

### Icon Inventory

| Icon | Semantic Purpose | Frequency |
|------|-----------------|-----------|
| `bi-pencil` | Edit | High |
| `bi-plus-lg` | Add (large) | High |
| `bi-plus` | Add (small) | Medium |
| `bi-plus-circle` | Add (circle) | Medium |
| `bi-trash` | Delete/Remove | High |
| `bi-archive` | Archive | Medium |
| `bi-search` | Search | High |
| `bi-chevron-left` | Back navigation | High |
| `bi-chevron-right` | Forward/mobile row action | High |
| `bi-three-dots` | More options (horizontal) | Low |
| `bi-three-dots-vertical` | More options (vertical) | Medium |
| `bi-person` | Owner/user | High |
| `bi-award` | Campaign | High |
| `bi-box-seam` | Content pack | Medium |
| `bi-arrow-clockwise` | Refresh/Update | Medium |
| `bi-eye` / `bi-eye-slash` | Public/Unlisted | Medium |
| `bi-info-circle` | Information | Medium |
| `bi-exclamation-triangle` | Warning/Error | Medium |
| `bi-exclamation-triangle-fill` | Warning/Error (filled) | Low |
| `bi-check-circle` | Enable/Confirm | Medium |
| `bi-x-circle` | Disable | Medium |
| `bi-arrow-right` | Next (wizard) | Low |
| `bi-arrow-left-right` | Transfer | Low |
| `bi-dash` | Sub-item indicator | Medium |
| `bi-crosshair` | Weapon accessory | Low |
| `bi-arrow-up-circle` | Upgrade | Low |
| `bi-arrow-90deg-up` | Sub-menu arrow | Low |
| `bi-dot` | Content indicator | Low |
| `bi-clipboard` / `bi-check2` | Copy/Copied | Low |
| `bi-printer` | Print | Low |
| `bi-copy` | Clone | Low |
| `bi-file-text` | Lore/report | Low |
| `bi-journal-text` | Notes | Low |
| `bi-flag` | Action/battle | Low |
| `bi-envelope` | Invitations | Low |
| `bi-heartbreak` | Kill | Low |
| `bi-heart-pulse` | Resurrect | Low |
| `bi-person-add` | Add fighter | Low |
| `bi-truck` | Add vehicle | Low |
| `bi-person-bounding-box` | Embed | Low |
| `bi-trophy-fill` | Winner/Staff | Low |
| `bi-dice-1` through `bi-dice-6` | Dice faces | Low |
| `bi-gear` | Settings | Low |
| `bi-list` / `bi-list-ul` | List indicator | Low |
| `bi-clock` | Time/join date | Low |
| `bi-arrow-up` | Back to top | Low |
| `bi-link-45deg` | Heading anchor | Low |
| `bi-box-arrow-in-down` | Copy to | Low |
| `bi-box-arrow-up` | Copy from | Low |
| `bi-tags` | Attributes | Low |
| `bi-people` | Permissions | Low |
| `bi-x-lg` | Close/remove group | Low |
| `bi-dash-lg` | Decrease | Low |
| `bi-stop-circle` | Stop/End | Low |
| `bi-play-circle` | Start | Low |

### Icon Format Inconsistency

Two formats are used interchangeably:

| Format | Example | Frequency | Classification |
|--------|---------|-----------|----------------|
| Single class `bi-{name}` | `bi-pencil` | ~95% | **Canonical** |
| Two classes `bi bi-{name}` | `bi bi-pencil`, `bi bi-info-circle`, `bi bi-dice-6` | ~5% | **Drift** |

Both formats work but the codebase should standardize on `bi-{name}` (single class).

### Semantic Icon Inconsistencies

| Action | Icon Variants Used | Recommendation |
|--------|-------------------|----------------|
| Add | `bi-plus`, `bi-plus-lg`, `bi-plus-circle` | Standardize: `bi-plus-lg` for buttons, `bi-plus-circle` for inline actions |
| More options | `bi-three-dots`, `bi-three-dots-vertical` | Standardize: `bi-three-dots-vertical` for dropdown triggers |
| Warning/Error | `bi-exclamation-triangle`, `bi-exclamation-triangle-fill` | Standardize: `bi-exclamation-triangle` for warnings |

---

## 8. Dropdowns

**Total instances:** ~20
**Distinct variants:** 4

### Variant Table

| Trigger Pattern | Menu Classes | Frequency | Views | Classification |
|----------------|-------------|-----------|-------|----------------|
| `btn btn-secondary btn-sm dropdown-toggle` | `dropdown-menu dropdown-menu-end` | ~5 | list-detail, campaign-detail, pack-detail | **Canonical** | Overflow/more-options menu |
| `btn btn-outline-primary btn-sm dropdown-toggle` | `dropdown-menu shadow-sm p-2 fs-7 dropdown-menu-mw` | ~6 | lists-index, campaigns-index, weapons-edit, gear-edit, pack-lists | **Canonical** | Filter dropdown with checkboxes |
| `btn btn-link btn-sm p-0 text-secondary` | `dropdown-menu dropdown-menu-end` | ~3 | campaign-detail (row), campaign-assets (mobile) | **Acceptable Variant** | Inline row actions |
| `btn btn-outline-secondary dropdown-toggle` (no btn-sm) | `dropdown-menu` | 2 | flatpage-about (mobile nav), account-home (menu) | **Drift** | Missing btn-sm |

### Dropdown Item Patterns

| Pattern | Frequency | Classification |
|---------|-----------|----------------|
| `dropdown-item icon-link` | High | **Canonical** |
| `dropdown-item text-danger` | Medium | **Canonical** (destructive items) |
| `dropdown-item icon-link disabled` | Low | **Acceptable Variant** |
| `dropdown-divider` | Medium | **Canonical** |
| `dropdown-header text-uppercase small` | Low | **Acceptable Variant** |
| `dropdown-item-text text-muted small` | Low | **Acceptable Variant** (disabled state text) |

---

## 9. Callouts, Alerts & Feedback Messaging

**Total instances:** ~50+
**Distinct variants:** 13 (documented in detail in `feedback-messaging-patterns.md`)

### Error Patterns

| Pattern | Classes | Frequency | Views | Classification |
|---------|---------|-----------|-------|----------------|
| Border error box | `border border-danger rounded p-2 text-danger` | 8 | gear-edit, pack add pages, campaign-add-lists | **Canonical** | Per design convention |
| Bootstrap alert error | `alert alert-danger` | 8 | stats-edit, weapons-edit, injuries-edit delete confirm, advancement forms, login, allauth | **Drift** | Convention says avoid `alert` for inline errors |
| Inline field error | `invalid-feedback d-block` | ~15 | form_field.html, most manual form templates | **Canonical** | Bootstrap validation styling |
| Inline text error | `text-danger small` / `text-danger fs-7` | ~8 | campaign copy pages, pack permissions, counters edit | **Drift** | Should use `invalid-feedback` |
| Full dict error dump | `alert alert-danger` with `form.errors` | 1 | list_attribute_edit | **Anti-pattern** | Renders entire error dict |

### Warning Patterns

| Pattern | Classes | Frequency | Views | Classification |
|---------|---------|-----------|-------|----------------|
| Bootstrap alert warning | `alert alert-warning` | ~19 | Campaign confirm pages, fighter state changes, advancement warnings | **Canonical** (for simple warnings) | Most common |
| Alert with heading | `alert alert-warning` + `alert-heading h4` | ~5 | Campaign remove pages | **Acceptable Variant** | Structured warnings |
| Border warning box | `border border-warning rounded p-3 bg-warning bg-opacity-10` | 2 | list-archive, pack default assignment remove | **Acceptable Variant** | Rich content warnings |
| Border warning (subtle bg) | `border border-warning rounded p-3 bg-warning-subtle` | 2 | Campaign copy conflict detection | **Drift** | Should unify with `bg-opacity-10` variant |
| Compact alert warning | `alert alert-warning p-2 fs-7` | 1 | advancement-skill-form | **Drift** | Non-standard padding/size |
| Border warning (no bg) | `border border-warning rounded p-3` | 1 | campaign-add-lists pack confirm | **Drift** | Should have background |

### Info Patterns

| Pattern | Classes | Frequency | Views | Classification |
|---------|---------|-----------|-------|----------------|
| Bootstrap alert info | `alert alert-info` | ~11 | injuries-edit empty state, advancement dice, campaign action log | **Canonical** (for prominent notes) | |
| Subtle info box | `border rounded p-2 text-secondary` | ~5 | fighter state edit, remove injury | **Canonical** (for subtle notes) | With `bi-info-circle` icon |
| Neutral border box | `border rounded p-2` (no colour) | ~2 | campaign battles empty state | **Drift** | Should choose info or secondary |
| Inline muted text | `p.text-muted.small` with icon | ~3 | battle views | **Drift** | Should use border rounded pattern |

### Success Pattern

| Pattern | Classes | Frequency | Views | Classification |
|---------|---------|-----------|-------|----------------|
| Flash message | `alert alert-success alert-dismissible fade show` | ~all POST redirects | base.html | **Canonical** | Only place success feedback appears |

### Recommended Consolidation

1. **Errors (inline):** `border border-danger rounded p-2 text-danger` with `bi-x-circle` icon
2. **Errors (field):** `invalid-feedback d-block`
3. **Warnings (simple):** `alert alert-warning`
4. **Warnings (structured):** `border border-warning rounded p-3 bg-warning bg-opacity-10`
5. **Info (prominent):** `alert alert-info`
6. **Info (subtle):** `border rounded p-2 text-secondary` with `bi-info-circle`
7. **Success:** Flash message at top of page (existing pattern)

---

## 10. Section Headers

**Total instances:** ~30
**Distinct variants:** 3

### Variant Table

| Pattern | Frequency | Views | Classification | Notes |
|---------|-----------|-------|----------------|-------|
| `bg-body-secondary rounded px-2 py-1 mb-2` with `h3.h5.mb-0` or `h2.h5.mb-0` | ~20 | list-detail (attributes, resources, actions), campaign-detail (6 sections), pack-detail, list-packs | **Canonical** | Grey header bar with section title |
| `h2.h5.mb-2` or `h2.h5.mb-3` (no background bar) | ~10 | campaign sub-pages (assets, resources, attributes, packs, add-lists) | **Acceptable Variant** | Sub-page section headings without bar |
| `caps-label mb-1` | ~5 | list-detail (sub-sections), campaign-detail (table headers), campaign sub-page table headers | **Canonical** | Small uppercase label for sub-sections |

### Canonical Definition

**Section header bar:**

```html
<div class="d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1">
  <h2 class="h5 mb-0">Section Title</h2>
  <!-- optional action links -->
</div>
```

**Sub-section label:**

```html
<div class="caps-label mb-1">Sub-section</div>
```

### Inconsistencies

- Section header `mb` values vary: `mb-2` vs `mb-3` depending on template
- Heading levels vary: `h2.h5` on detail pages, `h3.h5` on list-detail -- should standardize on `h2.h5`
- Section header is NOT extracted as a template include despite being repeated ~20 times

---

## 11. Empty States

**Total instances:** ~20
**Distinct variants:** 5

### Variant Table

| Pattern | Frequency | Views | Classification | Notes |
|---------|-----------|-------|----------------|-------|
| `text-muted fst-italic` "None" | ~5 | Fighter card cells (skills, rules, gear) | **Canonical** | Inline empty indicator in tables |
| `text-muted` / `text-secondary` "No X added yet." | ~8 | Lore/notes pages, campaign sections, pack sections | **Canonical** | Block-level empty state |
| `text-center text-muted mb-0` / `text-center text-secondary mb-0` | ~4 | list-packs, pack-detail, rules-edit | **Drift** | Centered variant; inconsistent with left-aligned norm |
| `alert alert-info` with icon | 1 | injuries-edit ("no injuries") | **Anti-pattern** | Convention says avoid alerts for empty states |
| Unstyled `<p>` or `<div>` | ~3 | Home empty states, lists-index empty state | **Drift** | No consistent styling applied |

### Canonical Definition

**Inline empty (in tables/cells):**

```html
<span class="text-muted fst-italic">None</span>
```

**Block-level empty state:**

```html
<p class="text-secondary mb-0">No items added yet.</p>
```

### Migration Targets

| Current | Target |
|---------|--------|
| `alert alert-info` (injuries) | `p.text-secondary.mb-0` or border rounded pattern |
| Unstyled `<p>` / `<div>` | `p.text-secondary.mb-0` |
| Centered empty states | Left-align to match canonical (or document as centered variant) |
| Mixed `text-muted` / `text-secondary` | Standardize on `text-secondary` |

---

## 12. Tooltips

**Total instances:** ~15
**Distinct variants:** 3

### Variant Table

| Data Attributes | Frequency | Views | Classification |
|----------------|-----------|-------|----------------|
| `data-bs-toggle="tooltip" data-bs-title="..."` | ~10 | campaign-detail, list-detail, pack-detail | **Canonical** |
| `data-bs-toggle="tooltip" title="..."` | ~3 | Various older templates | **Drift** |
| `.tooltipped` class (custom) | ~5 | Modified stat values, default weapons | **Canonical** | Info-coloured underline for tooltip triggers |

### Canonical Definition

```html
<span data-bs-toggle="tooltip" data-bs-title="Tooltip text">Content</span>
```

For linked tooltip triggers: use `.tooltipped` custom class.

---

## 13. Pagination

**Total instances:** 5
**Distinct variant:** 1

| Classes | Views | Classification |
|---------|-------|----------------|
| `pagination justify-content-center` with `page-item` / `page-link` | lists-index, campaigns-index, rules-edit, pack-activity, pack-lists | **Canonical** |

Via `core/includes/pagination.html` -- fully standardized.

---

## 14. Progress Bars

**Total instances:** 4
**Distinct variant:** 1

| Pattern | Views | Classification |
|---------|-------|----------------|
| Bootstrap progress bar via `advancement_progress.html` | advancement-dice-choice, advancement-type, advancement-select, advancement-other | **Canonical** |

---

## 15. List Groups

**Total instances:** ~8
**Distinct variants:** 3

| Pattern | Frequency | Views | Classification |
|---------|-----------|-------|----------------|
| `list-group list-group-flush` with `list-group-item px-0` | 4 | campaign-detail (battles, actions, invitations), xp-edit/advancements | **Canonical** |
| `list-group` with `list-group-item vstack gap-2` | 1 | list-detail (embed offcanvas) | **Acceptable Variant** |
| `list-unstyled mb-0` with `li.py-2` (custom list items) | 2 | list-packs, pack-detail | **Acceptable Variant** | Not a list-group but serves same purpose |

---

## 16. Missing Components (Raw HTML that should be components)

These patterns are implemented with raw HTML + utility classes across multiple templates and should be extracted into reusable template includes or documented as formal design system components.

### 16.1 Section Header Bar

**Current:** `div.d-flex.justify-content-between.align-items-center.mb-3.bg-body-secondary.rounded.px-2.py-1` repeated ~20 times inline.

**Recommendation:** Create `core/includes/section_header.html`:

```html
{% comment %}Usage: {% include "core/includes/section_header.html" with title="Section" %}{% endcomment %}
<div class="d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1">
  <h2 class="h5 mb-0">{{ title }}</h2>
  {% if action_block %}{{ action_block }}{% endif %}
</div>
```

### 16.2 Inline Error Box

**Current:** `div.border.border-danger.rounded.p-2.text-danger` repeated on 8+ pages with `<strong>Error:</strong>` prefix.

**Recommendation:** Create `core/includes/error_box.html`:

```html
<div class="border border-danger rounded p-2 text-danger">
  <i class="bi-x-circle me-1"></i>
  <strong>Error:</strong> {{ message }}
</div>
```

### 16.3 Warning Callout

**Current:** `div.border.border-warning.rounded.p-3.bg-warning.bg-opacity-10` on 5+ pages.

**Recommendation:** Create `core/includes/warning_callout.html`.

### 16.4 Info Note

**Current:** `div.border.rounded.p-2.text-secondary` with `bi-info-circle` icon on ~5 pages.

**Recommendation:** Create `core/includes/info_note.html`.

### 16.5 Empty State

**Current:** 5 different patterns across ~20 instances.

**Recommendation:** Create `core/includes/empty_state.html`:

```html
<p class="text-secondary mb-0">{{ message|default:"No items yet." }}</p>
```

### 16.6 Flash Message with Icons

**Current:** Flash messages in `base.html` render as `alert alert-{tag}` without icons, while inline callouts consistently use icons.

**Recommendation:** Add icons to flash messages:

- success: `bi-check-circle`
- error: `bi-x-circle`
- warning: `bi-exclamation-triangle`
- info: `bi-info-circle`

---

## 17. Shared Template Includes (Component Inventory)

Every `{% include %}` template that functions as a reusable UI component, listed by category.

### Layout & Navigation

| Include | Purpose | Used By (approx) |
|---------|---------|-------------------|
| `core/includes/back.html` | Breadcrumb back navigation | ~20 views |
| `core/includes/back_to_list.html` | Back-to-list specific variant | ~2 views |
| `core/includes/home.html` | Home breadcrumb | 3 views |
| `core/includes/cancel.html` | Cancel link for forms | ~3 views |
| `core/includes/pagination.html` | Paginated navigation | 5 views |
| `core/includes/site_banner.html` | Site-wide banner | base layout |

### Fighter Card System

| Include | Purpose | Used By (approx) |
|---------|---------|-------------------|
| `core/includes/fighter_card.html` | Fighter card wrapper (handles compact mode) | list, about, notes |
| `core/includes/fighter_card_content.html` | Fighter card full content (tabs, header, body) | fighter_card.html |
| `core/includes/fighter_card_content_inner.html` | Fighter card inner content (statline, details) | fighter_card_content.html |
| `core/includes/fighter_card_cost.html` | Cost badge display | fighter_card_content.html |
| `core/includes/fighter_card_gear.html` | Gear tab content / gear edit card | list, gear-edit |
| `core/includes/fighter_card_stash.html` | Stash card content | list |
| `core/includes/fighter_card_weapon_menu.html` | Weapon action links (edit, reassign, delete) | fighter_card_gear.html |
| `core/includes/fighter_card_gear_menu.html` | Gear action links | fighter_card_gear.html |
| `core/includes/fighter_card_gear_default_menu.html` | Default gear action links | fighter_card_gear.html |
| `core/includes/blank_fighter_card.html` | Empty fighter card for print | list-print |
| `core/includes/blank_vehicle_card.html` | Empty vehicle card for print | list-print |

### Fighter Data Components

| Include | Purpose | Used By (approx) |
|---------|---------|-------------------|
| `core/includes/list_fighter_statline.html` | Fighter stat value row | fighter_card_content_inner.html |
| `core/includes/list_fighter_weapons.html` | Weapons table for a fighter | fighter_card, weapons-edit |
| `core/includes/list_fighter_weapon_rows.html` | Individual weapon rows in table | list_fighter_weapons.html |
| `core/includes/list_fighter_weapon_profile_statline.html` | Weapon profile stat values | weapon rows |
| `core/includes/list_fighter_weapon_assign_name.html` | Weapon assignment name display | weapon rows |
| `core/includes/list_fighter_weapon_assign_upgrade_form.html` | Weapon upgrade radio/checkbox form | weapon rows |
| `core/includes/gear_assign_name.html` | Gear assignment name with tooltip | fighter_card_gear.html |
| `core/includes/parent_fighter_link.html` | Link to parent fighter | fighter_card_content.html |
| `core/includes/rule.html` | Rule display with tooltip | fighter_card_content_inner.html |
| `core/includes/fighter_switcher.html` | Fighter context switcher dropdown | list_common_header.html |
| `core/includes/weapon_stat_headers.html` | Weapon table column headers | pack-detail, weapon_profile_edit |

### List Components

| Include | Purpose | Used By (approx) |
|---------|---------|-------------------|
| `core/includes/list.html` | Full list content (fighter grid, sections) | list, list-print |
| `core/includes/list_common_header.html` | Gang header with stats bar | ~15 fighter/list views |
| `core/includes/list_about.html` | Lore tab content | list-about |
| `core/includes/list_notes.html` | Notes tab content | list-notes |
| `core/includes/list_attributes.html` | Gang attributes section | list |
| `core/includes/list_campaign_actions.html` | Campaign action log section | list |
| `core/includes/list_campaign_resources_assets.html` | Resources & assets section | list |

### Filter Components

| Include | Purpose | Used By (approx) |
|---------|---------|-------------------|
| `core/includes/lists_filter.html` | Lists search/filter form | lists-index, home, pack-lists |
| `core/includes/campaigns_filter.html` | Campaigns search/filter form | campaigns-index |
| `core/includes/packs_filter.html` | Packs search/filter form | packs-index |
| `core/includes/fighter_gear_filter.html` | Weapons/gear search with category/availability/cost dropdowns | weapons-edit, gear-edit |
| `core/includes/fighter_skills_filter.html` | Skills search with nav tabs | skills-edit |
| `core/includes/fighter_psyker_powers_filter.html` | Psyker powers search | psyker-powers-edit |

### Campaign Components

| Include | Purpose | Used By (approx) |
|---------|---------|-------------------|
| `core/campaign/includes/campaign_lists.html` | Campaign gangs table | campaign-detail, campaign-add-lists |
| `core/campaign/includes/list_row.html` | Individual gang row in campaign table | campaign_lists.html |
| `core/campaign/includes/resource_row.html` | Resource amount row | campaign-detail |
| `core/campaign/includes/status.html` | Campaign status badge | campaign-detail, campaigns-index |
| `core/includes/campaign_action_item.html` | Action log item | list, campaign-detail |
| `core/includes/campaign_captured_fighters.html` | Captured fighters section | campaign-detail |
| `core/includes/battle_summary_card.html` | Battle summary in list group | campaign-detail |

### Advancement Components

| Include | Purpose | Used By (approx) |
|---------|---------|-------------------|
| `core/includes/advancement_progress.html` | Wizard progress bar with back link | 4 advancement views |
| `core/includes/advancement_equipment_form.html` | Equipment selection form partial | advancement-select |
| `core/includes/advancement_skill_form.html` | Skill selection form partial | advancement-select |

### Form Components

| Include | Purpose | Used By (approx) |
|---------|---------|-------------------|
| `core/includes/form_field.html` | Standard form field rendering (label, input, help, errors) | campaign forms |
| `core/includes/refund_checkbox.html` | Refund option checkbox | equipment sell/delete |

### Pack Components

| Include | Purpose | Used By (approx) |
|---------|---------|-------------------|
| `core/includes/pack_activity_item.html` | Pack activity log item | pack-detail, pack-activity |
| `core/pack/includes/weapon_profiles_display.html` | Weapon profiles table | pack-detail |
| `core/pack/includes/fighter_default_equipment.html` | Default equipment display | pack item pages |
| `core/pack/includes/fighter_equipment_list.html` | Equipment list display | pack item pages |

---

## 18. Text Colour Inconsistency: `text-muted` vs `text-secondary`

**Total instances of `text-muted`:** High (~50+)
**Total instances of `text-secondary`:** Medium (~20+)

These two classes are used interchangeably for the same purpose (de-emphasized text). In Bootstrap 5.3+, `text-body-secondary` is the recommended replacement for both. The current codebase mixes them without clear rules.

| Context | Current Class | Recommendation |
|---------|--------------|----------------|
| Metadata (owner, timestamps) | `text-muted` | Standardize on `text-secondary` |
| Empty states | Mixed | Standardize on `text-secondary` |
| Help text | `form-text` (inherits muted) | Keep as-is |
| Section descriptions | Mixed | Standardize on `text-secondary` |

---

## 19. Page Title (h1) Inconsistency

| Pattern | Frequency | Views | Classification |
|---------|-----------|-------|----------------|
| `<h1 class="h3">` | ~15 | Most edit/sub-pages | **Canonical** |
| `<h1>` (no class) | ~5 | flatpage-about, pack-detail, packs-index | **Drift** |
| `<h1 class="mb-0">` | 2 | campaign-detail, pack-detail | **Drift** |
| `<h1 class="h3 mb-0">` | 2 | pack-activity | **Acceptable Variant** |
| `<h1 class="h3 mb-1">` | 2 | pack-lists, list-packs | **Acceptable Variant** |
| `<h1 class="mb-1">` | 3 | lists-index, campaigns-index, packs-index | **Drift** |
| `<h2>` used as page title | 3 | xp-edit, advancements, list-credits | **Anti-pattern** |
| No visible `<h1>` at all | 3 | list-about, list-notes, account-home | **Anti-pattern** |

### Canonical Definition

**Sub-pages / edit pages:** `<h1 class="h3">Page Title</h1>`
**Top-level entity pages:** `<h1 class="mb-0">Entity Name</h1>` (acceptable for campaign/pack detail)
**Index pages:** `<h1 class="mb-1">Page Title</h1>`

### Migration Targets

| Current | Target | Views |
|---------|--------|-------|
| `<h2>` as page title | `<h1 class="h3">` | xp-edit, advancements, list-credits |
| No `<h1>` | Add `<h1>` | list-about, list-notes, account-home |
| `<h1>` without `.h3` on sub-pages | Add `.h3` | flatpage-about, pack-detail, packs-index |

---

## 20. Column Width Patterns

No documented convention exists. These are the width patterns in use:

| Pattern | Purpose | Views |
|---------|---------|-------|
| `col-12 col-md-8 col-lg-6` | Form pages | fighter-edit, fighter-new, stats-edit, narrative-edit, notes-edit, campaign-edit, campaign-new, list-edit, list-new, pack-edit, xp-edit, login |
| `col-12 col-xl-6` | Content pages (narrow) | list-packs |
| `col-12 col-lg-8` | Content pages (medium) | injuries-edit, skills-edit |
| `col-12 col-xl-8` | Content pages (wide) | pack-detail, pack-activity, pack-lists |
| `col-lg-12` / `col-12` | Full-width data pages | weapons-edit, gear-edit, packs-index |
| `col-12 col-md-8 col-xl-6` | Flatpage content | flatpage-about |

### Recommended Convention

| Page Type | Width Pattern |
|-----------|--------------|
| Form pages | `col-12 col-md-8 col-lg-6` |
| Content sub-pages | `col-12 col-xl-8` |
| Data-dense pages | `col-12` (full width) |
| Narrow content | `col-12 col-xl-6` |

---

## 21. Custom CSS Classes Summary

| Class | Definition | Category | Usage |
|-------|-----------|----------|-------|
| `.linked` | `link-underline-opacity-25 link-underline-opacity-100-hover link-offset-1` | Link | General-purpose link style |
| `.link-sm` | Same as `.linked` + `fs-7` | Link | Small link variant |
| `.tooltipped` | `link-underline-opacity-50 link-underline-info link-underline-opacity-100-hover link-offset-1 text-decoration-underline` | Link | Tooltip trigger styling |
| `.caps-label` | `small text-uppercase text-muted fw-semibold` + `letter-spacing: 0.03em` | Typography | Sub-section labels |
| `.fs-7` | `font-size: base * 0.9` (0.7875rem) | Typography | Custom small font size |
| `.table-fixed` | `table-layout: fixed; width: 100%` | Table | Fixed-width stat tables |
| `.table-nowrap` | `overflow: hidden; text-overflow: ellipsis; white-space: nowrap` | Table | Truncation in fixed tables |
| `.table-group-divider` | `border-top: ... !important` | Table | Group border in borderless tables |
| `.auto-flow-dense` | `grid-auto-flow: row dense` | Layout | Dense grid packing |
| `.break-inside-avoid` | `break-inside: avoid` | Layout | Prevent page breaks in print |
| `.flash-warn` | Keyframe animation warning-bg-subtle to inherit (2s) | Feedback | Highlight newly changed items |
| `.mb-last-0` | `> :last-child { margin-bottom: 0 !important }` | Spacing | Remove trailing margin |
| `.errorlist` | `list-unstyled` + `color: danger` | Form | Django form error list |
| `.hero` | `height: 25vh; background-size: cover; background-position: center` | Layout | Home page hero banner |
| `.fighter-switcher-btn` | Transparent, borderless button | Component | Fighter dropdown trigger |
| `.fighter-switcher-menu` | `max-height: 20em; overflow-y: auto` | Component | Scrollable fighter menu |
| `.dropdown-menu-mw` | `min-width: 25em; width: 100%; max-width: 35em` | Component | Wide dropdown menus |
| `.color-radio-label` / `.color-radio-input` | Scale on hover/focus, ring on checked | Form | Colour picker radios |
| `.stickyboi` | `top: 1em` at md+ | Layout | Sticky sidebar positioning |
| `.stat-input-cell` | `width: 4rem` | Form | Pack fighter stat inputs |
| `.sq-{1-6}` | `height/width: {n}em` | Sizing | Square containers |
| `.size-em-{1-5}` | `width/height: {1,2,4,8,16}em` | Sizing | Responsive image sizing |
| `.w-em-{n}` | `width: {n}em` | Sizing | Table column widths |
| `.img-link-transform` | 3D hover effect | Image | Marketing image links |
| `.flatpage-content` | Content area styling, image overflow at xl | Content | Flatpage rendering |
| `.fs-{bp}-normal` | `font-size: base !important` at breakpoint | Typography | Responsive font size reset |
| `.border-{bp}-0` / `.rounded-{bp}-0` | Responsive border/radius removal | Layout | Responsive border control |

---

## Summary of Key Findings

### Highest Priority Fixes

1. **Badge class migration:** 15+ instances of `bg-*` badges should use `text-bg-*` pattern
2. **Error display standardization:** 8 pages use `alert alert-danger` where convention requires `border border-danger rounded p-2 text-danger`
3. **Empty state unification:** 5 different patterns need consolidation into 2 (inline + block)
4. **Missing h1 elements:** 3 pages have no `<h1>` at all; 3 use `<h2>` as page title
5. **Invalid button class:** `btn btn-outline` on dice page is not a valid Bootstrap class

### Components to Extract as Template Includes

1. Section header bar (~20 inline repetitions)
2. Inline error box (~8 repetitions)
3. Warning callout (~5 repetitions)
4. Info note (~5 repetitions)
5. Empty state (~20 repetitions)

### Cross-Cutting Consistency Issues

1. `text-muted` vs `text-secondary` -- used interchangeably (~70+ total instances)
2. Icon format `bi-name` vs `bi bi-name` -- should standardize on single class
3. `bi-plus` vs `bi-plus-lg` vs `bi-plus-circle` -- three add icons with no clear semantic rule
4. `bi-three-dots` vs `bi-three-dots-vertical` -- two more-options icons
5. Column width breakpoints have no documented convention
6. Form button group containers use 4 different patterns for the same concept
