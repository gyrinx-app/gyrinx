# View Audit: List Edit

## Metadata

- **URL**: `/list/<id>/edit`
- **Template**: `core/list_edit.html`
- **Extends**: `core/layouts/base.html` -> `core/layouts/foundation.html`
- **Template tags loaded**: `allauth`, `custom_tags`
- **Key includes**:
  - `core/includes/back.html` (breadcrumb navigation)
  - `core/includes/cancel.html` (cancel link)

## Components Found

### Buttons

| Pattern | Classes | Location |
|---------|---------|----------|
| Save | `btn btn-primary` | form submit (**no `btn-sm`**) |
| Cancel | `btn btn-link` | cancel.html include |
| Manage Content Packs | `btn btn-secondary btn-sm` | conditional content packs section |

### Forms

| Pattern | Classes | Location |
|---------|---------|----------|
| Main form | `vstack gap-3` | list_edit.html |
| Form action | POST to `core:list-edit` | list_edit.html |
| CSRF token | `{% csrf_token %}` | list_edit.html |
| Form media | `{{ form.media }}` | list_edit.html (for rich text editors, etc.) |
| Form rendering | `{{ form }}` (default Django rendering) | list_edit.html |
| Button group | `mt-3` (wrapper div) | list_edit.html |

### Navigation

| Pattern | Classes | Location |
|---------|---------|----------|
| Back breadcrumb | `breadcrumb` / `breadcrumb-item active` | back.html |
| Back icon | `bi-chevron-left` | back.html |

### Icons

- `bi-chevron-left` - Back navigation
- `bi-box-seam` - Content Packs link

### Other Components

| Pattern | Classes | Location |
|---------|---------|----------|
| Content packs section | `border-top pt-3 mt-2` | list_edit.html (conditional) |
| Content packs description | `text-muted small` | list_edit.html |

## Typography Usage

| Element | Classes | Size | Context |
|---------|---------|------|---------|
| Page title | `h1.h3` | h3 size | "Edit {list.name}" |
| Content packs heading | `h2.h5` | h5 size | "Content Packs" |
| Content packs description | `text-muted small` | small | Pack description text |
| Form labels | (Django default rendering) | base | Form field labels |

## Colour Usage

| Colour | Bootstrap Class | Context |
|--------|----------------|---------|
| Primary | `btn btn-primary` | Save button |
| Secondary | `btn btn-secondary btn-sm` | Manage Content Packs button |
| Muted | `text-muted` | Content packs description |
| Link | `btn btn-link` | Cancel button |

## Spacing Values

| Property | Values Used | Context |
|----------|-------------|---------|
| Content column | `col-12 col-md-8 col-lg-6` | form wrapper |
| Column padding | `px-0` | form wrapper |
| Form gap | `gap-3` (vstack) | form element |
| Button group margin | `mt-3` | submit/cancel wrapper |
| Content packs section | `border-top pt-3 mt-2` | divider section |

## Custom CSS

No custom CSS classes beyond Bootstrap utilities.

## Inconsistencies

1. **Save button lacks `btn-sm`**: The Save button uses `btn btn-primary` without `btn-sm`, while the Content Packs button uses `btn btn-secondary btn-sm`. Primary action buttons on form pages appear to use full-size, while secondary actions use `btn-sm`. This is a deliberate pattern but should be documented.

2. **Cancel button as `btn btn-link`**: The Cancel action renders as `btn btn-link` via the `cancel.html` include. This is different from the List New page which uses `<a href="..." class="btn btn-link">Cancel</a>` inline. Both produce the same output but via different mechanisms.

3. **Form rendering**: Uses `{{ form }}` (Django's default table-based rendering in some versions, div-based in Django 5+). This differs from the credits edit page which uses `{{ form.as_div }}`. The rendering method should be consistent.

4. **Content packs section conditional**: The `has_custom_content` flag controls whether the Content Packs section is shown. This creates a different page structure for different users, which may surprise some users.

5. **Column width**: Uses `col-12 col-md-8 col-lg-6`, which is slightly different from the `col-12 col-xl-6` pattern used on the Packs page. Form pages don't have a consistent max-width pattern.

6. **Heading semantic levels**: `h1.h3` for the page title and `h2.h5` for the section heading. The visual sizes are reasonable but the semantic structure (h1 -> h2) is correct here, unlike some other pages.

## Accessibility Notes

1. **Has `<h1>`**: This page correctly uses `<h1 class="h3">` for the page title, unlike the Lore and Notes pages.

2. **Form accessibility**: Relies on Django's default form rendering for labels, input IDs, and help text associations. The exact accessibility depends on the form class implementation.

3. **Back navigation**: Uses breadcrumb `<nav aria-label="breadcrumb">` which is semantically appropriate. The `breadcrumb-item active` has `aria-current="page"` which is correctly used.

4. **No explicit `<label>` association visible**: The form rendering depends on Django's form rendering. If using `{{ form }}` without explicit template customization, labels should be auto-associated.

5. **Cancel link**: The cancel.html include renders as an `<a>` with `btn btn-link` class. This is semantically correct as navigation (not a form reset).
