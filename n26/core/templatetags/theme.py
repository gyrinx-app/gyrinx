"""Template helpers for resolving theme values."""

from django import template

register = template.Library()

# Tokens that are a colour in their own right rather than a step on a scale, so
# they take no shade: var(--color-accent), not var(--color-accent-500).
SINGULAR = {
    "accent",
    "accent-content",
    "accent-foreground",
    "accent-muted",
    "muted",
    "bg",
    "surface",
    "box-border",
    "input-bg",
    "white",
    "black",
}


@register.filter
def css_color(value, shade="500"):
    """Resolve a colour prop to something usable in a style attribute.

    Lets one prop take either a literal or a theme colour, so a call site never
    has to say which kind it meant::

        {{ "#8d9900"|css_color }}      -> #8d9900
        {{ "accent"|css_color }}       -> var(--color-accent)
        {{ "red"|css_color:"600" }}    -> var(--color-red-600)

    A value is a literal if it contains "#" or "(" — covering hex, rgb(), oklch()
    and var(). Anything else is a token name, and resolving through var() rather
    than a fixed value is the point: a swatch set to `accent` follows a theme
    change, where a hex is frozen deliberately because a person chose it.

    Names are not validated. An unknown one yields a var() that resolves to
    nothing, which shows up as a transparent swatch rather than an exception —
    the right failure for a decorative mark.
    """
    if not value:
        return "transparent"
    value = str(value)
    if "#" in value or "(" in value:
        return value
    if value in SINGULAR:
        return f"var(--color-{value})"
    return f"var(--color-{value}-{shade})"
