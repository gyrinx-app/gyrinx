# View Audit: List Detail

## Metadata

- **URL**: `/list/<id>`
- **Template**: `core/list.html`
- **Extends**: `core/layouts/base.html` -> `core/layouts/foundation.html`
- **Template tags loaded**: `allauth`, `custom_tags`, `color_tags`, `group_tags`
- **Key includes**:
  - `core/includes/list.html` (main content)
  - `core/includes/list_common_header.html` (gang header with stats table)
  - `core/includes/list_campaign_actions.html` (campaign actions card)
  - `core/includes/list_campaign_resources_assets.html` (resources/assets card)
  - `core/includes/list_attributes.html` (gang attributes card)
  - `core/includes/fighter_card.html` -> `fighter_card_content.html` -> `fighter_card_content_inner.html`
  - `core/includes/fighter_card_stash.html`
  - `core/includes/list_fighter_weapons.html` -> `list_fighter_weapon_rows.html`
  - `core/includes/fighter_card_cost.html`
  - `core/includes/fighter_card_weapon_menu.html`
  - `core/includes/parent_fighter_link.html`
  - `core/includes/rule.html`
  - `core/includes/gear_assign_name.html`
  - `core/includes/list_fighter_statline.html`
  - `core/includes/list_fighter_weapon_profile_statline.html`
  - `core/includes/list_fighter_weapon_assign_name.html`
  - `core/includes/campaign_action_item.html`
  - `core/includes/fighter_switcher.html`
  - `core/campaign/includes/status.html`
  - `core/includes/site_banner.html`

## Components Found

### Buttons

| Pattern | Classes | Location |
|---------|---------|----------|
| Add fighter | `btn btn-primary btn-sm` | list.html toolbar |
| Add vehicle | `btn btn-primary btn-sm` | list.html toolbar |
| Print | `btn btn-secondary btn-sm d-none d-sm-inline-flex` | list.html toolbar (hidden mobile) |
| Edit | `btn btn-secondary btn-sm` | list.html toolbar |
| More options (dropdown toggle) | `btn btn-secondary btn-sm dropdown-toggle` | list.html toolbar |
| Invitations | `btn btn-info text-bg-info btn-sm` | list.html toolbar (conditional) |
| Unarchive | `btn btn-sm btn-secondary` | list.html archive banner |
| Add a fighter (empty state) | `btn btn-primary` | list.html empty list (**no `btn-sm`**) |
| Add a vehicle (empty state) | `btn btn-primary` | list.html empty list (**no `btn-sm`**) |
| Refresh cost | `btn btn-link btn-sm p-0 text-secondary` | list_common_header.html |
| Edit (fighter card) | `btn btn-outline-secondary btn-sm` | fighter_card_content.html |
| Split dropdown (fighter) | `btn btn-outline-secondary btn-sm dropdown-toggle dropdown-toggle-split` | fighter_card_content.html |
| Clipboard copy | `btn btn-outline-secondary btn-sm` | embed offcanvas |
| Close offcanvas | `btn-close` | embed offcanvas |
| Log Action | `icon-link small` (link, not button) | list_campaign_actions.html |
| Add outcome | `linked` (link) | campaign_action_item.html |

### Cards

| Pattern | Classes | Location |
|---------|---------|----------|
| Fighter card | `card {grid_classes} break-inside-avoid` | fighter_card_content.html |
| Fighter card header | `card-header p-2 hstack align-items-start` | fighter_card_content.html |
| Fighter card header (dead) | `card-header p-2 hstack align-items-start bg-danger-subtle` | fighter_card_content.html |
| Fighter card header (captured/sold) | `card-header p-2 hstack align-items-start bg-warning-subtle` | fighter_card_content.html |
| Fighter card body | `card-body p-0` | fighter_card_content.html |
| Stash card | `card {grid_classes} break-inside-avoid` | fighter_card_stash.html |
| Stash card header | `card-header p-2` | fighter_card_stash.html |
| Stash card body | `card-body vstack gap-2 p-0 p-sm-2 pt-2` | fighter_card_stash.html |
| Navigation (in-card) card | `nav card card-body flex-column mb-3 p-2` | (used in about/notes, not detail) |

### Tables

