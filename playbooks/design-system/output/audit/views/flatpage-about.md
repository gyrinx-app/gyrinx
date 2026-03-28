# View Audit: Flatpage About

## Metadata

| Field         | Value                                                     |
|---------------|-----------------------------------------------------------|
| URL           | `/about/`                                                 |
| Template      | `flatpages/default.html`                                  |
| Extends       | `core/layouts/base.html` > `core/layouts/foundation.html` |
| Includes      | None (content is dynamic from flatpage database field)     |
| Template tags | `allauth`, `pages` (custom flatpage tags)                 |

**Note:** This template is shared with `/help/` and all other flatpages. The audit covers the template structure; content varies per page.

## Components Found

### Navigation

- **Parent breadcrumb:** Conditional `bi-chevron-left` + link to parent page using `.link-underline.link-underline-opacity-0.link-underline-opacity-75-hover`, or static `span.text-secondary` "Help & Documentation" text when at root level
- **Sidebar navigation (desktop):** `ul.d-none.d-md-flex.nav.flex-column` with `li` items containing page links or underlined current-page text
- **Sidebar navigation (mobile):** `.dropdown.d-md-none.mb-3` with `.btn.btn-outline-secondary.dropdown-toggle` trigger and `.dropdown-menu` containing all pages
- **Sub-page listing:** `ul.list-unstyled` at bottom of content area for child pages
- **Back to top button:** `button#back-to-top.btn.btn-sm.btn-secondary.position-fixed.bottom-0.start-0.ms-3.mb-3.z-1.d-none`

### Dropdowns

- Mobile page navigation: `.dropdown-menu` with `.dropdown-item` links and `.dropdown-item.active` (as `<span>`) for current page

### Buttons

- `.btn.btn-outline-secondary.dropdown-toggle` -- mobile navigation trigger (no `.btn-sm`)
- `.btn.btn-sm.btn-secondary.position-fixed` -- back-to-top button with `bi-arrow-up` icon

### Layout

- Two-column layout: `.row` > `.col-md-4` (sidebar) + `.col-12.col-md-8.col-xl-6` (content)
- Sticky sidebar: `.stickyboi.sticky-md-top` (custom class name + Bootstrap sticky utility)

### Content Area

- `.flatpage-content` wrapper class for content column
- Content rendered via `{{ flatpage.content|add_heading_links }}` template filter
- Sub-pages section: `div.mt-5.pt-3.border-top` with `h2.h5.mb-3` heading

### Icons

- `bi-chevron-left` (parent navigation)
- `bi-arrow-up` (back to top)
- `bi-link-45deg` (heading anchors, added by `add_heading_links` filter -- styled via `.flatpage-content a > h*` CSS)

### Other

- **Horizontal rule:** `<hr class="my-3 my-md-4">` between title and sidebar nav
- **External scripts:** iframe-resizer library (`@iframe-resizer/parent@5.3.2`) loaded in `extra_script` block
- **Back-to-top JS:** Inline script toggling `.d-none` based on `window.scrollY > 300`

## Typography Usage

| Element                 | Tag / Class                      | Notes                          |
|-------------------------|----------------------------------|--------------------------------|
| Page title              | `<h1>` (no class override)      | Raw `h1`, no `.h3` -- differs from design system convention |
| Parent breadcrumb text  | Inline text, default size        | No explicit size class         |
| Root label              | `span.text-secondary`            | Grey muted text                |
| Sub-pages heading       | `<h2 class="h5 mb-3">`          | Semantic `h2` styled as `h5`  |
| Sidebar nav items       | `<li>` with `<a>` or `<span>`   | Default text size, `.mb-1` spacing |
| Current page indicator  | `span.text-decoration-underline` | Underlined, no link            |
| Dropdown items          | `.dropdown-item`                 | Bootstrap default              |
| Dropdown indent         | `style="padding-left:{% page_depth page %}em"` | Inline style for nesting depth |

## Colour Usage

| Usage                 | Class / Value              | Notes                          |
|-----------------------|----------------------------|--------------------------------|
| Root label            | `.text-secondary`          | Grey muted                     |
| Parent link           | `.link-underline.link-underline-opacity-0.link-underline-opacity-75-hover` | Invisible underline until hover |
| Current sidebar page  | `.text-decoration-underline` | Default text colour, underlined |
| Sub-page links        | `.text-decoration-none`    | No underline on sub-page links |
| Sub-page hover bg     | Custom CSS: `var(--bs-secondary-bg-subtle)` | Subtle hover highlight |
| Back-to-top button    | `.btn-secondary`           | Grey secondary                 |
| Active dropdown item  | `.dropdown-item.active`    | Bootstrap active highlight     |

