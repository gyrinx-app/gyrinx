# View Audit: Advancement Type

## Metadata

| Field            | Value                                                    |
| ---------------- | -------------------------------------------------------- |
| URL pattern      | `.../advancements/new/type`                              |
| Template         | `core/list_fighter_advancement_type.html`                |
| Extends          | `core/layouts/base.html`                                 |
| Includes         | `core/includes/advancement_progress.html`                |
| Template tags    | `allauth`                                                |
| Form rendering   | Manual per-field: radio/select for advancement choice, number inputs for costs |
| Has JS           | Yes, inline `<script>` in `extra_script` block           |

## Components Found

### Navigation

- **Progress bar** (`advancement_progress.html`): Dynamic step/progress from `steps` context variable (not hardcoded like dice choice). Includes back link and heading.
- **Back link** (in navigation nav): `icon-link` with `bi-chevron-left` to go back to dice choice. Only shown if `step > 1`.
- **No common header**: Wizard step, same pattern as dice choice.

### Alerts

| Type      | Classes                           | Content                              |
| --------- | --------------------------------- | ------------------------------------ |
| Danger    | `alert alert-danger mb-last-0 mb-0` | Non-field form errors              |
| Secondary | `alert alert-secondary mb-0`     | Available XP with badge              |
| Info      | `alert alert-info`               | Dice roll result (conditional)       |

Note: Non-field error alert has both `mb-last-0` and `mb-0` applied, which is redundant (`mb-0` already sets margin-bottom to 0, `mb-last-0` targets last child).

### Badges

| Element         | Classes                   | Context                |
| --------------- | ------------------------- | ---------------------- |
| Available XP    | `badge text-bg-primary`   | In secondary alert     |

### Forms

- `form.vstack.gap-4` with `method="post"` and `aria-label="Select advancement form"`
- CSRF token
- Hidden campaign_action_id field
- Fields container: `div.vstack.gap-3`
- Cost fields in a `div.row` > `div.col-md-6` grid (two columns at md+)

### Form Fields

| Field              | Label pattern      | Help text class | Error class                |
| ------------------ | ------------------ | --------------- | -------------------------- |
| Advancement choice | `label.form-label` | (none)          | `invalid-feedback d-block` |
| XP cost            | `label.form-label` | `form-text`     | `invalid-feedback d-block` |
| Cost increase      | `label.form-label` | `form-text`     | `invalid-feedback d-block` |

Note: Advancement choice label and field content are separated -- label is in a `div`, then `div.vstack.gap-2` for the choices. This supports radio button rendering.

### Dice Result Display

- Conditional `alert alert-info` with flex layout
- `bi-dice-6` icon at `fs-3` with `me-2`
- Results formatted as "d1 + d2 = total" with `<strong>` tags

### Buttons

| Label                | Element    | Classes            | Notes                          |
| -------------------- | ---------- | ------------------ | ------------------------------ |
| Next ->              | `button`   | `btn btn-primary`  | Has `bi-arrow-right` icon      |
| <- Back              | `a`        | `icon-link`        | Has `bi-chevron-left` icon     |

### Icons

| Icon              | Class              | Context                   |
| ----------------- | ------------------ | ------------------------- |
| Dice              | `bi-dice-6 fs-3`   | Dice result display       |
| Chevron left      | `bi-chevron-left`  | Back link                 |
| Arrow right       | `bi-arrow-right`   | Next button               |

## Typography Usage

| Element           | Tag      | Classes              | Text example                       |
| ----------------- | -------- | -------------------- | ---------------------------------- |
| Progress heading  | `h2`     | `mb-0`               | "New Advancement for {name}"      |
| Step heading      | `h3`     | `h5 mb-0`            | "Select Advancement"              |
| Form labels       | `label`  | `form-label`         | "Advancement", "XP Spend", etc.   |
| Strong text       | `strong` | (none)               | "Dice Roll:", total value          |

## Colour Usage

| Purpose              | Colour token        | Bootstrap class             |
| -------------------- | ------------------- | --------------------------- |
| Next button          | Primary             | `btn btn-primary`           |
| Available XP badge   | Primary             | `text-bg-primary`           |
| XP info bar          | Secondary           | `alert alert-secondary`     |
| Dice result          | Info                | `alert alert-info`          |
| Errors               | Danger              | `alert alert-danger`        |
| Back link            | Default link colour | `icon-link`                 |

## Spacing Values

| Location                    | Classes                                  |
| --------------------------- | ---------------------------------------- |
| Outer column                | `col-12 col-md-8 col-lg-6 vstack gap-4` |
| Progress + heading          | `vstack gap-1`                           |
| Form                        | `vstack gap-4`                           |
| Fields container            | `vstack gap-3`                           |
| Cost fields row             | `row` > `col-md-6`                       |
| Advancement choice          | `vstack gap-2`                           |
| Dice result flex             | `d-flex align-items-center`             |
| Dice icon spacing           | `me-2`                                   |
| Navigation                  | `nav.vstack.gap-3` > `hstack gap-3`     |
| Nav help text               | `visually-hidden`                        |

## Custom CSS

- `mb-last-0`: On the non-field errors alert.
- No other custom classes in this template.

## Inconsistencies

1. **Navigation wrapper**: Uses `nav.vstack.gap-3` > `div.hstack.gap-3` for the back/next buttons, while dice choice uses `nav` directly around the button, and select uses `nav.hstack.gap-3`. Three different nav patterns in the same wizard flow.
2. **Redundant margin classes**: `mb-last-0 mb-0` on the error alert is redundant.
3. **Form gap**: Uses `vstack gap-4` for the form (like dice choice's outer), while most other views use `vstack gap-3`.
4. **Dice result layout**: Unique to this step, using `d-flex align-items-center` inside an alert with a large icon (`fs-3`). This is well-designed but a one-off pattern.
5. **`aria-describedby="nav-help"`**: The next button has this, pointing to a visually-hidden span. The dice choice and select steps handle help text differently.
6. **`icon-link` for back**: Uses Bootstrap's `icon-link` class for the back link, which is a proper pattern. But this is different from the advancement select page's approach (also `icon-link`) -- at least these two are consistent.
7. **`allauth` tag loaded but unused in this template**.

## Accessibility Notes

- Form has `aria-label="Select advancement form"`.
- Next button has `aria-describedby="nav-help"` with visually-hidden explanation.
- Arrow icon has `aria-hidden="true"`.
- Progress bar from the include has full ARIA attributes.
- Labels use `for` with `id_for_label`.
- Error feedback is in `invalid-feedback d-block` but not linked via `aria-describedby` to the inputs.
- Campaign action hidden field is accessible to screen readers (should be fine as it's `type="hidden"`).

## JavaScript

The `extra_script` block contains inline JavaScript that:

- Reads advancement configuration JSON (`advancementConfigs`) from a server-rendered variable
- Listens for changes to the advancement choice select
- Auto-fills XP cost and cost increase fields based on the selection
- No external dependencies, vanilla JS
- Uses `getElementById` with Django template variables for IDs
- The `advancementConfigs` data is rendered with `|safe` filter (potential XSS if user-controlled, though likely server-generated)
