# Components Specification

This specification defines every reusable UI component in the Gyrinx design system. Each component
is documented with enough detail to be implemented from the description alone.

Approved decisions applied throughout:

- Feedback uses `alert alert-icon` everywhere (dismissible or not), always with icon
- Cards are only for fighter grids and equipment categories; everything else uses `border rounded p-*`
- Badges use `text-bg-*` format (not `bg-*`)
- Small text uses `fs-7` (not `.small`)
- De-emphasised text uses `text-secondary` (not `text-muted`)

---

## 1. Alert / Feedback

### Alert

**Purpose:** Communicate feedback, warnings, errors, and informational messages to users.

**When to use:** For flash messages after form submissions, inline error/warning/info callouts,
and any message that needs to attract user attention. Use for both dismissible (flash) and
non-dismissible (inline) feedback.

**Canonical classes:** `alert alert-{variant} alert-icon`

**Variants:**

| Variant | Classes | Icon | Use Case |
|---------|---------|------|----------|
| Success | `alert alert-success alert-icon` | `bi-check-circle` | Flash message after successful action |
| Danger | `alert alert-danger alert-icon` | `bi-x-circle` | Error messages, validation failures |
| Warning | `alert alert-warning alert-icon` | `bi-exclamation-triangle` | Destructive action confirmations, cautionary notes |
| Info | `alert alert-info alert-icon` | `bi-info-circle` | Informational notes, tips, action log entries |
| Secondary | `alert alert-secondary alert-icon` | `bi-info-circle` | Debug messages, low-priority notices |

**Anatomy (non-dismissible):**

```html
<div class="alert alert-danger alert-icon" role="alert">
    <i class="bi-x-circle"></i>
    <div><strong>Error:</strong> Equipment cannot be assigned to this fighter.</div>
</div>
```

**Anatomy (dismissible, for flash messages):**

```html
<div class="alert alert-success alert-icon alert-dismissible fade show" role="alert">
    <i class="bi-check-circle"></i>
    <div>Fighter saved successfully.</div>
    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
</div>
```

**Anatomy (with heading, for structured warnings):**

```html
<div class="alert alert-warning alert-icon" role="alert">
    <i class="bi-exclamation-triangle"></i>
    <div>
        <h4 class="alert-heading">This action cannot be undone</h4>
        <p class="mb-0">Removing this Gang from the Campaign will delete all associated
        action log entries and resource assignments.</p>
    </div>
</div>
```

**Do / Don't:**

- DO always include an icon as the first child inside `alert-icon`
- DO wrap text content in a `<div>` so flexbox layout works correctly
- DO use `<strong>Error:</strong>` prefix for error alerts
- DO use `alert-heading` with an `<h4>` for multi-paragraph warnings
- DON'T use `border border-danger rounded p-2 text-danger` for errors -- use `alert alert-danger alert-icon` instead
- DON'T use alerts without the `alert-icon` class
- DON'T use alerts for empty states (use the Empty State component instead)
- DON'T mix icon styles: use `bi-exclamation-triangle` (outline) not `bi-exclamation-triangle-fill`

**Migration notes:**

- `border border-danger rounded p-2 text-danger` (8 pages) becomes `alert alert-danger alert-icon`
- `alert alert-danger` without icon (8 pages) adds `alert-icon` and `bi-x-circle`
- `alert alert-warning` without icon (~19 instances) adds `alert-icon` and `bi-exclamation-triangle`
- `alert alert-info` without icon (~11 instances) adds `alert-icon` and `bi-info-circle`
- `border border-warning rounded p-3 bg-warning bg-opacity-10` (5 pages) becomes `alert alert-warning alert-icon`
- `border border-warning rounded p-3 bg-warning-subtle` (2 pages) becomes `alert alert-warning alert-icon`
- `border rounded p-2 text-secondary` with info icon (~5 pages) becomes `alert alert-secondary alert-icon` or remains as a Container with icon for very subtle notes
- Flash messages in `base.html` and `allauth/layouts/base.html` gain `alert-icon` class and per-variant icons
- `text-danger small` inline field errors remain as-is (these are field-level, not alert-level); prefer `invalid-feedback d-block` for field errors

---

## 2. Button

**Purpose:** Trigger actions such as form submissions, navigation to action pages, and toggling UI state.

**When to use:** For any clickable action. Use `btn-sm` in toolbars and data views; use full-size in
standalone forms. Use `<button>` for actions, `<a>` for navigation.

**Canonical classes:** `btn btn-{variant}` (forms) or `btn btn-{variant} btn-sm` (toolbars/data views)

**Variants:**

