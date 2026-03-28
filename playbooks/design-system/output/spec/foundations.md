# Foundations

The foundational layer of the Gyrinx Design System. Every component and page layout builds on these primitives.

---

## 1. Principles

### 1.1 Information density over white space

**Statement:** Prefer compact, data-rich layouts. Show more information per screen rather than spreading content across multiple pages or hiding it behind interactions.

**Rationale:** Necromunda gang management involves tracking dozens of fighters, each with stats, equipment, skills, injuries, and XP. Players need to compare fighters side by side, spot stat modifications, and plan purchases -- all of which demand density.

**Example:** Fighter cards use `fs-7` (12.6px) for stat tables and weapon profiles. Stat headers, weapon columns, and gear lists all render at this compact size so an entire gang roster fits on one screen.

### 1.2 Colour sparingly, for emphasis

**Statement:** The default UI is neutral grey. Colour appears only to communicate state (injured, dead, active), signal actions (danger, success), or highlight modifications (stat changes). Never use colour decoratively.

**Rationale:** Fighter cards carry dense data. If backgrounds, borders, and text all compete for attention with colour, nothing stands out. Colour must be reserved for the moments that matter -- a stat that changed, a fighter that died, a button that destroys data.

**Example:** A modified stat cell gets `bg-warning-subtle` to draw the eye. A dead fighter's card header gets `bg-danger-subtle`. Everything else is the default body colour.

### 1.3 Mobile-first, desktop-optimised

**Statement:** Design for phone screens first. Layer in wider layouts and additional columns at `md` and above. Never build a desktop layout and then try to make it fit mobile.

**Rationale:** Players check their gang rosters on their phones at the game table. The app must be fully usable at 375px width. Desktop layouts are an enhancement, not the baseline.

**Example:** Fighter cards stack vertically at mobile widths (`col-12`). At `xl` breakpoint, page content constrains to `col-12 col-xl-6` to maintain readable line lengths.

### 1.4 Server-rendered, not interactive

**Statement:** Prefer full-page loads with Django template rendering. Use JavaScript only when server-rendered HTML cannot achieve the interaction (clipboard copy, dropdown menus, tooltips). Never build client-side state management.

**Rationale:** Gyrinx is a planning tool, not a real-time app. Server rendering keeps the codebase simple, the pages accessible, and the bundle size zero. Every form submission is a standard POST.

**Example:** Equipment assignment is a Django form with a select widget and a submit button. It is not a drag-and-drop interface with optimistic updates.

### 1.5 Bootstrap vocabulary, extended minimally

**Statement:** Use Bootstrap 5.3 utility classes as the primary design language. Add custom classes only when Bootstrap lacks the capability. Never duplicate Bootstrap functionality with custom CSS.

**Rationale:** Bootstrap provides a shared vocabulary across the team. Custom CSS adds maintenance burden and diverges from documentation that developers already know. Every custom class must justify its existence by filling a gap Bootstrap cannot.

**Example:** `.mb-last-0` removes the trailing margin from the last child of rich-text containers -- something Bootstrap has no utility for. `.linked` composes three Bootstrap link utilities into a single reusable class.

### 1.6 Semantic HTML structure

**Statement:** Use heading levels (`h1` through `h6`) for document structure, not visual styling. Override visual size with Bootstrap's `.h1`-`.h6` classes when the semantic level and visual size diverge.

**Rationale:** Screen readers, search engines, and browser outline tools depend on heading hierarchy. A page that skips from `h1` to `h5` or uses `h2` for visual styling breaks these tools.

**Example:** A sub-page title is `<h1 class="h3">` -- semantically the page's primary heading, but visually sized as h3 to reflect its subordinate position in the navigation hierarchy.

### 1.7 Consistent state vocabulary

**Statement:** Map every UI state to exactly one colour. Active = success (green). Injured/captured = warning (yellow). Dead = danger (red). Never use a colour for a state it is not assigned to.

**Rationale:** Players scan fighter cards for status at a glance during games. Inconsistent colour-to-state mapping forces them to read labels instead of scanning visually.

**Example:** `text-bg-success` for "Active" badges. `bg-warning-subtle` for injured card headers. `bg-danger-subtle` for dead card headers. No exceptions.

---

## 2. Colour

### 2.1 Brand palette

