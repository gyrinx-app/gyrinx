# Gyrinx Design System

## Updates

| Date | Change |
|------|--------|
| 2026-03-28 | Initial spec: principles, colour, typography, spacing, icons, containers, feedback, buttons, tables, forms, page shells, empty states |
| 2026-03-28 | v2: Remove `bi-plus-circle`/`bi-check-circle` — use `bi-plus-lg` and `bi-check-lg` only. Button colours: `btn-success` for create/confirm, `btn-primary` for navigation/open. Section header bar now includes padded inner content. Alert heading uses body font size. Unify list/detail page shells. Add search pattern, list header, campaign info columns. |

---

## Principles

1. **Dense over spacious** — show more data per screen. Use `fs-7` for data tables, compact spacing. Gang rosters must fit on one screen.
2. **Colour for state only** — the UI is neutral grey. Colour signals state (injured=warning, dead=danger, active=success) or action type. Never decorative.
3. **Mobile-first** — design at 375px, enhance at `md`/`lg`/`xl`. Players check gangs on phones at the table.
4. **Server-rendered** — full-page loads, Django templates, standard form POST. No client-side state.
5. **Bootstrap vocabulary** — use Bootstrap classes as the primary language. Custom classes only for gaps Bootstrap can't fill.
6. **Semantic HTML** — every page has one `<h1>`. Heading levels never skip. Use `.h3`/`.h5` classes to override visual size.
7. **Consistent state colours** — active=success, injured/captured=warning, dead=danger. No exceptions.

---

## Colour

### Palette (SCSS overrides in `styles.scss`)

| Name | Hex | Bootstrap var | Role |
|------|-----|--------------|------|
| Primary | `#0771ea` | `$blue` | Navigation, opening actions, XP/credits badges |
| Success | `#1a7b49` | `$green` | Active state, create/confirm/save actions |
| Danger | `#cb2b48` | `$red` | Dead state, errors, destructive actions |
| Warning | `#e8a10a` | `$yellow` | Injured/captured, stat highlights |
| Info | `#10bdd3` | `$cyan` | Informational callouts |

### Rules

| What | Use | Don't use |
|------|-----|-----------|
| De-emphasised text | `text-secondary` | ~~`text-muted`~~ (deprecated) |
| Badges | `text-bg-primary`, `text-bg-secondary`, etc. | ~~`bg-primary`~~ (deprecated) |
| Links: edit/reset | `link-secondary` | |
| Links: delete/archive | `link-danger` | |
| Links: add/create | `link-primary` | |
| Hardcoded colours | Never. Use SCSS vars or Bootstrap classes. | |

---

## Typography

### Font

`mynor-variable` with system fallbacks. Base size: `0.875rem` (14px) on screen, `1rem` on print.

### Scale

| Name | Size | Class | Use for |
|------|------|-------|---------|
| Page title (index) | 2.19rem | `h1` | Index page titles |
| Page title (sub) | 1.53rem | `h1.h3` | Edit forms, sub-page titles |
| Section | 1rem | `h2.h5` | Section headings |
| Body | 0.875rem | (default) | Everything |
| Compact | 0.79rem | `fs-7` | Stats, weapons, tabs, metadata |

**`fs-7` is canonical for small text.** ~~`.small`~~ is deprecated (0.35px difference, not worth two classes).

### Heading hierarchy

Every page: one `<h1>`. Index pages use full `<h1>`. Sub-pages use `<h1 class="h3">`. Sections use `<h2 class="h5 mb-0">`. Card headers use `<h3 class="h5 mb-0">`.

### Caps label

`.caps-label` — small, uppercase, semibold, tracked. For section sub-headers and metadata labels. Never manually compose with `text-uppercase text-secondary fw-light`.

---

## Spacing

Bootstrap's default scale (0-5) unmodified.

### Page-level gaps

