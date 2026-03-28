# View Audit: List About (Lore)

## Metadata

- **URL**: `/list/<id>/about`
- **Template**: `core/list_about.html`
- **Extends**: `core/layouts/base.html` -> `core/layouts/foundation.html`
- **Template tags loaded**: `allauth`, `custom_tags`
- **Key includes**:
  - `core/includes/list_common_header.html` (with `link_list="true"`)
  - `core/includes/list_about.html` (main content)
  - `core/includes/fighter_card.html` (compact mode, per fighter)

## Components Found

### Buttons

| Pattern | Classes | Location |
|---------|---------|----------|
| Edit (list overview) | `btn btn-outline-secondary btn-sm` | list_about.html overview section |
| Edit (fighter narrative) | `btn btn-outline-secondary btn-sm` | list_about.html per-fighter |
| Add lore (fighter, no narrative) | `btn btn-outline-secondary btn-sm` | list_about.html per-fighter |
| Refresh cost | `btn btn-link btn-sm p-0 text-secondary` | list_common_header.html |

### Cards

| Pattern | Classes | Location |
|---------|---------|----------|
| Navigation card | `nav card card-body flex-column mb-3 p-2` | list_about.html (table of contents) |
| Fighter card (compact) | `card {classes} break-inside-avoid` | fighter_card_content.html (compact=True) |

### Tables

| Pattern | Classes | Location |
|---------|---------|----------|
| Stats summary | `table table-sm table-borderless table-responsive text-center mb-0` | list_common_header.html |
| Fighter statline (compact) | `table table-sm table-borderless table-fixed mb-0` | fighter_card_content_inner.html |
| Weapons table (compact) | `table table-sm table-borderless mb-0 fs-7` | list_fighter_weapons.html |

### Navigation

| Pattern | Classes | Location |
|---------|---------|----------|
| Tab bar (Lore/Notes) | `nav nav-tabs mb-4` | list_about.html |
| Active tab (Lore) | `nav-link active` | list_about.html |
| Inactive tab (Notes) | `nav-link` | list_about.html |
| In-page TOC | `nav card card-body flex-column mb-3 p-2` | list_about.html |
| TOC links | `nav-link p-2 py-1` | list_about.html |

### Icons

- `bi-pencil` - Edit buttons
- `bi-plus` - Add lore button
- `bi-person` - Owner link (from list_common_header.html)
- `bi-award` - Campaign link (from list_common_header.html)

### Other Components

| Pattern | Classes | Location |
|---------|---------|----------|
| CSS grid | `grid auto-flow-dense` | list_about.html fighter grid |
| Grid items | `g-col-12 g-col-md-6` | list_about.html per-fighter |
| Fighter image | `img-fluid rounded size-em-5` | list_about.html (lore images) |
| Empty state | `text-muted fst-italic` | list_about.html (no lore text) |
| Rich text output | `|safe_rich_text|safe` filter | narrative content |

## Typography Usage

| Element | Classes | Size | Context |
|---------|---------|------|---------|
| Gang name | `h2.mb-0.h3` | h3 size | list_common_header.html (linked) |
| Section title "Overview" | `h3.h4` | h4 size | list_about.html |
| Fighter name | `h3.h4` | h4 size | list_about.html per-fighter |
| Tab label | default nav-link size | base | nav tabs |
| TOC links | default nav-link size with `p-2 py-1` | base | navigation card |
| Fighter card name | `h3.h5.mb-0` | h5 size | fighter_card_content.html (compact) |
| Rich text content | (rendered HTML) | varies | narratives |
| Empty state text | `text-muted fst-italic` | base | "No lore added yet." |
| Empty list text | default | base | "This List is empty." |

## Colour Usage

| Colour | Bootstrap Class | Context |
|--------|----------------|---------|
| Secondary | `btn-outline-secondary`, `text-secondary` | Edit/Add buttons |
| Muted | `text-muted` | Owner name, empty states |
| Body secondary | `bg-body-secondary` | (via list_common_header.html section headers) |

## Spacing Values

| Property | Values Used | Context |
|----------|-------------|---------|
| Tab bar margin | `mb-4` | nav-tabs |
| TOC card | `mb-3 p-2` | navigation card |
| TOC link padding | `p-2 py-1` | nav-link items |
| Overview section | `mb-4` | list-overview div |
| Fighter image margin | `mb-2` | image wrapper |
| Edit button margin | `mt-2` | after narrative content |
| Header border | `mb-3 pb-4 border-bottom` | list_common_header.html (with link_list) |
| Content wrapper gap | `gap-5` | outer vstack |

## Custom CSS

| Class | Definition | Used In |
|-------|-----------|---------|
| `linked` | Underline link styling | Owner link in header |
| `size-em-5` | `width: 16em; height: 16em` | Fighter lore images |
| `auto-flow-dense` | `grid-auto-flow: row dense` | Fighter grid |

## Inconsistencies

1. **Heading hierarchy**: The page has no `<h1>` -- it goes straight from the header's `h2.h3` to the overview's `h3.h4`. The semantic heading levels skip `h1` entirely, which is an accessibility concern.

2. **Fighter lore vs no lore structure**: When a fighter has a narrative, the Edit button is wrapped in `<div class="ms-auto">` inside an `hstack`. When there is no narrative, the Add button is wrapped in a `<p>` tag with no `ms-auto` or `hstack`. Different structural patterns for the same conceptual action.

3. **Tab and TOC double navigation**: The page has both a tab bar for switching between Lore and Notes, and a TOC card for jumping to fighters. These are two navigation patterns that serve different purposes but are placed near each other without clear visual separation.

4. **Empty fighter narrative text inconsistency**: Fighters with no lore show `<p class="text-muted">No lore added yet.</p>` (a `<p>` with `text-muted`), but the list overview shows `<div class="text-muted fst-italic">No lore added yet.</div>` (a `<div>` with `text-muted fst-italic`). The overview version uses italic; the fighter version does not.

5. **Edit button placement**: For the overview, the Edit button is in the header `hstack` with `ms-auto`. For fighters with narrative, it's also in the header `hstack` with `ms-auto`. But for fighters without narrative, it's below the empty state text in a standalone `<p>`. Three slightly different placements.

6. **Compact fighter card paired with lore**: Each fighter gets a full lore column AND a compact fighter card side by side in the grid. The compact card uses `g-col-12 g-col-md-6`, matching the lore column. This creates a nice two-column layout at md+ but the cards are quite dense at mobile.

## Accessibility Notes

1. **Missing h1**: No `<h1>` exists on this page. The title is set via `<title>` in the head but there's no visible h1 landmark.

2. **Tab navigation ARIA**: The Lore/Notes nav-tabs use basic Bootstrap nav-tabs without explicit `role="tablist"`, `role="tab"`, or `aria-selected` attributes. This is the simpler Bootstrap pattern (link-based tabs navigating between pages rather than in-page tab panels), so ARIA tab roles would be incorrect here -- they're page navigation links, not tabs.

3. **Anchor links**: The TOC uses `#about-list` and `#about-{fighter.id}` anchors. The target elements have `id` attributes. However, the `<a>` elements in the TOC don't have `aria-current` or similar indicators for the currently visible section.

4. **Image alt text**: Fighter images use `alt="{{ fighter.name }}"`, which provides basic context.

5. **Rich text content**: User-generated narratives are rendered with `|safe_rich_text|safe`. The content structure depends on user input, which could introduce accessibility issues (e.g., heading hierarchies within narratives).
