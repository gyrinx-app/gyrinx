# View Audit: List Notes

## Metadata

- **URL**: `/list/<id>/notes`
- **Template**: `core/list_notes.html`
- **Extends**: `core/layouts/base.html` -> `core/layouts/foundation.html`
- **Template tags loaded**: `allauth`, `custom_tags`
- **Key includes**:
  - `core/includes/list_common_header.html` (with `link_list="true"`)
  - `core/includes/list_notes.html` (main content)
  - `core/includes/fighter_card.html` (compact mode, per fighter)

## Components Found

### Buttons

| Pattern | Classes | Location |
|---------|---------|----------|
| Edit (list overview) | `btn btn-outline-secondary btn-sm` | list_notes.html overview section |
| Edit (fighter notes) | `btn btn-outline-secondary btn-sm` | list_notes.html per-fighter |
| Add notes (fighter) | `btn btn-outline-secondary btn-sm` | list_notes.html per-fighter (no notes yet) |
| Refresh cost | `btn btn-link btn-sm p-0 text-secondary` | list_common_header.html |

### Cards

| Pattern | Classes | Location |
|---------|---------|----------|
| Navigation card | `nav card card-body flex-column mb-3 p-2` | list_notes.html (table of contents) |
| Fighter card (compact) | `card {classes} break-inside-avoid` | fighter_card_content.html (compact=True) |

### Tables

| Pattern | Classes | Location |
|---------|---------|----------|
| Stats summary | `table table-sm table-borderless table-responsive text-center mb-0` | list_common_header.html |

### Navigation

| Pattern | Classes | Location |
|---------|---------|----------|
| Tab bar (Lore/Notes) | `nav nav-tabs mb-4` | list_notes.html |
| Inactive tab (Lore) | `nav-link` | list_notes.html |
| Active tab (Notes) | `nav-link active` | list_notes.html |
| In-page TOC | `nav card card-body flex-column mb-3 p-2` | list_notes.html |
| TOC links | `nav-link p-2 py-1` | list_notes.html |

### Icons

- `bi-pencil` - Edit buttons
- `bi-plus` - Add notes button

### Other Components

| Pattern | Classes | Location |
|---------|---------|----------|
| CSS grid | `grid auto-flow-dense` | list_notes.html fighter grid |
| Grid items | `g-col-12 g-col-md-6` | list_notes.html per-fighter |
| Private notes label | `text-uppercase fs-7 fw-light text-secondary mb-1` | list_notes.html |
| Private notes wrapper | `mb-2 mt-2` | list_notes.html |
| Empty state | `text-muted fst-italic` | list_notes.html (no notes text, overview) |
| Empty state (fighter) | `text-muted` | list_notes.html (no notes, per fighter) |
| Rich text output | `|safe_rich_text|safe` filter | notes/private_notes content |

## Typography Usage

| Element | Classes | Size | Context |
|---------|---------|------|---------|
| Gang name | `h2.mb-0.h3` | h3 size | list_common_header.html (linked) |
| Section title "Overview" | `h3.h4` | h4 size | list_notes.html |
| Fighter name | `h3.h4` | h4 size | list_notes.html per-fighter |
| Private notes label | `text-uppercase fs-7 fw-light text-secondary` | ~0.79rem, uppercase | list_notes.html |
| Tab label | default nav-link size | base | nav tabs |
| TOC links | default nav-link size with `p-2 py-1` | base | navigation card |
| Empty state text (overview) | `text-muted fst-italic` | base, italic | "No notes added yet." |
| Empty state text (fighter) | `text-muted` | base (no italic) | "No notes added yet." |

## Colour Usage

| Colour | Bootstrap Class | Context |
|--------|----------------|---------|
| Secondary | `btn-outline-secondary`, `text-secondary` | Edit/Add buttons, private label |
| Muted | `text-muted` | Empty states, fighter no-notes |

## Spacing Values

| Property | Values Used | Context |
|----------|-------------|---------|
| Tab bar margin | `mb-4` | nav-tabs |
| TOC card | `mb-3 p-2` | navigation card |
| TOC link padding | `p-2 py-1` | nav-link items |
| Overview section | `mb-4` | list-overview div |
| Private notes wrapper | `mb-2 mt-2` | private notes section |
| Private notes label | `mb-1` | label div |
| Content wrapper gap | `gap-5` | outer vstack |
| Header border spacing | `mb-3 pb-4 border-bottom` | list_common_header.html (with link_list) |

## Custom CSS

| Class | Definition | Used In |
|-------|-----------|---------|
| `linked` | Underline link styling | Owner link in header |
| `auto-flow-dense` | `grid-auto-flow: row dense` | Fighter grid |

## Inconsistencies

1. **Empty state style difference from Lore page**: Overview empty state uses `text-muted fst-italic` (italic), but fighter empty state uses just `text-muted` (no italic). This is the same inconsistency as the Lore page but here both variants lack `fst-italic` for fighters. On the Lore page, the overview uses italic while fighter does not.

2. **TOC filtering logic differs from Lore**: The Lore TOC lists ALL active fighters. The Notes TOC only lists fighters with notes or private notes. This means the TOC contents differ in coverage between the two sibling pages, which could be confusing when switching tabs.

3. **Private notes pattern**: Private notes are wrapped in `<div class="mb-2 mt-2">` with a label `<div class="text-uppercase fs-7 fw-light text-secondary mb-1">Private</div>`. This label styling (`fw-light`) differs from the `caps-label` pattern used elsewhere (`fw-semibold`). Both are uppercase and small, but the font weight is opposite.

4. **Missing heading for fighters without notes**: When a fighter has no notes and the owner is viewing, the structure shows `<h3 class="h4">` then `<p class="text-muted">` then a `<p>` with the Add button. When a fighter has notes, the structure is `<h3 class="h4">` inside an `hstack` with `ms-auto` Edit button. The heading is not inside an `hstack` for the no-notes case, so the layout differs.

5. **Heading hierarchy**: Same issue as Lore -- no `<h1>` on the page.

6. **Conditional fighter grid rendering**: Fighters only appear in the grid if they have notes/private_notes OR if the owner is viewing (for the no-notes Add prompt). However, the `{% empty %}` block shows "This List is empty." for all empty lists regardless of authentication, and the Notes TOC only shows fighters with content. This means some fighters appear in the grid but not the TOC.

## Accessibility Notes

1. **Missing h1**: Same as Lore page -- no `<h1>`.

2. **Private notes visibility**: Private notes are only shown to the list owner. The "Private" label is a `<div>` with styling but no ARIA landmark or role to distinguish it from public notes for screen readers.

3. **Tab navigation**: Same link-based pattern as Lore -- pages are separate URLs, not in-page tabs, so no ARIA tab roles needed.

4. **Empty fighter filtering**: Screen reader users navigating the TOC may not find fighters that have no notes but do appear in the grid (for owners), creating a mismatch between navigation and content.