## Spacing Values

| Location                | Class(es)                             | Value              |
|-------------------------|---------------------------------------|--------------------|
| Content column          | `.col-12.col-md-8.col-xl-6.mt-2.mt-md-0` | 0.5rem top (mobile), 0 (desktop) |
| Sidebar                 | `.col-md-4`                           | 4/12 width at md+  |
| Sidebar sticky offset   | Custom CSS `.stickyboi { top: 1em }` at md+ | 1em from top |
| Horizontal rule         | `.my-3.my-md-4`                       | 1rem / 1.5rem      |
| Sub-pages section       | `.mt-5.pt-3.border-top`              | 3rem top margin, 1rem top padding |
| Sub-page items          | `.mb-2`                               | 0.5rem bottom      |
| Sub-page links          | `.d-block.p-2.rounded`               | 0.5rem padding all sides |
| Sidebar nav items       | `.mb-1`                               | 0.25rem bottom     |
| Mobile dropdown         | `.mb-3`                               | 1rem bottom        |
| Back-to-top position    | `.ms-3.mb-3`                          | 1rem left, 1rem bottom from edges |
| Dropdown item indent    | Inline `padding-left: {depth}em`      | Variable per depth  |

## Custom CSS

| Class / Selector            | Source          | Description                                   |
|-----------------------------|-----------------|-----------------------------------------------|
| `.stickyboi`                | `styles.scss`   | Custom sticky positioning (`top: 1em` at md+) via `.flatpage-heading .stickyboi` |
| `.flatpage-content`         | `styles.scss`   | Content area: image `max-width: 100%` (133% at xl), heading link icon styles |
| `.flatpage-content .list-unstyled a` | `styles.scss` | Sub-page link hover: `background-color: var(--bs-secondary-bg-subtle)` |
| `.flatpage-content a > h*`  | `styles.scss`   | Heading anchor icons: absolute positioned `bi-link-45deg`, opacity 0 by default, fades in on hover/focus |

## Inconsistencies

1. **Page title uses raw `<h1>`** without `.h3` class. The design system convention says "Gyrinx typically uses `<h1 class='h3'>` for page titles." Flatpages use a full-size `h1` which is visually much larger than other pages.
2. **Sidebar indentation uses inline `style="padding-left:...em"`** for both mobile dropdown items and desktop nav items. This should use CSS classes or utility classes per design system principles.
3. **Parent link uses a non-standard underline pattern** (`.link-underline.link-underline-opacity-0.link-underline-opacity-75-hover`) that differs from the design system's documented patterns (`.linked`, `.link-sm`, or the `.link-secondary.link-underline-opacity-25...` pattern).
4. **Sub-page links use `.text-decoration-none`** which removes underlines entirely, differing from the design system's convention of using opacity-based underline patterns for links.
5. **Mobile dropdown button lacks `.btn-sm`**, while similar dropdown triggers on other pages (e.g., pack detail more-options) use `.btn-sm`. The design system says btn-sm is standard.
6. **The `.stickyboi` class name** is informal and not documented in the design system. All other custom classes use conventional naming.
7. **Layout width `.col-12.col-md-8.col-xl-6`** differs from pack pages' `.col-12.col-xl-8`. There is no documented convention for content column widths.
8. **Two navigation mechanisms** for the same data: mobile dropdown and desktop sidebar list. While responsive behaviour is good, the markup is fully duplicated.

## Accessibility Notes

- Active dropdown item uses `<span class="dropdown-item active">` (not a link) preventing navigation to current page -- correct pattern
- Back to top button has `aria-label="Back to top"` -- good
- Content heading links get `bi-link-45deg` icons that appear on `:hover` and `:focus-within` -- keyboard accessible
- Mobile dropdown uses standard Bootstrap ARIA attributes (`aria-expanded`)
- Missing: The parent link and sidebar navigation are NOT wrapped in a `<nav>` element with `aria-label`. The sidebar uses a bare `<ul>` with no landmark role
- Missing: No `aria-current="page"` on the desktop sidebar current page indicator (only uses visual `.text-decoration-underline`)
- Missing: `<h1>` has no `id` for skip-link targeting; the page's `#content` targets the container div in the base layout
- Missing: Inline depth-based padding has no semantic meaning for screen readers
- Missing: Sub-page listing section lacks an `aria-labelledby` linking it to the `h2` heading
- External iframe-resizer script loaded without `integrity` attribute
