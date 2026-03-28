# View Audit: Fighter Edit

## Metadata

| Field           | Value                                                        |
| --------------- | ------------------------------------------------------------ |
| URL pattern     | `/list/<id>/fighter/<fid>`                                   |
| URL name        | `core:list-fighter-edit`                                     |
| Template        | `core/list_fighter_edit.html`                                |
| Extends         | `core/layouts/base.html`                                     |
| Includes        | `core/includes/list_common_header.html` (with `link_list`, `fighter`, `fighter_url_name`) |
| Template tags   | `allauth`, `custom_tags`                                     |
| Purpose         | Edit a fighter's name, type, legacy type, category override, and cost override |

## Components Found

### Buttons

| Element                   | Classes                | Type      | Notes                                       |
| ------------------------- | ---------------------- | --------- | ------------------------------------------- |
| Save button               | `btn btn-primary`      | Bootstrap | No `btn-sm` -- inconsistent with convention |
| Cancel link               | `btn btn-link`         | Bootstrap | Styled as link-button, not `btn-sm`         |
| Edit Stats link           | `icon-link link-primary` | Bootstrap | Inline icon-link, not a button              |

### Cards

None. This page uses no card components -- it is a plain form layout.

### Tables

None in the primary template. The `list_common_header.html` include renders a summary stats table (Rating, Credits, Stash, Wealth).

### Navigation

| Component           | Source include                       | Notes                                   |
| ------------------- | ------------------------------------ | --------------------------------------- |
| Common header       | `list_common_header.html`            | List name, owner, house, stats table    |
| Fighter switcher    | `fighter_switcher.html` (via header) | Dropdown to switch between fighters     |

### Forms

| Element                  | Classes / pattern                     | Notes                                            |
| ------------------------ | ------------------------------------- | ------------------------------------------------ |
| Main form                | `vstack gap-3`                        | POST to `core:list-fighter-edit`                 |
| Field wrapper divs       | Plain `<div>` (no class)             | Each field in its own div                        |
| Labels                   | `{{ form.field.label_tag }}`          | Django default label rendering                   |
| Field inputs             | `{{ form.field }}` (Django widget)    | Widget classes set on form, not in template      |
| Help text                | `form-text`                           | Bootstrap form-text class                        |
| Error messages            | `invalid-feedback d-block`           | Bootstrap validation class, forced visible       |
| CSRF token               | `{% csrf_token %}`                    | Standard                                         |

### Icons

| Icon class              | Context                           |
| ----------------------- | --------------------------------- |
| `bi-pencil-square`      | Edit Stats link                   |
| `bi-person`             | Owner in common header            |
| `bi-award`              | Campaign link in common header    |
| `bi-arrow-clockwise`    | Refresh button in common header   |

### Other

- "Edit Stats" inline link below cost_override field, linking to `core:list-fighter-stats-edit`

## Typography Usage

| Element         | Classes    | Rendered size | Notes                                  |
| --------------- | ---------- | ------------- | -------------------------------------- |
| Page title      | `h1.h3`   | h3            | Semantic h1, visual h3                 |
| Header list name | `h2.h3`  | h3            | In common header                       |
| Edit Stats text | body size  | normal        | Uses `icon-link` with icon             |
| Help text       | `form-text`| small/muted   | Bootstrap default form help            |

## Colour Usage

| Usage              | Class / value      | Notes                                        |
| ------------------ | ------------------ | -------------------------------------------- |
| Edit Stats link    | `link-primary`     | Blue link with icon                          |
| Error messages     | `invalid-feedback` | Bootstrap danger red                         |
| Help text          | `form-text`        | Muted/secondary by Bootstrap                 |
| Owner link         | `text-muted`       | In common header                             |

## Spacing Values

| Element           | Spacing classes   | Notes                                         |
| ----------------- | ----------------- | --------------------------------------------- |
| Content column    | `px-0`            | No horizontal padding                         |
| Form              | `vstack gap-3`    | Vertical stack with 1rem gap                   |
| Submit row        | `mt-3`            | Extra top margin before buttons                |
| Header            | `mb-2`, `mb-3 pb-4 border-bottom` | When `link_list` is true       |

## Custom CSS

| Class              | Source       | Purpose                              |
| ------------------ | ------------ | ------------------------------------ |
| `fighter-switcher-btn` | `styles.scss` | Transparent button with no border |
| `fighter-switcher-menu` | `styles.scss` | Max-height scroll for dropdown  |
| `linked`           | `styles.scss` | Underline opacity link style        |

## Inconsistencies

1. **Button sizing**: Save button uses `btn btn-primary` (default size) instead of `btn btn-primary btn-sm` as specified in the project's button convention. Cancel uses `btn btn-link` also without `btn-sm`.
2. **Form field rendering**: Each field is manually rendered with `label_tag`, widget, help_text, and error loop. This pattern is repeated 4+ times but not extracted to a reusable include or template tag.
3. **Column widths differ from sibling views**: This page uses `col-12 col-md-8 col-lg-6` while skills/rules pages use `col-12 col-lg-8` and weapons/gear use `col-lg-12` or `col-12`.
4. **Cancel link destination**: Hardcodes `{% url 'core:list' list.id %}` rather than using `{% safe_referer %}` like the "new" view does.
5. **No error summary**: If the form has non-field errors, there is no rendering for `form.non_field_errors`.

## Accessibility Notes

- Labels are provided via `label_tag` (proper `<label>` elements with `for` attributes).
- Error messages use `invalid-feedback` but lack `role="alert"` or `aria-describedby` linkage to the input.
- The "Edit Stats" link uses an icon with text, which is accessible.
- Common header tooltips have `aria-label` attributes on stat column headers.
- No `aria-live` region for form submission feedback.
