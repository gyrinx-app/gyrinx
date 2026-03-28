# View Audit: Fighter Gear Edit

## Metadata

| Field           | Value                                                        |
| --------------- | ------------------------------------------------------------ |
| URL pattern     | `/list/<id>/fighter/<fid>/gear`                              |
| URL name        | `core:list-fighter-gear-edit`                                |
| Template        | `core/list_fighter_gear_edit.html`                           |
| Extends         | `core/layouts/base.html`                                     |
| Includes        | `list_common_header.html`, `fighter_card_gear.html` (with `weapons_mode="gear"`, `gear_mode="edit"`), `fighter_gear_filter.html` |
| Template tags   | `allauth`, `custom_tags`                                     |
| Purpose         | Add gear (non-weapon equipment) to a fighter                 |

## Components Found

### Buttons

| Element                         | Classes                                | Type      | Notes                                     |
| ------------------------------- | -------------------------------------- | --------- | ----------------------------------------- |
| Add gear button                 | `btn btn-outline-primary btn-sm`       | Bootstrap | Per gear item, includes icon              |
| Search button                   | `btn btn-primary`                      | Bootstrap | In filter bar, no `btn-sm`                |
| Clear search button             | `btn btn-outline-secondary`            | Bootstrap | Conditional                               |
| Filter dropdown buttons         | `btn btn-outline-primary btn-sm dropdown-toggle` | Bootstrap | Same as weapons edit          |
| Update filter buttons           | `btn btn-link icon-link btn-sm`        | Bootstrap | Inside dropdowns                          |
| Reset filter links              | `btn btn-link text-secondary icon-link btn-sm` | Bootstrap | Inside dropdowns              |
| Upgrade radio "None"            | `btn btn-sm` (via `btn-check`)         | Bootstrap | For single-upgrade mode                   |
| Upgrade radio options           | `btn btn-outline-secondary btn-sm`     | Bootstrap | For single-upgrade mode                   |

### Cards

| Element                | Classes                          | Notes                                       |
| ---------------------- | -------------------------------- | ------------------------------------------- |
| Fighter card (gear)    | `card g-col-12 g-col-md-6`      | Via `fighter_card_gear.html`, `gear_mode="edit"` |
| Card footer            | `card-footer p-2 fs-7`          | "Edit weapons" link (from gear card)        |
| Equipment category card | `card g-col-12 g-col-md-6`     | One per gear category                       |
| Card header            | `card-header p-2`               | Consistent with weapons view                |
| Card body (category)   | `card-body vstack p-0 px-sm-2 py-sm-1` | Different padding from weapons view   |

### Tables

| Element           | Classes                                          | Notes                                     |
| ----------------- | ------------------------------------------------ | ----------------------------------------- |
| Statline table    | `table table-sm table-borderless table-fixed mb-0` | In fighter card gear                    |
| Stats summary     | `table table-sm table-borderless table-responsive text-center mb-0` | In common header  |

No weapon-stats table since this page is for non-weapon gear.

### Navigation

| Component           | Source include                       | Notes                                       |
| ------------------- | ------------------------------------ | ------------------------------------------- |
| Common header       | `list_common_header.html`            | With fighter switcher                       |
| Fighter switcher    | `fighter_switcher.html`              | Same as weapons view                        |

### Forms

| Element                  | Classes / pattern                     | Notes                                            |
| ------------------------ | ------------------------------------- | ------------------------------------------------ |
| Per-gear form            | `p-2 p-sm-0 py-sm-2 hstack gap-2`   | Inline form per gear item (visible, not hidden)  |
| Hidden query params      | Multiple hidden inputs                | Propagates filter state across POST              |
| Search/filter form       | Same as weapons via `fighter_gear_filter.html` | Shared component                      |
| Upgrade checkboxes       | `form-check fs-7`, `form-check-input` | For multi-upgrade mode                          |
| Upgrade radios           | `btn-check` + `btn-group`            | For single-upgrade mode (same as weapons)        |

### Icons

| Icon class              | Context                              |
| ----------------------- | ------------------------------------ |
| `bi-search`             | Search input prepend                 |
| `bi-plus`               | Add gear button                      |
| `bi-arrow-clockwise`    | Update/Reset filter                  |
| `bi-arrow-up-circle`    | Upgrade section legend               |
| `bi-arrow-90deg-up`     | Gear action menu arrow               |
| `bi-box-seam`           | Content pack indicator (in gear name)|

### Other

- **Error display**: `border border-danger rounded p-2 text-danger` with `<strong>Error:</strong>` prefix -- follows project convention (unlike weapons edit)
- **CSS grid layout**: `grid`, `g-col-12`, `g-col-md-6`
- **Flash animation**: `{% flash "search" %}` for highlight
- **Gear item layout**: Each gear item rendered as an inline form with hstack, unlike weapons which use a table
- **Upgrade display**: Supports two modes -- radio buttons (single upgrade) and checkboxes (multi upgrade)