| Page type | Gap | Examples |
|-----------|-----|---------|
| Form/edit | `gap-3` (1rem) | fighter-edit, list-edit |
| Index/listing | `gap-4` (1.5rem) | lists, campaigns |
| Detail | `gap-4` (1.5rem) | list detail, campaign detail |

### Common patterns

- Form fields: `vstack gap-3`
- Button row below form: `div.mt-3`
- Section heading in bar: `mb-0` (bar padding provides space)
- Standalone section heading: `mb-2`

---

## Icons

Bootstrap Icons only. **Hyphenated format**: `bi-pencil` not `bi bi-pencil`.

### Key icons

| Concept | Icon | Notes |
|---------|------|-------|
| Add | `bi-plus-lg` | All add actions (top-level and contextual) |
| Edit | `bi-pencil` | |
| Delete | `bi-trash` | |
| Back | `bi-chevron-left` | |
| Search | `bi-search` | |
| Warning | `bi-exclamation-triangle` | Errors and warnings |
| Info | `bi-info-circle` | |
| Save/confirm | `bi-check-lg` | All save/confirm/create buttons |
| More options | `bi-three-dots-vertical` | |
| Content pack | `bi-box-seam` | |
| Archive | `bi-archive` | |
| Clone | `bi-copy` | |

**Removed:** ~~`bi-plus-circle`~~ (use `bi-plus-lg`), ~~`bi-check-circle`~~ (use `bi-check-lg`).

Sizes: inherit from parent (default), `fs-7` for compact, `fs-4` for featured.

---

## Containers & Cards

| Pattern | Classes | When to use |
|---------|---------|-------------|
| Standard container | `border rounded p-3` | Grouped content, forms, callouts |
| Compact container | `border rounded p-2` | Inline metadata, section bars |
| Section header bar | `bg-body-secondary rounded px-2 py-1` | Section labels with optional action link |
| Card | `card` with `card-header`/`card-body` | **Fighter grids and equipment categories only** |

### Section header bar

The bar contains a title and optional action. Content below the bar is padded to align with the title.

```html
<div class="d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1">
    <h2 class="h5 mb-0">Section title</h2>
    <a href="#" class="fs-7 linked">Action</a>
</div>
<div class="px-2">
    <!-- Section content, padded to align with title -->
</div>
```

Cards are NOT for: info panels, form wrappers, action confirmations, campaign details. Use `border rounded p-3` instead.

---

## Feedback (Alerts)

Use `alert alert-icon` everywhere. Add/remove `alert-dismissible` based on context. Content uses body font size (no `alert-heading` size inflation).

```html
<div class="alert alert-danger alert-icon" role="alert">
    <i class="bi-exclamation-triangle"></i>
    <div>Error message here.</div>
</div>
```

| Colour | Icon | When |
|--------|------|------|
| `alert-success` | `bi-check-lg` | Action completed (flash messages) |
| `alert-danger` | `bi-exclamation-triangle` | Errors, validation failures |
| `alert-warning` | `bi-exclamation-triangle` | Destructive confirmations, cautions |
| `alert-info` | `bi-info-circle` | Contextual hints, "will be logged" notes |
| `alert-secondary` | `bi-info-circle` | Neutral meta info (XP display) |

For multi-line alerts with a title:

```html
<div class="alert alert-warning alert-icon" role="alert">
    <i class="bi-exclamation-triangle"></i>
    <div>
        <strong>Remove gang?</strong>
        <p class="mb-0">The gang will be archived.</p>
    </div>
</div>
```

Use `<strong>` for the title line, not `<h5 class="alert-heading">` — keeps the font size consistent within the alert.

Flash messages (after redirect) are dismissible. Inline contextual alerts are not.

---

## Buttons