| Variant | Classes (toolbar) | Classes (form) | Use Case |
|---------|-------------------|----------------|----------|
| Primary | `btn btn-primary btn-sm` | `btn btn-primary` | Main action: Save, Add, Create |
| Secondary | `btn btn-secondary btn-sm` | -- | Secondary toolbar action |
| Outline Primary | `btn btn-outline-primary btn-sm` | -- | Add/subscribe in data views |
| Outline Secondary | `btn btn-outline-secondary btn-sm` | -- | Edit action on content items |
| Danger | `btn btn-danger btn-sm` | -- | Destructive action: Delete, End |
| Outline Danger | `btn btn-outline-danger btn-sm` | -- | Destructive action (less prominent) |
| Cancel | -- | `btn btn-link` | Cancel link on form pages |
| Filter Update | `btn btn-link icon-link btn-sm` | -- | Apply filter |
| Filter Reset | `btn btn-link text-secondary icon-link btn-sm` | -- | Reset filter |

**Anatomy (form submit area):**

```html
<div class="mt-3">
    <button type="submit" class="btn btn-primary">Save</button>
    <a href="{{ cancel_url }}" class="btn btn-link">Cancel</a>
</div>
```

**Anatomy (toolbar action):**

```html
<a href="{% url 'core:fighter-edit' list.id fighter.id %}"
   class="btn btn-outline-secondary btn-sm">
    <i class="bi-pencil"></i> Edit
</a>
```

**Anatomy (icon button with Bootstrap icon-link):**

```html
<a href="{% url 'core:campaign-add-lists' campaign.id %}"
   class="icon-link link-primary linked fs-7">
    <i class="bi-plus-circle"></i> Add Gangs
</a>
```

**Do / Don't:**

- DO use `btn-sm` for all buttons in toolbars, data views, and header action bars
- DO use full-size `btn btn-primary` for form submit buttons
- DO use `btn btn-link` for cancel actions on forms (not `btn-outline-*`)
- DO pair destructive actions with a confirmation step or warning alert
- DON'T use `btn btn-outline` without a variant (e.g., `btn btn-outline` alone is invalid)
- DON'T use `btn-warning` or `btn-info` for actions (these are bespoke one-offs to remove)
- DON'T mix `btn-sm` and full-size in the same toolbar
- DON'T omit `btn-sm` on dropdown toggles in toolbars

**Migration notes:**

- `btn btn-outline` (dice page) becomes `btn btn-outline-secondary`
- `btn btn-outline-secondary dropdown-toggle` without `btn-sm` (flatpage-about, account-home) adds `btn-sm`
- `btn btn-info text-bg-info btn-sm` (list-detail invitations) becomes `btn btn-primary btn-sm` or `btn btn-outline-primary btn-sm`
- `btn btn-warning btn-sm` (home change-username) becomes `btn btn-secondary btn-sm`

---

## 3. Card

**Purpose:** Visually group a fighter or equipment category as a distinct, self-contained unit within a grid layout.

**When to use:** Only for fighter cards displayed in grids, and equipment/skill/rule category cards in
edit views. For all other grouped content, use the Container component (`border rounded p-*`).

**Canonical classes:** `card {grid_classes} break-inside-avoid`

**Variants:**

| Variant | Classes | Body Classes | Use Case |
|---------|---------|-------------|----------|
| Fighter card (screen) | `card g-col-12 g-col-md-6 g-col-xl-4 break-inside-avoid` | `card-body p-0 p-sm-2` | Interactive fighter display |
| Fighter card (print/compact) | `card g-col-12 g-col-sm-6 g-col-md-3 g-col-xl-2 break-inside-avoid` | `card-body p-0` | Print view, compact mode |
| Equipment category card | `card g-col-12 g-col-md-6` | `card-body vstack gap-2 p-0 p-sm-2` | Weapons/gear edit categories |

**Anatomy (fighter card):**

```html
<div class="card g-col-12 g-col-md-6 g-col-xl-4 break-inside-avoid"
     id="{{ fighter.id }}">
    <div class="card-header p-2 hstack align-items-start">
        <div class="vstack gap-1">
            <h3 class="h5 mb-0">{{ fighter.name }}</h3>
            <!-- fighter type, cost badge -->
        </div>
        <!-- action menu -->
    </div>
    <div class="card-body p-0 p-sm-2">
        <!-- statline, weapons, gear, tabs -->
    </div>
</div>
```

**Anatomy (equipment category card):**

```html
<div class="card g-col-12 g-col-md-6">
    <div class="card-header p-2">
        <h3 class="h5 mb-0">{{ category.name }}</h3>
    </div>
    <div class="card-body vstack gap-2 p-0 p-sm-2">
        <!-- equipment list table -->
    </div>
</div>
```

**Do / Don't:**

- DO use cards for fighters in grid layouts and equipment categories in edit views
- DO always include `break-inside-avoid` on fighter cards (prevents splitting across print pages)
- DO use `card-header p-2` (not default padding) for compact headers
- DO use `p-0 p-sm-2` for card bodies (zero padding on mobile, standard on larger screens)
- DON'T use cards for standalone content boxes (stats edit, user profile, injury display) -- use Container instead
- DON'T use `shadow-sm` on cards (advancement dice cards are the only instance; migrate to Container or document as wizard-specific)
- DON'T use `card-body` with default padding -- always specify `p-0` or `p-0 p-sm-2`

