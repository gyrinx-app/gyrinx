# View Audit: Packs Index

## Metadata

| Field         | Value                                                     |
|---------------|-----------------------------------------------------------|
| URL           | `/packs/`                                                 |
| Template      | `core/pack/packs.html`                                    |
| Extends       | `core/layouts/base.html` > `core/layouts/foundation.html` |
| Includes      | `core/includes/packs_filter.html`, `core/includes/pagination.html` |
| Template tags | `allauth`, `custom_tags`                                  |

## Components Found

### Navigation

- **Breadcrumb:** None (this is a top-level page, no back button)
- **Pagination:** Standard `core/includes/pagination.html` using Bootstrap `.pagination .justify-content-center`, `.page-item`, `.page-link`

### Search / Filter

- **Packs filter form** (`packs_filter.html`):
  - Input group: `.input-group` with `.input-group-text` icon (`bi-search`), `.form-control` search input, `.btn.btn-primary` submit
  - Toggle switch: `.form-check.form-switch` for "Your Packs Only" with `.form-check-input`, `.form-check-label.fs-7`
  - Button group: `.btn-group` with `.btn.btn-link.icon-link.btn-sm` (Update) and `.btn.btn-link.text-secondary.icon-link.btn-sm` (Reset)
  - CSS Grid layout: `.grid`, `.g-col-12`, `.g-col-xl-6`

### Cards

- None

### Lists

- Pack items rendered as `div.hstack.gap-3.position-relative` blocks (not list elements)

### Badges

- `.badge.bg-secondary` for "Unlisted" label

### Buttons

- `.btn.btn-primary` (search submit, full-size -- inconsistency: design system says `btn-sm` is standard)
- `.btn.btn-link.icon-link.btn-sm` (Update filter)
- `.btn.btn-link.text-secondary.icon-link.btn-sm` (Reset filter)

### Icons

- `bi-person` (pack owner)
- `bi-chevron-right` (mobile row arrow)
- `bi-search` (search input)
- `bi-arrow-clockwise` (Update filter button)

### Other

- **Stretched link:** `a.stretched-link.p-3` on the mobile chevron, making the entire pack row tappable on mobile
- **Empty state:** Plain `div.py-2` with text "No content packs available."

## Typography Usage

| Element                  | Tag / Class                  | Notes                         |
|--------------------------|------------------------------|-------------------------------|
| Page title               | `<h1 class="mb-1">`         | Full `h1`, no `.h3` override. Differs from other pack pages |
| Subtitle                 | `<p class="fs-5 col-12 col-md-6 mb-0">` | `.fs-5` for lead text        |
| Pack name                | `<h2 class="mb-0 h5">`      | Semantic `h2` styled as `h5`  |
| Pack summary             | `div.mb-last-0.text-secondary` | Rich text, secondary colour  |
| Filter label             | `.form-check-label.fs-7`    | Custom `.fs-7` size           |

## Colour Usage

| Usage            | Class / Value         | Notes                       |
|------------------|-----------------------|-----------------------------|
| Pack owner text  | Default link colour   | No explicit colour class    |
| Unlisted badge   | `.bg-secondary`       | Bootstrap semantic          |
| Summary text     | `.text-secondary`     | Muted secondary             |
| Search button    | `.btn-primary`        | Blue (#0771ea override)     |
| Reset link       | `.text-secondary`     | Via `.btn.btn-link`         |

## Spacing Values

| Location              | Class(es)                                | Value         |
|-----------------------|------------------------------------------|---------------|
| Outer container       | `.px-0`, `.vstack.gap-4`                | 0 horiz, 1.5rem vert gap |
| Pack row              | `.hstack.gap-3`                         | 1rem gap      |
| Pack name row         | `.hstack.column-gap-2.row-gap-1`        | 0.5rem / 0.25rem |
| Inner column          | `.flex-column.gap-1`                    | 0.25rem gap   |
| Page title            | `.mb-1`                                 | 0.25rem       |
| Filter grid           | `.grid` (CSS Grid via Bootstrap)        | Default       |
| Empty state           | `.py-2`                                 | 0.5rem top/bottom |

## Custom CSS

| Class          | Source        | Description                                |
|----------------|---------------|--------------------------------------------|
| `.mb-last-0`   | `styles.scss` | Removes bottom margin from last child      |
| `.fs-7`        | `styles.scss` | Custom font size: `base * 0.9`             |
| `data-gy-toggle-submit` | JS attribute | Auto-submit on toggle change    |

## Inconsistencies

1. **Page title uses raw `<h1>`** while other pack pages use `<h1 class="h3">`. The design system debug page notes "Gyrinx typically uses `<h1 class='h3'>` for page titles."
2. **Search button is full-size `.btn.btn-primary`** (no `.btn-sm`), while the design system says "typically btn-sm in the app." The packs_filter search button lacks `.btn-sm` but the lists_filter compact version has it.
3. **Badge uses `.bg-secondary`** instead of the design system's `.text-bg-secondary` pattern. Both work but the design system documents `.text-bg-*` as the badge convention.
4. **Container width is `.col-lg-12`** which is effectively full-width. Other pack pages use `.col-12.col-xl-8`. This is intentional for a listing page but differs from detail pages.
5. **Mixed text colour approach:** Pack summary uses `.text-secondary`, owner link uses no colour class (inherits default link). This is fine but differs from pack detail which uses `.text-muted`.
6. **Mobile chevron uses `.d-md-none`** to hide on desktop, but the pack name link itself is always visible. There is no hover state or visual affordance for desktop click targets.

## Accessibility Notes

- Pagination includes `aria-label="Page navigation"`
- Search input has `aria-label="Search packs"`
- Toggle switch uses `role="switch"`
- Tooltip on "Your Packs Only" toggle for unauthenticated users uses `data-bs-toggle="tooltip"`
- Missing: No `aria-label` on the mobile chevron stretched-link
- Missing: The pack list has no landmark role (e.g., `role="list"` or semantic list element)
- Empty state text "No content packs available." is a plain div with no ARIA live region