Gyrinx overrides Bootstrap's default colour variables with a palette that is darker and more saturated than Bootstrap's defaults. These are set in `styles.scss` before the Bootstrap variable import.

| Token | Hex | SCSS Variable | Bootstrap CSS Variable | Role |
|-------|-----|---------------|----------------------|------|
| `$gy-primary` | `#0771ea` | `$blue` | `--bs-primary` | Primary actions, XP/credits badges |
| `$gy-success` | `#1a7b49` | `$green` | `--bs-success` | Active state, confirmations, start |
| `$gy-danger` | `#cb2b48` | `$red` | `--bs-danger` | Dead state, errors, destructive actions |
| `$gy-warning` | `#e8a10a` | `$yellow` | `--bs-warning` | Injured/captured state, stat highlights |
| `$gy-info` | `#10bdd3` | `$cyan` | `--bs-info` | Informational callouts, invitations |
| `$gy-secondary` | Bootstrap default | -- | `--bs-secondary` | De-emphasised text, edit actions, cost badges |

### 2.2 Extended palette (overridden but not directly used in UI)

These colours are overridden to maintain a cohesive palette in Bootstrap's internal colour map. They do not appear in any UI pattern and are available for future use.

| SCSS Variable | Hex | Notes |
|---------------|-----|-------|
| `$indigo` | `#5111dc` | Reserved |
| `$purple` | `#5d3cb0` | Reserved |
| `$pink` | `#c02d83` | Reserved |
| `$orange` | `#ea5d0c` | Reserved |
| `$teal` | `#1fb27e` | Reserved |

### 2.3 Semantic colour tokens

| Token | CSS Variable | Usage |
|-------|-------------|-------|
| `$gy-action-primary` | `var(--bs-primary)` | Add, create, submit buttons (`btn-primary`) |
| `$gy-action-edit` | `var(--bs-secondary)` | Edit, secondary actions (`btn-secondary`, `link-secondary`) |
| `$gy-action-destroy` | `var(--bs-danger)` | Delete, remove, archive (`btn-danger`, `link-danger`) |
| `$gy-action-enable` | `var(--bs-success)` | Enable, start, confirm (`btn-success`, `link-success`) |
| `$gy-action-warn` | `var(--bs-warning)` | Sell, caution (`link-warning`) |
| `$gy-state-active` | `var(--bs-success)` | Active/alive fighter badge |
| `$gy-state-injured` | `var(--bs-warning)` | Injured/captured fighter badge and card header |
| `$gy-state-dead` | `var(--bs-danger)` | Dead fighter badge and card header |
| `$gy-surface-section` | `var(--bs-secondary-bg)` | Section header bar background (`bg-body-secondary`) |
| `$gy-surface-group` | `var(--bs-tertiary-bg)` | Fighter group background (`bg-secondary-subtle`) |
| `$gy-surface-highlight` | `var(--bs-warning-bg-subtle)` | Modified stat highlight (`bg-warning-subtle`) |
| `$gy-text-muted` | `var(--bs-secondary-color)` | De-emphasised text |
| `$gy-dot-size` | `10px` | Standardised colour dot indicator size |

### 2.4 Text colour usage

| Purpose | Class | Notes |
|---------|-------|-------|
| De-emphasised text | `text-secondary` | **Canonical.** Use for metadata, timestamps, owner names, empty states. |
| Error text | `text-danger` | Form errors, destructive action labels |
| Warning text | `text-warning` | Caution callouts |
| Default body text | `text-body` | Inherited; rarely needs explicit class |
| Light text on dark | `text-light` | Hero sections only |

**Deprecated:** `text-muted` is deprecated in the Gyrinx design system. Use `text-secondary` for all new code. Existing `text-muted` usage (~120 occurrences) will be migrated.

### 2.5 Badge colour usage

| Purpose | Class | Notes |
|---------|-------|-------|
| XP badges, credits | `text-bg-primary` | **Canonical badge pattern.** Always use `text-bg-*` (not `bg-*`). |
| Cost badges, counters | `text-bg-secondary` | |
| Campaign status, advancement | `text-bg-success` | |
| Pending, cost override | `text-bg-warning` | |
| Attribute values | `text-bg-light` | |

**Deprecated:** `bg-primary`, `bg-secondary`, etc. on badges is deprecated. Use `text-bg-*` which automatically sets contrast text colour.

