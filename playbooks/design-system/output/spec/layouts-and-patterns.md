# Layouts and Patterns

Specification for page layout and recurring UI patterns. All layouts are mobile-first and
server-rendered using Bootstrap 5 utility classes. No `xxl` breakpoint is used anywhere in the
application.

---

## 1. Layout -- Grid System

### Bootstrap Grid

The application uses Bootstrap 5's standard grid system (`container` > `row` > `col-*`) for all
page-level layouts. The outermost wrapper is a `.container` (max-width responsive, never
`.container-fluid`), defined in `base.html`:

```html
<div id="content" class="container my-3 my-md-5">
  {% block content %}{% endblock %}
</div>
```

Container max-widths follow Bootstrap defaults: 540px (sm), 720px (md), 960px (lg), 1140px (xl).

### CSS Grid

CSS Grid (Bootstrap's `$enable-cssgrid: true`) is reserved exclusively for **fighter card grids**
and **filter form layouts**. All other multi-column layouts use Bootstrap row/col.

CSS Grid uses `grid` as the container class and `g-col-*` for column sizing. The custom class
`.auto-flow-dense` (`grid-auto-flow: row dense`) enables dense packing for fighter cards.

### Breakpoints

| Token | Width | Primary role |
|-------|------:|-------------|
| (none/xs) | 0 | Mobile baseline -- full-width columns, stacked layouts |
| `sm` | 576px | Fighter card grid columns (2-up), minor spacing adjustments |
| `md` | 768px | Form pages narrow to 67%, fighter cards 2-up, navbar remains collapsed |
| `lg` | 992px | Form pages narrow to 50%, navbar expands, sidebar layouts activate |
| `xl` | 1200px | Detail pages constrain width, fighter cards 3-up |
| `xxl` | 1400px | **Not used** -- do not introduce |

### Layout method summary

| Method | Usage | When to use |
|--------|-------|-------------|
| `vstack` | Primary vertical stacking (302 instances) | Page sections, form fields, card content |
| `row` / `col-*` | Page-level column layouts (165 instances) | Page shells, sidebar layouts, footer |
| `d-flex` / `hstack` | Inline horizontal layouts (310 instances) | Headers, button rows, metadata lines |
| `grid` / `g-col-*` | Fighter card grids only (23 instances) | Fighter card grids, filter form grids |

---

## 2. Layout -- Page Shells

Four standard page shells. Every page extends `core/layouts/base.html`, which provides the
navbar, flash messages, and the `container my-3 my-md-5` content wrapper. Templates place their
content inside `{% block content %}`.

### Shell reference

| Shell | Classes | Gap | Used for |
|-------|---------|-----|----------|
| **form-page** | `col-12 col-md-8 col-lg-6 px-0 vstack gap-3` | `gap-3` (1rem) | Edit forms, confirmations, settings, action pages |
| **list-page** | `col-lg-12 px-0 vstack gap-4` | `gap-4` (1.5rem) | Index/listing pages, search results, browsing |
| **detail-page** | `col-12 col-xl-8 px-0 vstack gap-5` | `gap-5` (3rem) | Detail pages with multiple content sections |
| **sidebar-page** | `px-0` + `row g-4` + `col-lg-8` / `col-lg-4` | `g-4` (1.5rem gutter) | Pages with main content and a sidebar |

---

### 2.1 form-page

**Purpose:** Any form, edit, confirmation, or action page. The narrowest shell, constraining
content to roughly half-width on desktop for comfortable form readability.

**Classes:** `col-12 col-md-8 col-lg-6 px-0 vstack gap-3`

**Width progression:** 100% -> 67% at md -> 50% at lg

**Views using this shell:** fighter-edit, fighter-new, list-edit, list-new, campaign-edit,
campaign-new, pack-edit, pack-new, fighter-archive, fighter-delete, list-archive, and ~70 more
confirmation and edit pages.

**DOM structure:**

```html
{% extends "core/layouts/base.html" %}
{% block content %}
  {% include "core/includes/back.html" with url=return_url text="Back text" %}
  <div class="col-12 col-md-8 col-lg-6 px-0 vstack gap-3">
    <h1 class="h3">Page Title</h1>
    <form method="post" action="..." class="vstack gap-3">
      {% csrf_token %}
      {{ form }}
      <div class="mt-3">
        <button type="submit" class="btn btn-primary">Save</button>
        <a href="..." class="btn btn-link">Cancel</a>
      </div>
    </form>
  </div>
{% endblock %}
```

**Rules:**

- Always include `px-0` to reset column padding
- Back link goes _outside_ the column wrapper, directly inside `{% block content %}`
- Page title uses `<h1 class="h3">` (visually sized as h3)
- Form container uses `form.vstack.gap-3` for consistent 1rem field spacing
- Submit button row uses `div.mt-3`
- Submit button: `btn btn-primary` (full size, no `btn-sm`)
- Cancel link: `btn btn-link`

---

### 2.2 list-page

**Purpose:** Index pages, listing pages, search results, and browsing views. Full-width to
accommodate tables, filter bars, and list items.

**Classes:** `col-lg-12 px-0 vstack gap-4`

**Width:** 100% at all breakpoints (constrained only by the `.container` max-width).

**Views using this shell:** lists-index, campaigns-index, packs-index, dice, archived-fighters.

**Layout template:** `core/layouts/page.html` provides this shell as a reusable base. New listing
pages should extend `page.html` rather than reimplementing the wrapper.

**DOM structure:**

```html
{% extends "core/layouts/page.html" %}
{% block page_title %}Lists & Gangs{% endblock %}
{% block page_description %}Browse and manage your Lists.{% endblock %}
{% block page_content %}
  <!-- filter bar -->
  <div class="grid">
    {% include "core/includes/lists_filter.html" %}
  </div>
  <!-- tab navigation (optional) -->
  <ul class="nav nav-tabs">
    <li class="nav-item"><a class="nav-link active">All</a></li>
    ...
  </ul>
  <!-- list items -->
  <div class="vstack gap-4">
    {% for item in items %}
      <!-- item row -->
    {% empty %}
      <p class="text-secondary mb-0">No items available.</p>
    {% endfor %}
    {% include "core/includes/pagination.html" %}
  </div>
{% endblock %}
```

**If not using page.html**, the equivalent manual structure is:

```html
{% extends "core/layouts/base.html" %}
{% block content %}
  <div class="col-lg-12 px-0 vstack gap-4">
    <div>
      <h1 class="mb-1">Page Title</h1>
      <p class="fs-5 col-12 col-md-6 mb-0">Description text.</p>
    </div>
    <!-- content sections -->
  </div>
{% endblock %}
```

**Rules:**

- Page title uses `<h1 class="mb-1">` (full size, with small bottom margin for subtitle)
- Subtitle uses `<p class="fs-5 col-12 col-md-6 mb-0">` to constrain width
- Filter/search bars sit between the header and the list content
- Tab navigation (if present) uses `ul.nav.nav-tabs`
- List items are wrapped in `div.vstack.gap-4` for consistent vertical rhythm
- Pagination uses `{% include "core/includes/pagination.html" %}`

---

### 2.3 detail-page

**Purpose:** Detail/show pages with multiple distinct content sections. Constrained width with
generous section spacing.

**Classes:** `col-12 col-xl-8 px-0 vstack gap-5`

**Width progression:** 100% -> 67% at xl

**Views using this shell:** pack-detail, campaign-actions, campaign-resources, campaign-packs.

**DOM structure:**

```html
{% extends "core/layouts/base.html" %}
{% block content %}
  {% include "core/includes/back.html" with url=return_url text="Back text" %}
  <div class="col-12 col-xl-8 px-0 vstack gap-5">
    <!-- Header -->
    <div class="vstack gap-0">
      <div class="d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2 mb-2">
        <h1 class="mb-0">Entity Name</h1>
        <nav class="nav btn-group flex-nowrap ms-md-auto">
          <a href="..." class="btn btn-primary btn-sm"><i class="bi-pencil"></i> Edit</a>
          <!-- more action buttons -->
        </nav>
      </div>
      <div class="d-flex flex-wrap gap-2 text-muted small">
        <!-- metadata: owner, visibility, timestamps -->
      </div>
    </div>

    <!-- Section 1 -->
    <section>
      <div class="d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1">
        <h2 class="h5 mb-0">Section Title</h2>
        <a href="..." class="link-primary small">Manage &#8594;</a>
      </div>
      <!-- section content -->
    </section>

    <!-- Section 2 -->
    <section>
      <!-- ... -->
    </section>
  </div>
{% endblock %}
```

**Rules:**

- Page title uses `<h1 class="mb-0">` (full size, no bottom margin -- the parent vstack provides gap)
- Action buttons use `btn btn-{variant} btn-sm` (small buttons in toolbars)
- Header row uses `d-flex flex-column flex-md-row` to stack on mobile, row on desktop
- Action buttons right-align on desktop via `ms-md-auto`
- Each content section is wrapped in `<section>` with a section header bar
- `gap-5` (3rem) provides visual separation between major sections

---

### 2.4 sidebar-page

**Purpose:** Pages with a main content area and a sidebar (navigation, summary, or context).

**Classes:** `px-0` on the outer wrapper, then `row g-4` with `col-lg-8` (main) + `col-lg-4`
(sidebar).

**Views using this shell:** campaign-detail, home (logged in), user-profile.

**DOM structure:**

```html
{% extends "core/layouts/base.html" %}
{% block content %}
  {% include "core/includes/back.html" with url=return_url text="Back text" %}
  <div class="col-lg-12 px-0 vstack gap-5">
    <!-- Page header (full width, above sidebar split) -->
    <div class="vstack gap-0">
      <h1 class="mb-0">Page Title</h1>
      <!-- metadata -->
    </div>

    <!-- Sidebar split -->
    <div class="row g-4">
      <div class="col-lg-8">
        <!-- Main content -->
      </div>
      <div class="col-lg-4">
        <!-- Sidebar content -->
      </div>
    </div>
  </div>
{% endblock %}
```

**Rules:**

- The page header sits _above_ the `row` so it spans full width
- The sidebar split activates at `lg` (992px) -- below that, both columns stack vertically
- Gutter is `g-4` (1.5rem) for all sidebar pages
- Main content is always `col-lg-8`, sidebar is `col-lg-4`
- Sidebar position (left or right in the DOM) depends on content: main content first is the
  default; reverse for profile-style pages where sidebar contains the avatar/summary

---

## 3. Layout -- Responsive Behaviour

### Mobile-first approach

All layouts start at full width (`col-12`) and progressively constrain at larger breakpoints.
The key layout transitions are:

| Breakpoint | What changes |
|------------|-------------|
| **xs** (< 576px) | Everything full-width. Forms, details, lists all span 100%. Fighter cards stack 1-up. Navbar is collapsed. Action buttons stack vertically. |
| **sm** (576px) | Fighter cards in compact/print mode go 2-up (`g-col-sm-6`). Minor padding adjustments (`p-sm-2` on card bodies). |
| **md** (768px) | Form pages narrow to 67% (`col-md-8`). Fighter cards go 2-up in normal mode (`g-col-md-6`). Header rows switch from stacked to horizontal (`flex-md-row`). Content container top margin increases (`my-md-5`). |
| **lg** (992px) | Form pages narrow to 50% (`col-lg-6`). Navbar expands (`navbar-expand-lg`). Sidebar layouts activate (`col-lg-8` + `col-lg-4`). List-page uses full width (`col-lg-12`). |
| **xl** (1200px) | Detail pages narrow to 67% (`col-xl-8`). Fighter cards go 3-up (`g-col-xl-4`). Compact fighter cards go 6-up (`g-col-xl-2`). |

### Fighter card grid responsiveness

Fighter cards use CSS Grid with two distinct responsive patterns:

**Normal view (interactive):**

```html
<div class="grid auto-flow-dense">
  <div class="card g-col-12 g-col-md-6 g-col-xl-4 break-inside-avoid">
    ...
  </div>
</div>
```

| Breakpoint | Columns | Card width |
|------------|--------:|-----------|
| xs | 1 | 100% |
| md | 2 | 50% |
| xl | 3 | 33% |

**Compact view (print, stash):**

```html
<div class="card g-col-12 g-col-sm-6 g-col-md-3 g-col-xl-2 break-inside-avoid">
```

| Breakpoint | Columns | Card width |
|------------|--------:|-----------|
| xs | 1 | 100% |
| sm | 2 | 50% |
| md | 4 | 25% |
| xl | 6 | ~17% |

### Content container spacing

The content container uses responsive vertical margin:

```html
<div id="content" class="container my-3 my-md-5">
```

- Mobile: `my-3` (1rem top and bottom)
- Desktop (md+): `my-md-5` (3rem top and bottom)

---

## 4. Patterns -- Data Display

### 4.1 Fighter card grid

The central data display pattern. Fighter cards live in a CSS Grid container with dense
auto-flow. Each card is a Bootstrap card with a compact header and body.

```html
<div class="grid auto-flow-dense">
  <!-- Repeat for each fighter -->
  <div class="card g-col-12 g-col-md-6 g-col-xl-4 break-inside-avoid" id="{{ fighter.id }}">
    <div class="card-header p-2 hstack align-items-start">
      <div class="vstack gap-1">
        <div class="hstack align-items-start">
          <h3 class="h5 mb-0">{{ fighter.name }}</h3>
          <!-- status badges -->
        </div>
        <!-- fighter type, cost -->
      </div>
    </div>
    <div class="card-body p-0 p-sm-2">
      <!-- statline table, weapons, gear, skills tabs -->
    </div>
  </div>
</div>
```

**Rules:**

- Container: `div.grid.auto-flow-dense`
- Card classes: `card {g-col classes} break-inside-avoid`
- Card header: `card-header p-2 hstack align-items-start`
- Card body: `card-body p-0 p-sm-2` (no padding on mobile, 0.5rem on sm+)
- Cards are the **only** context where `card` is used -- other bordered containers use
  `border rounded p-2` or `border rounded p-3`

### 4.2 Stats table

Fighter statlines use a fixed-layout table for consistent column widths.

```html
<div class="table-responsive">
  <table class="table table-sm table-borderless table-fixed mb-0">
    <thead>
      <tr>
        <th>M</th><th>WS</th><th>BS</th><!-- ... -->
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>5"</td><td>3+</td><td>4+</td><!-- ... -->
      </tr>
    </tbody>
  </table>
</div>
```

**Classes:** `table table-sm table-borderless table-fixed mb-0`

### 4.3 Weapon stats table

Weapon profiles use a compact data table with `fs-7` for smaller text.

```html
<div class="table-responsive">
  <table class="table table-sm table-borderless mb-0 fs-7">
    <thead>
      <tr>
        <th>Weapon</th><th>Rng S</th><th>Rng L</th><th>Acc S</th><!-- ... -->
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Autogun</td><td>8"</td><td>24"</td><td>+1</td><!-- ... -->
      </tr>
    </tbody>
  </table>
</div>
```

**Classes:** `table table-sm table-borderless mb-0 fs-7`

All tables should be wrapped in `div.table-responsive` for horizontal scroll on narrow
viewports.

### 4.4 Standard data table

General-purpose data tables (campaign gangs, assets, resources).

**Classes:** `table table-sm table-borderless mb-0 align-middle`

### 4.5 Key/value metadata display

Campaign detail pages use a flex-wrap layout with `caps-label` headers for key/value pairs.

```html
<div class="d-flex flex-wrap gap-3 border-bottom pb-3 mb-2">
  <div class="flex-grow-1 col-md-3 flex-md-grow-0">
    <div class="caps-label">Status</div>
    <div>In Progress</div>
  </div>
  <div class="flex-grow-1 col-md-3 flex-md-grow-0">
    <div class="caps-label">Budget</div>
    <div>1000c</div>
  </div>
</div>
```

**Rules:**

- Each key/value pair is a `div.flex-grow-1.col-md-3.flex-md-grow-0`
- Label uses the `.caps-label` class (small, uppercase, muted, semibold, letter-spaced)
- The container uses `d-flex flex-wrap gap-3` for wrapping on narrow viewports
- Optional `border-bottom pb-3 mb-2` to separate from the next section

---

## 5. Patterns -- Forms

### 5.1 Standard form layout

The canonical form pattern used by ~84 pages. Forms sit inside the **form-page** shell.

```html
<div class="col-12 col-md-8 col-lg-6 px-0 vstack gap-3">
  <h1 class="h3">Edit Fighter</h1>
  <form method="post" action="..." class="vstack gap-3">
    {% csrf_token %}
    {{ form }}
    <div class="mt-3">
      <button type="submit" class="btn btn-primary">Save</button>
      <a href="..." class="btn btn-link">Cancel</a>
    </div>
  </form>
</div>
```

**Rules:**

- Form element: `form.vstack.gap-3`
- Use `{{ form }}` for Django's default rendering wherever possible
- For manual field rendering, wrap each field in a `<div>`:

```html
<div>
  {{ form.name.label_tag }}
  {{ form.name }}
  {% if form.name.help_text %}<div class="form-text">{{ form.name.help_text }}</div>{% endif %}
  {% for error in form.name.errors %}<div class="invalid-feedback d-block">{{ error }}</div>{% endfor %}
</div>
```

- Submit button row: `div.mt-3` containing the submit button and cancel link
- Submit: `btn btn-primary` (full size)
- Cancel: `btn btn-link`
- For destructive actions, submit uses `btn btn-danger`

### 5.2 Form with context card

Some forms display a context card alongside the form (e.g., attribute editing). These use a
sidebar-like row layout within the form-page shell.

```html
<div class="row g-3 mb-3">
  <div class="col-lg-8">
    <div class="card">
      <div class="card-body">
        <h2 class="h5">Attribute Name</h2>
        <form method="post">
          {% csrf_token %}
          <div class="mb-3">{{ form.values }}</div>
          <div class="hstack gap-2">
            <button type="submit" class="btn btn-primary btn-sm">
              <i class="bi-check-lg"></i> Save
            </button>
            <a href="..." class="btn btn-link">Cancel</a>
          </div>
        </form>
      </div>
    </div>
  </div>
</div>
```

**Note:** This is the only context where a `card` may be used outside of fighter grids for a
form container. Prefer the standard form layout unless the form requires additional visual
context.

### 5.3 Search/filter forms

Search and filter forms appear on list-page shells. They use a combination of input groups,
dropdown filters, and toggle switches.

```html
<form method="get" action="..." class="grid g-col-12">
  <!-- Search row -->
  <div class="g-col-12 g-col-xl-6">
    <div class="hstack gap-2 align-items-end">
      <div class="input-group">
        <span class="input-group-text"><i class="bi-search"></i></span>
        <input class="form-control" type="search" name="q" placeholder="Search lists">
        <button class="btn btn-primary" type="submit">Search</button>
      </div>
    </div>
  </div>
  <!-- Filter controls row -->
  <div class="g-col-12 align-items-baseline hstack gap-3 flex-wrap">
    <!-- Dropdown filter -->
    <div class="btn-group">
      <button type="button"
              class="btn btn-outline-primary btn-sm dropdown-toggle"
              data-bs-toggle="dropdown"
              data-bs-auto-close="outside">Filter Label</button>
      <div class="dropdown-menu shadow-sm p-2 fs-7 dropdown-menu-mw">
        <!-- checkbox items -->
        <div class="btn-group align-items-center">
          <button class="btn btn-link icon-link btn-sm" type="submit">
            <i class="bi-arrow-clockwise"></i> Update
          </button>
          &bull;
          <a class="btn btn-link text-secondary icon-link btn-sm" href="...">Reset</a>
        </div>
      </div>
    </div>
    <!-- Toggle switches -->
    <div class="form-check form-switch mb-0">
      <input class="form-check-input" type="checkbox" role="switch" name="..." value="1">
      <label class="form-check-label fs-7 mb-0">Toggle Label</label>
    </div>
    <!-- Update/Reset for outer form -->
    <div class="btn-group align-items-center">
      <button class="btn btn-link icon-link btn-sm" type="submit">
        <i class="bi-arrow-clockwise"></i> Update
      </button>
      &bull;
      <a class="btn btn-link text-secondary icon-link btn-sm" href="...">Reset</a>
    </div>
  </div>
</form>
```

**Rules:**

- Filter forms use `method="get"` (not POST)
- Filter dropdown trigger: `btn btn-outline-primary btn-sm dropdown-toggle`
- Filter dropdown menu: `dropdown-menu shadow-sm p-2 fs-7 dropdown-menu-mw`
- Toggle switches use `form-check form-switch mb-0` with `form-check-label fs-7 mb-0`
- Update button: `btn btn-link icon-link btn-sm` with `bi-arrow-clockwise`
- Reset link: `btn btn-link text-secondary icon-link btn-sm`

### 5.4 Form submit button placement

| Context | Pattern |
|---------|---------|
| Standard form page | `div.mt-3` containing `btn btn-primary` + `btn btn-link` |
| Destructive confirmation | `div.mt-3` containing `btn btn-danger` + cancel link |
| Inline form in data view | `btn btn-primary btn-sm` or `btn btn-outline-primary btn-sm` |
| Filter form | `btn btn-link icon-link btn-sm` (Update) + `a.btn.btn-link.text-secondary.icon-link.btn-sm` (Reset) |

---

## 6. Patterns -- Navigation

### 6.1 Page header pattern

The standard page structure follows: **back link -> page title -> action buttons**.

**Form pages (narrow):**

```html
{% include "core/includes/back.html" with url=return_url text="Back to list" %}
<div class="col-12 col-md-8 col-lg-6 px-0 vstack gap-3">
  <h1 class="h3">Page Title</h1>
  <!-- content -->
</div>
```

**Detail pages (wide):**

```html
{% include "core/includes/back.html" with url=return_url text="All Campaigns" %}
<div class="col-12 col-xl-8 px-0 vstack gap-5">
  <div class="vstack gap-0">
    <div class="d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2 mb-2">
      <h1 class="mb-0">Entity Name</h1>
      <nav class="nav btn-group flex-nowrap ms-md-auto">
        <a href="..." class="btn btn-primary btn-sm"><i class="bi-pencil"></i> Edit</a>
        <!-- overflow dropdown -->
      </nav>
    </div>
  </div>
</div>
```

**Rules:**

- Back link always comes first, outside the column wrapper
- Back link uses `{% include "core/includes/back.html" with url=... text="..." %}`
- On form pages: `<h1 class="h3">` (downsized heading)
- On detail/index pages: `<h1 class="mb-0">` or `<h1 class="mb-1">` (full-size heading)
- Action buttons right-align on desktop via `ms-md-auto` on the nav container
- Action buttons in toolbars always use `btn-sm`

### 6.2 Back link

The canonical back navigation component. Renders as a breadcrumb with a chevron-left icon.

```html
{% include "core/includes/back.html" with url=target_url text="Back to list" %}
```

Renders:

```html
<nav aria-label="breadcrumb">
  <ol class="breadcrumb">
    <li class="breadcrumb-item active" aria-current="page">
      <i class="bi-chevron-left"></i>
      <a href="...">Back to list</a>
    </li>
  </ol>
</nav>
```

### 6.3 Section header bar with action links

Used on detail pages to introduce content sections. Repeated ~20 times across templates.

```html
<div class="d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1">
  <h2 class="h5 mb-0">Section Title</h2>
  <div class="hstack gap-3">
    <a href="..." class="link-primary link-underline-opacity-25 link-underline-opacity-100-hover small">
      Manage &#8594;
    </a>
    <a href="..." class="icon-link link-primary link-underline-opacity-25 link-underline-opacity-100-hover small">
      <i class="bi-plus-circle"></i> Add Items
    </a>
  </div>
</div>
```

**Rules:**

- Container: `d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1`
- Heading: `h2.h5.mb-0` (always `h2` semantic level, visually sized as h5, no bottom margin)
- Action links use `small` size with link utility classes
- Bottom margin is `mb-3` (standardised)

### 6.4 Sub-section label

For sub-sections within a detail page section.

```html
<div class="caps-label mb-1">Sub-section Name</div>
```

The `.caps-label` class applies: `small text-uppercase text-muted fw-semibold` with
`letter-spacing: 0.03em`.

### 6.5 Page tabs

Tab navigation between related pages (e.g., Lists/Campaign Gangs tabs, Lore/Notes tabs).

```html
<ul class="nav nav-tabs mb-4">
  <li class="nav-item">
    <a href="..." class="nav-link active" aria-current="page">Tab One</a>
  </li>
  <li class="nav-item">
    <a href="..." class="nav-link">Tab Two</a>
  </li>
</ul>
```

**Rules:**

- Container: `ul.nav.nav-tabs.mb-4`
- Active tab: `nav-link active` with `aria-current="page"`
- Tabs link to separate URLs (server-rendered, not JavaScript-toggled)

### 6.6 Fighter switcher

A dropdown that allows switching between fighters on fighter sub-pages (edit, weapons, skills,
etc.). Styled as a title with a dropdown indicator.

```html
<div class="dropdown">
  <button class="fighter-switcher-btn h1 h3 dropdown-toggle" data-bs-toggle="dropdown">
    {{ fighter.name }}
  </button>
  <div class="dropdown-menu fighter-switcher-menu dropdown-menu-mw">
    <!-- fighter links -->
  </div>
</div>
```

**Custom classes:**

- `.fighter-switcher-btn`: transparent, borderless button with `padding: 0.25em 0.5em`
- `.fighter-switcher-menu`: `max-height: 20em; overflow-y: auto` for scrollable list

### 6.7 Toolbar button group

Action buttons in page headers use a `nav` with button-group styling.

```html
<nav class="nav btn-group flex-nowrap ms-md-auto">
  <a href="..." class="btn btn-primary btn-sm"><i class="bi-pencil"></i> Edit</a>
  <a href="..." class="btn btn-success btn-sm"><i class="bi-play-circle"></i> Start</a>
  <div class="btn-group" role="group">
    <button type="button"
            class="btn btn-secondary btn-sm dropdown-toggle"
            data-bs-toggle="dropdown"
            aria-expanded="false"
            aria-label="More options">
      <i class="bi-three-dots-vertical"></i>
    </button>
    <ul class="dropdown-menu dropdown-menu-end">
      <li><a class="dropdown-item icon-link" href="..."><i class="bi-copy"></i> Clone</a></li>
      <li><a class="dropdown-item icon-link" href="..."><i class="bi-archive"></i> Archive</a></li>
    </ul>
  </div>
</nav>
```

**Rules:**

- Container: `nav.nav.btn-group.flex-nowrap`
- Buttons: `btn btn-{variant} btn-sm`
- Overflow trigger: `btn btn-secondary btn-sm dropdown-toggle` with `bi-three-dots-vertical`
- Dropdown menu: `dropdown-menu dropdown-menu-end`
- Destructive items in dropdown use `dropdown-item text-danger`

---

## 7. Patterns -- Empty States

### 7.1 Block-level empty state

The standard empty state for sections and lists where there is no content to display.

```html
<p class="text-secondary mb-0">No items added yet.</p>
```

**Rules:**

- Use `text-secondary` (not `text-muted` -- standardise on `text-secondary`)
- Use `mb-0` (the parent vstack gap provides spacing)
- Left-aligned (not centered)
- Plain `<p>` tag, no additional padding or border

### 7.2 Empty state with action link

When the current user can add content, include an action link or button.

```html
<p class="text-secondary mb-0">
  No lore added yet. <a href="...">Add some</a> to tell the story of your gang.
</p>
```

Or with a button for more prominent actions:

```html
<div>
  <p class="text-secondary mb-0">No items yet.</p>
  <a href="..." class="btn btn-outline-primary btn-sm mt-2">
    <i class="bi-plus-lg"></i> Add Item
  </a>
</div>
```

**Rules:**

- Show the "Add" link inline in the text when the action is low-prominence
- Show a button below the text when the action is the primary next step
- Only show add links/buttons to users who have permission (typically the owner)
- Non-owners see only the text without an action link

### 7.3 Inline empty state

For empty cells within tables or card content.

```html
<span class="text-muted fst-italic">None</span>
```

---

## 8. Patterns -- Confirmation Pages

### 8.1 Standard confirmation layout

Confirmation pages for destructive or significant actions (archive, delete, remove, sell) use
the **form-page** shell with a warning/info block.

```html
{% extends "core/layouts/base.html" %}
{% block content %}
  {% include "core/includes/back.html" with url=return_url text="Back" %}
  <div class="col-12 col-md-8 col-lg-6 px-0 vstack gap-3">
    <h1 class="h3">Archive: {{ entity.name }}</h1>

    <p>Are you sure you want to archive this item?</p>

    <!-- Explanation block (what happens) -->
    <div class="border rounded p-3 bg-body-secondary">
      <p class="mb-2"><strong>What happens when you archive:</strong></p>
      <ul class="mb-0">
        <li>The item will be hidden from your main page</li>
        <li>You can unarchive it later</li>
      </ul>
    </div>

    <!-- Warning block (if applicable) -->
    <div class="border border-warning rounded p-3 bg-warning bg-opacity-10">
      <p class="mb-2"><strong class="text-warning">Warning text</strong></p>
      <p class="mb-0">Additional warning details.</p>
    </div>

    <!-- Action form -->
    <form method="post" action="...">
      {% csrf_token %}
      <input type="hidden" name="archive" value="1">
      <div class="mt-3">
        <button type="submit" class="btn btn-danger">Archive</button>
        <a href="..." class="btn btn-link">Cancel</a>
      </div>
    </form>
  </div>
{% endblock %}
```

### 8.2 Confirmation page rules

**Structure:**

1. Back link (via `back.html` include)
2. Page title: `<h1 class="h3">Action: Entity Name</h1>`
3. Confirmation question: `<p>Are you sure you want to...?</p>`
4. Explanation block (optional): `border rounded p-3 bg-body-secondary`
5. Warning block (optional): `border border-warning rounded p-3 bg-warning bg-opacity-10`
6. Action form with hidden fields + submit button

**Button variants by action type:**

| Action | Submit button | Cancel |
|--------|-------------|--------|
| Archive | `btn btn-danger` | `btn btn-link` |
| Delete | `btn btn-danger` | `btn btn-link` |
| Remove | `btn btn-danger` | `btn btn-link` |
| Unarchive | `btn btn-primary` | `btn btn-link` |
| Restore | `btn btn-primary` | `btn btn-link` |

**Warning block classes:**

- Standard warning: `border border-warning rounded p-3 bg-warning bg-opacity-10`
- Info note: `border border-info rounded p-3 bg-info bg-opacity-10`
- Neutral explanation: `border rounded p-3 bg-body-secondary`

**Rules:**

- Never use `alert` classes for inline warnings on confirmation pages -- use `border rounded`
  pattern instead
- The form action should be a POST to the same URL
- Hidden input fields carry the action type (e.g., `name="archive" value="1"`)
- Cancel links should return to the entity's detail page
