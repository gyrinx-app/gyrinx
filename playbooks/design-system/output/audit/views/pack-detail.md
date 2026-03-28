# View Audit: Pack Detail

## Metadata

| Field         | Value                                                     |
|---------------|-----------------------------------------------------------|
| URL           | `/pack/<id>`                                              |
| Template      | `core/pack/pack.html`                                     |
| Extends       | `core/layouts/base.html` > `core/layouts/foundation.html` |
| Includes      | `core/includes/back.html`, `core/includes/weapon_stat_headers.html`, `core/pack/includes/weapon_profiles_display.html`, `core/includes/pack_activity_item.html` |
| Template tags | `allauth`, `custom_tags`                                  |

## Components Found

### Navigation

- **Back button:** `core/includes/back.html` with `url="/packs/"` `text="Customisation"` -- uses breadcrumb pattern: `nav[aria-label="breadcrumb"] > ol.breadcrumb > li.breadcrumb-item.active` with `bi-chevron-left`
- **Section headers:** `div.d-flex.justify-content-between.align-items-center.mb-3.bg-body-secondary.rounded.px-2.py-1` with `h2.h5.mb-0` -- acts as a toolbar/section divider

### Buttons

- `.btn.btn-primary.btn-sm` -- "Add to List" with `bi-list-ul` icon, "Add to Campaign" with `bi-award` icon, section "Add" with `bi-plus-lg`
- `.btn.btn-secondary.btn-sm` -- "Edit" with `bi-pencil` icon
- `.btn.btn-secondary.btn-sm.dropdown-toggle` -- More options ("...") with `bi-three-dots-vertical`
- `.btn-group` -- Groups Edit button + More dropdown
- Nested `.btn-group` for dropdown sub-group

### Dropdowns

- Owner actions dropdown: `.dropdown-menu.dropdown-menu-end` with `.dropdown-item.icon-link` containing `bi-people` icon

### Badges

- `.badge.bg-primary-subtle` -- Count badges inside "Add to List" / "Add to Campaign" buttons

### Tables

- Weapon stats table: `.table.table-sm.table-borderless.mb-0.fs-7`
- Headers via `weapon_stat_headers.html`: `.table-group-divider` on `<thead>`, `th.text-center`, some with `.border-start`
- Profile rows via `weapon_profiles_display.html`: `.align-top` on `<tr>`, `.text-center` on stat cells

### Lists

- Fighter list: `ul.list-unstyled.mb-0` with `li.py-1`
- Generic item list: same pattern
- Activity list: `div.list-group.list-group-flush`

### Links

- Owner link: `a.linked` (custom class extending underline opacity)
- Archived items: `.link-secondary.link-underline-opacity-25.link-underline-opacity-100-hover.small`
- Edit/Archive item links: `.link-secondary...` / `.link-danger...` same pattern
- "View all" activity (header): `.link-primary.link-underline-opacity-25.link-underline-opacity-100-hover.small`
- "View all" activity (bottom): `.small.mt-2.d-inline-block` (no explicit link class)

### Icons

- `bi-list-ul` (Add to List)
- `bi-award` (Add to Campaign)
- `bi-pencil` (Edit)
- `bi-three-dots-vertical` (More options)
- `bi-people` (Permissions)
- `bi-person` (Owner)
- `bi-eye` / `bi-eye-slash` (Public / Unlisted visibility)
- `bi-plus-lg` (Add section item)
- `bi-dash` (Profile name prefix in weapon table)
- `bi-arrow-90deg-up` (Add profile action in weapon table)

### Tooltips

- Visibility indicator: `data-bs-toggle="tooltip"` with `data-bs-title` on public/unlisted spans

### Activity Item Component (`pack_activity_item.html`)

- Outer: `div.list-group-item.px-0`
- Header row: `small.text-muted.hstack.w-100.justify-content-between`
  - Left: `div.flex-grow-1` with `<strong>` for username/system
  - Right: `div.ms-auto` with `<em>` for timestamp
  - Separator: bullet character
- Body: `p.mb-0` for item description
- Changes list: `ul.mb-0.small.text-muted`

### Other

- **Section pattern:** `<section>` elements wrapping each content type and activity
- **Section header bar:** `div.bg-body-secondary.rounded.px-2.py-1` -- custom compound pattern not in design system
- **House grouping:** `.text-secondary.text-uppercase.small.mb-1` label for fighter groups
- **Empty states:** `p.text-center.text-secondary.mb-0` for content sections; `p.text-muted.small.mb-0` for activity

## Typography Usage