**Migration notes:**

- `card` + `card-body` only (stats-edit, injuries state, user-profile) becomes `border rounded p-3` Container
- `card h-100 shadow-sm` (advancement dice choice) becomes Container or stays as documented wizard exception
- `nav card card-body` (TOC sidebar in list-about, list-notes) becomes a dedicated navigation pattern or Container
- Inconsistent `pt-2` additions on card bodies (stash, gear) standardise to `p-0 p-sm-2`

---

## 4. Table

**Purpose:** Display structured data in rows and columns, such as fighter stats, equipment lists,
campaign resources, and action logs.

**When to use:** For any tabular data. Always use the compact, borderless style. Wrap in
`div.table-responsive` for horizontal scroll safety on narrow viewports.

**Canonical classes:** `table table-sm table-borderless mb-0`

**Variants:**

| Variant | Classes | Use Case |
|---------|---------|----------|
| Standard data table | `table table-sm table-borderless mb-0 align-middle` | Campaign assets, resources, actions, stash items |
| Fixed-layout stat table | `table table-sm table-borderless table-fixed mb-0` | Fighter statlines |
| Compact data table | `table table-sm table-borderless mb-0 fs-7` | Weapons tables, attribute values, resource values |
| Centered summary | `table table-sm table-borderless table-responsive text-center mb-0` | List header stats summary |

**Custom table utilities (from SCSS):**

| Class | Purpose |
|-------|---------|
| `table-group-divider` | Adds a top border to `<tbody>` to visually separate table sections, even in `table-borderless` |
| `table-fixed` | Sets `table-layout: fixed` with `width: 100%` for fixed column widths |
| `table-nowrap` | Used inside `table-fixed` -- truncates cell content with ellipsis |

**Anatomy:**

```html
<div class="table-responsive">
    <table class="table table-sm table-borderless mb-0 align-middle">
        <thead>
            <tr>
                <th class="caps-label">Name</th>
                <th class="caps-label">Value</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Item name</td>
                <td>42</td>
            </tr>
        </tbody>
    </table>
</div>
```

**Anatomy (with group divider):**

```html
<table class="table table-sm table-borderless mb-0">
    <tbody>
        <!-- first group -->
        <tr><td>Row 1</td></tr>
    </tbody>
    <tbody class="table-group-divider">
        <!-- second group, visually separated -->
        <tr><td>Row 2</td></tr>
    </tbody>
</table>
```

**Do / Don't:**

- DO always include `mb-0` to prevent trailing margin
- DO add `align-middle` when rows contain mixed content heights (badges, icons, text)
- DO use `caps-label` on `<th>` elements for header styling
- DO wrap tables in `div.table-responsive` unless the table is inside a card body that already handles overflow
- DON'T use tables with visible borders -- always include `table-borderless`
- DON'T omit `table-sm` -- the default table padding is too generous for the app's dense UI

**Migration notes:**

- `table table-sm mb-0` without `table-borderless` (captured fighters, campaign-add-lists) adds `table-borderless`
- `table table-borderless table-sm` (reversed class order, 2 instances) reorders to `table table-sm table-borderless`
- Tables missing `table-responsive` wrapper (injuries-edit, advancements) get wrapper added

---

## 5. Section Header Bar

**Purpose:** Introduce a major content section with an optional action link, providing visual hierarchy
and a touchpoint for related actions.

**When to use:** At the top of each major section on detail pages (campaigns, lists, packs) to label
the section and optionally provide a management link. Do not use on sub-pages or form pages -- use
plain `h2.h5` headings there.

**Canonical classes:** `d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1`

**Variants:**

| Variant | Classes | Use Case |
|---------|---------|----------|
| Standard | `d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1` | Section with optional action link |
| Title only | `bg-body-secondary rounded px-2 py-1 mb-3` | Section without action link |

**Anatomy (with action link):**

```html
<div class="d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1">
    <h2 class="h5 mb-0">Gangs</h2>
    <a href="{% url 'core:campaign-add-lists' campaign.id %}"
       class="icon-link link-primary linked fs-7">
        <i class="bi-plus-circle"></i> Add Gangs
    </a>
</div>
```

**Anatomy (with multiple action links):**

```html
<div class="d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1">
    <h2 class="h5 mb-0">Assets</h2>
    <div class="hstack gap-3">
        <a href="{% url 'core:campaign-assets' campaign.id %}"
           class="link-primary linked fs-7">Manage Assets</a>
    </div>
</div>
```

**Anatomy (title only):**

```html
<div class="bg-body-secondary rounded px-2 py-1 mb-3">
    <h2 class="h5 mb-0">Attributes</h2>
</div>
```

**Do / Don't:**

