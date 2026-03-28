# View Audit: Advancement Dice Choice

## Metadata

| Field            | Value                                                    |
| ---------------- | -------------------------------------------------------- |
| URL pattern      | `.../advancements/new/dice`                              |
| Template         | `core/list_fighter_advancement_dice_choice.html`         |
| Extends          | `core/layouts/base.html`                                 |
| Includes         | `core/includes/advancement_progress.html`                |
| Template tags    | `allauth`                                                |
| Form rendering   | Custom: buttons + select dropdowns for dice              |
| Has JS           | No                                                       |

## Components Found

### Navigation

- **Progress bar** (`advancement_progress.html`): Step 1 of 3, 33% progress. Includes a back link to the advancements list and an `<h2>` heading "New Advancement for {name}".
- **No common header**: Unlike the advancements list page, this wizard step does not include `list_common_header.html`. The progress include provides its own back link and heading.
- **Back link**: Inside the progress include, rendered via `back.html` as breadcrumb.

### Cards

| Card                  | Classes                     | Content                                |
| --------------------- | --------------------------- | -------------------------------------- |
| Roll for random       | `card h-100 shadow-sm`      | Roll button, manual dice entry         |
| Choose advancement    | `card h-100 shadow-sm`      | Link to skip dice and choose directly  |

Note: These are the only cards in the audited views that use `shadow-sm`. No other view in this group adds shadows to cards.

### Alerts

| Type    | Classes              | Content                                    |
| ------- | -------------------- | ------------------------------------------ |
| Info    | `alert alert-info`   | Dice roll will be added to action log      |
| Warning | `alert alert-warning` | Fighter can't roll (not Ganger/Beast)     |
| Danger  | `alert alert-danger mb-last-0` | Non-field form errors              |

### Forms

- `form.vstack.gap-2` with `method="post"` and `aria-label="Roll for advancement form"`
- Contains two card sections within a `div.row.g-3`
- CSRF token included
- Non-field errors displayed at top

### Form Controls

| Control              | Type      | Classes        | ARIA                                |
| -------------------- | --------- | -------------- | ----------------------------------- |
| Roll auto button     | `button`  | `btn btn-primary` | `aria-describedby="roll-help"`   |
| D6 select 1          | `select`  | `form-select`  | `aria-label="First D6 result"`     |
| D6 select 2          | `select`  | `form-select`  | `aria-label="Second D6 result"`    |
| Confirm result       | `button`  | `btn btn-outline-primary` | (none)                    |
| Select (choose link) | `a`       | `btn btn-outline-secondary` | `aria-describedby`          |

### Buttons

| Label                 | Element    | Classes                     | Notes                          |
| --------------------- | ---------- | --------------------------- | ------------------------------ |
| Generate a 2D6 roll   | `button`   | `btn btn-primary`           | Conditionally `disabled`       |
| Confirm result        | `button`   | `btn btn-outline-primary`   | In input-group, conditionally disabled |
| Select ->             | `a`        | `btn btn-outline-secondary` | Has `bi-arrow-right` icon      |

### Icons

| Icon                    | Class                      | Context                         |
| ----------------------- | -------------------------- | ------------------------------- |
| Info circle             | `bi-info-circle`           | Info alert in roll card         |
| Exclamation triangle    | `bi-exclamation-triangle`  | Warning alert in roll card      |
| Arrow right             | `bi-arrow-right`           | Choose advancement link         |

### Fieldsets

- `fieldset.vstack.gap-2` with `<legend>` for the tabletop result section
- `fieldset.vstack.gap-2.mb-0` with `<legend class="form-label mb-1">` for the choose section
- Two fieldsets in one form -- good semantic grouping

### Input Groups

- `div.input-group` containing two `select.form-select` and a submit button
- `aria-describedby="tabletop-result-label"` on the input group

## Typography Usage

