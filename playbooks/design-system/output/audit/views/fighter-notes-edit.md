# View Audit: Fighter Notes Edit

## Metadata

| Field            | Value                                                        |
| ---------------- | ------------------------------------------------------------ |
| URL pattern      | `/list/<id>/fighter/<fid>/notes`                             |
| Template         | `core/list_fighter_notes_edit.html`                          |
| Extends          | `core/layouts/base.html`                                     |
| Includes         | `core/includes/list_common_header.html` (with fighter switcher) |
| Template tags    | `allauth`, `custom_tags`                                     |
| Form rendering   | Manual per-field with labels, help text                      |
| Has JS           | Possibly via `{{ form.media }}`                              |

## Components Found

### Navigation

- **Common header** (`list_common_header.html`): Included with `link_list="true"`, `fighter=form.instance`, `fighter_url_name="core:list-fighter-notes-edit"` for fighter switcher.
- **Fighter switcher**: Active.

### Forms

- `form` with `method="post"`, explicit `action` URL
- Hidden `return_url` input
- `{{ form.media }}` included
- CSRF token
- Fields in a `div.vstack.gap-3` container

### Form Fields

| Field          | Label pattern      | Help text class | Error handling |
| -------------- | ------------------ | --------------- | -------------- |
| Save roll      | `label.form-label` | `form-text`     | None shown     |
| Notes          | `label.form-label` | `form-text`     | None shown     |
| Private notes  | `label.form-label` | `form-text`     | None shown     |

Note: This template does NOT include error display for any fields. The narrative edit view includes `invalid-feedback` blocks for its fields, but this template omits them entirely. This is a significant oversight.

### Buttons

| Label  | Element    | Classes            | Notes                    |
| ------ | ---------- | ------------------ | ------------------------ |
| Save   | `button`   | `btn btn-primary`  | No `btn-sm`              |
| Cancel | `a`        | `btn btn-link`     | Links to `return_url`    |

### Icons

- None in the primary template.

## Typography Usage

| Element      | Tag     | Classes        | Text example                                   |
| ------------ | ------- | -------------- | ---------------------------------------------- |
| Page heading | `h1`    | `h3`           | "Notes: {name} - {content_fighter.name}"      |
| Form labels  | `label` | `form-label`   | "Save roll", "Notes", "Private notes"          |
| Help text    | `div`   | `form-text`    | Field help text                                |

## Colour Usage

| Purpose   | Colour token    | Bootstrap class |
| --------- | --------------- | --------------- |
| Help text | Muted (via BS)  | `form-text`     |

Minimal colour usage -- even less than narrative edit because there are no error states.

## Spacing Values

| Location               | Classes                                       |
| ---------------------- | --------------------------------------------- |
| Outer column           | `col-12 col-md-8 col-lg-6 px-0 vstack gap-3` |
| Fields container       | `vstack gap-3`                                |
| Each field wrapper     | `div` (no classes)                            |
| Button wrapper         | `mt-3`                                        |

## Custom CSS

No custom CSS classes used in this template.

## Inconsistencies

1. **No error display**: Unlike narrative edit (which shows `invalid-feedback` per-field) and stats edit (which shows both per-field and page-level errors), this template has no error rendering at all. If form validation fails, the user will not see why.
2. **Field wrapper styling**: Each field is in a bare `div` inside the `vstack`, while narrative edit uses `div.mb-3` per field. Since notes uses `vstack gap-3`, the visual spacing result is similar, but the approach is inconsistent.
3. **Form structure**: Uses `vstack gap-3` for fields, narrative uses sequential `div.mb-3` blocks. Both produce similar visual results but via different spacing mechanisms.
4. **`allauth` tag loaded but unused**.
5. **Heading format**: "Notes: {name} - {content_fighter.name}" matches narrative's "{label}: {name} - {content_fighter.name}" pattern. Consistent within this pair.
6. **No `enctype`**: Correct (no file upload), but the form does include `{{ form.media }}` -- worth verifying this isn't needed.
7. **Three text fields**: This view has three fields (save_roll, notes, private_notes) compared to narrative's two (image, narrative). The vertical `vstack gap-3` layout works well for this.

## Accessibility Notes

- Form labels use `for` attribute with `id_for_label`, correctly linking labels to inputs.
- No `aria-label` on the form element.
- No error feedback means screen readers cannot announce validation failures.
- Help text is rendered as `form-text` divs but not linked to inputs via `aria-describedby`.
- The `{{ form.media }}` may introduce widgets with their own accessibility implications.