- DO use `h2.h5.mb-0` for the heading inside the bar (renders at h5 size regardless of semantic level)
- DO use `mb-3` for consistent spacing below the bar
- DO use `linked fs-7` on action links within the bar
- DO use `icon-link` with an appropriate icon for "Add" actions
- DON'T use different heading levels -- always `h2` styled as `h5`
- DON'T use `mb-2` or `mb-1` (standardise on `mb-3`)
- DON'T use `hstack gap-2 align-items-center` as an alternative layout -- use `d-flex justify-content-between`

**Migration notes:**

- This component appears ~20 times as inline HTML. Consider extracting to `core/includes/section_header.html` as a template include.
- `mb-2` variants (list_attributes.html, list_campaign_resources_assets.html) become `mb-3`
- `mb-1` variant (list_campaign_actions.html) becomes `mb-3`
- `h3.h5` (list-detail sub-sections) becomes `h2.h5` for consistency
- `hstack gap-2 align-items-center` variant (list_campaign_actions.html) becomes `d-flex justify-content-between align-items-center`

---

## 6. Caps Label

**Purpose:** Provide a small, uppercase label for sub-section headers, table column headers, and
metadata categories.

**When to use:** For labelling groups within a section (e.g., asset type names within the Assets
section, table column headers, fighter type categories). Not a replacement for Section Header Bar --
use Caps Label for sub-divisions within a section.

**Canonical classes:** `caps-label`

**Variants:** None -- single variant only.

**SCSS definition:**

```scss
.caps-label {
    @extend .small;
    @extend .text-uppercase;
    @extend .text-muted;       // to be migrated to text-secondary
    @extend .fw-semibold;
    letter-spacing: 0.03em;
}
```

**Rendered equivalent:** `small text-uppercase text-secondary fw-semibold` plus `letter-spacing: 0.03em`

**Anatomy:**

```html
<div class="caps-label mb-2">Weapons</div>
```

**Anatomy (as table header):**

```html
<th class="caps-label">Name</th>
```

**Do / Don't:**

- DO use `caps-label` for all sub-section labels (57 instances already use it consistently)
- DO add `mb-1` or `mb-2` spacing below when used as a standalone label
- DON'T manually spell out the constituent classes (`small text-uppercase text-secondary fw-semibold`) -- use `caps-label`
- DON'T use `caps-label` for major section headings -- use Section Header Bar instead

**Migration notes:**

- The SCSS currently `@extend`s `.text-muted`. Update to `@extend .text-secondary` to match the approved decision.
- 57 instances across 12 files already use this class. No template migration needed.

---

## 7. Badge

**Purpose:** Display short metadata values such as credits, XP, status indicators, and counts.

**When to use:** For compact, inline labels that communicate a value or status. Always use the
`text-bg-*` format for proper colour contrast in both light and dark modes.

**Canonical classes:** `badge text-bg-{variant}`

**Variants:**

| Variant | Classes | Use Case |
|---------|---------|----------|
| Primary | `badge text-bg-primary` | Credits, current XP, primary values |
| Secondary | `badge text-bg-secondary` | Total XP, cost display, neutral metadata |
| Success | `badge text-bg-success` | "In Progress" campaign status, positive states |
| Danger | `badge text-bg-danger` | "Dead" fighter state |
| Warning | `badge text-bg-warning` | "Injured" fighter state, XP cost |
| Info | `badge text-bg-info` | Invitation count |
| Light | `badge text-bg-light border` | Neutral tag with border (campaign attribute values) |

**Anatomy:**

```html
<span class="badge text-bg-primary">150&#162;</span>
```

**Anatomy (as a link):**

```html
<a href="{% url 'core:list-fighter-state-edit' list.id fighter.id %}"
   class="badge ms-2 text-decoration-none text-bg-warning">
    Injured
</a>
```

**Do / Don't:**

- DO use `text-bg-*` format (not `bg-*`) for all badges
- DO use `text-bg-light border` for neutral tags that need visual separation
- DO add `text-decoration-none` when using badges as links
- DON'T use `bg-primary`, `bg-secondary`, etc. without the `text-` prefix
- DON'T use `bg-warning text-dark` -- `text-bg-warning` handles text colour automatically

**Migration notes:**

- `badge bg-secondary` (4 instances) becomes `badge text-bg-secondary`
- `badge bg-success` (2 instances) becomes `badge text-bg-success`
- `badge bg-primary` (2 instances) becomes `badge text-bg-primary`
- `badge bg-warning` (2 instances) becomes `badge text-bg-warning`
- `badge bg-danger` (2 instances) becomes `badge text-bg-danger`
- `badge bg-info` (1 instance) becomes `badge text-bg-info`
- `badge bg-warning text-dark` (2 instances) becomes `badge text-bg-warning`

---

## 8. Nav Tabs

**Purpose:** Switch between related content panels or pages within the same context.