| Context | Classes | Examples |
|---------|---------|---------|
| Page header action | `btn btn-primary btn-sm` | Edit (in btn-group with dropdown) |
| Form submit | `btn btn-success` | Save, Create, Confirm |
| Lifecycle action | `btn btn-success btn-sm` or `btn btn-danger btn-sm` | Start Campaign, End Campaign |
| Secondary action | `btn btn-secondary btn-sm` | Cancel, Clear |
| Destructive | `btn btn-danger btn-sm` | Delete, Archive |
| Section "add" link | `icon-link linked` in section header bar | "Add Gangs", "Add Fighter" |
| Back link | `{% include "core/includes/back.html" %}` | All back navigation |

**Rules:**

- Page header: Edit + dropdown grouped in `btn-group`. "Add" links go in section header bars as `icon-link linked`, not in the page header.
- Form submit: `btn-success` for save/create/confirm. `btn-primary` for search (navigation).
- Lifecycle: `btn-success` for start/reopen, `btn-danger` for end.

---

## Tables

Canonical: `table table-sm table-borderless mb-0`

Variants: add `table-fixed` for stat grids, `fs-7` for compact data.

---

## Nav Tabs

Standard Bootstrap `nav nav-tabs`. Use `fs-7 px-2 py-1` on tab buttons for compact contexts (fighter card tabs).

---

## Forms

Standard layout: `form.vstack.gap-3` containing field groups. Submit button row: `div.mt-3`.

Render fields with `{% include "core/includes/form_field.html" %}` for consistent label/input/error structure.

---

## Search Pattern

The standard search bar used on the home page, lists index, campaigns index, and add-gangs pages:

```html
<div class="input-group">
    <span class="input-group-text"><i class="bi-search"></i></span>
    <input class="form-control" type="search" placeholder="Search..." name="q" value="">
    <button class="btn btn-primary" type="submit">Search</button>
</div>
```

The search icon is in an `input-group-text` prepend. The submit button is `btn-primary` (not `btn-success` — search is navigation, not creation). Optional "Clear" link appears after the group when a query is active.

---

## Page Shells

| Shell | Width classes | Gap | Use for |
|-------|-------------|-----|---------|
| Form page | `col-12 col-md-8 col-lg-6` | `gap-3` | Edit forms, settings |
| List page | `col-lg-12 px-0` | `gap-4` | Index pages, detail pages |
| Sidebar page | `row g-4` | — | Lore, notes (with TOC nav) |

**Note:** List and detail pages are unified — both use `col-lg-12 px-0 vstack gap-4`.

---

## Page Patterns

### List/detail header

The standard page header: title left, action buttons right, metadata below.

```html
<div class="d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2 mb-2">
    <h1 class="mb-0">Page Title</h1>
    <nav class="nav btn-group flex-nowrap ms-md-auto">
        <a href="#" class="btn btn-primary btn-sm"><i class="bi-pencil"></i> Edit</a>
        <a href="#" class="btn btn-success btn-sm"><i class="bi-plus-lg"></i> Add</a>
    </nav>
</div>
<div class="d-flex flex-wrap gap-2 text-secondary fs-7">
    <span><i class="bi-person"></i> Owner</span>
    <span><i class="bi-eye"></i> Public</span>
</div>
```

### Campaign info columns

Key metadata displayed as a horizontal flex row of label/value pairs, with a bottom border:

```html
<div class="d-flex flex-wrap gap-3 border-bottom pb-3 mb-2">
    <div class="flex-grow-1 col-md-3 flex-md-grow-0">
        <div class="caps-label">Status</div>
        <div>In Progress</div>
    </div>
    <div class="flex-grow-1 col-md-3 flex-md-grow-0">
        <div class="caps-label">Budget</div>
        <div>1500¢</div>
    </div>
    <div class="flex-grow-1 col-md-3 flex-md-grow-0">
        <div class="caps-label">Content Packs</div>
        <div>Scavvy</div>
        <a href="#" class="fs-7 linked">Edit</a>
    </div>
</div>
```

Each column: `flex-grow-1 col-md-3 flex-md-grow-0`. Label: `.caps-label`. Value: default body text. Optional action link below.

---

## Empty States

