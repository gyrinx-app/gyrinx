# View Audit: Campaign Edit

## Metadata

| Field | Value |
|---|---|
| URL | `/campaign/<id>/edit/` |
| Template | `core/campaign/campaign_edit.html` |
| Extends | `core/layouts/base.html` |
| Template tags loaded | `allauth`, `custom_tags` |
| Included templates | `core/includes/back.html` |
| Complexity | Low -- simple form page |

## Components Found

### Buttons

| Element | Classes | Variant | Context |
|---|---|---|---|
| Save submit | `btn btn-primary` | Primary (no size modifier) | Form submit |
| Cancel link | `btn btn-link` | Link (no size modifier) | Form cancel |

**Observations:**

- Neither button uses `btn-sm`, unlike the campaign detail page where all buttons are `btn-sm`
- This is appropriate for a form page -- full-size buttons are standard for form actions
- `btn btn-link` for Cancel is the project standard for form cancellation

### Cards

No card components used.

### Tables

No tables used.

### Navigation

| Element | Classes | Context |
|---|---|---|
| Back breadcrumb | `breadcrumb` / `breadcrumb-item active` | Top of page, links back using `form.instance.name` |

### Forms

| Form | Method | Classes | Context |
|---|---|---|---|
| Edit form | POST | `vstack gap-3` | Main campaign edit form |

**Observations:**

- Form renders via `{{ form }}` (Django form rendering) -- no manual field layout
- `{{ form.media }}` included for form widget assets (likely for rich text editor)
- Form container uses `vstack gap-3` for vertical spacing between fields
- Button container uses `mt-3` for top margin separation from form fields

### Icons

No icons used directly in this template (back.html uses `bi-chevron-left`).

### Other Components

None.

## Typography Usage

| Element | Classes | Usage |
|---|---|---|
| Page heading | `h1` with `h3` | "Edit Campaign" -- uses h3 sizing on h1 element |

**Observations:**

- Uses `h1.h3` pattern (semantic h1 with visual h3 size), which differs from campaign detail's plain `h1`
- This is a common pattern for sub-pages that are visually subordinate to the main entity page

## Colour Usage

| Colour | Bootstrap class | Context |
|---|---|---|
| Primary blue | `btn-primary` | Save button |
| Link default | `btn-link` | Cancel button |

Minimal colour usage -- form fields inherit from Django form widget rendering.

## Spacing Values

| Spacing class | Context |
|---|---|
| `col-12 col-md-8 col-lg-6` | Form container responsive width |
| `px-0` | Remove horizontal padding from col |
| `vstack gap-3` | Form container and form element spacing |
| `mt-3` | Button group top margin |

**Observations:**

- Container width `col-12 col-md-8 col-lg-6` restricts form width on larger screens -- different from campaign_new which uses the same pattern
- This is the standard form-page width constraint used across the project

## Custom CSS

No custom CSS classes used in this template.

## Inconsistencies

1. **Back button text**: Uses `form.instance.name` (the campaign name) as back text, linking back to the referrer. The campaign detail uses a hardcoded "All Campaigns" text. The other sub-pages (assets, resources, etc.) use "Back to Campaign" as back text. This page breaks the pattern by showing the campaign name instead of "Back to Campaign".

2. **Heading level pattern**: Uses `h1.h3` while the detail page uses a plain `h1`. This is intentional (sub-page visual subordination) but worth documenting as a pattern.

3. **Button sizing**: Full-size buttons (no `btn-sm`) vs `btn-sm` used on campaign detail. This is appropriate for form context but a design system should document when to use which size.

4. **No `color_tags` loaded**: Unlike most other campaign templates, this one does not load `color_tags`. This is correct since no colour-related template tags are used.

## Accessibility Notes

- Form has proper `method="post"` and CSRF token
- The back link uses breadcrumb ARIA semantics from `back.html`
- Missing: No visible form field labels are shown in the template -- these come from `{{ form }}` rendering, which should include labels. Verify that Django form rendering includes proper `<label>` elements.
- Missing: No form validation error display is explicitly templated -- relies on Django's built-in form error rendering.
- The Cancel link provides a clear escape path back to the campaign page.