| Pattern | Classes | Location |
|---------|---------|----------|
| Stats summary (header) | `table table-sm table-borderless table-responsive text-center mb-0` | list_common_header.html |
| Fighter statline | `table table-sm table-borderless table-fixed mb-0` | fighter_card_content_inner.html |
| Weapons table | `table table-sm table-borderless mb-0 fs-7` | list_fighter_weapons.html |
| Attributes table | `table table-sm table-borderless mb-0 fs-7` | list_attributes.html |
| Fighter type summary | `table table-borderless table-sm mb-0 fs-7` | list_attributes.html |
| Resources table | `table table-sm table-borderless mb-0 fs-7` | list_campaign_resources_assets.html |
| Stash gear table | `table table-sm table-borderless mb-0` | fighter_card_stash.html |
| Stash weapons table | `table table-sm table-borderless mb-0 fs-7` | fighter_card_stash.html |

### Navigation

| Pattern | Classes | Location |
|---------|---------|----------|
| Toolbar nav | `nav hstack gap-1 flex-nowrap` | list.html |
| Fighter tabs | `nav nav-tabs flex-grow-1 px-1` | fighter_card_content.html |
| Tab buttons | `nav-link fs-7 px-2 py-1` | fighter_card_content.html |
| Tab content | `tab-content`, `tab-pane fade show active vstack` | fighter_card_content.html |
| Button group (Edit + dropdown) | `btn-group` | fighter_card_content.html |
| Button group (toolbar) | `btn-group` (nested) | list.html toolbar |
| Fighter switcher dropdown | `dropdown` with custom `fighter-switcher-btn` | fighter_switcher.html |

### Dropdowns

| Pattern | Classes | Location |
|---------|---------|----------|
| Toolbar more options | `dropdown-menu` | list.html |
| Fighter actions | `dropdown-menu` | fighter_card_content.html |
| Dropdown items | `dropdown-item icon-link` | list.html |
| Dropdown items (danger) | `dropdown-item text-danger` | fighter_card_content.html |
| Dropdown items (disabled) | `dropdown-item icon-link disabled` | list.html (stash toggle) |
| Dropdown divider | `dropdown-divider` | list.html, fighter_card_content.html |
| Dropdown header | `dropdown-header text-uppercase small` | list.html (Internal section) |
| Fighter switcher menu | `dropdown-menu dropdown-menu-end fighter-switcher-menu` | fighter_switcher.html |

### Badges

| Pattern | Classes | Context |
|---------|---------|---------|
| XP | `badge text-bg-primary` | fighter_card_content_inner.html |
| Counter value | `badge text-bg-secondary` | fighter_card_content_inner.html |
| Advancement count | `badge text-bg-success` | fighter_card_content_inner.html |
| Cost (normal) | `badge text-bg-secondary bg-secondary` | fighter_card_cost.html |
| Cost (overridden) | `badge text-bg-warning bg-warning` | fighter_card_cost.html |
| Cost (print) | `badge text-body border fw-normal` | fighter_card_cost.html |
| Injury state (injured) | `badge ms-2 bg-warning` | fighter_card_content.html |
| Injury state (dead) | `badge ms-2 bg-danger` | fighter_card_content.html |
| Captured | `badge ms-2 bg-warning text-dark` | fighter_card_content.html |
| Sold to Guilders | `badge ms-2 bg-secondary` | fighter_card_content.html |
| Campaign status | `badge bg-secondary` / `badge bg-success` | campaign status.html |
| Invitation count | `badge bg-info ms-1` | list.html dropdown |
| Stash credits | `badge bg-primary fs-7` | fighter_card_stash.html |

### Forms

| Pattern | Classes | Location |
|---------|---------|----------|
| Refresh cost form | inline form with `d-inline` | list_common_header.html |
| Weapon add forms | `d-none` hidden forms | list_fighter_weapons.html |
| Checkbox (weapon profiles) | `form-check`, `form-check-input`, `form-check-label` | list_fighter_weapon_rows.html |

### Icons (Bootstrap Icons)

Used extensively throughout. Key icons:

