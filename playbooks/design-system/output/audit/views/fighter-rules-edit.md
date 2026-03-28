# View Audit: Fighter Rules Edit

## Metadata

| Field           | Value                                                        |
| --------------- | ------------------------------------------------------------ |
| URL pattern     | `/list/<id>/fighter/<fid>/rules`                             |
| URL name        | `core:list-fighter-rules-edit`                               |
| Template        | `core/list_fighter_rules_edit.html`                          |
| Extends         | `core/layouts/base.html`                                     |
| Includes        | `list_common_header.html` (no skill/gear filter includes)    |
| Template tags   | `allauth`, `custom_tags`                                     |
| Purpose         | View/manage default rules, user-added rules, search and add new rules |

## Components Found

### Buttons

| Element                       | Classes                                     | Type      | Notes                                     |
| ----------------------------- | ------------------------------------------- | --------- | ----------------------------------------- |
| Enable default rule           | `btn btn-link icon-link fs-7 link-success`  | Bootstrap | Toggle button in table                    |
| Disable default rule          | `btn btn-link icon-link fs-7 link-danger`   | Bootstrap | Toggle button in table                    |
| Remove user rule              | `btn btn-link icon-link fs-7 link-danger`   | Bootstrap | Delete in table                           |
| Add rule                      | `btn btn-sm btn-outline-primary`            | Bootstrap | Per rule in available rules list           |
| Search button                 | `btn btn-primary`                           | Bootstrap | In search form, no `btn-sm`               |
| Clear search button           | `btn btn-secondary`                         | Bootstrap | Conditional, no `btn-sm`                  |

### Cards

| Element                    | Classes                       | Notes                                       |
| -------------------------- | ----------------------------- | ------------------------------------------- |
| Default Rules card         | `card`                        | Standalone, no grid class                   |
| User-added Rules card      | `card`                        | Standalone, no grid class                   |
| Add Rules card             | `card`                        | Contains search form and available rules    |
| Card header (all)          | `card-header p-2`             | Consistent                                  |
| Card body (default/user)   | `card-body p-0 p-sm-2`       | Responsive padding, matches skills          |
| Card body (add rules)      | `card-body p-2`               | Fixed padding -- different from other cards |

### Tables

| Element                | Classes                                          | Notes                                     |
| ---------------------- | ------------------------------------------------ | ----------------------------------------- |
| Default rules table    | `table table-borderless table-sm align-middle mb-0` | Same as skills                         |
| User-added rules table | `table table-borderless table-sm align-middle mb-0` | Same as skills                         |
| All wrapped in         | `table-responsive`                               | Horizontal scroll wrapper                 |

### Navigation

| Component           | Source include                       | Notes                                       |
| ------------------- | ------------------------------------ | ------------------------------------------- |
| Common header       | `list_common_header.html`            | With fighter switcher                       |
| Fighter switcher    | `fighter_switcher.html`              | Same as skills/weapons/gear                 |

### Forms

| Element                  | Classes / pattern                     | Notes                                            |
| ------------------------ | ------------------------------------- | ------------------------------------------------ |
| Toggle rule form         | `d-inline`, POST                      | Enable/disable default rules                     |
| Remove rule form         | `d-inline`, POST                      | Remove user-added rules                          |
| Add rule form            | `d-inline ms-2`, POST                 | Add rule from available list                     |
| Search form              | `mb-3`, GET with `input-group`        | Inline in the "Add Rules" card                   |

### Icons

| Icon class              | Context                              |
| ----------------------- | ------------------------------------ |
| `bi-check-circle`       | Enable rule button                   |
| `bi-x-circle`           | Disable rule button                  |
| `bi-trash`              | Remove rule button                   |
| `bi-plus-lg`            | Add rule button                      |
| `bi-search`             | Search button (inside button, not prepend) |
| `bi-x`                  | Clear search button                  |

### Pagination

| Element              | Classes                                  | Notes                                     |
| -------------------- | ---------------------------------------- | ----------------------------------------- |
| Pagination nav       | `pagination pagination-sm justify-content-center mb-0` | Bootstrap pagination              |
| Active page          | `page-item active`                       | Standard Bootstrap                        |
| Page link            | `page-link`                              | Standard Bootstrap                        |
| Container            | `<nav aria-label="Rules pagination">`    | Proper semantic nav                       |

### Other

- **Available rules list**: Uses `row g-2` with `col-12 col-md-6` -- Bootstrap row/col grid (not CSS Grid)
- **Rule item**: `d-flex align-items-center justify-content-between p-2 border rounded` -- ad-hoc bordered box
- **Empty state**: `text-center text-secondary p-3` in a full-width column
- **Pagination**: Full pagination with page numbers, Previous/Next

## Typography Usage