```html
<p class="text-secondary mb-0">No fighters yet.</p>
```

For inline empty values in table cells: `<span class="text-secondary fst-italic">None</span>`

---

## Comma-Separated Lists (spaceless)

When rendering a list of items inline without unwanted whitespace (e.g., rules, skills, injuries on fighter cards), use `{% spaceless %}` with `<span>` wrappers and a comma separator:

```html
{% spaceless %}
    {% for item in items %}
        <span>{{ item }}</span>
        {% if not forloop.last %}<span>,&nbsp;</span>{% endif %}
    {% endfor %}
{% endspaceless %}
```

**Why this pattern exists:** Django templates insert whitespace between tags. Without `{% spaceless %}` and `<span>` wrappers, you get `item1 , item2` instead of `item1,&nbsp;item2`. The `&nbsp;` after the comma prevents line breaks mid-list.

**Rules:**

- Wrap each item in `<span>` so `{% spaceless %}` can collapse the surrounding whitespace
- Wrap the comma+space in `<span>,&nbsp;</span>` — not a bare comma
- Use `{% if not forloop.last %}` to skip the trailing separator
- The entire block must be inside `{% spaceless %}...{% endspaceless %}`
- An optional "Edit" link can follow *outside* the `{% spaceless %}` block

---

## Confirmation Pages

Pattern: back link, `alert-warning alert-icon` explaining consequences, form with confirm button (`btn-danger`) and cancel link.

---

## Inline Action Menus

Contextual action links shown below equipment, weapons, and gear on fighter cards. The `bi-arrow-90deg-up` icon visually connects the menu to the item above. Links are separated by the `{% dot %}` tag (`&nbsp;·&nbsp;`).

### Weapon menu (table row)

Inside weapon stat tables, the menu occupies a full-width `<td>` with `colspan`:

```html
<tr>
    <td colspan="9" class="text-end">
        <div class="d-flex flex-wrap">
            <i class="bi-arrow-90deg-up text-secondary me-1"></i>
            <a href="..." class="link-secondary">Edit</a>
            {% dot %}
            <a href="..." class="link-secondary">Accessories</a>
            {% dot %}
            <a href="..." class="link-secondary">Cost</a>
            {% dot %}
            <a href="..." class="link-secondary">Reassign</a>
            {% dot %}
            <a href="..." class="link-danger">Delete</a>
        </div>
    </td>
</tr>
```

### Gear / default equipment menu (inline)

No table wrapper. A `<br>` before the icon:

```html
<br>
<i class="bi-arrow-90deg-up text-secondary me-1"></i>
<a href="..." class="link-secondary">Cost</a>
{% dot %}
<a href="..." class="link-secondary">Reassign</a>
{% dot %}
<a href="..." class="link-danger">Delete</a>
```

### Rules

| Element | Classes / pattern |
|---------|------------------|
| Arrow icon | `bi-arrow-90deg-up text-secondary me-1` |
| Action link | `link-secondary` (edit, cost, reassign, accessories) |
| Destructive link | `link-danger` (delete, archive) |
| Sell link | `link-warning` (stash sell actions) |
| Separator | `{% dot %}` renders `&nbsp;·&nbsp;` |
| Wrapper (table) | `d-flex flex-wrap` inside full-width `<td>` |
| Wrapper (inline) | No wrapper — `<br>` before icon |

---

## Custom CSS Classes

| Class | Purpose |
|-------|---------|
| `.alert-icon` | Flex layout for alerts with pinned icon |
| `.caps-label` | Uppercase, tracked, semibold section labels |
| `.linked` | Composed link style (secondary, underline-opacity) |
| `.fs-7` | Compact font size (0.79rem) |
| `.mb-last-0` | Remove margin from last child in rich text |
| `.flash-warn` | 2s warning-colour fade animation for new items |
| `.tooltipped` | Info-underline style with help cursor |
| `.table-fixed` | `table-layout: fixed` for stat grids |
