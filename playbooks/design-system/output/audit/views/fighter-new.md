# View Audit: Fighter New

## Metadata

| Field           | Value                                                        |
| --------------- | ------------------------------------------------------------ |
| URL pattern     | `/list/<id>/fighters/new`                                    |
| URL name        | `core:list-fighter-new`                                      |
| Template        | `core/list_fighter_new.html`                                 |
| Extends         | `core/layouts/base.html`                                     |
| Includes        | `core/includes/list_common_header.html` (with `link_list`, no `fighter` or `fighter_url_name`) |
| Template tags   | `allauth`, `custom_tags`                                     |
| Purpose         | Add a new fighter to a list                                  |

## Components Found

### Buttons

| Element                   | Classes                | Type      | Notes                                       |
| ------------------------- | ---------------------- | --------- | ------------------------------------------- |
| Add Fighter button        | `btn btn-primary`      | Bootstrap | No `btn-sm` -- matches fighter-edit          |
| Cancel link               | `btn btn-link`         | Bootstrap | Uses `{% safe_referer %}` for URL            |

### Cards

None.

### Tables

None in primary template. Stats table in common header include.

### Navigation

| Component           | Source include                       | Notes                                       |
| ------------------- | ------------------------------------ | ------------------------------------------- |
| Common header       | `list_common_header.html`            | No fighter switcher (no `fighter` passed)   |

### Forms

| Element                  | Classes / pattern                     | Notes                                            |
| ------------------------ | ------------------------------------- | ------------------------------------------------ |
| Main form                | `vstack gap-3`                        | POST to `core:list-fighter-new`                  |
| Form rendering           | `{{ form }}`                          | Entire form rendered by Django, not field-by-field |
| CSRF token               | `{% csrf_token %}`                    | Standard                                         |

### Icons

Only those in the common header (bi-person, bi-award, bi-arrow-clockwise).

### Other

No additional components.

## Typography Usage

| Element         | Classes    | Rendered size | Notes                          |
| --------------- | ---------- | ------------- | ------------------------------ |
| Page title      | `h1.h3`   | h3            | Semantic h1, visual h3         |
| Header list name | `h2.h3`  | h3            | In common header               |

## Colour Usage

| Usage              | Class / value      | Notes                                        |
| ------------------ | ------------------ | -------------------------------------------- |
| Buttons            | `btn-primary`      | Primary blue                                 |
| Cancel             | `btn-link`         | Link-styled button                           |

Minimal colour usage beyond Bootstrap defaults.

## Spacing Values

| Element           | Spacing classes   | Notes                                         |
| ----------------- | ----------------- | --------------------------------------------- |
| Content column    | `px-0`            | No horizontal padding                         |
| Form              | `vstack gap-3`    | Vertical stack with 1rem gap                   |
| Submit row        | `mt-3`            | Extra top margin before buttons                |

## Custom CSS

None directly. Only custom classes from includes (common header).

## Inconsistencies

1. **Form rendering differs from fighter-edit**: Uses `{{ form }}` (full Django form rendering) rather than the manual field-by-field pattern in fighter-edit. This means field layout, error display, and help text rendering are controlled by Django defaults, not the template. This creates a visual inconsistency between the two most closely-related views.
2. **Button sizing**: Same issue as fighter-edit -- `btn btn-primary` without `btn-sm`.
3. **Cancel URL pattern differs**: Uses `{% safe_referer list.get_absolute_url %}` (good practice) while fighter-edit hardcodes the list URL. These should be consistent.
4. **Column width matches fighter-edit**: Both use `col-12 col-md-8 col-lg-6`, which is correct for a form-only page.
5. **No fighter switcher**: This is intentional since no fighter exists yet, but the page is noticeably simpler than the edit page as a result.

## Accessibility Notes

- Form fields rendered by Django will include proper labels if the form class defines them.
- No explicit error rendering in the template -- relies on Django's default form rendering for error messages.
- Cancel link text is clear ("Cancel").
- No `aria-live` region for form submission feedback.
- `{{ form }}` output quality depends entirely on the Django form class -- not visible in the template.
