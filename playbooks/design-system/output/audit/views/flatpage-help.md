# View Audit: Flatpage Help

## Metadata

| Field         | Value                                                     |
|---------------|-----------------------------------------------------------|
| URL           | `/help/`                                                  |
| Template      | `flatpages/default.html` (same as `/about/`)              |
| Extends       | `core/layouts/base.html` > `core/layouts/foundation.html` |
| Includes      | None (content is dynamic from flatpage)                   |
| Template tags | `allauth`, `pages` (custom flatpage tags)                 |

**Note:** This view uses the exact same template as the "About" flatpage. All structural analysis from the `flatpage-about.md` audit applies identically. This audit focuses on the differences that arise from the `/help/` URL context and its role as a navigation hub.

## Components Found

All components are identical to the About flatpage audit. The key contextual differences:

### Navigation Context

- **Help is linked from the main navbar:** `base.html` line 60-66 conditionally renders a "Help" nav-item pointing to `/help/`. This makes it a primary navigation destination.
- **Root label:** Since `/help/` is likely a root-level page (depth=0), the template renders `<span class="text-secondary">Help & Documentation</span>` instead of a parent link with `bi-chevron-left`.
- **Sidebar shows child pages:** The `/help/` page likely has sub-pages (e.g., `/help/getting-started/`, `/help/faq/`), making the sidebar navigation populated with child links.

### Sub-pages Section

- If `/help/` has child pages, the bottom sub-page listing (`div.mt-5.pt-3.border-top`) will render with clickable links to child pages, creating a dual-navigation pattern (sidebar + bottom listing).

## Typography Usage

Identical to the About flatpage. See `flatpage-about.md`.

## Colour Usage

Identical to the About flatpage. See `flatpage-about.md`.

## Spacing Values

Identical to the About flatpage. See `flatpage-about.md`.

## Custom CSS

Identical to the About flatpage. See `flatpage-about.md`.

## Inconsistencies

All inconsistencies from the About flatpage apply. Additional context-specific observations:

1. **Dual navigation redundancy:** If `/help/` has sub-pages, users see the same child pages in both the sidebar (desktop) and the bottom sub-pages listing. On desktop, this creates visual redundancy. On mobile, the sidebar is a dropdown while the bottom listing is always visible, which may be intentional for discoverability.
2. **Navbar active state:** The "Help" link in the navbar uses `{% active_flatpage help_page.url %}` which may not correctly highlight when on sub-pages (e.g., `/help/getting-started/`). This depends on the `active_flatpage` template tag implementation.
3. **Help page is conditionally shown in navbar** only when the flatpage at `/help/` exists (`{% get_page_by_url '/help/' as help_page %}`). This is a runtime check on every page load.

## Accessibility Notes

All accessibility notes from the About flatpage apply. Additional:

- The "Help" navbar link inherits proper `aria-current` handling from the `active_flatpage_aria` template tag
- As a documentation hub, the heading hierarchy within the flatpage content (rendered via `flatpage.content|add_heading_links`) is critical for screen reader navigation. The `add_heading_links` filter adds anchor links to headings which should maintain heading levels.
- The page serves as a documentation index, making the heading structure of child page links particularly important for findability
