# Django Template Components Implementation

## Process

### 1. Create Template Include Files

In `templates/components/`, one `.html` file per component from the spec:

- Each accepts parameters via `{% with %}` or template context
- Each has a comment block at the top documenting parameters
- Uses Bootstrap classes internally — the component is the abstraction
- Naming: `components/{component-name}.html` (kebab-case)

### 2. Custom Template Tags (if needed)

If any components need them, create in the `designsystem` app's `templatetags/` directory.

### Example Component

```django
{# components/button.html #}
{# Params: variant (primary|secondary|outline|danger), size (sm|md|lg), icon (bi-* class), text, href (optional) #}
{% with variant=variant|default:"primary" size=size|default:"md" %}
{% if href %}
<a href="{{ href }}" class="btn btn-{{ variant }}{% if size != 'md' %} btn-{{ size }}{% endif %}">
  {% if icon %}<i class="bi {{ icon }}"></i> {% endif %}{{ text }}
</a>
{% else %}
<button type="{{ type|default:'button' }}" class="btn btn-{{ variant }}{% if size != 'md' %} btn-{{ size }}{% endif %}">
  {% if icon %}<i class="bi {{ icon }}"></i> {% endif %}{{ text }}
</button>
{% endif %}
{% endwith %}
```