**When to use:** For switching between views of the same entity (e.g., "My Lists" / "Subscribed" tabs on
the lists page, "Lore" / "Notes" tabs on a fighter card, "About" / "Notes" tabs on a list page).

**Canonical classes:** `nav nav-tabs`

**Variants:**

| Variant | Classes | Use Case |
|---------|---------|----------|
| Page tabs | `nav nav-tabs mb-4` | Top-level page tab navigation |
| In-card tabs | `nav nav-tabs flex-grow-1 px-1` | Tabs within fighter cards |

**Anatomy (page tabs with links):**

```html
<ul class="nav nav-tabs mb-4">
    <li class="nav-item">
        <a href="{% url 'core:list-about' list.id %}"
           class="nav-link {% if active_tab == 'about' %}active{% endif %}">About</a>
    </li>
    <li class="nav-item">
        <a href="{% url 'core:list-notes' list.id %}"
           class="nav-link {% if active_tab == 'notes' %}active{% endif %}">Notes</a>
    </li>
</ul>
```

**Anatomy (in-card tabs with JavaScript):**

```html
<ul class="nav nav-tabs flex-grow-1 px-1" role="tablist">
    <li class="nav-item" role="presentation">
        <button class="nav-link active fs-7 px-2 py-1"
                data-bs-toggle="tab"
                data-bs-target="#stats-{{ fighter.id }}"
                type="button" role="tab">Stats</button>
    </li>
    <li class="nav-item" role="presentation">
        <button class="nav-link fs-7 px-2 py-1"
                data-bs-toggle="tab"
                data-bs-target="#gear-{{ fighter.id }}"
                type="button" role="tab">Gear</button>
    </li>
</ul>
```

**Do / Don't:**

- DO use `mb-4` on page-level tabs for spacing below
- DO use `fs-7 px-2 py-1` on tab buttons within cards for compact sizing
- DO use `role="tablist"` and `role="tab"` attributes for JS-driven tabs
- DO use standard `<a>` tags with `nav-link` for page-navigation tabs
- DON'T use nav-tabs for unrelated navigation -- use the back link or breadcrumbs instead

**Migration notes:**

- No major migration needed. Pattern is already consistent across the 7 instances.
- Ensure `mb-4` spacing is used consistently on page-level tabs (some use `mb-0`).

---

## 9. Dropdown / Action Menu

**Purpose:** Provide a set of actions behind a compact trigger, keeping the interface clean while
offering access to secondary or overflow actions.

**When to use:** For "more options" menus on cards, list rows, and page headers. Use the three-dots
icon trigger pattern for overflow menus.

**Canonical classes (trigger):** `btn btn-secondary btn-sm dropdown-toggle`

**Variants:**

| Variant | Trigger Classes | Icon | Use Case |
|---------|----------------|------|----------|
| Overflow menu | `btn btn-secondary btn-sm dropdown-toggle` | `bi-three-dots-vertical` | Fighter cards, list rows, pack headers |
| Filter dropdown | `btn btn-outline-primary btn-sm dropdown-toggle` | none (text label) | Filter controls on index pages |
| Inline row action | `btn btn-link btn-sm p-0 text-secondary` | `bi-three-dots-vertical` | Row-level actions in tables |

**Anatomy (overflow menu):**

```html
<div class="dropdown">
    <button type="button"
            class="btn btn-secondary btn-sm dropdown-toggle"
            data-bs-toggle="dropdown"
            aria-expanded="false"
            aria-label="More options">
        <i class="bi-three-dots-vertical"></i>
    </button>
    <ul class="dropdown-menu dropdown-menu-end">
        <li>
            <a href="{{ action_url }}" class="dropdown-item icon-link">
                <i class="bi-printer"></i> Print
            </a>
        </li>
        <li><hr class="dropdown-divider"></li>
        <li>
            <a href="{{ danger_url }}" class="dropdown-item icon-link text-danger">
                <i class="bi-archive"></i> Archive
            </a>
        </li>
    </ul>
</div>
```

**Anatomy (filter dropdown):**

```html
<div class="dropdown">
    <button type="button"
            class="btn btn-outline-primary btn-sm dropdown-toggle"
            data-bs-toggle="dropdown"
            aria-expanded="false">
        Filter by House
    </button>
    <div class="dropdown-menu shadow-sm p-2 fs-7 dropdown-menu-mw">
        <!-- filter checkboxes/form content -->
    </div>
</div>
```

**Dropdown item patterns:**

| Pattern | Classes | Use Case |
|---------|---------|----------|
| Standard item | `dropdown-item icon-link` | Action with icon |
| Destructive item | `dropdown-item icon-link text-danger` | Delete, archive, remove |
| Disabled item | `dropdown-item icon-link disabled` | Unavailable action |
| Divider | `dropdown-divider` (on `<hr>`) | Separates item groups |
| Header | `dropdown-header text-uppercase small` | Labels a group of items |

**Do / Don't:**