- `bi-archive` - archive/archived
- `bi-person-add` - add fighter
- `bi-truck` - add vehicle
- `bi-printer` - print
- `bi-pencil` - edit
- `bi-three-dots-vertical` - more options
- `bi-eye` / `bi-eye-slash` - public/unlisted
- `bi-file-text` - lore
- `bi-journal-text` - notes
- `bi-copy` - clone
- `bi-award` - campaign
- `bi-box-seam` - content packs
- `bi-person` - owner
- `bi-arrow-clockwise` - refresh
- `bi-person-bounding-box` - embed
- `bi-plus-circle` - show stash
- `bi-flag` - actions
- `bi-envelope` - invitations
- `bi-exclamation-triangle` - mark captured
- `bi-heartbreak` - kill
- `bi-heart-pulse` - resurrect
- `bi-trash` - delete
- `bi-dash` - sub-item indicator (weapon profiles)
- `bi-crosshair` - weapon accessories
- `bi-arrow-up-circle` - weapon upgrades
- `bi-arrow-90deg-up` - sub-menu indicator
- `bi-dot` - content indicator on tabs
- `bi-clipboard` / `bi-check2` - copy/copied
- `bi-plus` - add
- `bi-arrow-left-right` - transfer

### Other Components

| Pattern | Classes | Location |
|---------|---------|----------|
| Offcanvas (embed) | `offcanvas offcanvas-end` | list.html |
| Archive banner | `border rounded p-2 mb-3 hstack gap-2 align-items-center text-secondary` | list.html |
| Section headers | `bg-body-secondary rounded px-2 py-1 mb-2` | list_attributes.html, list_campaign_resources_assets.html |
| Section header (with action) | `bg-body-secondary rounded px-2 py-1 mb-1 hstack gap-2 align-items-center` | list_campaign_actions.html |
| Caps label | `caps-label mb-1` (custom class) | list_campaign_resources_assets.html |
| Grid layout | `grid auto-flow-dense` (CSS grid with custom class) | list.html |
| Fighter groups | `grid h-100 gap-2 gap-md-0 border rounded p-2 bg-secondary-subtle` | list.html |
| List group (embed) | `list-group`, `list-group-item vstack gap-2` | list.html embed offcanvas |
| List group item (action) | `list-group-item px-0` | campaign_action_item.html |
| Tooltipped text | `tooltipped` (custom class) | various |
| QR code | `sq-6` (custom class, 6em square) | list.html (print mode) |
| Debug banner | `bg-warning-subtle border border-warning rounded px-2 py-1 mb-2 fs-7 font-monospace` | list_common_header.html |
| Flash animation | `flash-warn` (custom class) | fighter cards |

## Typography Usage

| Element | Classes | Size | Context |
|---------|---------|------|---------|
| Gang name | `h3` (via `h2.mb-0.h3`) | h3 size | list_common_header.html |
| Owner name | `fs-7 text-muted` | ~0.79rem (0.9 * 0.875rem) | list_common_header.html |
| House / campaign info | `fs-7` | ~0.79rem | list_common_header.html |
| Stats table headers | `fs-7` (screen) / `fs-6` (values) | varies by mode | list_common_header.html |
| Metadata links row | `fs-7` | ~0.79rem | list.html |
| Fighter name | `h5 mb-0` (via `h3.h5`) | h5 size | fighter_card_content.html |
| Fighter type | default size (no class) | base | fighter_card_content.html |
| Tab buttons | `fs-7 px-2 py-1` | ~0.79rem | fighter_card_content.html |
| Stat headers | `fs-7` (screen) / `fs-5` (print) | varies | fighter_card_content_inner.html |
| Stat values | `fs-7` (screen) / `fs-5` (print) | varies | list_fighter_statline.html |
| Detail rows | `fs-7` | ~0.79rem | fighter_card_content_inner.html |
| Weapons table | `fs-7` | ~0.79rem | list_fighter_weapons.html |
| Section headers | `h5 mb-0` (via `h3.h5`) | h5 size | list_attributes.html, etc. |
| Sub-section headers | `caps-label mb-1` | small, uppercase, semibold | various |
| Stash credits header | `h6 mb-0` (via `h4.h6`) | h6 size | fighter_card_stash.html |
| Embed fighter name | `h6 mb-0` (via `h3.h6`) | h6 size | list.html embed offcanvas |
| Code snippets | `code` | default | embed offcanvas |
| Debug text | `fs-7 font-monospace` | ~0.79rem, monospace | list_common_header.html |
| Empty state text | default | base | list.html |

## Colour Usage

