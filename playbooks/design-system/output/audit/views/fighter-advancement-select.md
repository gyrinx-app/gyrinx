# View Audit: Advancement Select

## Metadata

| Field            | Value                                                    |
| ---------------- | -------------------------------------------------------- |
| URL pattern      | `.../advancements/new/select`                            |
| Template         | `core/list_fighter_advancement_select.html`              |
| Extends          | `core/layouts/base.html`                                 |
| Includes         | `core/includes/advancement_progress.html`, `core/includes/advancement_equipment_form.html` OR `core/includes/advancement_skill_form.html` |
| Template tags    | `allauth`                                                |
| Form rendering   | Delegated to conditional includes                        |
| Has JS           | No                                                       |

## Components Found

### Navigation

- **Progress bar** (`advancement_progress.html`): Dynamic step/progress from `steps` context variable. Includes back link and heading.
- **Back link**: In the bottom `nav`, `icon-link` with `bi-chevron-left` pointing to advancement type page.
- **No common header**: Wizard step pattern.

### Conditional Includes

The form body is entirely delegated to one of two partials:

1. **`advancement_equipment_form.html`** (when `advancement_type == "equipment"`): Equipment select with error display.
2. **`advancement_skill_form.html`** (when skill): Skill select or category select (if random).

#### Equipment Form Partial

| Component                  | Classes                          |
| -------------------------- | -------------------------------- |
| Error alert (no options)   | `alert alert-danger mb-3`       |
| Error alert (non-field)    | `alert alert-danger mb-3`       |
| Label                      | `label.form-label`              |
| Help text                  | `form-text`                     |
| Field errors               | `invalid-feedback d-block`      |

Icons: `bi-exclamation-triangle` in error alerts.

#### Skill Form Partial

| Component                  | Classes                          |
| -------------------------- | -------------------------------- |
| Category label (random)    | `label.form-label`              |
| Skill label (non-random)   | `label.form-label`              |
| Help text                  | `form-text`                     |
| Field errors               | `invalid-feedback d-block`      |
| Warning alert (random)     | `alert alert-warning p-2 fs-7`  |

Icons: `bi-exclamation-triangle` in warning alert.

### Forms

- `form.vstack.gap-3` with `method="post"` and `aria-label="Choose {type} form"`
- CSRF token

### Buttons

| Label                | Element    | Classes            | Notes                          |
| -------------------- | ---------- | ------------------ | ------------------------------ |
| Confirm Advancement  | `button`   | `btn btn-success`  | Has `bi-check-circle` icon     |
| <- Back              | `a`        | `icon-link`        | Has `bi-chevron-left` icon     |

Note: This is the ONLY view in the audit that uses `btn-success` (green). All other submit buttons use `btn-primary` (blue). This is intentional to signal a final confirmation action, but it breaks the otherwise uniform button colour.

### Icons

| Icon              | Class              | Context                   |
| ----------------- | ------------------ | ------------------------- |
| Chevron left      | `bi-chevron-left`  | Back link                 |
| Check circle      | `bi-check-circle`  | Confirm button            |
| Exclamation tri   | `bi-exclamation-triangle` | Error/warning alerts |

## Typography Usage

| Element          | Tag      | Classes        | Text example                         |
| ---------------- | -------- | -------------- | ------------------------------------ |
| Progress heading | `h2`     | `mb-0`         | "New Advancement for {name}"        |
| Step heading     | `h3`     | `h5 mb-0`      | "Choose {type} Skill" / "Accept..." |
| Form labels      | `label`  | `form-label`   | "Select Skill", "Select Equipment"  |

### Notes

- The step heading dynamically changes text based on `advancement_type` and `is_random`. There are four variants:
  - Equipment + random: "Accept {name}"
  - Equipment + non-random: "Choose {name}"
  - Skill + random: "Choose {type} Skill Set"
  - Skill + non-random: "Choose {type} Skill"

## Colour Usage

| Purpose               | Colour token     | Bootstrap class             |
| --------------------- | ---------------- | --------------------------- |
| Confirm button        | Success (green)  | `btn btn-success`           |
| Back link             | Default          | `icon-link`                 |
| Equipment error alert | Danger           | `alert alert-danger`        |
| Skill warning alert   | Warning          | `alert alert-warning`       |

## Spacing Values

| Location                    | Classes                                  |
| --------------------------- | ---------------------------------------- |
| Outer column                | `col-12 col-md-8 col-lg-6 vstack gap-4` |
| Progress + heading          | `vstack gap-3` > `vstack gap-1`         |
| Form                        | `vstack gap-3`                           |
| Navigation                  | `nav.hstack.gap-3`                       |
| Equipment error alert       | `mb-3`                                   |
| Skill warning alert         | `p-2 fs-7`                               |

Note: Outer wrapping has `vstack gap-3` > `vstack gap-1` nesting for the progress section, which is slightly different from dice choice and type views.

## Custom CSS

- `mb-last-0`: Not used directly in this template.
- `fs-7`: Used in the skill form partial's warning alert for smaller text.

## Inconsistencies

1. **`btn-success` for confirm**: This is the only view using a green submit button. The "other" advancement page uses `btn-primary` for its continue button. Within the wizard, the final action button colour differs from intermediate steps.
2. **Form gap**: Uses `vstack gap-3` while dice choice and type use `gap-2` and `gap-4` respectively. Three different gap sizes across wizard steps.
3. **Nav pattern**: Uses `nav.hstack.gap-3` (flat), while type uses `nav.vstack.gap-3` > `hstack gap-3` (nested). Inconsistent nav structure across wizard steps.
4. **Confirm help text**: Has `aria-describedby="confirm-help"` with visually-hidden text, consistent with the type page's approach.
5. **Extra nesting**: The progress section has `div.vstack.gap-3` > `div.vstack.gap-1`, creating an unnecessary wrapper level compared to type and dice choice which go directly to `vstack gap-1`.
6. **Skill warning alert uses `p-2 fs-7`**: Custom padding (`p-2` instead of default alert padding) and smaller font. This is the only alert with reduced padding and custom font size.
7. **`allauth` tag loaded but unused**.

## Accessibility Notes

- Form has `aria-label` with dynamic content type.
- Confirm button has `aria-describedby="confirm-help"` pointing to visually-hidden text.
- Check circle icon has `aria-hidden="true"`.
- Progress bar from include has full ARIA attributes.
- Equipment form partial error icons lack `aria-hidden`.
- Skill form partial warning icon lacks `aria-hidden`.
- Labels use `for` with `id_for_label`.
