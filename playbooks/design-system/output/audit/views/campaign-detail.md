# View Audit: Campaign Detail

## Metadata

| Field | Value |
|---|---|
| URL | `/campaign/<id>` |
| Template | `core/campaign/campaign.html` |
| Extends | `core/layouts/base.html` |
| Template tags loaded | `allauth`, `custom_tags`, `color_tags` |
| Included templates | `core/includes/back.html`, `core/campaign/includes/campaign_lists.html` (which includes `list_row.html`), `core/campaign/includes/resource_row.html`, `core/includes/battle_summary_card.html`, `core/includes/campaign_action_item.html`, `core/includes/campaign_captured_fighters.html` |
| Complexity | High -- most complex campaign page with 7 sections and 6 included templates |

## Components Found

### Buttons

| Element | Classes | Variant | Context |
|---|---|---|---|
| Edit link | `btn btn-primary btn-sm` | Primary small | Header action bar |
| Start link | `btn btn-success btn-sm` | Success small | Header action bar (conditional) |
| End link | `btn btn-danger btn-sm` | Danger small | Header action bar (conditional) |
| Reopen link | `btn btn-success btn-sm` | Success small | Header action bar (conditional) |
| Dropdown toggle | `btn btn-secondary btn-sm dropdown-toggle` | Secondary small | Header overflow menu |
| Unarchive submit | `btn btn-sm btn-secondary` | Secondary small | Archive banner |
| Add Gangs (empty state) | `btn btn-primary btn-sm` | Primary small | campaign_lists.html empty state |
| Dropdown trigger (lists) | `btn btn-link btn-sm p-0 text-secondary` | Link small, custom padding | campaign_lists.html row actions |

**Observations:**

- Buttons consistently use `btn-sm` throughout
- Button group pattern (`nav btn-group flex-nowrap`) wraps primary action + conditional state button + overflow dropdown
- The `btn btn-link btn-sm p-0 text-secondary` pattern is used for inline dropdown triggers

### Cards

No Bootstrap `.card` components used. Content sections use:

- `border rounded p-2` for the archived banner (custom card-like container)
- `list-group-item` for battle summary cards and action items

### Tables

| Table | Classes | Context |
|---|---|---|
| Assets table | `table table-sm table-borderless mb-0 align-middle` | Per-asset-type listing |
| Resources table | `table table-sm table-borderless mb-0 align-middle` | Resource summary by gang |
| Gangs table (campaign_lists.html) | `table table-sm table-borderless mb-0 align-middle` | Gang listing |
| Captured fighters table | `table table-sm mb-0` | campaign_captured_fighters.html |

**Observations:**

- Three tables use `table-borderless`; captured fighters table does NOT, making it the only bordered table
- All tables use `table-sm` and `mb-0`
- `align-middle` is used on three of four tables but not on the captured fighters table

### Navigation

| Element | Classes | Context |
|---|---|---|
| Back breadcrumb | `breadcrumb` / `breadcrumb-item active` | Top of page, links to "All Campaigns" |
| Header btn-group | `nav btn-group flex-nowrap ms-md-auto` | Owner action buttons |

### Forms

| Form | Method | Context |
|---|---|---|
| Unarchive form | POST | Inline form in archive banner |

### Icons (Bootstrap Icons)

| Icon class | Context |
|---|---|
| `bi-archive` | Archive banner |
| `bi-pencil` | Edit button |
| `bi-play-circle` | Start button |
| `bi-stop-circle` | End button |
| `bi-arrow-clockwise` | Reopen button |
| `bi-three-dots` | Overflow menu trigger |
| `bi-box-arrow-in-down` | Copy to Campaign |
| `bi-box-arrow-up` | Copy from Campaign |
| `bi-tags` | Attributes menu item |
| `bi-box-seam` | Content Packs menu item |
| `bi-eye` / `bi-eye-slash` | Public/Unlisted visibility |
| `bi-person` | Owner metadata |
| `bi-info-circle` | Tooltip info icons (Assets, Resources, Action Log headings) |
| `bi-plus-circle` | Add Gangs, New Battle, Log Action links |
| `bi-arrow-left-right` | Transfer asset |
| `bi-file-text` | Battle report count |
| `bi-trophy-fill` | Battle winner indicator |
| `bi-flag` | Battle link in action item |
| `bi-dice-6` / `bi bi-dice-6` | Dice rolls in action items |
| `bi-three-dots` | List row dropdown trigger (campaign_lists.html) |
| `bi-trash` | Remove from Campaign (campaign_lists.html) |
| `bi-chevron-left` | Back breadcrumb |

**Observations:**

- Dice icon uses inconsistent class format: `bi bi-dice-6` (space-separated) in campaign_action_item.html vs the `bi-*` (hyphenated) pattern elsewhere

### Badges

| Classes | Context |
|---|---|
| `badge fw-normal text-bg-light border d-inline-flex align-items-center gap-1` | Attribute value tags on gang rows |
| `badge text-bg-warning` | "Pending" invitation badge (campaign_lists.html) |
| `badge bg-secondary` | "Sold" captured fighter status |
| `badge bg-warning text-dark` | "Captured" fighter status |

