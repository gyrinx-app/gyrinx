# View Audit: Fighter Skills Edit

## Metadata

| Field           | Value                                                        |
| --------------- | ------------------------------------------------------------ |
| URL pattern     | `/list/<id>/fighter/<fid>/skills`                            |
| URL name        | `core:list-fighter-skills-edit`                              |
| Template        | `core/list_fighter_skills_edit.html`                         |
| Extends         | `core/layouts/base.html`                                     |
| Includes        | `list_common_header.html`, `fighter_skills_filter.html`      |
| Template tags   | `allauth`, `custom_tags`                                     |
| Purpose         | View/manage default skills, user-added skills, and add new skills from categories |

## Components Found

### Buttons

| Element                      | Classes                                     | Type      | Notes                                     |
| ---------------------------- | ------------------------------------------- | --------- | ----------------------------------------- |
| Enable default skill         | `btn btn-link icon-link fs-7 link-success`  | Bootstrap | Toggle button in table                    |
| Disable default skill        | `btn btn-link icon-link fs-7 link-danger`   | Bootstrap | Toggle button in table                    |
| Remove user skill            | `btn btn-link icon-link fs-7 link-danger`   | Bootstrap | Delete in table                           |
| Add skill                    | `btn btn-sm btn-outline-primary`            | Bootstrap | Per skill in category grid                |
| Search button                | `btn btn-primary`                           | Bootstrap | In filter, no `btn-sm`                    |
| Clear search                 | `btn btn-outline-secondary`                 | Bootstrap | Conditional, in filter                    |
| Jump to category (mobile)    | `btn btn-secondary dropdown-toggle`         | Bootstrap | No `btn-sm`                               |

### Cards

| Element                    | Classes                          | Notes                                      |
| -------------------------- | -------------------------------- | ------------------------------------------ |
| Default Skills card        | `card`                           | No grid class -- standalone                |
| User-added Skills card     | `card`                           | No grid class -- standalone                |
| Skill category card        | `card g-col-12 g-col-md-6`      | In CSS grid, one per category              |
| Card header (default)      | `card-header p-2`                | Standard                                   |
| Card header (special)      | `card-header p-2 bg-info-subtle` | Highlighted for special categories         |
| Card body                  | `card-body p-0 p-sm-2`          | Consistent responsive padding              |

### Tables

| Element               | Classes                                          | Notes                                     |
| --------------------- | ------------------------------------------------ | ----------------------------------------- |
| Default skills table  | `table table-borderless table-sm align-middle mb-0` | In default skills card                 |
| User-added skills table | `table table-borderless table-sm align-middle mb-0` | In user-added skills card            |
| Category skills table | `table table-borderless table-sm align-middle mb-0` | In each category card                  |
| All wrapped in        | `table-responsive`                               | Outer div for horizontal scroll           |

### Navigation

| Component              | Source include                       | Notes                                       |
| ---------------------- | ------------------------------------ | ------------------------------------------- |
| Common header          | `list_common_header.html`            | With fighter switcher                       |
| Fighter switcher       | `fighter_switcher.html`              | Same as weapons/gear                        |
| Nav tabs (filter)      | `nav nav-tabs mb-0`                  | Primary/Secondary, All, All + Restricted    |
| Category quick-nav     | `row row-cols-3 g-0` (desktop)       | Anchor links to category cards              |
| Category dropdown      | Bootstrap dropdown (mobile)          | Mobile alternative to quick-nav             |

### Forms

| Element                  | Classes / pattern                     | Notes                                            |
| ------------------------ | ------------------------------------- | ------------------------------------------------ |
| Toggle skill form        | `d-inline`, POST                      | Enable/disable default skills                    |
| Remove skill form        | `d-inline`, POST                      | Remove user-added skills                         |
| Add skill form           | `d-inline`, POST                      | Add skill from category grid                     |
| Search form              | `vstack gap-3`, GET                   | In `fighter_skills_filter.html`                  |
| Hidden inputs            | `flash`, `cb`, `category_filter`      | State preservation in filter                     |

### Icons

| Icon class              | Context                              |
| ----------------------- | ------------------------------------ |
| `bi-check-circle`       | Enable skill button                  |
| `bi-x-circle`           | Disable skill button                 |
| `bi-trash`              | Remove skill button                  |
| `bi-plus-lg`            | Add skill button                     |
| `bi-search`             | Search input prepend                 |

### Badges

| Element              | Classes                | Notes                                |
| -------------------- | ---------------------- | ------------------------------------ |
| Primary badge        | `badge bg-primary`     | On primary skill categories          |
| Secondary badge      | `badge bg-secondary`   | On secondary skill categories        |

### Other

- **CSS grid layout**: `grid`, `g-col-12`, `g-col-md-6` for category cards
- **Tab navigation**: Bootstrap nav-tabs for filter modes
- **Responsive show/hide**: `d-none d-lg-block` for desktop quick-nav, `d-lg-none` for mobile dropdown
- **Category anchors**: `id="category-{{ cat_data.category.id }}"` on cards, with anchor links in nav
- **Empty state**: Plain text message in `g-col-12` div