### 2.6 Link colour usage

| Purpose | Class | Notes |
|---------|-------|-------|
| Edit actions, reset links | `link-secondary` | Most common link colour |
| Delete, archive, remove | `link-danger` | |
| Add, create | `link-primary` | |
| Enable toggle | `link-success` | |
| Sell action | `link-warning` | |

### 2.7 Alert / callout usage

| Purpose | Class | Notes |
|---------|-------|-------|
| Error messages | `border border-danger rounded p-2 text-danger` | Preferred pattern per conventions |
| Destructive confirmations | `alert alert-warning` | Retained for prominent confirmation dialogs |
| Informational callouts | `alert alert-info` | Retained for prominent informational blocks |
| Flash messages (success) | `alert alert-success` | Django messages framework |

### 2.8 Hardcoded colour rules

No hardcoded colour values in SCSS or templates. All colour references must use:

1. SCSS variables (`$blue`, `$red`, etc.) in `.scss` files
2. CSS custom properties (`var(--bs-primary)`, `var(--bs-primary-rgb)`) in custom CSS rules
3. Bootstrap utility classes (`text-danger`, `bg-warning-subtle`) in templates

**Known violations to fix:** `.color-radio-input` uses hardcoded `rgba(13, 110, 253, ...)` instead of `rgba(var(--bs-primary-rgb), ...)`.

---

## 3. Typography

### 3.1 Font stack

```scss
$font-family-sans-serif:
    "mynor-variable",
    system-ui, -apple-system, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, "Noto Sans", "Liberation Sans",
    sans-serif, "Apple Color Emoji", "Segoe UI Emoji",
    "Segoe UI Symbol", "Noto Color Emoji";
```

**Primary typeface:** `mynor-variable` (Adobe Typekit variable font). System fonts serve as fallbacks.

### 3.2 Base font size

| Context | `$font-size-base` | Effective px |
|---------|-------------------|-------------|
| Screen (`screen.scss`) | `0.875rem` | 14px |
| Print (`print.scss`) | `1rem` | 16px (then `zoom: 50%` = ~8px visual) |

### 3.3 Complete type scale

| Scale Name | SCSS Formula | Screen Size | Font Weight | Line Height | Bootstrap Class | Semantic Role |
|------------|-------------|-------------|-------------|-------------|-----------------|---------------|
| Display | `$font-size-base * 2.5` | `2.1875rem` (35px) | `300` (default heading) | `1.2` | `fs-1` / `h1` | Index page titles, entity detail titles |
| Page title | `$font-size-base * 1.75` | `1.53125rem` (24.5px) | `500` (default heading) | `1.2` | `.h3` on `h1` | Sub-page titles, edit/new form headings |
| Section | `$font-size-base * 1.25` | `1.09375rem` (17.5px) | `500` (default heading) | `1.2` | `.h5` on `h2` | Section headings within pages |
| Body | `$font-size-base * 1` | `0.875rem` (14px) | `400` | `1.5` | (default) | Body text, form inputs, paragraphs |
| Compact | `$font-size-base * 0.9` | `0.7875rem` (12.6px) | `400` | `1.5` | `fs-7` | Stats, weapon tables, tabs, filters, metadata |
| Small (deprecated) | `$font-size-base * 0.875` | `0.765625rem` (12.25px) | `400` | `1.5` | `.small` | **Deprecated.** Use `fs-7` instead. |

**Important:** `fs-7` is the canonical class for small/compact text. `.small` is deprecated for new code because the 0.35px difference between `fs-7` and `.small` is visually imperceptible, and maintaining two near-identical sizes creates confusion.

The `.small` class is retained internally within `.caps-label` (which `@extend`s it) but should not be used directly in templates.

### 3.4 Heading hierarchy convention

Every page must have exactly one `<h1>`. Heading levels must not skip (no jumping from `h1` to `h3`).

| Semantic Level | Visual Override | Usage |
|----------------|----------------|-------|
| `<h1>` | (none) | Index pages, entity detail pages (full-size title) |
| `<h1 class="h3">` | Downsized to h3 | Sub-pages, edit/new forms |
| `<h2 class="h5 mb-0">` | Downsized to h5 | Section headings (inside header bars and standalone) |
| `<h3 class="h5 mb-0">` | Downsized to h5 | Card headers, category headings within sections |
| `<h4>` | (default) | Sub-items within cards (advancement cards, gear items) |