- DO use `bi-three-dots-vertical` for overflow menu triggers (not `bi-three-dots`)
- DO use `dropdown-menu-end` to align menus to the right edge of the trigger
- DO use `icon-link` on dropdown items for consistent icon + text alignment
- DO use `text-danger` on destructive dropdown items
- DO add `aria-label="More options"` on icon-only triggers
- DON'T omit `btn-sm` on dropdown triggers in toolbars
- DON'T use `dropdown-menu-mw` on overflow menus (only for filter dropdowns)

**Migration notes:**

- `bi-three-dots` (horizontal, 2 instances in campaign templates) becomes `bi-three-dots-vertical`
- `btn btn-outline-secondary dropdown-toggle` without `btn-sm` (2 instances) adds `btn-sm`

---

## 10. Back Link

**Purpose:** Provide breadcrumb-style back navigation to the parent page.

**When to use:** At the top of sub-pages, edit forms, and detail pages that have a clear parent context.
Use the shared template include for consistency.

**Canonical classes:** `breadcrumb` / `breadcrumb-item`

**Variants:** None -- single component with variable text and URL.

**Anatomy (via template include):**

```html
{% include "core/includes/back.html" with url=target_url text="Back to Campaign" %}
```

**Rendered output:**

```html
<nav aria-label="breadcrumb">
    <ol class="breadcrumb">
        <li class="breadcrumb-item active" aria-current="page">
            <i class="bi-chevron-left"></i>
            <a href="/campaign/abc123/">Back to Campaign</a>
        </li>
    </ol>
</nav>
```

**Parameters:**

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | No | Falls back to `return_url`, then `{% safe_referer "/" %}` | Target URL |
| `text` | No | `"Back"` | Link text |

**Do / Don't:**

- DO always provide `url` and `text` parameters for clarity
- DO use descriptive text like "Back to Campaign" rather than just "Back"
- DO use `{% safe_referer "/" %}` as the fallback (already built into the include)
- DON'T build back navigation manually -- always use the include
- DON'T use this for in-page navigation (use Nav Tabs instead)

**Migration notes:**

- Some views pass `return_url` instead of `url`. Both work but prefer `url` for new code.
- Some views omit `text`, falling back to "Back". Add descriptive text.

---

## 11. Icon Link

**Purpose:** Combine an icon with a text label for inline action links that are visually lighter
than buttons.

**When to use:** For secondary actions within section headers, alongside content, or in contexts
where a full button would be too heavy. Common for "Add", "Edit", "View" actions within
section header bars and content areas.

**Canonical classes:** `icon-link linked`

**Variants:**

| Variant | Classes | Use Case |
|---------|---------|----------|
| Standard | `icon-link linked` | Inline action link (Add, Edit) |
| Small | `icon-link linked fs-7` | Compact inline action in headers |
| With colour | `icon-link link-primary linked fs-7` | Action link with primary colour |
| Danger | `icon-link link-danger` | Destructive inline action (Remove) |
| In dropdown | `dropdown-item icon-link` | Action within a dropdown menu |

**Anatomy:**

```html
<a href="{% url 'core:campaign-add-lists' campaign.id %}"
   class="icon-link link-primary linked fs-7">
    <i class="bi-plus-circle"></i> Add Gangs
</a>
```

**Custom CSS reference:**

The `.linked` class is a shorthand defined in SCSS:

```scss
.linked {
    @extend .link-underline-opacity-25;
    @extend .link-underline-opacity-100-hover;
    @extend .link-offset-1;
}
```

**Do / Don't:**

- DO use `.linked` instead of spelling out `link-underline-opacity-25 link-underline-opacity-100-hover link-offset-1`
- DO place the icon `<i>` before the text inside the link
- DO use `fs-7` for compact icon links within section headers
- DON'T use `icon-link` without `.linked` for standalone action links (dropdown items are an exception since `.dropdown-item` provides its own styling)

**Migration notes:**

- Templates that spell out `link-underline-opacity-25 link-underline-opacity-100-hover` (homepage "Show all" links, campaign detail, error pages) should use `.linked` instead.
- `.link-sm` (4 instances) is equivalent to `.linked` + `.fs-7` and can be used as a shorthand.

---

## 12. Form Field

**Purpose:** Render a single form field with its label, input, help text, and error display in a
consistent layout.

**When to use:** For individual fields within forms. Use the shared template include for standard
fields. Use manual rendering only for fields that need custom layout (e.g., inline in tables).

**Canonical classes:** Standard Bootstrap form classes

**Variants:**

| Variant | Approach | Use Case |
|---------|----------|----------|
| Auto-rendered | `{{ form }}` within `form.vstack.gap-3` | Simple forms (edit, create) |
| Include-based | `{% include "core/includes/form_field.html" with field=form.name %}` | Custom form layout needing field-by-field control |
| Manual | Label + input + help text + errors inline | Complex layouts (stats, tables) |

