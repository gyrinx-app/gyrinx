# View Audit: Fighter Narrative Edit

## Metadata

| Field            | Value                                                        |
| ---------------- | ------------------------------------------------------------ |
| URL pattern      | `/list/<id>/fighter/<fid>/narrative`                         |
| Template         | `core/list_fighter_narrative_edit.html`                      |
| Extends          | `core/layouts/base.html`                                     |
| Includes         | `core/includes/list_common_header.html` (with fighter switcher) |
| Template tags    | `allauth`, `custom_tags`                                     |
| Form rendering   | Manual per-field with labels, help text, error display        |
| Has JS           | Possibly via `{{ form.media }}` (rich text editor widget)     |

## Components Found

### Navigation

- **Common header** (`list_common_header.html`): Included with `link_list="true"`, `fighter=form.instance`, and `fighter_url_name="core:list-fighter-narrative-edit"` for the fighter switcher.
- **Fighter switcher**: Active via the common header include.

### Images

- Conditional fighter image display: `img.size-em-4.size-em-md-5.img-thumbnail`
- Image is inside a `div.mb-2.me-2.flex-shrink-0` wrapper
- Uses custom `size-em-*` classes from `styles.scss` for responsive sizing

### Forms

- `form` with `method="post"`, `enctype="multipart/form-data"` (for image upload), explicit `action` URL
- Hidden `return_url` input
- `{{ form.media }}` included for widget JS/CSS (likely a rich text editor for narrative)
- CSRF token
- Two field groups, each in `div.mb-3`

### Form Fields

| Field      | Label pattern                         | Help text class | Error class                   |
| ---------- | ------------------------------------- | --------------- | ----------------------------- |
| Image      | `label.form-label`                    | `form-text`     | `invalid-feedback d-block`    |
| Narrative  | `label.form-label`                    | `form-text`     | `invalid-feedback d-block`    |

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
| Page heading | `h1`    | `h3`           | "Lore: {name} - {content_fighter.name}"       |
| Form labels  | `label` | `form-label`   | "Image", "Narrative"                           |
| Help text    | `div`   | `form-text`    | Field help text                                |

### Notes

- Heading text says "Lore" while the page title block says "Lore" too -- this is consistent within the view.
- `h1.h3` pattern matches stats/injuries/notes views.

## Colour Usage

| Purpose        | Colour token    | Bootstrap class          |
| -------------- | --------------- | ------------------------ |
| Error feedback | Danger (via BS) | `invalid-feedback`       |
| Help text      | Muted (via BS)  | `form-text`              |

Minimal colour usage -- this is a straightforward form.

## Spacing Values

| Location               | Classes                                              |
| ---------------------- | ---------------------------------------------------- |
| Outer column           | `col-12 col-md-8 col-lg-6 px-0 vstack gap-3`        |
| Image field group      | `mb-3`                                               |
| Image flex container   | `d-flex flex-column flex-md-row gap-2`               |
| Image preview wrapper  | `mb-2 me-2 flex-shrink-0`                            |
| Narrative field group  | `mb-3`                                               |
| Button wrapper         | `mt-3`                                               |

## Custom CSS

- `size-em-4`: 8em width/height (from `styles.scss` `$em-sizes` map)
- `size-em-md-5`: 16em width/height at md+ breakpoint (responsive variant)
- These are used for the fighter image thumbnail, providing responsive image sizing.

## Inconsistencies

1. **Heading text "Lore"**: Uses "Lore" while the URL name is `list-fighter-narrative-edit` and the field is `narrative`. The term "Lore" is user-facing microcopy that doesn't match the codebase naming.
2. **Form layout differs from notes**: This view uses `div.mb-3` for field groups, while the notes view uses a `div.vstack.gap-3` wrapper. Both are valid spacing patterns but the inconsistency is unnecessary.
3. **Image field uses flex layout**: The image upload has a complex `d-flex flex-column flex-md-row gap-2` layout for side-by-side preview and input at md+. This is unique to this view.
4. **`enctype="multipart/form-data"`**: Correct for image upload, but the other form views don't need it. Not an inconsistency per se, but a difference worth noting.
5. **Error display for image**: Iterates over errors with `{% for error in form.image.errors %}{{ error }}{% endfor %}` without separators, while other fields use `.errors.0` (first error only). Inconsistent error display strategy within the same template.
6. **`allauth` tag loaded but unused**.
7. **Submit label "Save"**: Matches notes view but differs from XP edit ("Update XP") and stats edit ("Save Changes").
8. **Button container**: Uses `div.mt-3` (no flex), same as stats/notes. XP edit uses `hstack gap-2 mt-3`.

## Accessibility Notes

- Form labels use `for` attribute with `id_for_label`, correctly linking labels to inputs.
- Image preview `img` has an `alt` attribute with `fighter.name`.
- No `aria-label` on the form element itself.
- Error feedback divs are not programmatically linked to their inputs via `aria-describedby`.
- `{{ form.media }}` may introduce additional accessibility considerations depending on the widget (e.g., rich text editors often have their own ARIA attributes).