### 3.5 Text style: caps-label

The `.caps-label` class is a composite text style for section sub-headers, metadata labels, and table column overlines.

```scss
.caps-label {
    @extend .small;
    @extend .text-uppercase;
    @extend .text-muted;       // will migrate to text-secondary
    @extend .fw-semibold;
    letter-spacing: 0.03em;
}
```

**Properties:** Small size, uppercase, muted colour, semibold weight, slight letter-spacing.

**Usage:** Section labels, metadata category headers, table overlines. 57 instances across 12 files.

**Rule:** Never manually compose uppercase labels with `text-uppercase text-secondary small fw-light` or similar. Always use `.caps-label`.

### 3.6 Font weight conventions

| Class | Weight | Usage |
|-------|--------|-------|
| `fw-semibold` | 600 | `.caps-label` internally, form labels, attribute labels |
| `fw-medium` | 500 | Pack names, content pack labels |
| `fw-normal` | 400 | Resetting inherited bold (print badges, attribute badges) |
| `fw-light` | 300 | Hero heading only |
| `fw-bold` | 700 | Not used in production (design system demo only) |

### 3.7 Text decoration conventions

| Class | Usage |
|-------|-------|
| `text-decoration-underline` | `.tooltipped` links, current sidebar item |
| `text-decoration-line-through` | Disabled skills/rules |
| `text-decoration-none` | Sub-page nav links, badge links |
| `fst-italic` | Empty state text (lore/notes overview) |

---

## 4. Spacing

### 4.1 Spacing scale

Gyrinx uses Bootstrap 5's default spacing scale without modification.

| Scale | Value | rem | px (at 16px root) | Semantic Role in Gyrinx |
|------:|------:|----:|-------------------:|------------------------|
| 0 | `0` | 0 | 0 | Resets (`mb-0`, `px-0`, `gap-0`) |
| 1 | `0.25rem` | 0.25 | 4 | Tight: icon gaps, small adjustments, list item spacing |
| 2 | `0.5rem` | 0.5 | 8 | Standard: inline spacing, `hstack` gaps, compact containers (`p-2`) |
| 3 | `1rem` | 1 | 16 | Default: `vstack gap-3` form fields, section margins, `mt-3` button rows |
| 4 | `1.5rem` | 1.5 | 24 | Section: listing page gaps, tabs margin |
| 5 | `3rem` | 3 | 48 | Major: page-level section separation on detail pages |

### 4.2 Page-level gap conventions

The outermost `vstack` (or `d-flex flex-column`) on each page type uses a specific gap.

| Page Type | Gap Class | Value | Examples |
|-----------|-----------|-------|----------|
| Form / edit pages | `gap-3` | 1rem | fighter-edit, list-edit, campaign-new, pack-edit |
| Listing / index pages | `gap-4` | 1.5rem | lists-index, campaigns-index, pack-lists |
| Detail / show pages | `gap-5` | 3rem | campaign-detail, pack-detail, list-about |

### 4.3 Section heading margin convention

| Context | Pattern | Margin |
|---------|---------|--------|
| Inside a section header bar (`bg-body-secondary rounded px-2 py-1`) | `<h2 class="h5 mb-0">` | `mb-0` (bar padding provides spacing) |
| Standalone section heading | `<h2 class="h5 mb-2">` | `mb-2` (0.5rem) |
| Card header heading | `<h3 class="h5 mb-0">` | `mb-0` (card body padding provides spacing) |

### 4.4 Page title margin convention

| Context | Pattern | Margin |
|---------|---------|--------|
| Title with subtitle | `<h1 class="mb-1">` | `mb-1` (0.25rem before subtitle) |
| Title without subtitle (in vstack) | `<h1 class="mb-0">` | `mb-0` (vstack gap provides spacing) |

### 4.5 Form spacing conventions