**Observations:**

- Attribute badges use `text-bg-light` (Bootstrap 5.3 pattern) while captured fighter badges use older `bg-*` pattern
- Inconsistent badge API: `text-bg-warning` vs `bg-warning text-dark` for warning badges

### Dropdowns

| Trigger | Menu classes | Context |
|---|---|---|
| `btn btn-secondary btn-sm dropdown-toggle` | `dropdown-menu dropdown-menu-end` | Header overflow menu |
| `btn btn-link btn-sm p-0 text-secondary` | `dropdown-menu dropdown-menu-end` | Gang row actions (campaign_lists.html) |

### Tooltips

| Element | Data attributes | Context |
|---|---|---|
| Public/Unlisted span | `data-bs-toggle="tooltip"`, `data-bs-title="..."` | Visibility indicator |
| Assets heading icon | `data-bs-toggle="tooltip"`, `data-bs-title="..."` | Section info |
| Resources heading icon | `data-bs-toggle="tooltip"`, `data-bs-title="..."` | Section info |
| Action Log heading icon | `data-bs-toggle="tooltip"`, `data-bs-title="..."` | Section info |

### Other Components

| Component | Classes/Pattern | Context |
|---|---|---|
| Section headers | `d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1` | Gangs, Assets, Resources, Battles, Action Log, Captured Fighters |
| List group (battles) | `list-group-item list-group-item-action px-0` | battle_summary_card.html |
| List group (actions) | `list-group-item px-0` | campaign_action_item.html |
| List group (invitations) | `list-group list-group-flush` / `list-group-item px-0` | Pending invitations (campaign_lists.html) |
| Colour dots | `d-inline-block rounded-circle` + inline `background-color` style | Group headers, attribute badges |

## Typography Usage

| Element | Classes | Usage |
|---|---|---|
| Page title | `h1` with `mb-0` | Campaign name |
| Section headings | `h2` with `h5 mb-0` | Gangs, Assets, Resources, Battles, Action Log, Captured Fighters |
| Gang row name | `h6 mb-1` (in list_row.html) | Gang name within table |
| Battle mission | `h6 mb-1` (in battle_summary_card.html) | Battle title |
| Metadata text | `small text-muted` or `text-muted small` | Owner, dates, stats, empty states |
| Caps label | `.caps-label` (custom: `small text-uppercase text-muted fw-semibold` + `letter-spacing: 0.03em`) | Status, Phase, Budget, Content Packs labels; table headers |
| Group header | `small text-uppercase text-secondary` + `strong` | Gang group name |
| Asset name | `fw-semibold` | Asset table cells |
| Dropdown header | `dropdown-header` (h6) | "Assets, Resources & Attributes" in overflow menu |
| Rich text content | via `safe_rich_text\|safe` filter | Summary, narrative, phase notes |
| Custom font size | `fs-7` (custom: 0.9rem) | Used in Assets header action links |

**Observations:**

- `text-muted` and `text-secondary` are used interchangeably -- e.g. group headers use `text-secondary` while most metadata uses `text-muted`
- The `small` class order varies: sometimes `small text-muted`, sometimes `text-muted small` (no functional difference but inconsistent)
- Rich text uses `mb-last-0` custom class to strip trailing margin from last child
- Custom `fs-7` used on the Assets header area links but not on equivalent links in Resources or other sections

## Colour Usage

| Colour | Bootstrap class | Context |
|---|---|---|
| Primary blue | `btn-primary`, `link-primary` | Edit button, Add links |
| Success green | `btn-success` | Start/Reopen buttons |
| Danger red | `btn-danger`, `text-danger`, `link-danger` | End button, Remove actions, error text |
| Warning yellow | `text-warning`, `text-bg-warning`, `bg-warning` | Trophy icon, Pending badge, Captured badge |
| Secondary grey | `btn-secondary`, `text-secondary`, `link-secondary`, `text-muted`, `bg-body-secondary` | Overflow toggle, metadata, section headers |
| Light | `text-bg-light` | Attribute value badges |
| Inline colour | `style="background-color: {{ value.colour }}"` | Group colour dots (10px circles), attribute colour dots (8px circles) |
| Inline border colour | `style="border-color: {{ group.colour }}; border-width: 2px; opacity: 0.5"` | Group separator `<hr>` |

**Observations:**

- `text-muted` and `text-secondary` both appear for grey text -- Bootstrap 5.3 recommends `text-body-secondary` but neither alias is used here
- Inline `background-color` styles for dynamic colour dots -- two different sizes used (10px in gangs/resources group headers, 8px in attribute badge dots in campaign_lists.html)
- Captured fighters badges use inconsistent patterns: `bg-secondary` and `bg-warning text-dark` vs `text-bg-*` used elsewhere

## Spacing Values

