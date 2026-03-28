# View Audit: Pack Activity

## Metadata

| Field         | Value                                                     |
|---------------|-----------------------------------------------------------|
| URL           | `/pack/<id>/activity/`                                    |
| Template      | `core/pack/pack_activity.html`                            |
| Extends       | `core/layouts/base.html` > `core/layouts/foundation.html` |
| Includes      | `core/includes/back.html`, `core/includes/pack_activity_item.html`, `core/includes/pagination.html` |
| Template tags | `allauth`, `custom_tags`                                  |

## Components Found

### Navigation

- **Back button:** `core/includes/back.html` with `url=pack.get_absolute_url` and `text="Back to Content Pack"`
- **Pagination:** Standard `core/includes/pagination.html`

### Lists

- **Activity list:** `div.list-group.list-group-flush` containing activity items

### Activity Item Component (`pack_activity_item.html`)

- Outer: `div.list-group-item.px-0`
- Header row: `small.text-muted.hstack.w-100.justify-content-between`
  - Left: `div.flex-grow-1` with `<strong>` for username/system
  - Right: `div.ms-auto` with `<em>` for timestamp
  - Separator: `&bullet;` (bullet character)
- Body: `p.mb-0` for item description
- Changes list: `ul.mb-0.small.text-muted` for change details

### Other

- **Empty state:** `p.text-muted` for "No activity yet." (no `.small`, no `.mb-0`)

## Typography Usage

| Element                 | Tag / Class                | Notes                         |
|-------------------------|----------------------------|-------------------------------|
| Page title              | `<h1 class="h3 mb-0">`    | Correct `.h3` override       |
| Pack name subtitle      | `<h2 class="h5 text-muted">` | Semantic `h2` styled as `h5`, muted |
| Activity username       | `<strong>`                 | Bold within `small.text-muted` |
| Activity timestamp      | `<em>`                     | Italic within `small.text-muted` |
| Activity description    | `p.mb-0`                   | Default text size             |
| Activity changes        | `ul.mb-0.small.text-muted` | Small muted list              |

## Colour Usage

| Usage              | Class / Value     | Notes                       |
|--------------------|-------------------|-----------------------------|
| Activity metadata  | `.text-muted`     | Grey muted text             |
| Activity changes   | `.text-muted`     | Grey muted text             |
| Empty state        | `.text-muted`     | Consistent with activity items |

## Spacing Values

| Location              | Class(es)                         | Value              |
|-----------------------|-----------------------------------|--------------------|
| Outer container       | `.col-12.col-xl-8.px-0.vstack.gap-3` | 1rem vert gap  |
| Header block          | No gap class on inner div         | 0                  |
| Page title            | `.mb-0`                           | 0                  |
| Activity items        | `.px-0` override on list-group-item | 0 horizontal     |
| List group            | `.list-group-flush`               | No outer borders   |

## Custom CSS

None used beyond the base layout and standard Bootstrap classes.

## Inconsistencies

1. **Back button text says "Back to Content Pack"** while other pack pages use the pack name as the back text. The pack detail page uses `text="Customisation"` pointing to the index. There is no consistent convention for back button text.
2. **Page title + subtitle pattern** (`h1.h3` + `h2.h5.text-muted`) is unique to this page. Other pack pages put the pack name in the `h1`. This inverted hierarchy uses the pack name as a subtitle.
3. **Empty state uses `p.text-muted`** without `.small` or `.mb-0`, differing from:
   - Pack detail activity empty state: `p.text-muted.small.mb-0`
   - Pack detail content empty state: `p.text-center.text-secondary.mb-0`
   - Pack lists empty state: `div.py-2.text-muted.small`
4. **Outer container gap uses `.gap-3`** (1rem) while pack detail uses `.gap-5` (3rem) and pack lists uses `.gap-4` (1.5rem). No consistent gap size across pack pages.
5. **Activity item uses `.list-group-item.px-0`** which removes horizontal padding but retains the list-group-item border. The border-top of each item creates visual separation, but the combination of flush + px-0 is somewhat redundant since `.list-group-flush` already removes outer borders.
6. **Timestamp uses `<em>` (italic)** which is semantically "emphasis" but visually acts as a style differentiator. This is not documented in the design system.

## Accessibility Notes

- Back button inherits breadcrumb ARIA
- Pagination inherits proper ARIA from the include
- Activity items use semantic `<strong>` for usernames
- Missing: The activity list has no `aria-label` to describe its purpose
- Missing: Timestamps do not use `<time>` element with `datetime` attribute for machine-readable dates
- Missing: The relationship between `h1` (Activity) and `h2` (pack name) reverses the expected visual hierarchy, which could confuse screen reader users who navigate by heading level
