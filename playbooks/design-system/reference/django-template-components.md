# Django Template Components Guide

How to build reusable UI components using Django's template system.

## `{% include %}` with `{% with %}`

The primary component pattern:

```django
{% include "components/button.html" with variant="primary" size="sm" text="Save" icon="bi-check" %}
```

The included template receives the variables in its context.

## Custom Template Tags

For more complex components:

```python
# templatetags/designsystem.py
@register.inclusion_tag("components/card.html")
def card(title, variant="default"):
    return {"title": title, "variant": variant}
```

Usage: `{% card title="My Card" variant="primary" %}`

## Template Fragments with `{% block %}`

For composable layouts:

```django
{% extends "layouts/page.html" %}
{% block content %}...{% endblock %}
```

## Naming Conventions

- Directory: `templates/components/`
- Files: kebab-case (`section-header.html`, `data-table.html`)
- Template tags: snake_case (`{% section_header %}`)

## Documentation Pattern

Every component template starts with a comment block:

```django
{# components/button.html #}
{# Purpose: Renders a styled button or link-button #}
{# Required params: text #}
{# Optional params: variant (primary|secondary|outline|danger), size (sm|md|lg), icon (bi-* class), href, type #}
```

## Limitations

- No prop validation (convention-based)
- No TypeScript-style type checking
- Variables leak into/out of included templates unless `{% with %}` scopes them
- Testing requires rendering the template with a test context