| Spacing class | Count/Context |
|---|---|
| `gap-5` | Main page column vstack; row gutters between Assets/Resources and Battles/Action Log |
| `gap-3` | Section header hstack; campaign info flex items |
| `gap-2` | Header flex layout; metadata flex; battle vstack; action vstack; attribute hstack; misc |
| `gap-1` | Summary/narrative vstack; attribute badge hstack in campaign_lists.html |
| `gap-0` | Header vstack |
| `mb-0` | h1, h2, p in various places |
| `mb-1` | h6 in list_row and battle_summary_card |
| `mb-2` | Header d-flex; caps-label in asset table; campaign info border-bottom |
| `mb-3` | Section header mb; content packs edit link; pagination vstack |
| `mt-2` | Pending invitations border-top; "View all" link |
| `py-1` | Section headers |
| `py-3` | Empty captured fighters |
| `px-0` | Main column; list-group items; table cells (ps-0) |
| `px-2` | Section headers; archive banner |
| `p-2` | Archive banner |
| `p-3` | Empty gangs state |
| `pb-3` | Campaign info border-bottom |
| `pt-3` | Group rows (non-first) |

**Observations:**

- Main vertical stacking uses `gap-5` for major sections
- Section headers consistently use `mb-3 px-2 py-1` with `bg-body-secondary rounded`
- The archive banner uses `p-2` (all-sides padding) while section headers use `px-2 py-1` (different vertical padding)

## Custom CSS

| Class | Source | Usage in this view |
|---|---|---|
| `caps-label` | `styles.scss` | Table headers, info labels (Status, Phase, Budget, Content Packs) |
| `mb-last-0` | `styles.scss` | Rich text containers (summary, narrative, phase_notes) |
| `linked` | `styles.scss` | Action item links, owner link, battle links |
| `fs-7` | `styles.scss` (custom font size map) | Assets header links |
| `w-em-*` | `styles.scss` | Not used directly in campaign.html but used in campaign_assets.html |
| `flash-warn` | `styles.scss` | Not used in this view |
| `{% property_nowrap_class %}` | Template tag | Asset property spans -- generates CSS class dynamically |
| `{% list_with_theme %}` | Template tag | Renders gang name with theme colour |
| `{% credits %}` | Template tag | Formats credit values |

## Inconsistencies

1. **Badge pattern inconsistency**: Captured fighters use `bg-secondary` and `bg-warning text-dark` (Bootstrap 4/early 5 pattern) while attribute badges use `text-bg-light` (Bootstrap 5.3 pattern). Should standardize on `text-bg-*`.

2. **Icon class format**: `campaign_action_item.html` uses `bi bi-dice-6` (space-separated prefix) while all other icons use the `bi-*` hyphenated format (e.g. `bi-person`, `bi-pencil`).

3. **Colour dots inconsistency**: Group header dots are `10px` (in both campaign.html and campaign_lists.html) while attribute badge dots in campaign_lists.html are `8px`. The campaign_attributes.html page uses `16px` for the same concept.

4. **text-muted vs text-secondary**: Both used for grey/secondary text with no clear rule. Group headers use `text-secondary` while all other metadata uses `text-muted`.

5. **Table consistency**: Captured fighters table uses `table table-sm mb-0` (with borders) while all other tables use `table table-sm table-borderless mb-0 align-middle` (borderless, aligned).

6. **Empty state pattern inconsistency**: Assets/Resources empty states use `p.text-muted.small.mb-0`, captured fighters uses `p.text-muted.mb-0.text-center.py-3`, gangs uses `div.p-3.text-center.text-muted`. No uniform empty-state component.

7. **Link style inconsistency**: "Copy from Campaign" non-owner link uses `icon-link link-secondary link-underline-opacity-25 link-underline-opacity-100-hover small` while section "View all" links use `link-primary link-underline-opacity-25 link-underline-opacity-100-hover small`. The `linked` class (custom) is used in action items but not in the main template.

8. **Section header pattern**: Six section headers use the identical `d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1` pattern, which is good consistency. However this pattern is NOT extracted into an include -- it is repeated inline each time.

9. **Resource table edit icon**: In `resource_row.html`, the edit pencil uses `link-secondary small ms-1` with no `link-underline-opacity-*` classes, which differs from how edit links are styled elsewhere.

## Accessibility Notes

- Back navigation uses `<nav aria-label="breadcrumb">` with proper ARIA semantics
- Dropdown overflow menu has `aria-expanded="false"` and `aria-label="More options"`
- Tooltips use `data-bs-toggle="tooltip"` with descriptive `data-bs-title` text
- Skip-to-content link (`visually-hidden-focusable`) is in the base layout
- Missing: `<section>` elements lack `aria-label` or `aria-labelledby` attributes to connect them with their h2 headings
- Missing: Tables lack `<caption>` elements for screen readers
- Missing: The colour dots (group indicators) rely solely on colour with no text alternative -- partially mitigated by the adjacent group name text
- Concern: Inline dropdown triggers (`btn btn-link btn-sm p-0`) may have insufficient touch target size on mobile (no minimum 44x44px guarantee)
