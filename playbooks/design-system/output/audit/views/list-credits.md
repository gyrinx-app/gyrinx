# View Audit: List Credits Edit

## Metadata

- **URL**: `/list/<id>/credits`
- **Template**: `core/list_credits_edit.html`
- **Extends**: `core/layouts/page.html` -> `core/layouts/base.html` -> `core/layouts/foundation.html`
- **Template tags loaded**: `custom_tags`
- **Key includes**:
  - `core/includes/list_common_header.html` (with `link_list="true"`)

## Components Found

### Buttons

| Pattern | Classes | Location |
|---------|---------|----------|
| Update Credits | `btn btn-primary` | form submit (**no `btn-sm`**) |
| Cancel | `btn btn-link` | inline link |
| Refresh cost | `btn btn-link btn-sm p-0 text-secondary` | list_common_header.html |

### Forms

| Pattern | Classes | Location |
|---------|---------|----------|
| Credits form | (no class on `<form>`) | list_credits_edit.html |
| Form rendering | `{{ form.as_div }}` | list_credits_edit.html (**differs from other forms**) |
| CSRF token | `{% csrf_token %}` | list_credits_edit.html |
| Button group | `hstack gap-2 mt-3 align-items-center` | list_credits_edit.html |

### Tables

| Pattern | Classes | Location |
|---------|---------|----------|
| Stats summary | `table table-sm table-borderless table-responsive text-center mb-0` | list_common_header.html |

### Navigation

| Pattern | Classes | Location |
|---------|---------|----------|
| (No back breadcrumb) | -- | Missing, uses common header instead |

### Badges

| Pattern | Classes | Context |
|---------|---------|---------|
| Current credits | `badge text-bg-primary` | credits display |
| Total earned | `badge text-bg-secondary` | credits display |

### Icons

- `bi-person` - Owner link (from list_common_header.html)
- `bi-award` - Campaign link (from list_common_header.html)

### Other Components

| Pattern | Classes | Location |
|---------|---------|----------|
| Container | `container` | wrapper div (from page.html block + explicit container) |
| Content column | `col-12 col-md-8 col-lg-6` | form wrapper |
| List group | `list-group list-group-flush` with `fs-5` | credits display |
| List group items | `list-group-item` | individual credit entries |

## Typography Usage

| Element | Classes | Size | Context |
|---------|---------|------|---------|
| Gang name | `h2.mb-0.h3` | h3 size | list_common_header.html (linked) |
| Page title | `h2` (plain) | h2 default size | "Edit Credits for {list.name}" |
| Credits list | `fs-5` on `<ul>` | ~1.25rem | credits values |
| Badge text | `badge text-bg-primary` / `badge text-bg-secondary` | badge size | credit amounts |
| Current label | default | base | "Current" |
| Total Earned label | default | base | "Total Earned" |

## Colour Usage

| Colour | Bootstrap Class | Context |
|--------|----------------|---------|
| Primary | `btn btn-primary`, `text-bg-primary` | Update button, current credits badge |
| Secondary | `text-bg-secondary` | Total earned badge |
| Link | `btn btn-link` | Cancel button |

## Spacing Values

| Property | Values Used | Context |
|----------|-------------|---------|
| Container | `container` (Bootstrap default) | outer wrapper |
| Row/Col | `row` / `col-12 col-md-8 col-lg-6` | form layout |
| Credits list margin | `mb-3` | list group |
| Button group | `gap-2 mt-3` (hstack) | submit/cancel |
| Header border spacing | `mb-3 pb-4 border-bottom` | list_common_header.html (with link_list) |

## Custom CSS

| Class | Definition | Used In |
|-------|-----------|---------|
| `linked` | Underline link styling | Owner link, list name link in header |

## Inconsistencies

1. **Extends `page.html` instead of `base.html`**: This is the only list view that extends `core/layouts/page.html` instead of `core/layouts/base.html` directly. The page.html layout adds a `col-lg-12 px-0 vstack gap-4` wrapper and `page_title`/`page_description` blocks, but this template doesn't use those blocks -- it overrides `content` directly. This means the page.html wrapper structure is present but unused, and the template adds its own `<div class="container">` inside, creating a **nested container** (`container` > `container` from base.html body).

2. **Double container**: Because `page.html` extends `base.html` which already wraps `{% block content %}` in `<div id="content" class="container my-3 my-md-5">`, and this template adds `<div class="container">` inside the content block, there are two nested `.container` divs. This causes the content to be narrower than intended.

3. **Form rendering method**: Uses `{{ form.as_div }}` while List Edit uses `{{ form }}` and List New uses `{{ form }}`. Three form pages, two rendering methods.

4. **Button group layout**: Uses `hstack gap-2 mt-3 align-items-center` while List Edit uses a plain `<div class="mt-3">` and List New also uses `<div class="mt-3">`. Different layout patterns for the same button group concept.

5. **No back navigation**: Unlike List Edit and List New which use `{% include "core/includes/back.html" %}`, this page has no back breadcrumb. Instead, it uses `list_common_header.html` with `link_list="true"`, which provides a link to the list but not a proper back navigation pattern.

6. **Page title is `<h2>` not `<h1>`**: The page title "Edit Credits for {list.name}" uses a plain `<h2>` without any sizing class override. Other edit/new pages use `<h1 class="h3">`. This means this page has no `<h1>`, and the `list_common_header.html`'s `h2.h3` appears before the page's `<h2>`, creating two `<h2>` elements with the first one visually styled as h3.

7. **List group for credits display**: Uses `list-group list-group-flush` with `list-group-item` for the credits summary. No other page in this audit uses `list-group` for displaying data (the embed offcanvas uses `list-group` but for a different purpose). This component choice is unique to this page.

8. **Cancel link implementation**: Uses `<a href="{% url 'core:list' list.id %}" class="btn btn-link">Cancel</a>` with a hardcoded URL. List Edit uses `{% include "core/includes/cancel.html" %}` which uses `{% safe_referer %}`. List New uses `{% safe_referer '/lists/' %}`. Three different cancel patterns across form pages.

9. **Currency symbol**: Credits are displayed with `¢` suffix (e.g., `{{ list.credits_current }}¢`). This matches the pattern used in the list_common_header.html stats table. Consistent within the app.

## Accessibility Notes

1. **Missing `<h1>`**: The page has no `<h1>`. The heading hierarchy goes `h2` (gang name in header) -> `h2` (page title). This is incorrect -- there should be an `<h1>` and the heading levels should not repeat at the same level for different content.

2. **List group semantics**: The `<ul class="list-group">` with `<li class="list-group-item">` elements is semantically correct for a list of items.

3. **Form label association**: Uses `{{ form.as_div }}` which provides proper label-input associations in Django 5+.

4. **Cancel link**: Clear text "Cancel" with a link to the list page. Semantically correct as navigation.

5. **Badge readability**: The badges use `text-bg-primary` and `text-bg-secondary` which ensure sufficient contrast between text and background colours.

6. **Stats table**: Inherits the same accessibility patterns (and issues) as `list_common_header.html` used on other pages.
