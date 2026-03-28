# View Audit: Campaign New

## Metadata

| Field | Value |
|---|---|
| URL | `/campaigns/new/` |
| Template | `core/campaign/campaign_new.html` |
| Extends | `core/layouts/base.html` |
| Template tags loaded | `allauth`, `custom_tags` |
| Included templates | `core/includes/back.html` |
| Complexity | Low -- simple form page, nearly identical to campaign_edit |

## Components Found

### Buttons

| Element | Classes | Variant | Context |
|---|---|---|---|
| Create submit | `btn btn-primary` | Primary (no size modifier) | Form submit |
| Cancel link | `btn btn-link` | Link (no size modifier) | Form cancel |

**Observations:**

- Identical button pattern to campaign_edit
- Submit label is "Create" (vs "Save" in edit) -- correct verb differentiation
- Cancel links to `{% safe_referer '/campaigns/' %}` (referrer with fallback) vs edit page's explicit URL

### Cards

No card components used.

### Tables

No tables used.

### Navigation

| Element | Classes | Context |
|---|---|---|
| Back breadcrumb | `breadcrumb` / `breadcrumb-item active` | Top of page, no custom text (defaults to "Back") |

**Observations:**

- Uses `{% include "core/includes/back.html" %}` with NO `url` or `text` parameters, so it falls back to `{% safe_referer "/" %}` for the URL and "Back" for the text. This differs from campaign_edit which passes `text=form.instance.name`.

### Forms

| Form | Method | Classes | Context |
|---|---|---|---|
| Create form | POST | `vstack gap-3` | Main campaign creation form |

**Observations:**

- Identical form structure to campaign_edit
- `{{ form.media }}` included for widget assets
- Action URL uses `{% url 'core:campaigns-new' %}` (note: plural `campaigns-new` vs `campaign-edit` singular)

### Icons

No icons used directly.

### Other Components

None.

## Typography Usage

| Element | Classes | Usage |
|---|---|---|
| Page heading | `h1` with `h3` | "Create a new Campaign" |

**Observations:**

- Same `h1.h3` pattern as campaign_edit
- Heading text "Create a new Campaign" follows microcopy guidelines (sentence case, proper noun "Campaign")

## Colour Usage

| Colour | Bootstrap class | Context |
|---|---|---|
| Primary blue | `btn-primary` | Create button |
| Link default | `btn-link` | Cancel button |

## Spacing Values

| Spacing class | Context |
|---|---|
| `col-12 col-md-8 col-lg-6` | Form container responsive width |
| `px-0` | Remove horizontal padding from col |
| `vstack gap-3` | Form container and form element spacing |
| `mt-3` | Button group top margin |

Identical spacing to campaign_edit.

## Custom CSS

No custom CSS classes used in this template.

## Inconsistencies

1. **Back button behaviour**: No `text` or `url` parameters passed to `back.html`, so it shows generic "Back" text and uses the referrer URL. Compare with campaign_edit which passes `text=form.instance.name`, and other sub-pages which pass `url=campaign.get_absolute_url text="Back to Campaign"`. Since this is a creation page (no existing campaign to reference), the generic "Back" is defensible, but the fallback to referrer could be surprising if the referrer is unexpected.

2. **Cancel link destination**: Uses `{% safe_referer '/campaigns/' %}` which is referrer-based with a fallback. Campaign_edit uses a deterministic `{% url 'core:campaign' form.instance.id %}`. The referrer-based approach is necessary here since no campaign exists yet.

3. **Template near-duplication**: This template is nearly identical to campaign_edit -- only the heading text, submit button label, form action URL, back link parameters, and cancel link destination differ. These could potentially share a base form template.

## Accessibility Notes

- Form has proper `method="post"` and CSRF token
- Back link uses breadcrumb ARIA semantics
- Same considerations as campaign_edit regarding form field labels from `{{ form }}` rendering
- The `safe_referer` tag prevents open redirect vulnerabilities in the cancel link
