# View Audit: List New

## Metadata

- **URL**: `/lists/new`
- **Template**: `core/list_new.html`
- **Extends**: `core/layouts/base.html` -> `core/layouts/foundation.html`
- **Template tags loaded**: `allauth`, `custom_tags`
- **Key includes**:
  - `core/includes/back.html` (breadcrumb navigation)

## Components Found

### Buttons

| Pattern | Classes | Location |
|---------|---------|----------|
| Create | `btn btn-primary` | form submit (**no `btn-sm`**) |
| Cancel | `btn btn-link` | inline (not via cancel.html) |

### Forms

| Pattern | Classes | Location |
|---------|---------|----------|
| Main form | `vstack gap-3` | list_new.html |
| Form action | POST to `core:lists-new` | list_new.html |
| CSRF token | `{% csrf_token %}` | list_new.html |
| Form media | `{{ form.media }}` | list_new.html |
| Form rendering | `{{ form }}` (default Django rendering) | list_new.html |
| Button group | `mt-3` (wrapper div) | list_new.html |

### Badges

| Pattern | Classes | Context |
|---------|---------|---------|
| Content pack name | `badge bg-secondary` | selected_packs display |

### Navigation

| Pattern | Classes | Location |
|---------|---------|----------|
| Back breadcrumb | `breadcrumb` / `breadcrumb-item active` | back.html |
| Back icon | `bi-chevron-left` | back.html |

### Links

| Pattern | Classes | Location |
|---------|---------|----------|
| Change packs | `link-secondary small` | selected_packs section |

### Other Components

| Pattern | Classes | Location |
|---------|---------|----------|
| Selected packs box | `border rounded p-3` | list_new.html (conditional) |
| Pack header row | `d-flex justify-content-between align-items-center mb-2` | list_new.html |
| Pack label | `fw-medium` | list_new.html |
| Pack badges container | `d-flex flex-wrap gap-1` | list_new.html |

## Typography Usage

| Element | Classes | Size | Context |
|---------|---------|------|---------|
| Page title | `h1.h3` | h3 size | "Create a new List" |
| Content packs label | `fw-medium` (span) | base, medium weight | "Content Packs" |
| Change link | `link-secondary small` | small | "Change" |
| Pack badges | `badge bg-secondary` | badge size | pack names |
| Form labels | (Django default rendering) | base | Form field labels |

## Colour Usage

| Colour | Bootstrap Class | Context |
|--------|----------------|---------|
| Primary | `btn btn-primary` | Create button |
| Secondary | `bg-secondary`, `link-secondary` | Pack badges, Change link |
| Link | `btn btn-link` | Cancel button |
| Border | `border rounded` | Selected packs container |

## Spacing Values

| Property | Values Used | Context |
|----------|-------------|---------|
| Content column | `col-12 col-md-8 col-lg-6` | form wrapper |
| Column padding | `px-0` | form wrapper |
| Form gap | `gap-3` (vstack) | form element |
| Button group margin | `mt-3` | submit/cancel wrapper |
| Selected packs box | `p-3` | border rounded container |
| Packs header margin | `mb-2` | header row |
| Packs badges gap | `gap-1` | flex-wrap container |

## Custom CSS

No custom CSS classes used beyond Bootstrap utilities.

## Inconsistencies

1. **Cancel button implementation differs from List Edit**: Here, the Cancel link is written inline as `<a href="{% safe_referer '/lists/' %}" class="btn btn-link">Cancel</a>`. The List Edit page uses `{% include "core/includes/cancel.html" %}`. Both produce the same visual result but the implementation differs. The cancel.html include also supports custom text and URL parameters that aren't used here.

2. **Column width matches List Edit**: Both use `col-12 col-md-8 col-lg-6`, which is consistent within form pages. This is good.

3. **Selected packs container uses `p-3`**: The selected packs container uses `p-3`, while most other bordered containers in the app (like the archive banner) use `p-2`. This is a minor spacing inconsistency.

4. **No content packs section heading**: The selected packs section doesn't use a heading element -- it uses `<span class="fw-medium">Content Packs</span>`. The List Edit page uses `<h2 class="h5">Content Packs</h2>` for its content packs section. Different semantic elements for the same concept.

5. **Pack badge style differs from Packs page**: Here, pack names are shown as `badge bg-secondary`. On the Packs page, pack names are shown as `fw-medium` links. The visual representation of pack names is inconsistent.

6. **Create vs Save button text**: This page uses "Create" while List Edit uses "Save". This is semantically correct (create vs update) and is a good pattern. Both lack `btn-sm`.

## Accessibility Notes

1. **Has `<h1>`**: This page correctly uses `<h1 class="h3">` for the page title.

2. **Back navigation**: Uses breadcrumb with proper ARIA (`aria-label="breadcrumb"`, `aria-current="page"`).

3. **Form accessibility**: Same as List Edit -- relies on Django's default form rendering for label associations.

4. **Selected packs**: The packs display section has no `role` or ARIA attributes. Screen readers will read it as generic content. The pack names in badges are readable.

5. **Cancel link**: Uses `{% safe_referer %}` for the URL, which is a security-aware redirect. The link text "Cancel" is clear.
