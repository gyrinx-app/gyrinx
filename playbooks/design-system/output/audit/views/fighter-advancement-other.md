# View Audit: Advancement Other

## Metadata

| Field            | Value                                                    |
| ---------------- | -------------------------------------------------------- |
| URL pattern      | `.../advancements/new/other`                             |
| Template         | `core/list_fighter_advancement_other.html`               |
| Extends          | `core/layouts/base.html`                                 |
| Includes         | `core/includes/advancement_progress.html`                |
| Template tags    | `allauth`, `custom_tags`                                 |
| Form rendering   | Manual per-field with label, help text, errors           |
| Has JS           | No                                                       |

## Components Found

### Navigation

- **Progress bar** (`advancement_progress.html`): Step 2 of 3, 66% progress (hardcoded, unlike type/select which use dynamic `steps`). Includes back link and heading.
- **Back link**: In the bottom navigation, `a.btn.btn-secondary` linking to advancement type page with query string via `{% qt request %}`. This is a DIFFERENT back button pattern from the other wizard steps which use `icon-link`.
- **No common header**: Wizard step pattern.

### Alerts

| Type      | Classes                            | Content                                   |
| --------- | ---------------------------------- | ----------------------------------------- |
| Danger    | `alert alert-danger mb-last-0 mb-0` | Non-field form errors                   |
| Secondary | `alert alert-secondary mb-0`      | XP info bar with available XP and cost    |

### Badges

| Element         | Classes                   | Context                |
| --------------- | ------------------------- | ---------------------- |
| Available XP    | `badge text-bg-primary`   | In secondary alert     |
| XP cost         | `badge text-bg-warning`   | In secondary alert     |

Note: This is the ONLY view that uses `text-bg-warning` badge. The advancement type page shows available XP with `text-bg-primary` only (no cost display). This page adds the cost alongside with a warning badge for visual distinction.

### Forms

- `form.vstack.gap-4` with `method="post"` and `aria-label="Describe advancement form"`
- CSRF token
- Single field: description

### Form Fields

| Field        | Label pattern      | Help text class | Error class                |
| ------------ | ------------------ | --------------- | -------------------------- |
| Description  | `label.form-label` | `form-text`     | `invalid-feedback d-block` |

### XP Info Bar

- `alert alert-secondary mb-0` with internal `d-flex justify-content-between`
- Left: "Available XP: {badge}" / Right: "Cost: {badge}"
- This is a more elaborate XP bar than the type page's single-badge version

### Buttons

| Label     | Element    | Classes              | Notes                          |
| --------- | ---------- | -------------------- | ------------------------------ |
| Continue  | `button`   | `btn btn-primary`    | `aria-describedby="continue-help"` |
| Back      | `a`        | `btn btn-secondary`  | Links to type page with QS     |

Note: Back button uses `btn btn-secondary` while all other wizard steps use `icon-link` (unstyled link with icon). This is a significant pattern inconsistency.

### Icons

- None in this template (no icons at all). This is the only wizard step without any icons in the primary template content.

## Typography Usage

| Element          | Tag      | Classes        | Text example                    |
| ---------------- | -------- | -------------- | ------------------------------- |
| Progress heading | `h2`     | `mb-0`         | "New Advancement for {name}"   |
| Step heading     | `h3`     | `h5 mb-0`      | "Describe Advancement"         |
| Form label       | `label`  | `form-label`   | Description label              |
| XP text          | inline   | (none)         | "Available XP:", "Cost:"       |

## Colour Usage

| Purpose              | Colour token        | Bootstrap class             |
| -------------------- | ------------------- | --------------------------- |
| Continue button      | Primary             | `btn btn-primary`           |
| Back button          | Secondary           | `btn btn-secondary`         |
| Available XP badge   | Primary             | `text-bg-primary`           |
| Cost badge           | Warning             | `text-bg-warning`           |
| XP info bar          | Secondary           | `alert alert-secondary`     |
| Errors               | Danger              | `alert alert-danger`        |

## Spacing Values

| Location                    | Classes                                  |
| --------------------------- | ---------------------------------------- |
| Outer column                | `col-12 col-md-8 col-lg-6 vstack gap-4` |
| Progress + heading          | `vstack gap-1`                           |
| Form                        | `vstack gap-4`                           |
| Fields container            | `vstack gap-3`                           |
| XP bar flex                 | `d-flex justify-content-between`         |
| Navigation                  | `nav.d-flex.gap-2`                       |

## Custom CSS

- `mb-last-0`: On the non-field errors alert.
- `{% qt request %}`: Template tag for preserving query string parameters (custom template tag from `custom_tags`).

## Inconsistencies

1. **Back button pattern**: Uses `btn btn-secondary` instead of `icon-link` with `bi-chevron-left` used by type and select steps. This is the most visually different navigation within the wizard flow.
2. **No icons**: Only wizard step with no icons at all. Others use arrows, chevrons, check marks, or dice icons.
3. **Hardcoded progress**: Uses `current_step=2 total_steps=3 progress=66` hardcoded in the include call, while type and select use dynamic `steps` variable. Dice choice also hardcodes `current_step=1 total_steps=3 progress=33`.
4. **Navigation container**: Uses `nav.d-flex.gap-2`, while type uses `nav.vstack.gap-3` > `hstack gap-3`, select uses `nav.hstack.gap-3`, and dice choice uses `nav` wrapping a button. Four different navigation patterns across four wizard steps.
5. **XP info bar enhanced**: Shows both available XP and cost side-by-side with a flex layout, while type only shows available XP. The information density is higher on this page.
6. **Warning badge colour**: `text-bg-warning` is only used here. The yellow badge for cost is visually distinct but appears nowhere else in the audited views.
7. **`custom_tags` loaded**: This is the only advancement wizard template that loads `custom_tags` (for the `{% qt %}` tag). Others load only `allauth`.
8. **Button order**: Continue button comes before Back button (left-to-right). In type page, Back link comes before Next button. Inconsistent ordering of primary/secondary actions within the wizard.

## Accessibility Notes

- Form has `aria-label="Describe advancement form"`.
- Continue button has `aria-describedby="continue-help"` with visually-hidden explanation.
- Progress bar from include has full ARIA attributes.
- Label uses `for` with `id_for_label`.
- Error feedback uses `invalid-feedback d-block` but not linked via `aria-describedby`.
- No `aria-hidden` on any icons (because there are no icons in this template).
- The XP info bar badges convey meaning through colour alone (primary = available, warning = cost). The text labels "Available XP" and "Cost" provide sufficient context for screen readers, but the colour distinction is not accessible.
