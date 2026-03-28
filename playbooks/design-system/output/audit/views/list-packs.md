# View Audit: List Packs

## Metadata

- **URL**: `/list/<id>/packs`
- **Template**: `core/list_packs.html`
- **Extends**: `core/layouts/base.html` -> `core/layouts/foundation.html`
- **Template tags loaded**: `allauth`, `custom_tags`
- **Key includes**:
  - `core/includes/back.html` (with `url=list_url text=list.name`)

## Components Found

### Buttons

| Pattern | Classes | Location |
|---------|---------|----------|
| Search | `btn btn-outline-secondary` | search form input group (**no `btn-sm`**) |
| Clear | `btn btn-outline-secondary` | search form input group (conditional) |
| Remove (unsubscribe) | `btn btn-sm btn-outline-danger` | subscribed packs list |
| Subscribe | `btn btn-sm btn-primary` | available packs list |

### Forms

| Pattern | Classes | Location |
|---------|---------|----------|
| Search form | `mb-3 vstack gap-2` (GET) | available packs section |
| Search input group | `input-group input-group-sm` | search form |
| Search input | `form-control` | search form |
| My packs toggle | `form-check form-switch mb-0` | search form |
| Checkbox input | `form-check-input` with `data-gy-toggle-submit` | my packs toggle |
| Checkbox label | `form-check-label fs-7 mb-0` | my packs toggle |
| Hidden input | `type="hidden" name="my" value="0"` | my packs toggle (fallback) |
| Unsubscribe form | `d-inline` (POST) | subscribed packs items |
| Subscribe form | (no extra classes, POST) | available packs items |

### Navigation

| Pattern | Classes | Location |
|---------|---------|----------|
| Back breadcrumb | `breadcrumb` / `breadcrumb-item active` | back.html (with list name) |
| Back icon | `bi-chevron-left` | back.html |

### Badges

| Pattern | Classes | Context |
|---------|---------|---------|
| Subscribed count | `badge bg-primary` | subscribed packs section header |

### Icons

- `bi-chevron-left` - Back navigation
- `bi-box-seam` - (not used directly on this page, but referenced in context)

### Other Components

| Pattern | Classes | Location |
|---------|---------|----------|
| Section headers | `d-flex justify-content-between align-items-center mb-3 bg-body-secondary rounded px-2 py-1` | both sections |
| Section heading | `h2.h5.mb-0` | both sections |
| Unstyled list | `list-unstyled mb-0` | subscribed and available packs |
| Pack list item | `py-2 d-flex justify-content-between align-items-center border-bottom` | pack items |
| Pack name link | `linked fw-medium` | pack items |
| Pack owner | `text-muted small` | pack items |
| Pack summary | `text-muted small` (in a `div`) | pack items (conditional) |
| Empty state (subscribed) | `text-center text-muted mb-0` | subscribed section |
| Empty state (available) | `text-center text-muted mb-0` | available section |
| Description text | `text-muted small` | page description |

## Typography Usage

| Element | Classes | Size | Context |
|---------|---------|------|---------|
| Page title | `h1.h3` | h3 size | "Content Packs" |
| Page description | `text-muted small` | small | Explanatory text |
| Section headers | `h2.h5.mb-0` | h5 size | "Subscribed Packs", "Available Packs" |
| Pack name | `linked fw-medium` | base, medium weight | pack links |
| Pack owner | `text-muted small` | small | "by {owner}" |
| Pack summary | `text-muted small` | small | truncated summary |
| Toggle label | `form-check-label fs-7 mb-0` | ~0.79rem | "Your Packs only" |
| Empty state | `text-center text-muted mb-0` | base | "No content packs subscribed yet." |
| Search placeholder | (input attribute) | input-group-sm size | "Search packs..." |

## Colour Usage

| Colour | Bootstrap Class | Context |
|--------|----------------|---------|
| Primary | `btn btn-sm btn-primary`, `badge bg-primary` | Subscribe button, count badge |
| Secondary | `btn btn-outline-secondary` | Search/Clear buttons |
| Danger (outline) | `btn btn-sm btn-outline-danger` | Remove button |
| Muted | `text-muted` | Owner names, summaries, empty states |
| Body secondary | `bg-body-secondary` | Section header backgrounds |

