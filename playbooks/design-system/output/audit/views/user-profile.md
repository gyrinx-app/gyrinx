# View Audit: User Profile

## Metadata

- **URL:** `/user/<slug>`
- **Template:** `core/user.html`
- **Template chain:** `core/layouts/foundation.html` > `core/layouts/base.html` > `core/user.html`
- **Includes:** `core/includes/home.html` (breadcrumb)

## Components Found

### Buttons

None found.

### Cards

| Element | Classes | Notes |
|---------|---------|-------|
| User info card | `card card-body vstack gap-2` | Contains username, join date, staff badge, list count |

### Navigation

| Component | Classes | Notes |
|-----------|---------|-------|
| Breadcrumb | `breadcrumb` / `breadcrumb-item active` | Via home.html include; single-item breadcrumb to Home |

### Forms

None found.

### Icons (Bootstrap Icons)

| Icon class | Context | Purpose |
|------------|---------|---------|
| `bi-chevron-left` | Breadcrumb | Back navigation indicator |
| `bi-clock` | Join date | Time indicator |
| `bi-trophy-fill` | Staff badge | Staff indicator |
| `bi-list` | List count | Lists indicator |
| `bi-person` | List owner in public lists | Owner indicator |
| `bi-chevron-right` | Mobile list row | Forward navigation |

### Badges

| Text | Classes | Context |
|------|---------|---------|
| "Staff" | `badge text-bg-success` | Staff indicator in user card |
| Credits value | `badge text-bg-primary` | In public list rows |

### Other Components

| Component | Classes | Notes |
|-----------|---------|-------|
| List row | `hstack gap-3 position-relative` | Same row pattern as other views |
| Empty state | `<div class="py-2">` | "No lists yet." text |

## Typography Usage

| Element | Classes applied | Semantic role |
|---------|----------------|---------------|
| Username | `<h1>` with `h2 mb-0` | Page heading; semantic `<h1>` but styled as `h2` |
| "Public Lists" heading | `<h2>` with `h4` | Section heading |
| List name | `<h2>` with `mb-0 h5` | Item heading; second `<h2>` level reused for list items |
| Join date | plain `<div>` with icon | Metadata |
| List count | plain `<div>` with icon | Metadata |
| Owner name | plain `<div>` with icon | Metadata |

## Colour Usage

| Element | Property | Source | Semantic purpose |
|---------|----------|-------|-----------------|
| Staff badge | background | `text-bg-success` | Positive indicator |
| Credits badge | background | `text-bg-primary` | Primary highlight |
| Breadcrumb | color | default `.breadcrumb` styling | Navigation |

## Spacing Values

| Element | Property | Source class | Notes |
|---------|----------|-------------|-------|
| Outer row | gap | `row g-3` | Grid gap |
| User card column | width | `col-lg-4` | Sidebar width |
| Lists column | width | `col-lg-8` | Main content width |
| User card | gap | `vstack gap-2` | Card content gap |
| Lists vstack | gap | `vstack gap-2` | Between list rows |
| Staff badge row | gap | `hstack gap-2` | Icon and badge |
| List row | gap | `hstack gap-3` | Row items |
| Metadata line | gap | `hstack column-gap-2 row-gap-1 flex-wrap` | Inline items |
| Chevron right | padding | `p-3` | Touch target |
| Empty state | padding | `py-2` | Vertical padding |
| Page wrapper | padding | `px-0` on outer div | Removes horizontal padding |

## Custom CSS

None used in this template directly (all classes are Bootstrap utilities or components).

## Inconsistencies

| Issue | Elements involved | Description | Severity |
|-------|-------------------|-------------|----------|
| Heading level reuse | `<h2 class="h4">` then `<h2 class="h5">` | "Public Lists" and each list name both use `<h2>`. The list names should be `<h3>` for proper nesting. | Medium |
| Missing "last edit" metadata | User profile lists vs home/lists page lists | Home and lists pages show "Last edit: X ago" but user profile lists do not. | Low |
| Owner name not linked | `list.owner_cached` shown as plain text | On the lists index page, the owner name is a link to the user profile. Here it is plain text (since you are already on that user's profile). This is intentional but worth noting. | Low |
| No list type indicator | Profile lists vs lists page | Lists page shows "Campaign: X" or "List" badges; user profile shows neither. | Low |
| Missing `aria-label` on chevron | Mobile chevron link | No `aria-label` attribute. | Medium |

## Accessibility Notes

- Breadcrumb has `aria-label="breadcrumb"` and `aria-current="page"` via Bootstrap defaults.
- User card is a `<div>` not a landmark; could benefit from a heading or region role.
- Mobile chevron links lack `aria-label`.
- The heading hierarchy has issues: `<h1>` then two levels of `<h2>`.