| Element          | Tag        | Classes              | Text example                            |
| ---------------- | ---------- | -------------------- | --------------------------------------- |
| Progress heading | `h2`       | `mb-0`               | "New Advancement for {name}"           |
| Step heading     | `h3`       | `h5 mb-0`            | "How will {name} advance?"             |
| Card title 1     | `h4`       | `card-title`         | "Roll for random advancement"          |
| Card title 2     | `h4`       | `card-title`         | "Choose advancement"                  |
| Legend 1         | `legend`   | (none)               | "Or enter a tabletop result:"          |
| Legend 2         | `legend`   | `form-label mb-1`    | "Already rolled? Skip..."             |

### Notes

- Heading hierarchy: h2 (progress) > h3 (step) > h4 (card titles). This is semantically correct.
- Uses `h3.h5` for the step heading (semantic h3, styled as h5), maintaining visual consistency with the progress bar heading.

## Colour Usage

| Purpose              | Colour token        | Bootstrap class             |
| -------------------- | ------------------- | --------------------------- |
| Roll button          | Primary             | `btn btn-primary`           |
| Confirm button       | Primary outline     | `btn btn-outline-primary`   |
| Choose button        | Secondary outline   | `btn btn-outline-secondary` |
| Info alert           | Info blue           | `alert alert-info`          |
| Warning alert        | Warning yellow      | `alert alert-warning`       |

## Spacing Values

| Location                    | Classes                                 |
| --------------------------- | --------------------------------------- |
| Outer column                | `col-12 col-md-8 col-lg-6 vstack gap-4` |
| Progress + heading          | `vstack gap-1`                          |
| Form                        | `vstack gap-2`                          |
| Card grid                   | `row g-3`                               |
| Card columns                | `col-12` (stacked, no side-by-side)     |
| Card body                   | `card-body vstack gap-3`               |
| Roll options                | `vstack gap-2`                          |
| Choose options              | `hstack gap-3`                          |

Note: Outer column uses `vstack gap-4` (larger gap) compared to most other views using `vstack gap-3`. This is specific to the advancement wizard steps.

## Custom CSS

- `mb-last-0`: Used on the non-field errors alert to remove bottom margin on the last child.
- `shadow-sm`: Bootstrap utility, but unique within this view group.

## Inconsistencies

1. **No common header**: The advancement wizard steps (dice choice, type, select, other) all omit `list_common_header.html`, using the progress bar include instead. This is a deliberate design choice for the wizard flow but means users lose the gang stats overview during the advancement process.
2. **`shadow-sm` on cards**: Only this template (and advancement-type via identical card pattern) adds shadows to cards. No other audited view uses card shadows.
3. **Outer `px-0` missing**: Uses `col-12 col-md-8 col-lg-6 vstack gap-4` without `px-0`, which the non-wizard views include. This means the padding treatment is slightly different.
4. **Gap size**: Uses `gap-4` in the outer container while other views use `gap-3`.
5. **No `aria-hidden` on info/warning icons**: The `bi-info-circle` and `bi-exclamation-triangle` icons don't have `aria-hidden="true"`, unlike `bi-arrow-right` which does. Inconsistent decorative icon handling.
6. **`nav` element wrapping a button**: The "Generate a 2D6 roll" button is wrapped in `<nav aria-label="Form navigation">` which is semantically questionable -- this is a form action, not navigation.
7. **Card equality**: Both cards use `h-100` for equal height, but they're in `col-12` (stacked), so `h-100` has no effect since there are no side-by-side cards.

## Accessibility Notes

- Form has `aria-label="Roll for advancement form"`.
- Roll button has `aria-describedby="roll-help"` pointing to a `visually-hidden` help span.
- Dice selects have `aria-label` attributes.
- Input group has `aria-describedby="tabletop-result-label"` linking to the legend.
- Choose section uses `aria-describedby="choose-advancement-label"`.
- Progress bar has `role="progressbar"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, and `aria-live="polite"`.
- Good overall accessibility implementation, best among the audited views.
- Disabled buttons properly use `disabled` attribute.
