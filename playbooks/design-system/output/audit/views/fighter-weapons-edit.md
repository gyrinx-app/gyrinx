# View Audit: Fighter Weapons Edit

## Metadata

| Field           | Value                                                        |
| --------------- | ------------------------------------------------------------ |
| URL pattern     | `/list/<id>/fighter/<fid>/weapons`                           |
| URL name        | `core:list-fighter-weapons-edit`                             |
| Template        | `core/list_fighter_weapons_edit.html`                        |
| Extends         | `core/layouts/base.html`                                     |
| Includes        | `list_common_header.html`, `fighter_card_gear.html`, `fighter_gear_filter.html`, `list_fighter_weapons.html` |
| Template tags   | `allauth`, `custom_tags`                                     |
| Purpose         | Add weapons to a fighter from the available equipment catalogue |

## Components Found

### Buttons

| Element                      | Classes                         | Type      | Notes                                    |
| ---------------------------- | ------------------------------- | --------- | ---------------------------------------- |
| Add weapon button            | `btn btn-outline-primary btn-sm` | Bootstrap | In `list_fighter_weapons.html`, per weapon |
| Search button                | `btn btn-primary`               | Bootstrap | In `fighter_gear_filter.html`, no `btn-sm` |
| Clear search button          | `btn btn-outline-secondary`     | Bootstrap | Conditional, no `btn-sm`                  |
| Category dropdown            | `btn btn-outline-primary btn-sm dropdown-toggle` | Bootstrap | Filter dropdown               |
| Availability dropdown        | `btn btn-outline-primary btn-sm dropdown-toggle` | Bootstrap | Filter dropdown               |
| Cost dropdown                | `btn btn-outline-primary btn-sm dropdown-toggle` | Bootstrap | Filter dropdown               |
| Update filter button         | `btn btn-link icon-link btn-sm` | Bootstrap | Inside each dropdown                     |
| Reset filter link            | `btn btn-link text-secondary icon-link btn-sm` | Bootstrap | Inside each dropdown           |
| Equipment List toggle        | form-check form-switch          | Bootstrap | Toggle switch                            |
| Update (main)                | `btn btn-link icon-link btn-sm` | Bootstrap | Bottom of filter bar                     |
| Upgrade radio "None"         | `btn btn-sm` (via `btn-check`)  | Bootstrap | In upgrade form                          |
| Upgrade radio options        | `btn btn-outline-secondary btn-sm` (via `btn-check`) | Bootstrap | In upgrade form      |

### Cards

| Element                | Classes                          | Notes                                     |
| ---------------------- | -------------------------------- | ----------------------------------------- |
| Fighter card (gear)    | `card g-col-12 g-col-md-6`      | Via `fighter_card_gear.html`              |
| Equipment category card | `card g-col-12 g-col-md-6`     | One per equipment category                |
| Card header            | `card-header p-2`               | Consistent padding                        |
| Card body (category)   | `card-body vstack gap-2 p-0 p-sm-2` | Responsive padding, includes flash class |
| Card body (fighter)    | `card-body vstack p-0 p-sm-2 pt-2` | Slightly different from category cards  |

### Tables

| Element           | Classes                                          | Notes                                     |
| ----------------- | ------------------------------------------------ | ----------------------------------------- |
| Weapon stats table | `table table-sm table-borderless mb-0 fs-7`    | In `list_fighter_weapons.html`            |
| Statline table    | `table table-sm table-borderless table-fixed mb-0` | In `fighter_card_gear.html`            |
| Stats summary     | `table table-sm table-borderless table-responsive text-center mb-0` | In common header  |

### Navigation

| Component           | Source include                       | Notes                                       |
| ------------------- | ------------------------------------ | ------------------------------------------- |
| Common header       | `list_common_header.html`            | With fighter switcher                       |
| Fighter switcher    | `fighter_switcher.html`              | Dropdown to switch fighters on this page    |

### Forms

| Element                  | Classes / pattern                     | Notes                                            |
| ------------------------ | ------------------------------------- | ------------------------------------------------ |
| Hidden weapon forms      | `d-none` (one per weapon)            | Each weapon has its own hidden form              |
| Search/filter form       | `hstack gap-2 align-items-end`       | GET form in `fighter_gear_filter.html`           |
| Filter dropdowns         | Bootstrap dropdown menus              | Category, Availability, Cost                     |
| Checkbox filters         | `form-check`, `form-check-input`     | Standard Bootstrap form checks                   |
| Range inputs             | `form-range`                          | For availability level and cost sliders          |
| Number inputs            | `form-control fs-7`                  | Paired with range for sync                       |
| Upgrade form (weapons)   | radio `btn-check` + `btn-group`      | Toggle-style radio buttons                       |

### Icons

| Icon class              | Context                              |
| ----------------------- | ------------------------------------ |
| `bi-search`             | Search input group prepend           |
| `bi-plus`               | Add weapon button                    |
| `bi-arrow-clockwise`    | Update/Reset filter buttons          |
| `bi-exclamation-triangle` | Error message alert                |
| `bi-arrow-up-circle`    | Upgrade legend                       |
| `bi-dash`               | Sub-profile indicator                |
| `bi-crosshair`          | Weapon accessory indicator           |
| `bi-arrow-90deg-up`     | Weapon menu action arrow             |

### Other

