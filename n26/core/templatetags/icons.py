"""Template access to the icon registry. See core/icons.py."""

from django import template

from n26.core import icons

register = template.Library()


@register.filter
def icon_paths(name):
    """The subpaths for an icon name, for <c-n26.icon> to loop over."""
    return icons.paths(name)


@register.filter
def is_local_icon(name):
    """Whether this drawing is ours rather than Heroicons', for the gallery."""
    return name in icons.LOCAL


@register.filter
def is_solid_icon(name):
    """Whether this drawing is filled rather than stroked — the brand marks."""
    return icons.is_solid(name)