| Element | Spacing | Notes |
|---------|---------|-------|
| Form field group | `vstack gap-3` | 1rem between fields |
| Button row below form | `div.mt-3` | 1rem top margin, always `mt-3` |
| Label to input | `margin-bottom: 0.25rem` | Global `label` override in SCSS |
| Fieldset legend | `font-size: $font-size-base` | Reset to body size (not Bootstrap's larger default) |

### 4.6 Common spacing patterns

| Pattern | Class | Count | Usage |
|---------|-------|-------|-------|
| Vstack default gap | `vstack gap-3` | ~170 | Most common layout pattern |
| Compact hstack gap | `hstack gap-2` | ~80 | Inline button groups, metadata rows |
| Tight item gap | `gap-1` | ~70 | Icon + text, badge groups |
| Section header bar padding | `px-2 py-1` | ~30 | Section header bars with `bg-body-secondary` |
| Compact container padding | `p-2` | ~78 | Cards, inline containers, section bars |
| Standard container padding | `p-3` | ~35 | Forms, larger content blocks |

### 4.7 Empty state spacing

Empty states should use no additional padding. The parent `vstack` gap provides spacing.

```html
<p class="text-secondary mb-0">No fighters yet.</p>
```

Do not add `py-2`, `text-center`, `.small`, or `fst-italic` to empty states.

---

## 5. Icons

### 5.1 Icon library

Gyrinx uses [Bootstrap Icons](https://icons.getbootstrap.com/) exclusively. No other icon library is permitted.

### 5.2 Syntax standard

Use the **hyphenated format** for all icon classes:

```html
<!-- Correct -->
<i class="bi-pencil"></i>

<!-- Incorrect (space-separated) -->
<i class="bi bi-pencil"></i>
```

Both are valid Bootstrap Icons syntax, but the hyphenated format is the Gyrinx standard. 22 instances of the space-separated format exist and should be migrated.

### 5.3 Canonical icon map

| Concept | Icon Class | Notes |
|---------|-----------|-------|
| **Add (primary)** | `bi-plus-lg` | Creating new top-level entities (campaigns, lists) |
| **Add (contextual)** | `bi-plus-circle` | Adding items within an existing context (log action, add gear) |
| **Add (inline)** | `bi-plus` | Inline form add buttons |
| **Edit** | `bi-pencil` | All edit actions. Never use `bi-pencil-square`. |
| **Delete** | `bi-trash` | Destructive deletion |
| **Close / dismiss** | `bi-x-lg` | Closing panels, clearing inputs |
| **Remove (inline)** | `bi-dash` | Removing list items, sub-item indentation |
| **Back** | `bi-chevron-left` | All back navigation. Never use `bi-arrow-left` or `bi-arrow-return-left`. |
| **Forward (step)** | `bi-arrow-right` | Wizard "Next" steps, explicit forward navigation |
| **Forward (row)** | `bi-chevron-right` | Mobile row affordance ("tap to view details") |
| **Home** | `bi-house-door` | Home navigation. Never use `bi-house`. |
| **Search** | `bi-search` | Search input groups |
| **Refresh / update** | `bi-arrow-clockwise` | Refresh and update actions |
| **Warning** | `bi-exclamation-triangle` | General warnings, form errors |
| **Warning (destructive)** | `bi-exclamation-triangle-fill` | Irreversible/destructive action confirmations only |
| **Info** | `bi-info-circle` | Informational callouts, tooltip triggers. Never use `-fill`. |
| **Confirm** | `bi-check-circle` | Confirmation actions (advancement confirm, sold) |
| **Save** | `bi-check-lg` | Save/submit buttons |
| **Copied** | `bi-check2` | Clipboard copy feedback state |
| **More options** | `bi-three-dots-vertical` | Overflow menus. Never use `bi-three-dots` (horizontal). |
| **Print** | `bi-printer` | Print actions |
| **Archive** | `bi-archive` | Archive actions |
| **Copy / clone** | `bi-copy` | Clone/duplicate entities |
| **User / owner** | `bi-person` | User identity, owner metadata |
| **Campaign** | `bi-award` | Campaign context indicator |
| **Content pack** | `bi-box-seam` | Content pack references |
| **Vehicle** | `bi-truck` | Vehicle context |
| **List type** | `bi-list-ul` | List type indicator |
| **Lore / text** | `bi-file-text` | Lore content, text sections |
| **Notes** | `bi-journal-text` | Notes sections |
| **Credits / currency** | `bi-coin` | Credits and currency |
| **History** | `bi-clock-history` | History/changelog views |
| **Settings** | `bi-gear` | Settings and configuration |
| **Visible / public** | `bi-eye` | Public/visible state |
| **Hidden / unlisted** | `bi-eye-slash` | Hidden/unlisted state |
| **Transfer** | `bi-arrow-left-right` | Transfer between entities |
| **Upgrade** | `bi-arrow-up-circle` | Equipment upgrades |
| **External link** | `bi-box-arrow-up-right` | Links to external sites |
| **Battle winner** | `bi-trophy-fill` | Campaign battle winner indicator |
| **Kill / dead** | `bi-heartbreak` | Kill actions |
| **Resurrect** | `bi-heart-pulse` | Resurrection actions |
| **Start** | `bi-play-circle` | Start campaign |
| **End / stop** | `bi-stop-circle` | End campaign |
| **Invitations** | `bi-envelope` | Invitation management |
| **Dropdown arrow** | `bi-chevron-down` | Dropdown toggle indicator |
| **Debug flag** | `bi-flag-fill` | Debug mode indicators |
| **Action log** | `bi-flag` | Action log entries |
| **Dice** | `bi-dice-*` (1-6) | Dice roll display |
| **Theme toggle** | `bi-circle-half` | Light/dark mode switch |
| **Light mode** | `bi-sun-fill` | Light mode indicator |
| **Dark mode** | `bi-moon-stars-fill` | Dark mode indicator |
| **GitHub** | `bi-github` | GitHub link |
| **Discord** | `bi-discord` | Discord link |
| **Embed** | `bi-person-bounding-box` | Embed/iframe context |

### 5.4 Size conventions

| Context | Size | Method |
|---------|------|--------|
| Inline with body text | Inherited | No size class (default) |
| Compact contexts | ~12.6px | `fs-7` on parent or icon |
| Featured / hero display | ~21px | `fs-4` on icon |
| Large display (dice) | ~24.5px | `fs-3` on icon |

Do not use ad-hoc `fs-5` or `fs-6` on icons. Use the default (inherited) size unless the icon needs explicit sizing.

### 5.5 Accessibility

**Rule:** Every icon must have an accessibility attribute.

| Icon Type | Requirement | Example |
|-----------|------------|---------|
| Decorative (with adjacent text) | `aria-hidden="true"` on `<i>` | `<i class="bi-pencil" aria-hidden="true"></i> Edit` |
| Functional (icon-only button/link) | `aria-label` on parent `<a>` or `<button>`, `aria-hidden="true"` on `<i>` | `<a href="..." aria-label="Edit fighter"><i class="bi-pencil" aria-hidden="true"></i></a>` |
| Informational (standalone meaning) | `role="img"` and `aria-label` on `<i>` | `<i class="bi-dice-6" role="img" aria-label="Dice showing 6"></i>` |

**Current state:** Only 2.2% of icons (9 of 414) have accessibility attributes. All new icons must include them. Existing icons will be migrated.

---

## 6. Elevation & Borders

### 6.1 Design philosophy

Gyrinx uses a flat design. There are no drop shadows on standard UI elements. Visual hierarchy is established through background colour, borders, and spacing -- not elevation.

### 6.2 Border conventions

| Pattern | Classes | Usage | Examples |
|---------|---------|-------|----------|
| Compact bordered container | `border rounded p-2` | Section header bars, inline metadata containers, compact callouts | Section headers with `bg-body-secondary` |
| Standard bordered container | `border rounded p-3` | Form groups, content blocks, larger callouts | Error containers, info callouts |
| Coloured border container | `border border-{colour} rounded p-2 text-{colour}` | Status callouts (replaces `alert` classes) | `border border-danger rounded p-2 text-danger` for errors |
| Card | Bootstrap `.card` | Fighter cards in grids only | Fighter roster grid |

### 6.3 When to use cards vs bordered containers

| Use Case | Pattern |
|----------|---------|
| Fighter cards in a grid layout | `.card` (Bootstrap card component) |
| Everything else | `border rounded p-2` or `border rounded p-3` |

Cards are reserved for fighter grids because they provide the card header/body/footer structure needed for fighter display. All other containers use simple bordered divs.

### 6.4 Box shadow

| Pattern | Class | Usage |
|---------|-------|-------|
| No shadow | (default) | All standard UI elements |
| Subtle shadow | `shadow-sm` | Not currently used in production templates |
| Hover shadow | Custom (`.img-link-transform`) | Homepage hero image hover effect only |

Do not add `shadow`, `shadow-sm`, `shadow-lg`, or any custom `box-shadow` to UI elements unless specifically approved.

### 6.5 Border radius

Bootstrap's default border-radius values apply throughout. No custom border-radius values are defined.

| Class | Value | Usage |
|-------|-------|-------|
| `rounded` | `0.375rem` (Bootstrap default) | Standard containers, callouts |
| `rounded-2` | `0.375rem` | Colour swatches in design system |
| `rounded-circle` | `50%` | Colour dot indicators, avatars |
| `rounded-0` | `0` | Removing radius at specific breakpoints |

### 6.6 Responsive border utilities

Gyrinx extends Bootstrap with responsive border removal/addition at the `md` breakpoint for layout shifts between mobile (stacked) and desktop (side-by-side) containers.

| Class | Effect |
|-------|--------|
| `border-start-md-0` | Remove left border at `md`+ |
| `border-end-md-0` | Remove right border at `md`+ |
| `border-start-md` | Add left border at `md`+ |
| `border-end-md` | Add right border at `md`+ |
| `rounded-start-md-0` | Remove left radius at `md`+ |
| `rounded-end-md-0` | Remove right radius at `md`+ |

Only the `md` breakpoint variants are in use. Other breakpoint variants are generated but unused.

### 6.7 Dividers

| Pattern | Class | Usage |
|---------|-------|-------|
| Table group divider | `.table-group-divider` (custom) | Visual separator between `<tbody>` groups in borderless tables. Uses `!important` to override `.table-borderless`. |
| Horizontal rule | `<hr>` | Rarely used. Prefer spacing (vstack gaps) for section separation. |

---

## Appendix: Custom CSS Classes Reference

A complete list of custom CSS classes defined in `styles.scss`, classified by type.

### Design tokens

| Class / Variable | Type | Usage Count |
|-----------------|------|-------------|
| `$blue` through `$cyan` | SCSS variable overrides | 10 colours |
| `fs-7` | Font-size utility extension | 120+ instances |
| `.caps-label` | Composite text style | 57 instances |

### Utility extensions

| Class | Purpose | Usage Count |
|-------|---------|-------------|
| `.mb-last-0` | Remove trailing margin from last child | 16 instances |
| `.auto-flow-dense` | CSS Grid dense auto-flow | 3 instances |
| `.break-inside-avoid` | Prevent print page breaks | 7 instances |
| `.table-group-divider` | Table group border separator | 13 instances |
| `.table-fixed` | Fixed table layout | 6 instances |
| `.table-nowrap` | Truncate overflowing table cells | 5 instances |
| `border-*-md-*` | Responsive border add/remove | 19 instances |

### Component classes

| Class | Purpose | Usage Count |
|-------|---------|-------------|
| `.linked` | Standard inline link style | 39 instances |
| `.link-sm` | Compact link (`.linked` + `fs-7`) | 4 instances |
| `.tooltipped` | Tooltip-bearing link with info underline | 11 instances |
| `.hero` | Homepage hero banner | 2 instances |
| `.dropdown-menu-mw` | Wide dropdown menu (25-35em) | 5 instances |
| `.fighter-switcher-btn` / `-menu` | Fighter name dropdown | 1 instance each |
| `.flash-warn` | Warning flash animation (2s fade) | dynamic |
| `.color-radio-label` / `-input` | Colour picker widget | 2 instances each |
| `.flatpage-heading` / `.flatpage-content` | Help/about page styles | 1 instance each |
| `.img-link-transform` | 3D hover effect for images | 2 instances |
| `.stat-input-cell` | Pack fighter stat input width (4rem) | 3 instances |
| `.alert-icon` | Alert with icon pinned left | component |

### Global overrides

| Rule | Purpose |
|------|---------|
| `[data-bs-toggle="tooltip"] { cursor: help }` | Help cursor on tooltips |
| `a[data-bs-toggle="tooltip"] { cursor: pointer }` | Pointer cursor on tooltip links |
| `fieldset legend { font-size: $font-size-base }` | Reset legend to body size |
| `label { margin-bottom: 0.25rem }` | Tighten label-to-input spacing |
| `img { max-width: 100%; height: auto }` | Responsive images globally |
| `.errorlist { ... }` | Style Django form error lists |
