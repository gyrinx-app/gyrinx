# View Audit: Pack Edit

## Metadata

| Field         | Value                                                     |
|---------------|-----------------------------------------------------------|
| URL           | `/pack/<id>/edit/`                                        |
| Template      | `core/pack/pack_edit.html`                                |
| Extends       | `core/layouts/base.html` > `core/layouts/foundation.html` |
| Includes      | `core/includes/back.html`                                 |
| Template tags | `allauth`, `custom_tags`                                  |

## Components Found

### Navigation

- **Back button:** `core/includes/back.html` with no explicit `url` or `text` -- falls back to `safe_referer "/"` and "Back" label

### Forms

- Django form rendered via `{{ form }}` -- outputs standard Django form HTML with Bootstrap-compatible classes (assuming crispy forms or similar configured)
- `{{ form.media }}` for form media (JS/CSS for rich text editor or similar)
- `{% csrf_token %}` for CSRF protection
- Form action: POST to `core:pack-edit`
- Layout: `.vstack.gap-3` for vertical form field spacing

### Buttons

- `.btn.btn-primary` -- "Save" (full-size, not `.btn-sm`)
- `.btn.btn-link` -- "Cancel" (full-size, not `.btn-sm`)

### Other

- Form wrapper: `<form>` with `.vstack.gap-3`
- Button row: `div.mt-3`

## Typography Usage

| Element       | Tag / Class           | Notes                                |
|---------------|-----------------------|--------------------------------------|
| Page title    | `<h1 class="h3">`    | Correct: uses `.h3` override per design system |

## Colour Usage

| Usage         | Class / Value    | Notes                    |
|---------------|------------------|--------------------------|
| Save button   | `.btn-primary`   | Blue primary action      |
| Cancel link   | `.btn-link`      | Default link colour      |

## Spacing Values

| Location              | Class(es)                         | Value              |
|-----------------------|-----------------------------------|--------------------|
| Outer container       | `.col-12.col-md-8.col-lg-6.px-0.vstack.gap-3` | 1rem vert gap |
| Form fields           | `.vstack.gap-3`                   | 1rem between fields |
| Button row            | `.mt-3`                           | 1rem top margin     |

## Custom CSS

None used beyond the base layout.

## Inconsistencies

1. **Save button is full-size `.btn.btn-primary`** without `.btn-sm`. The design system debug page says full-size buttons are "used sparingly" and shows the exact pattern of `btn btn-primary` (full) + `btn btn-link` (Cancel) as a valid form pattern. This is consistent with the design system's form submission convention, but inconsistent with the `.btn-sm` used everywhere else in the app.
2. **Back button has no explicit URL or text.** It falls back to `safe_referer` which may produce unexpected back navigation if the user arrived from a non-pack page. Other pack pages pass explicit `url` and `text`.
3. **Container width uses `.col-12.col-md-8.col-lg-6`** which is narrower than pack detail's `.col-12.col-xl-8`. This is appropriate for a form but uses a different breakpoint progression (`col-md-8.col-lg-6` vs `col-xl-8`).
4. **No error display pattern** visible in the template. Django form errors will be rendered by `{{ form }}` but there is no explicit error summary or error styling in this template. The `errorlist` custom class in `styles.scss` will handle individual field errors.

## Accessibility Notes

- Back button inherits `nav[aria-label="breadcrumb"]` from the include
- Form has no `aria-label` or `<fieldset>` / `<legend>` wrapping
- Save button has clear text label
- Cancel link provides a clear escape path
- Missing: No `aria-describedby` linking form fields to help text
- Missing: No visible form title associated with the form via `aria-labelledby`