| Element               | Classes          | Rendered size | Notes                                |
| --------------------- | ---------------- | ------------- | ------------------------------------ |
| Page title            | `h1.h3`         | h3            | Semantic h1, visual h3               |
| Section headings      | `h3.h5 mb-0`    | h5            | "Default Rules", "User-added Rules", "Add Rules" |
| Rule name (table)     | body text        | default       | In table cells                       |
| Rule name (list)      | `<span>`         | default       | In available rules flex items        |
| Button text           | `fs-7`           | 0.9rem        | Enable/Disable/Remove                |
| Search placeholder    | default          | default       | "Search rules..."                    |

## Colour Usage

| Usage                    | Class / value           | Notes                                  |
| ------------------------ | ----------------------- | -------------------------------------- |
| Enable button            | `link-success`          | Green -- matches skills                |
| Disable button           | `link-danger`           | Red -- matches skills                  |
| Remove button            | `link-danger`           | Red -- matches skills                  |
| Add button               | `btn-outline-primary`   | Blue outline -- matches skills         |
| Disabled rule row        | `text-decoration-line-through text-secondary` | Same as skills           |
| Empty state              | `text-secondary`        | Grey                                   |
| Clear search button      | `btn-secondary`         | Solid grey -- differs from skills `btn-outline-secondary` |
| Search button            | `btn-primary`           | Solid blue                             |
| Rule item border         | `border rounded`        | Default border colour                  |

## Spacing Values

| Element              | Spacing classes               | Notes                                   |
| -------------------- | ----------------------------- | --------------------------------------- |
| Content column       | `px-0`                        | No horizontal padding                   |
| Layout               | `vstack gap-3`                | 1rem vertical gap                       |
| Card header          | `p-2`                         | 0.5rem padding                          |
| Card body (tables)   | `p-0 p-sm-2`                  | Responsive padding                      |
| Card body (add)      | `p-2`                         | Fixed padding -- different              |
| Search form          | `mb-3`                        | Bottom margin after search              |
| Available rules grid | `row g-2`                     | 0.5rem gutter                           |
| Rule item            | `p-2`                         | Padding inside bordered box             |
| Add form             | `d-inline ms-2`               | Left margin for inline form             |
| Pagination           | `mt-3`                        | Top margin above pagination             |
| Empty state          | `p-3`                         | Padding in empty state                  |

## Custom CSS

No rules-specific custom CSS. Uses standard Bootstrap components only.

## Inconsistencies

1. **Search pattern differs from skills**: Rules has its own inline search form inside a card, while skills uses the `fighter_skills_filter.html` include with nav tabs and a separate search component. The search UX is completely different between these two structurally similar views.
2. **Search icon placement**: Rules places `bi-search` inside the search button. Skills filter places it in an `input-group-text` prepend. Weapons/gear also uses the prepend pattern. Rules is the outlier.
3. **Clear button style differs**: Rules uses `btn btn-secondary` (solid grey). Skills uses `btn btn-outline-secondary` (grey outline). Different variants for the same action.
4. **Clear button icon**: Rules uses `bi-x` icon inside the clear button. Skills has no icon in its clear button. The gear/weapons filter also has no icon.
5. **Available items layout**: Rules uses Bootstrap row/col grid (`row g-2`, `col-12 col-md-6`) with `d-flex` bordered boxes. Skills uses CSS Grid (`grid`, `g-col-12 g-col-md-6`) with card + table layout. Different layout systems for the same concept.
6. **No category grouping**: Rules has no category grouping -- all available rules are in a flat paginated list. Skills are grouped by category in separate cards. This is a significant UX difference.
7. **Pagination exists only here**: Rules is the only view in this group that has pagination. Skills, weapons, and gear show all items without pagination.
8. **Card body padding for "Add Rules"**: Uses `p-2` (fixed) while default/user rules cards use `p-0 p-sm-2` (responsive). Inconsistent within the same template.
9. **Table columns**: Rules tables have 2 columns (name, action) while skills tables have 3 columns (name, category, action). Rules does not show a category column since rules are not categorised.
10. **No filter/category system**: Unlike skills (which has nav tabs and category filtering) and weapons/gear (which has dropdown filters), rules has only a plain text search. Least sophisticated filter of all the views.
11. **Empty state pattern differs**: Rules uses `text-center text-secondary p-3` inside a bordered div. Skills and weapons/gear use plain text in a `g-col-12` grid cell.

## Accessibility Notes

- Pagination nav has `aria-label="Rules pagination"` -- good.
- Active pagination item uses `<span>` instead of `<a>`, preventing click on current page -- good UX.
- Search input has `placeholder` but no `aria-label` -- relies on placeholder for context, which is insufficient for screen readers.
- Clear search link in empty state text is a plain `<a>` tag -- accessible.
- Enable/Disable toggle buttons have clear text labels alongside icons -- accessible.
- Disabled rule rows use `text-decoration-line-through text-secondary` but no `aria-disabled` -- screen readers won't detect the disabled state.
- `table-responsive` wrapper ensures tables don't cause horizontal page overflow.
- No `role="status"` on empty state or search results area.
- Previous/Next pagination links have clear text -- no icon-only links.