| Colour | Bootstrap Class | Context |
|--------|----------------|---------|
| Primary (blue `#0771ea`) | `btn-primary`, `text-bg-primary`, `bg-primary` | Add fighter/vehicle buttons, XP badge, stash credits badge |
| Secondary | `btn-secondary`, `text-bg-secondary`, `bg-secondary`, `text-secondary`, `link-secondary`, `bg-body-secondary` | Edit/print buttons, cost badges, section headers, muted text |
| Info | `btn-info text-bg-info`, `bg-info` | Invitations button/badge |
| Warning | `bg-warning`, `bg-warning-subtle`, `text-bg-warning`, `link-warning` | Injury/captured badges, cost override, stat highlights, sell links |
| Danger | `bg-danger`, `bg-danger-subtle`, `text-danger`, `link-danger` | Dead badge, dead card header, archive/delete actions |
| Success | `bg-success`, `text-bg-success` | Campaign "In Progress" badge, advancement badge |
| Muted text | `text-muted` | Metadata, timestamps, empty states, secondary info |
| Body secondary | `bg-body-secondary` | Section header backgrounds |
| Secondary subtle | `bg-secondary-subtle` | Fighter group background |

## Spacing Values

| Property | Values Used | Context |
|----------|-------------|---------|
| Container margin | `my-3 my-md-5` | base.html body wrapper |
| Outer stack gap | `gap-5` | list.html wrapper |
| Inner grid gap | `gap-2` (print) / default (screen) | list.html grid |
| Card header padding | `p-2` | fighter cards |
| Card body padding | `p-0` (print/compact) / `p-0 p-sm-2` (screen) | fighter cards |
| Section header padding | `px-2 py-1` | section headers |
| Tab padding | `px-2 py-1` | fighter tabs |
| Tab content padding | `p-2` | lore/notes tab panes |
| Toolbar gap | `gap-1` | nav hstack |
| Card header gap | `gap-1` (vstack), `gap-2` (hstack) | fighter cards |
| Margin below header | `mb-2` | various headers |
| Grid item margins | `mt-4` | fighter card grid wrapper |
| Stash card body gap | `gap-2` | stash card body |
| Badge margin | `ms-2` | injury/state badges |

## Custom CSS

| Class | Definition | Used In |
|-------|-----------|---------|
| `linked` | `link-underline-opacity-25 link-underline-opacity-100-hover link-offset-1` | Various links throughout |
| `link-sm` | Same as `linked` + `fs-7` | Stash trading post links |
| `tooltipped` | `link-underline-opacity-50 link-underline-info link-underline-opacity-100-hover link-offset-1 text-decoration-underline` | Modified stats, default weapons |
| `table-group-divider` | Override with `!important` border-top | Table section dividers |
| `table-fixed` | `table-layout: fixed; width: 100%` | Fighter statline table |
| `table-nowrap` | Within `.table-fixed`, overflow hidden + text-overflow ellipsis | Stat value row |
| `auto-flow-dense` | `grid-auto-flow: row dense` | Fighter card grid |
| `break-inside-avoid` | `break-inside: avoid` | Fighter cards, groups |
| `flash-warn` | Keyframe animation from warning-bg-subtle to inherit | Highlight recently changed items |
| `caps-label` | `small text-uppercase text-muted fw-semibold` + letter-spacing | Sub-section headers |
| `sq-6` | `height: 6em; width: 6em` | QR code container |
| `size-em-5` | `width: 16em; height: 16em` | Fighter images (lore) |
| `fighter-switcher-btn` | Transparent button, underline on hover | Fighter switcher dropdown |
| `fighter-switcher-menu` | `max-height: 20em; overflow-y: auto` | Fighter switcher dropdown |
| `pack-icon` | (no custom CSS, just icon styling) | Content pack indicators |

## Inconsistencies

1. **Empty state button sizing**: When the list is empty, "Add a fighter" and "Add a vehicle" buttons use `btn btn-primary` (no `btn-sm`), but the same buttons in the toolbar use `btn btn-primary btn-sm`. This creates a size inconsistency between the two locations for the same action.

2. **Section header inconsistency**: The Actions section header uses `mb-1` while Assets & Resources uses `mb-2` and Attributes uses `mb-2`. The Actions header also includes `hstack gap-2 align-items-center` for the inline "Log Action" link, while the others don't have actions in the header.

3. **Cost badge double-class**: `fighter_card_cost.html` uses `text-bg-secondary bg-secondary` and `text-bg-warning bg-warning` -- the `bg-*` classes are redundant since `text-bg-*` already sets the background.

