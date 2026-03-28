# View Audit: Login

## Metadata

- **URL:** `/accounts/login/`
- **Template:** `account/login.html`
- **Template chain:** `core/layouts/foundation.html` > `core/layouts/base.html` > `allauth/layouts/base.html` > `allauth/layouts/entrance.html` > `account/base_entrance.html` > `account/login.html`
- **Element templates used:** `allauth/elements/h1.html`, `allauth/elements/form.html`, `allauth/elements/fields.html`, `allauth/elements/field.html`, `allauth/elements/button.html`, `allauth/elements/hr.html`, `allauth/elements/button_group.html`

## Components Found

### Buttons

| Text | Classes | Variant | Size | Icon | Notes |
|------|---------|---------|------|------|-------|
| Sign In (submit) | `btn btn-primary` | Primary | Default | None | Via `allauth/elements/button.html`; always `btn-primary` for submit type |
| Sign in with a passkey | `btn btn-primary` | Primary | Default | None | Conditional; via button element with `tags="prominent,login,outline,primary"` but tags are not reflected in CSS |
| Mail me a sign-in code | `btn btn-primary` or `<a>` with `btn btn-primary` | Primary | Default | None | Conditional; renders as `<a>` if `href` is set |

### Cards

None found.

### Navigation

| Component | Classes | Notes |
|-----------|---------|-------|
| Account menu dropdown (mobile) | `dropdown d-lg-none mb-3` | From `allauth/layouts/base.html`; shows for authenticated users only (not typically visible on login page) |
| Account menu tabs (desktop) | `d-none d-lg-flex nav nav-tabs` | From `allauth/layouts/base.html`; also only for authenticated users |

### Forms

| Form ID | Action | Method | Classes | Notes |
|---------|--------|--------|---------|-------|
| (login form) | `account_login` URL | POST | `col-12 col-12 col-md-8 col-lg-6` | Via `allauth/elements/form.html`; note doubled `col-12` |
| (implicit) CSRF token included | -- | -- | -- | Standard Django CSRF |

### Form Controls

| Control | Type | Classes | Notes |
|---------|------|---------|-------|
| Login field (username) | text/email | `form-control` | Via `allauth/elements/fields.html` with `add_bootstrap_class` filter |
| Password field | password | `form-control` | Via `allauth/elements/fields.html` |
| Remember me (if enabled) | checkbox | `form-check-input` | Conditional |

### Icons (Bootstrap Icons)

| Icon class | Context | Purpose |
|------------|---------|---------|
| `bi bi-info-circle` | Email warning message | Information indicator |

### Alerts

| Element | Classes | Notes |
|---------|---------|-------|
| Email warning | `form-text text-warning mb-3 d-none` | Initially hidden; shown via JS when input looks like email |
| Non-field errors (from fields.html) | `alert alert-danger` | Shown when form has validation errors |

### Other Components

| Component | Classes | Notes |
|-----------|---------|-------|
| Horizontal rule | `<hr>` | Via `allauth/elements/hr.html`; plain `<hr>` with no classes |
| Button group wrapper | `<div>` | Via `allauth/elements/button_group.html`; plain `<div>` with no classes |
| Form actions | `hstack gap-3 mt-4` | From `allauth/elements/form.html`; wraps submit button |
| Sign-up link | plain `<a>` in `<p>` | Standard link text |

## Typography Usage

| Element | Classes applied | Semantic role |
|---------|----------------|---------------|
| Page heading | `<h1>` (no classes) | Via `allauth/elements/h1.html`; "Sign In" |
| Sign-up prompt | `<p>` (no classes) | Instructional text |
| Form labels | `form-label` | Via `allauth/elements/fields.html` |
| Help text | `form-text` | Via `allauth/elements/fields.html` |
| Validation errors | `invalid-feedback d-block` | Error messages |
| Email warning | `form-text text-warning mb-3` | Warning text |

## Colour Usage

| Element | Property | Source | Semantic purpose |
|---------|----------|-------|-----------------|
| Submit button | background | `btn-primary` | Primary action |
| Email warning | color | `text-warning` | Warning state |
| Non-field errors | background/border | `alert alert-danger` | Error state |
| Validation errors | color | `invalid-feedback` | Error text |
| Sign-up link | color | default `<a>` | Navigation |

## Spacing Values

| Element | Property | Source class | Notes |
|---------|----------|-------------|-------|
| Content container | margin | `my-3 my-md-5` | From `allauth/layouts/base.html` |
| Form wrapper | width | `col-12 col-md-8 col-lg-6` | Responsive width constraint |
| Form fields | margin-bottom | `mb-3` | Between form fields |
| Form actions | margin-top | `mt-4` | Before submit button |
| Form actions | gap | `hstack gap-3` | Between action buttons |
| Email warning | margin-bottom | `mb-3` | Below warning text |

## Custom CSS

None used directly in this template. All styling comes from Bootstrap and allauth element templates.

## Inconsistencies

| Issue | Elements involved | Description | Severity |
|-------|-------------------|-------------|----------|
| Doubled `col-12` in form | `allauth/elements/form.html` | Template outputs `class="col-12 col-12 col-md-8 col-lg-6"` because it always adds `col-12` and the non-wide form also adds `col-12`. Harmless but redundant. | Low |
| Button tags not reflected in CSS | Passkey/code buttons | Element tags like `outline,primary` are passed but the button template ignores them -- all submit buttons get `btn-primary` regardless. The `outline` tag is not honoured. | Medium |
| `bi bi-info-circle` vs `bi-info-circle` | Email warning icon | Uses `bi bi-info-circle` (space-separated) while all other icons in the codebase use `bi-{name}` (hyphenated). Both work in Bootstrap Icons but the format is inconsistent. | Low |
| allauth base duplicates message handling | `allauth/layouts/base.html` vs `core/layouts/base.html` | Both templates have the messages block. The allauth base overrides `{% block body %}` to add its own container with messages, creating a potential for double-rendering if both are present. | Medium |
| No `btn-sm` on any button | Login form buttons | All buttons use default size, unlike many other pages that use `btn-sm`. For a standalone form page, this is likely intentional. | Low |

## Accessibility Notes

- Form fields use `<label>` with `for` attribute linking to field `id`.
- The email warning has `role="alert"` for screen reader announcement.
- The email warning is shown/hidden via `d-none` class toggle.
- Non-field errors use `role="alert"` via Bootstrap alert classes.
- Validation errors use `invalid-feedback` with `d-block` to ensure visibility.
- The login form does not have `aria-labelledby` linking to the `<h1>`.
- Password field should have `autocomplete="current-password"` (depends on allauth configuration).