## Typography Usage

| Element            | Classes        | Rendered size | Notes                                |
| ------------------ | -------------- | ------------- | ------------------------------------ |
| Page title         | `h1.h3`       | h3            | Semantic h1, visual h3               |
| Category heading   | `h3.h5 mb-0`  | h5            | In card headers                      |
| Gear item name     | `h4.h6 mb-0`  | h6            | Each gear item heading               |
| Gear cost          | `fs-7 text-muted` | 0.9rem    | Cost display beside name             |
| Rarity text        | `fs-7 text-muted` | 0.9rem    | Rarity level beside name             |
| Upgrade legend     | `legend.fs-7`  | 0.9rem       | Upgrade section label                |
| Checkbox labels    | `form-check-label` | default   | Standard Bootstrap                   |
| Filter labels      | `form-check-label fs-7 mb-0` | 0.9rem | Same as weapons view          |

## Colour Usage

| Usage                   | Class / value                   | Notes                                  |
| ----------------------- | ------------------------------- | -------------------------------------- |
| Error border            | `border-danger`, `text-danger`  | Red border and text -- follows convention |
| Add gear button         | `btn-outline-primary`           | Blue outline                           |
| Cost text               | `text-muted`                    | Grey/muted                             |
| Rarity text             | `text-muted`                    | Grey/muted                             |
| Upgrade options         | `btn-outline-secondary`         | Grey outline                           |
| Gear menu links         | `link-secondary`, `link-danger`, `link-warning` | Edit/Reassign, Delete, Sell |
| Tooltip default gear    | `tooltipped` (custom)           | Info-colour underline                  |
| Wargear default tooltip | `link-secondary link-underline-opacity-25 link-underline-opacity-100-hover` | Detailed inline classes |

## Spacing Values

| Element              | Spacing classes                       | Notes                                   |
| -------------------- | ------------------------------------- | --------------------------------------- |
| Content column       | `px-0`                                | No horizontal padding                   |
| Layout               | `vstack gap-3`                        | 1rem vertical gap                       |
| Card header          | `p-2`                                 | 0.5rem padding                          |
| Card body (category) | `p-0 px-sm-2 py-sm-1`                | Different from weapons: `py-sm-1` vs `p-sm-2` |
| Gear item form       | `p-2 p-sm-0 py-sm-2 hstack gap-2`    | Responsive padding per item             |
| Gear item inner      | `vstack gap-1`                        | Tight vertical stack                    |
| Upgrade radio group  | `hstack gap-1`                        | Same as weapons                         |

## Custom CSS

Same custom classes as weapons-edit view (see that audit). No gear-specific custom CSS.

## Inconsistencies

1. **Error display vs weapons-edit**: Gear uses `border border-danger rounded p-2 text-danger` (correct per convention), while weapons uses `alert alert-danger`. These sibling views should match.
2. **Card body padding differs from weapons**: Gear uses `p-0 px-sm-2 py-sm-1`, weapons uses `p-0 p-sm-2` with `gap-2`. The `py-sm-1` in gear gives tighter vertical spacing.
3. **Item layout differs from weapons**: Gear items are rendered as inline forms with `hstack`, while weapons use a `<table>`. This is a structural choice due to different data needs, but the visual feel differs.
4. **Column width**: Uses `col-12` (no responsive breakpoint) while weapons uses `col-lg-12`. Functionally identical (both full width) but the class is different.
5. **Heading depth**: Gear items use `h4.h6` while weapon category headings use `h3.h5`. Gear has one extra heading level.
6. **Tooltip approach for default gear**: In `fighter_card_gear.html`, default wargear tooltips use raw inline classes (`link-secondary link-underline-opacity-25 link-underline-opacity-100-hover`) instead of the `tooltipped` custom class. Inconsistent within the same include file.
7. **No `gap-2` on gear card body**: Weapons card body has `gap-2` between items; gear card body does not, relying on per-item padding instead. This can cause inconsistent spacing.

## Accessibility Notes

- Search input has `aria-label="Search"` -- good.
- Each gear form has a unique `id` (`gear-{{ assign.equipment.id }}`), and submit buttons reference it via `form=` attribute -- accessible pattern.
- Tooltips on default gear items explain "assigned by default" -- helpful context.
- Checkbox and radio inputs have proper `<label>` elements with `for` attributes.
- No `aria-live` region for dynamic content updates.
- Error display lacks `role="alert"`.
- The `<legend>` element for upgrades is used outside a `<fieldset>`, which is semantically incorrect.