4. **Heading level inconsistency**: Section headers use `h3` with class `h5` consistently, but stash sub-headers use `h4` with class `h6`, and the embed offcanvas uses `h3` with class `h6`. The semantic heading hierarchy is inconsistent -- `h3.h5` is used for both the gang name and section headers.

5. **Fighter card body classes**: The stash card body uses `vstack gap-2 p-0 p-sm-2 pt-2`, while regular fighter card bodies use `p-0` (print) or `p-0 p-sm-2` (screen). The stash card has an extra `pt-2` that regular cards don't.

6. **Link style variation for inline actions**: Weapon menu uses `link-secondary` and `link-danger` for action links with `{% dot %}` separators, but the stash gear section uses `link-secondary`, `link-warning`, and `link-danger` with `text-muted` dot separators (`<span class="text-muted">.</span>`). Two different separator patterns for the same conceptual UI.

7. **Tab content padding inconsistency**: The "Card" tab pane uses body_classes_ (`p-0 p-sm-2`), but Lore and Notes tab panes use a hardcoded `p-2`.

8. **Stats table font size switching**: Stat headers/values use `fs-7` on screen and `fs-5` in print mode. But the weapons table always uses `fs-7` regardless of print mode. The stat summary in `list_common_header.html` uses `fs-7` for headers and `fs-6` for values (a different pairing).

9. **Inconsistent grid column classes**: Fighter cards default to `g-col-12 g-col-md-6 g-col-xl-4` in screen mode but `g-col-12 g-col-sm-6 g-col-md-3 g-col-xl-2` in print mode. The inner_grid_layout_classes in list.html for non-grouped fighters uses `g-col-12 g-col-xl-8` (screen) vs `g-col-12 g-col-sm-6 g-col-md-6 g-col-xl-4` (print), but this outer wrapper class doesn't match the card grid classes at all.

10. **Mixed tooltip patterns**: Some tooltips use `data-bs-toggle="tooltip" data-bs-title="..."`, others use `data-bs-toggle="tooltip" title="..."`, and some also add `bs-tooltip` attribute. Three different patterns for the same functionality.

11. **Embed offcanvas has semantic issues**: The offcanvas body contains `<ul class="list-group">` with `<p>` tags as direct children before the `<li>` items.

12. **`text-muted` vs `text-secondary`**: Both are used throughout to convey the same concept of de-emphasized text. `text-muted` is the older Bootstrap pattern; `text-secondary` is the newer one. They're used interchangeably.

## Accessibility Notes

1. **Skip link**: The base layout includes `<a class="visually-hidden-focusable" href="#content">Skip to main content</a>`, which is good.

2. **Icon-only buttons**: The print button in the toolbar uses `<span class="visually-hidden">Print</span>` for screen readers. The "More options" dropdown toggle uses `aria-label="More options"`. However, the refresh cost button only has `aria-label` via tooltip title -- the pattern is inconsistent.

3. **Tab ARIA**: Fighter tabs use proper `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-controls`, `aria-selected`, and `tabindex="0"`. This is correct.

4. **Dropdown ARIA**: The more options dropdown uses `aria-expanded="false"` and `aria-label`. The fighter switcher also uses `aria-label="Switch to another fighter"`.

5. **Table headers**: Stats table headers in `list_common_header.html` include `aria-label` attributes for abbreviated headings (R, Cr, St, W), which is good. However, the weapon table headers (S, L, Str, Ap, D, Am) do not have aria-labels.

6. **Tooltip-dependent content**: Some information is only conveyed through tooltips (e.g., "This list is visible to all users" for Public), which may not be accessible to all users. The `.tooltipped` class uses underline decoration to hint at interactive content.

7. **Missing landmarks**: The fighter card grid doesn't use landmark roles. The toolbar uses `<nav>` but the dropdown-containing `btn-group` is nested inside another `<nav>`, creating potentially confusing navigation landmarks.

8. **Colour-only indicators**: The state badges (bg-warning for injured, bg-danger for dead) convey state through colour plus text, which is accessible. However, the stat highlight (`bg-warning-subtle`) conveys modification status through colour alone -- the tooltipped class provides a secondary cue.

9. **Embed offcanvas**: Uses `aria-labelledby="embedOffcanvasLabel"` and `aria-label="Close"` on the close button.