**Anatomy (shared include):**

```html
{% include "core/includes/form_field.html" with field=form.name %}
```

**Rendered output of the include:**

```html
<div>
    <label for="id_name">Name</label>
    <input type="text" name="name" id="id_name" class="form-control">
    <small class="form-text text-secondary">Help text here.</small>
    <div class="invalid-feedback d-block">Error message here.</div>
</div>
```

**Anatomy (full form page):**

```html
<form class="vstack gap-3" method="post" action="{% url 'core:list-edit' list.id %}">
    {% csrf_token %}
    {{ form }}
    <div class="mt-3">
        <button type="submit" class="btn btn-primary">Save</button>
        <a href="{{ cancel_url }}" class="btn btn-link">Cancel</a>
    </div>
</form>
```

**Anatomy (field-level validation error, for manual rendering):**

```html
<div>
    {{ field.label_tag }}
    {{ field }}
    {% if field.help_text %}
        <small class="form-text text-secondary">{{ field.help_text }}</small>
    {% endif %}
    {% if field.errors %}
        <div class="invalid-feedback d-block">{{ field.errors }}</div>
    {% endif %}
</div>
```

**Do / Don't:**

- DO use `form.vstack.gap-3` as the form container class
- DO use `{{ form }}` for simple forms where field order matches model order
- DO use the `form_field.html` include when fields need individual placement
- DO use `invalid-feedback d-block` for field-level errors (Bootstrap's validation style, always visible)
- DO use `text-secondary` (not `text-muted`) for help text
- DON'T use `{{ form.as_div }}` -- use `{{ form }}` instead
- DON'T render `form.errors` (the entire dict) inside an alert -- show field errors inline
- DON'T use `text-danger small` for field errors -- use `invalid-feedback d-block`
- DON'T use `vstack gap-4` on forms -- standardise on `gap-3`

**Migration notes:**

- `{{ form.as_div }}` (list-credits-edit) becomes `{{ form }}`
- `text-danger small` field errors (campaign-copy pages, 12 instances) become `invalid-feedback d-block`
- `text-muted` in help text (form_field.html include) becomes `text-secondary`
- `form.vstack.gap-4` (3 instances in advancement wizard) becomes `form.vstack.gap-3`
- `alert alert-danger` rendering `form.errors` dict (list_attribute_edit.html) is removed; field errors render inline

---

## 13. Empty State

**Purpose:** Communicate that a section or list has no content yet, optionally with a call to action.

**When to use:** When a list, table, or content section has zero items. Use the block-level variant
for standalone sections and the inline variant for table cells.

**Canonical classes:** `text-secondary mb-0` (block) or `text-secondary fst-italic` (inline)

**Variants:**

| Variant | Classes | Use Case |
|---------|---------|----------|
| Block empty state | `text-secondary mb-0` (on `<p>`) | Section with no items (packs, notes, actions) |
| Inline empty (table cell) | `text-secondary fst-italic` (on `<span>`) | Cell with no value (skills, rules, gear) |
| Empty state with action | `text-secondary mb-0` + linked action | Section where user can add content |

**Anatomy (block):**

```html
<p class="text-secondary mb-0">No Gangs added to this Campaign yet.</p>
```

**Anatomy (inline, in table cell):**

```html
<span class="text-secondary fst-italic">None</span>
```

**Anatomy (with action link):**

```html
<p class="text-secondary mb-0">
    No notes added yet.
    <a href="{% url 'core:list-edit' list.id %}" class="linked">Add some</a>
</p>
```

**Naming convention for messages:**

- Use the pattern "No {items} {context} yet." -- e.g., "No Gangs added to this Campaign yet."
- Use sentence case. Capitalise proper nouns (Campaign, Gang, Fighter, Asset, Resource).
- Keep it concise. Do not explain what the items are.

**Do / Don't:**

- DO use `text-secondary` (not `text-muted`) for empty state text
- DO use `mb-0` on block-level empty states to prevent extra spacing
- DO use `fst-italic` on inline "None" indicators in table cells
- DO include an action link when the user can resolve the empty state
- DON'T use `alert alert-info` for empty states -- alerts are for messages, not absence of content
- DON'T use unstyled `<p>` or `<div>` for empty states
- DON'T centre-align empty states -- left-align to match the content flow

**Migration notes:**

- `text-muted` on empty states (mixed usage) becomes `text-secondary`
- `text-muted fst-italic` (fighter card cells) becomes `text-secondary fst-italic`
- `alert alert-info` empty state (injuries-edit "no injuries") becomes `p.text-secondary.mb-0`
- Unstyled `<p>` / `<div>` empty states (home, lists-index) gain `text-secondary mb-0`
- `text-center text-muted mb-0` (centred variants, 4 instances) becomes left-aligned `text-secondary mb-0`
- `text-center text-secondary mb-0` (pack-detail) becomes left-aligned `text-secondary mb-0`

---

## 14. Tooltip

**Purpose:** Provide additional context on hover/focus for abbreviated content, stat modifications,
or icon-only elements.

**When to use:** For supplementary information that would clutter the UI if always visible. Common
on stat values that differ from the base, weapon profile names, and icon-only buttons. Do not use
for essential information that users need to act on.

**Canonical classes:** Uses Bootstrap data attributes, not CSS classes.

**Variants:**

| Variant | Implementation | Use Case |
|---------|---------------|----------|
| Standard tooltip | `data-bs-toggle="tooltip" data-bs-title="..."` | Stat explanations, info icons |
| Tooltipped link | `.tooltipped` class on `<a>` or `<span>` | Modified stat values, default weapons (info-coloured underline) |

**Anatomy (standard):**

```html
<span data-bs-toggle="tooltip"
      data-bs-title="Movement: base 5, +1 from advancement">
    6"
</span>
```

**Anatomy (tooltipped link):**

```html
<span class="tooltipped"
      data-bs-toggle="tooltip"
      data-bs-title="Default equipment from fighter template">
    Autopistol
</span>
```

**Anatomy (info icon with tooltip):**

```html
<i class="bi-info-circle text-secondary fs-7"
   data-bs-toggle="tooltip"
   data-bs-title="Assets are physical items or locations that gangs fight to control."></i>
```

**Custom CSS reference:**

```scss
/* Global cursor rules */
[data-bs-toggle="tooltip"] { cursor: help; }
a[data-bs-toggle="tooltip"] { cursor: pointer; }

/* Tooltipped link style - info-coloured underline */
.tooltipped {
    @extend .link-underline-opacity-50;
    @extend .link-underline-info;
    @extend .link-underline-opacity-100-hover;
    @extend .link-offset-1;
    @extend .text-decoration-underline;
}
```

**Do / Don't:**

- DO use `data-bs-title` (not `title`) for tooltip content
- DO use `.tooltipped` class on elements that show modified/derived values
- DO keep tooltip text concise (one sentence or less)
- DON'T use tooltips for essential information -- if users need it to complete a task, show it inline
- DON'T use `title` attribute instead of `data-bs-title` (older pattern, inconsistent)
- DON'T put interactive content (links, buttons) inside tooltip text

**Migration notes:**

- `title="..."` tooltip attributes (3 older templates) become `data-bs-title="..."`
- No structural migration needed. The `.tooltipped` class and data attribute patterns are already consistent.

---

## 15. Container

**Purpose:** Group related content visually without the semantic weight of a Card. Provides a
lightweight bordered box for content sections, info panels, and grouped fields.

**When to use:** For any grouped content that is not a fighter card or equipment category card.
This is the default grouping component -- use it instead of `card` + `card-body` for standalone
content boxes.

**Canonical classes:** `border rounded p-3` (standard) or `border rounded p-2` (compact)

**Variants:**

| Variant | Classes | Use Case |
|---------|---------|----------|
| Standard | `border rounded p-3` | Grouped content, info panels, form sections |
| Compact | `border rounded p-2` | Inline notes, compact info boxes |
| With rich text | `border rounded p-3 mb-last-0` | Containers holding user-authored HTML (removes trailing `<p>` margin) |

**Anatomy (standard):**

```html
<div class="border rounded p-3">
    <h3 class="h5 mb-2">Section Title</h3>
    <p>Content goes here.</p>
</div>
```

**Anatomy (compact with icon):**

```html
<div class="border rounded p-2 text-secondary">
    <i class="bi-info-circle me-1"></i>
    This fighter's injuries will be cleared when their state changes.
</div>
```

**Anatomy (rich text container):**

```html
<div class="border rounded p-3 mb-last-0">
    {{ fighter.lore|safe }}
</div>
```

**Do / Don't:**

- DO use `border rounded p-3` as the default for grouped content
- DO use `border rounded p-2` for compact inline containers
- DO add `mb-last-0` when the container holds user-authored HTML (`|safe` content)
- DO use this instead of `card` + `card-body` for non-fighter, non-equipment content
- DON'T use `alert` classes for neutral containers -- alerts are for feedback messages
- DON'T add semantic border colours (e.g., `border-warning`, `border-danger`) to containers -- use the Alert component for coloured feedback
- DON'T use `card` for standalone content boxes (stats edit, user profile, injury display)

**Migration notes:**

- `card` + `card-body` only (stats-edit, injuries state display, user-profile, campaign action outcome, campaign resource modify, campaign asset transfer, campaign filter form) becomes `border rounded p-3`
- `card h-100 shadow-sm` (advancement dice choice) becomes `border rounded p-3` or stays as documented wizard exception
- `border border-warning rounded p-3 bg-warning bg-opacity-10` containers become Alert (warning variant) per the feedback consolidation
- `border border-danger rounded p-2 text-danger` containers become Alert (danger variant) per the feedback consolidation