- **Error alert**: `alert alert-danger g-col-12 mb-0` -- uses Bootstrap alert class (project convention says to avoid alerts, prefer `border rounded p-2`)
- **CSS grid layout**: Uses Bootstrap CSS Grid (`grid`, `g-col-12`, `g-col-md-6`)
- **Flash animation**: `{% flash "search" %}` template tag adds `flash-warn` class for highlight animation
- **Empty state text**: Plain text with conditional "Clear your search" link

## Typography Usage

| Element            | Classes      | Rendered size | Notes                              |
| ------------------ | ------------ | ------------- | ---------------------------------- |
| Page title         | `h1.h3`     | h3            | Semantic h1, visual h3             |
| Category heading   | `h3.h5 mb-0` | h5           | In card headers                    |
| Weapon table header | `fs-7`      | 0.9rem        | Custom smaller font size           |
| Weapon stats       | `fs-7`      | 0.9rem        | Stat cells and trait rows          |
| Filter dropdown text | `fs-7`    | 0.9rem        | Inside filter dropdown menus       |
| Filter label       | `form-label` | default       | Labels in dropdowns                |
| Equipment List label | `form-check-label fs-7 mb-0` | 0.9rem | Toggle switch label       |

## Colour Usage

| Usage                   | Class / value                | Notes                                  |
| ----------------------- | ---------------------------- | -------------------------------------- |
| Error alert             | `alert-danger`               | Red background alert                   |
| Add weapon button       | `btn-outline-primary`        | Blue outline                           |
| Search button           | `btn-primary`                | Solid blue                             |
| Clear button            | `btn-outline-secondary`      | Grey outline                           |
| Filter dropdowns        | `btn-outline-primary`        | Blue outline                           |
| Reset links             | `text-secondary`             | Grey/muted                             |
| Upgrade options         | `btn-outline-secondary`      | Grey outline radio toggle              |
| Rarity text             | `text-muted`                 | In weapon name area                    |
| Stat highlight          | `bg-warning-subtle`          | Modified stat cells (in statline)      |
| Dropdown menu           | `shadow-sm`                  | Subtle shadow                          |
| Weapon menu links       | `link-secondary`, `link-danger` | Edit/Reassign vs Delete             |
| Tooltipped underline    | `tooltipped` (custom)        | Info-colour underline                  |

## Spacing Values

| Element              | Spacing classes                 | Notes                                   |
| -------------------- | ------------------------------- | --------------------------------------- |
| Content column       | `px-0`                          | No horizontal padding                   |
| Layout               | `vstack gap-3`                  | 1rem vertical gap                       |
| Card header          | `p-2`                           | Consistent 0.5rem padding               |
| Card body            | `p-0 p-sm-2`                   | No padding on mobile, 0.5rem on sm+     |
| Card body (weapons)  | `p-0 p-sm-2` with `gap-2`      | Adds gap between weapon groups          |
| Filter bar           | `hstack gap-2`, `gap-3`        | Horizontal gaps for filter components   |
| Filter dropdowns     | `p-2`                           | Internal padding                        |
| Upgrade radio group  | `hstack gap-1`                  | Tight horizontal gap                    |

## Custom CSS

| Class              | Source          | Purpose                                        |
| ------------------ | --------------- | ---------------------------------------------- |
| `table-fixed`      | `styles.scss`   | Fixed table layout for stat tables              |
| `table-nowrap`     | `styles.scss`   | Overflow ellipsis for stat cells                |
| `tooltipped`       | `styles.scss`   | Info-coloured underline for tooltip elements    |
| `flash-warn`       | `styles.scss`   | Animated highlight for newly-added items        |
| `dropdown-menu-mw` | `styles.scss`  | Min/max width for filter dropdowns              |
| `fighter-switcher-btn` | `styles.scss` | Transparent button styling for fighter dropdown |
| `fighter-switcher-menu` | `styles.scss` | Scrollable dropdown menu                     |
| `linked`           | `styles.scss`   | Link underline opacity style                    |
| `table-group-divider` | `styles.scss` | Force border on borderless table groups         |

## Inconsistencies

1. **Error display pattern**: Uses `alert alert-danger` (Bootstrap alert) which the project convention says to avoid. The gear-edit view uses `border border-danger rounded p-2 text-danger` for the same purpose. These two sibling views handle errors differently.
2. **Card body padding differs**: Weapons card body uses `p-0 p-sm-2` with `gap-2`, while the fighter card gear body uses `p-0 p-sm-2 pt-2`. Subtle difference.
3. **Column width**: Uses `col-lg-12` (full width) while fighter-edit uses `col-12 col-md-8 col-lg-6`. Justified by the data-dense table layout, but worth noting.
4. **Search button sizing**: The search button in `fighter_gear_filter.html` uses `btn btn-primary` (default size) while the filter dropdown buttons use `btn-sm`. Mixed sizing in the same toolbar.
5. **"Add" button icon**: Weapons use `bi-plus` while skills use `bi-plus-lg`. Different icon variants for the same semantic action.

## Accessibility Notes

- Search input has `aria-label="Search"` -- good.
- Filter dropdown buttons have `aria-expanded="false"` -- standard Bootstrap.
- Weapon stat table headers use `scope="col"` -- good.
- Tooltips on stat cells provide explanation for modified values.
- The `btn-check` radio/checkbox pattern is keyboard accessible via Bootstrap.
- Hidden forms (`d-none`) have no ARIA impact since they are visually and programmatically hidden.
- No `aria-live` region for dynamic content updates after adding a weapon.
- Empty state messages are plain text -- no `role="status"` to announce to screen readers.
- Availability filter area disabled state uses `disabled` attribute and `disabled` class -- both applied.
