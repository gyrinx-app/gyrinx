"""Template access to n26's icon library. See core/icons.py."""

from django import template

from n26.core import icons

register = template.Library()


@register.simple_tag
def resolve_icon(name):
    """Resolve a component name to validated inline SVG geometry."""

    return icons.resolve(name)
