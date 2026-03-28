# View Audit: Account Home

## Metadata

- **URL:** `/accounts/`
- **Template:** `core/account_home.html`
- **Template chain:** `core/layouts/foundation.html` > `core/layouts/base.html` > `allauth/layouts/base.html` > `allauth/layouts/manage.html` > `account/base_manage.html` > `core/account_home.html`
- **Includes (from allauth base):** `account/snippets/menu.html`

## Components Found

### Buttons

| Text | Classes | Variant | Size | Icon | Notes |
|------|---------|---------|------|------|-------|
| Menu (mobile dropdown toggle) | `btn btn-outline-secondary dropdown-toggle` | Outline Secondary | Default | None | From `allauth/layouts/base.html`; no `btn-sm` |

### Cards

None found.

### Navigation

| Component | Classes | Notes |
|-----------|---------|-------|
| Mobile account menu | `dropdown d-lg-none mb-3` | Dropdown with `dropdown-menu`, items from `menu.html` using `dropdown-item` class |
| Desktop account tabs | `d-none d-lg-flex nav nav-tabs` | Tab navigation with `nav-item` and `nav-link` classes |

### Menu Items (from `account/snippets/menu.html`)

| Text | Icon | Classes (tab mode) | Notes |
|------|------|--------------------|-------|
| {username} | `bi-gear` | `icon-link nav-link` + active class | Account home link |
| Change Username | None | `nav-link` | Only shown if username contains '@' |
| Change Email | None | `nav-link` | Standard allauth link |
| Change Password | None | `nav-link` | Standard allauth link |
| Two-Factor Authentication | None | `nav-link` | MFA link |
| Sessions | None | `nav-link` | User sessions link |
| Sign Out | None | `nav-link link-danger` | Danger-coloured link |

### Forms

None found (the content block is an empty `<div class="vstack gap-4">`).

### Icons (Bootstrap Icons)

| Icon class | Context | Purpose |
|------------|---------|---------|
| `bi-gear` | Account home menu item | Settings indicator |

### Dropdowns

| Trigger | Menu classes | Notes |
|---------|-------------|-------|
| "Menu" button | `dropdown-menu` | Standard dropdown; items use `dropdown-item` class |

### Other Components

| Component | Classes | Notes |
|-----------|---------|-------|
| Content area | `vstack gap-4` | Empty container; this page has no actual content |
| Messages container | (from allauth base) | Duplicated message handling block |

## Typography Usage

| Element | Classes applied | Semantic role |
|---------|----------------|---------------|
| Page title | "Your Account" via `{% trans %}` in `<title>` only | Only in browser tab; no visible heading on the page |
| Menu items | Standard link text | Navigation labels |

## Colour Usage

| Element | Property | Source | Semantic purpose |
|---------|----------|-------|-----------------|
| Sign Out link | color | `link-danger` | Destructive action warning |
| Active menu item | varies | Bootstrap `active` class on `nav-link` / `dropdown-item` | Current page indicator |
| Menu dropdown toggle | border/text | `btn-outline-secondary` | Neutral action |

## Spacing Values

| Element | Property | Source class | Notes |
|---------|----------|-------------|-------|
| Menu container | margin | `my-3 my-md-5` | From allauth base |
| Content container | margin | `my-3 my-md-5` | From allauth base; separate container |
| Mobile dropdown | margin-bottom | `mb-3` | Space below dropdown |
| Content vstack | gap | `gap-4` | Currently empty |

## Custom CSS

None used in this template. The `active` view detection uses custom template tags (`{% active_view %}`, `{% active_aria %}`).

## Inconsistencies

| Issue | Elements involved | Description | Severity |
|-------|-------------------|-------------|----------|
| No visible page heading | Account home page | The page has no `<h1>` or visible heading -- only the `<title>` tag says "Your Account". All other audited pages have at least a hidden `<h1>`. | High |
| Empty content area | `<div class="vstack gap-4"></div>` | The content block is completely empty. This page serves only as a navigation hub via the menu tabs, but the empty content area feels like a placeholder. | Medium |
| Two containers in allauth base | Menu container + content container | The allauth base template creates two separate `.container.my-3.my-md-5` elements -- one for the menu and one for content. This creates inconsistent vertical spacing compared to pages using the standard `base.html` content block. | Medium |
| Duplicate messages block | allauth base vs standard base | The allauth base overrides `{% block body %}` and adds its own messages handling, duplicating the pattern from `core/layouts/base.html`. | Medium |
| Menu button size | `btn btn-outline-secondary dropdown-toggle` | No `btn-sm`; same inconsistency as flatpage dropdown button and other dropdown toggles that use `btn-sm`. | Low |
| `link-danger` on Sign Out | Menu item | Only Sign Out uses `link-danger`; it also has a trailing space in the class string. Functionally fine but the extra space is sloppy. | Low |

## Accessibility Notes

- Tab navigation uses `{% active_aria %}` template tag which likely adds `aria-current="page"` for the active tab.
- Mobile dropdown uses standard Bootstrap dropdown ARIA.
- Missing visible `<h1>` heading -- screen readers rely on heading hierarchy for page navigation.
- Sign Out link is visually distinguished with `link-danger` but has no additional ARIA attribute to indicate its destructive nature.
- The menu is duplicated (dropdown + tabs) for responsive purposes, which means screen readers encounter the navigation twice.