| Element                   | Tag / Class                         | Notes                              |
|---------------------------|-------------------------------------|------------------------------------|
| Page title                | `<h1 class="mb-0">`                | Raw `h1`, no `.h3`. Inconsistent with design system |
| Section headings          | `<h2 class="h5 mb-0">`             | Semantic `h2` styled as `h5`       |
| Owner/visibility metadata | `div.text-muted.small`             | Uses `.text-muted` (not `.text-secondary`) |
| Pack summary              | `div.mb-last-0` (no colour class)  | Default text colour                |
| Pack description          | `div.text-muted.fs-7.mb-last-0`    | Custom `.fs-7` + `.text-muted`     |
| House group label         | `.text-secondary.text-uppercase.small` | Manual caps label (not `.caps-label`) |
| Fighter name              | `span.fw-medium`                   | Medium weight for emphasis          |
| Fighter category          | `div.text-secondary.small`         | Secondary + small                   |

## Colour Usage

| Usage                | Class / Value            | Notes                          |
|----------------------|--------------------------|--------------------------------|
| Section header bg    | `.bg-body-secondary`     | Theme-aware surface colour     |
| Owner text           | `.text-muted`            | Differs from packs index       |
| Description text     | `.text-muted`            | Consistent with metadata       |
| Visibility icon      | No explicit class        | Inherits from `.text-muted` parent |
| Badge (count)        | `.bg-primary-subtle`     | Subtle primary                 |
| Archive link         | `.link-danger`           | Red for destructive action     |
| Edit link            | `.link-secondary`        | Grey for secondary action      |
| "View all" link      | `.link-primary`          | Primary colour for activity link |
| Empty state (content)| `.text-secondary`        | Grey                           |
| Empty state (activity)| `.text-muted`           | Inconsistent with content sections |

## Spacing Values

| Location                | Class(es)                          | Value           |
|-------------------------|------------------------------------|-----------------|
| Outer container         | `.col-12.col-xl-8.px-0.vstack.gap-5` | 3rem vert gap |
| Header stack            | `.vstack.gap-0`                    | No gap          |
| Header row              | `.gap-2.mb-2`                      | 0.5rem gap, 0.5rem bottom |
| Action nav              | `.gap-2.ms-md-auto`               | 0.5rem between buttons |
| Section header          | `.mb-3.px-2.py-1`                 | 1rem bottom, 0.5rem horiz, 0.25rem vert |
| Fighter list items      | `li.py-1`                          | 0.25rem top/bottom |
| Activity item           | `.px-0` on `.list-group-item`     | 0 horizontal     |
| Pack info section       | `.vstack.gap-1.col-md-9`          | 0.25rem gap, constrained width |
| Weapon action row       | `.d-flex.gap-1.small.mb-1`        | 0.25rem gap, 0.25rem bottom |

## Custom CSS

| Class            | Source          | Description                              |
|------------------|-----------------|------------------------------------------|
| `.mb-last-0`     | `styles.scss`   | Removes bottom margin from last child    |
| `.fs-7`          | `styles.scss`   | Custom font size: `base * 0.9`           |
| `.linked`        | `styles.scss`   | Link style with underline opacity        |
| `.table-group-divider` | `styles.scss` | Border between table sections          |

## Inconsistencies

1. **Page title uses raw `<h1 class="mb-0">`** without `.h3` -- the design system says page titles should use `<h1 class="h3">`.
2. **Mixed text muting classes:** Uses `.text-muted` for metadata and description but `.text-secondary` for empty states. The design system documents both but does not prescribe when to use each.
3. **House group label uses `.text-secondary.text-uppercase.small`** instead of the custom `.caps-label` class that combines these exact properties plus `fw-semibold` and `letter-spacing`.
4. **Section header bar** (`.bg-body-secondary.rounded.px-2.py-1`) is a custom compound pattern not documented in the design system debug page.
5. **Weapon action row "Archive" link** uses both `.link-secondary.link-underline-opacity-25.link-underline-opacity-100-hover` and `.text-danger` on the same element. The `.link-secondary` sets the link colour but `.text-danger` overrides it, creating a conflict.
6. **Two "View all" links** for activity: one in the section header (`.link-primary` with underline pattern) and one below the list (plain `<a>` with `.small.mt-2.d-inline-block`). Different styling for the same action.
7. **Badge uses `.bg-primary-subtle`** inside a `.btn-primary` button. Unusual nesting of subtle badge inside a primary-coloured button.
8. **Empty state patterns are inconsistent** across sections: content uses `p.text-center.text-secondary.mb-0`, activity uses `p.text-muted.small.mb-0` (different alignment, colour class, and size).

## Accessibility Notes

- Back button uses `nav[aria-label="breadcrumb"]` with proper ARIA
- Dropdown toggle has `aria-expanded="false"` and `aria-label="More options"`
- Visibility indicators use `data-bs-toggle="tooltip"` with `data-bs-title`
- Weapon table uses `scope="col"` on headers
- `<section>` elements provide good document outline
- Missing: Sections lack `aria-label` to describe their purpose
- Missing: No `aria-label` on the "Add" buttons to distinguish which section they add to
- Missing: Activity `list-group` lacks `role="list"`
- Missing: The "Archive" action relies solely on colour (`.text-danger`) to indicate destructive intent