## Typography Usage

| Element               | Classes          | Rendered size | Notes                                |
| --------------------- | ---------------- | ------------- | ------------------------------------ |
| Page title            | `h1.h3`         | h3            | Semantic h1, visual h3               |
| Section heading       | `h3.h5 mb-0`    | h5            | "Default Skills", "User-added Skills"|
| Category heading      | `h3.h5 mb-0`    | h5            | Category card headers                |
| TOC heading           | `h3.h5 mb-1`    | h5            | "Skill Categories"                   |
| Skill name            | body text        | default       | In table cells                       |
| Category name (table) | `text-secondary` | default       | Second column in default/user tables |
| Button text           | `fs-7`           | 0.9rem        | Enable/Disable/Remove buttons        |
| Nav tab text          | default          | default       | Tab labels                           |

## Colour Usage

| Usage                    | Class / value           | Notes                                  |
| ------------------------ | ----------------------- | -------------------------------------- |
| Enable button            | `link-success`          | Green                                  |
| Disable button           | `link-danger`           | Red                                    |
| Remove button            | `link-danger`           | Red                                    |
| Add button               | `btn-outline-primary`   | Blue outline                           |
| Disabled skill row       | `text-decoration-line-through text-secondary` | Struck-through grey    |
| Category name            | `text-secondary`        | Grey                                   |
| Empty state              | `text-secondary`        | In default/user tables                 |
| Primary badge            | `bg-primary`            | Blue                                   |
| Secondary badge          | `bg-secondary`          | Grey                                   |
| Special category header  | `bg-info-subtle`        | Light blue/cyan background             |
| Active nav tab           | `active` (Bootstrap)    | Bold/highlighted                       |

## Spacing Values

| Element              | Spacing classes          | Notes                                   |
| -------------------- | ------------------------ | --------------------------------------- |
| Content column       | `px-0`                   | No horizontal padding                   |
| Layout               | `vstack gap-3`           | 1rem vertical gap                       |
| Card header          | `p-2`                    | 0.5rem padding                          |
| Card body            | `p-0 p-sm-2`            | Responsive padding                      |
| Nav tabs             | `mb-0`                   | No bottom margin                        |
| Quick-nav grid       | `row-cols-3 g-0`         | No gutter, 3 columns                    |
| Quick-nav items      | `py-1 px-2`              | Tight padding                           |
| Mobile dropdown      | `mb-2`                   | Bottom margin before content            |
| TOC heading          | `mb-1`                   | Tight margin below                      |

## Custom CSS

No skills-specific custom CSS. Uses standard Bootstrap components and project-wide custom classes.

## Inconsistencies

1. **Search filter differs from weapons/gear**: Skills uses `fighter_skills_filter.html` with nav tabs and a simpler search, while weapons/gear uses `fighter_gear_filter.html` with dropdown menus for category, availability, and cost. Different filter paradigms for sibling views.
2. **Search input layout**: Skills wraps search in `col-12 col-lg-6` within a `row`, while gear filter uses `g-col-12 g-col-xl-6` in CSS grid. Different grid systems for the same type of component.
3. **No filter state preservation on POST**: When adding/removing skills, the POST forms do not propagate search/filter query params. After an action, the user may lose their filter context. Weapons/gear propagate these via hidden inputs.
4. **Button consistency**: The "Jump to category" mobile dropdown button uses `btn btn-secondary dropdown-toggle` without `btn-sm`, while filter dropdowns in weapons/gear use `btn-sm`.
5. **"Add" button icon**: Uses `bi-plus-lg` while weapons uses `bi-plus` (different icon variant).
6. **Column width**: Uses `col-12 col-lg-8` -- different from weapons (`col-lg-12`) and fighter-edit (`col-12 col-md-8 col-lg-6`).
7. **Table columns**: Default skills table has 3 columns (name, category, action) with `colspan="3"` in empty state. Rules table has 2 columns (name, action) with `colspan="2"`. The skills table shows category but rules does not -- structural difference that may or may not be intentional.
8. **Clear search link style**: Skills filter uses `btn btn-outline-secondary` for clear, while the inline "Clear your search" in empty states is a plain `<a>` link. Two different styles for clearing search.

## Accessibility Notes

- Search input has `aria-label="Search skills"` -- specific and good.
- Table cells provide semantic structure but lack `scope="row"` on data cells.
- Enable/Disable buttons clearly communicate state via both icon and text label.
- `text-decoration-line-through` on disabled skills is visual-only -- no `aria-disabled` or similar.
- Nav tabs use standard Bootstrap `nav-tabs` with `active` class but lack `aria-current="page"`.
- Anchor links to categories (`#category-{{ id }}`) enable keyboard navigation.
- Mobile dropdown has no `aria-label` on the toggle button.
- Empty state messages have no `role="status"`.
- Badges ("Primary", "Secondary") are text labels -- accessible without extra ARIA.