## Spacing Values

| Property | Values Used | Context |
|----------|-------------|---------|
| Content column | `col-12 col-xl-6` | page wrapper |
| Column padding | `px-0` | page wrapper |
| Content gap | `gap-4` (vstack) | page wrapper |
| Section header margin | `mb-3` | section headers |
| Section header padding | `px-2 py-1` | section headers |
| List item padding | `py-2` | pack list items |
| Search form margin | `mb-3` | search form |
| Search form gap | `gap-2` (vstack) | search form elements |
| Page description spacing | (after h1, no explicit margin) | text-muted small |

## Custom CSS

| Class | Definition | Used In |
|-------|-----------|---------|
| `linked` | Underline link styling | Pack name links |

## Inconsistencies

1. **Column width differs from form pages**: This page uses `col-12 col-xl-6` while the form pages (List Edit, List New) use `col-12 col-md-8 col-lg-6`. The breakpoint and proportion differ -- this page is narrower at lg but wider at md.

2. **Search button lacks `btn-sm`**: The Search and Clear buttons use `btn btn-outline-secondary` without `btn-sm`, but they're inside an `input-group-sm` container. The input-group-sm should make the buttons small, but the explicit `btn-sm` class is missing (Bootstrap's input-group-sm handles sizing for children, so this is likely fine functionally but inconsistent with the explicit `btn-sm` used elsewhere).

3. **Section header pattern differs from list detail**: On the list detail page, section headers like "Attributes" and "Assets & Resources" use `bg-body-secondary rounded px-2 py-1 mb-2` with `h3.h5`. Here, the section headers use the same visual style but with `h2.h5` and `mb-3`. The heading level and margin differ.

4. **Pack list item structure inconsistency with list detail metadata**: The subscribed/available packs list items use `py-2 d-flex justify-content-between align-items-center border-bottom`. This list-item pattern (border-bottom separator, flex row) is unique to this page. Other list patterns in the app use `list-group` or `vstack`.

5. **Subscribe vs Remove button variants**: Subscribe uses `btn btn-sm btn-primary` while Remove uses `btn btn-sm btn-outline-danger`. The primary action (subscribe) uses a filled button, while the destructive action (remove) uses an outline button. This is a reasonable convention but differs from the list detail page where destructive actions (archive, delete) use `text-danger` on dropdown items rather than outline buttons.

6. **Empty state text alignment**: Empty states here use `text-center text-muted mb-0`, while empty states on other pages use left-aligned `text-muted` text. This is the only page that centers empty state messages.

7. **Description text placement**: The page description text (`text-muted small`) appears between the h1 and the first section with no explicit margin class. It relies on the vstack gap-4 for spacing, which creates more vertical space than typical description text spacing.

## Accessibility Notes

1. **Has `<h1>`**: This page correctly uses `<h1 class="h3">` for the page title.

2. **Proper heading hierarchy**: `h1` -> `h2` (sections). This is correct.

3. **Search form**: The search input lacks an explicit `<label>`. It uses a `placeholder` attribute ("Search packs...") which is not a substitute for a label. Screen readers may not announce the purpose of the field. The `aria-label` is also missing.

4. **Toggle switch**: The "Your Packs only" toggle uses `<label>` with `for="my-packs"` properly associated with the input via `id="my-packs"`. The hidden input with `name="my" value="0"` provides a fallback value when unchecked.

5. **Form submission via `data-gy-toggle-submit`**: The checkbox uses a custom data attribute to auto-submit the form on change. This JavaScript behavior may not be apparent to screen reader users. The form is still submittable via the Search button.

6. **Inline unsubscribe forms**: Each unsubscribe action is a separate `<form>` with a submit button. This means screen readers will encounter many forms on the page. Each form has a CSRF token and hidden inputs but no `aria-label` to distinguish them.

7. **Pack links**: Pack names link to the pack detail page using `<a href="..." class="linked fw-medium">`, which is semantically clear.

8. **Section landmark**: The page uses `<section>` elements for the subscribed and available packs sections. However, the sections lack `aria-label` or `aria-labelledby` attributes, so screen readers won't distinguish them by name.
