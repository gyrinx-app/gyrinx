"""Template helpers for resolving theme values."""

import re

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

# What css_color lets into a style attribute. A colour can be stored text a
# player typed, so anything that could carry a second declaration or load a
# URL is refused rather than passed through.
TOKEN = re.compile(r"[a-z][a-z0-9-]*")
LITERAL = re.compile(
    r"#[0-9a-fA-F]{3,8}"
    r"|(?:rgb|rgba|hsl|hsla|oklch|oklab|var)\([-\w\s.,%/]*\)"
)


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

    An unknown name yields a var() that resolves to nothing, which shows up as
    a transparent swatch rather than an exception — the right failure for a
    decorative mark. A value that is neither a plain name nor one of those
    literal forms is transparent too, and never reaches the page.
    """
    if not value:
        return "transparent"
    value = str(value).strip()
    if "#" in value or "(" in value:
        return value if LITERAL.fullmatch(value) else "transparent"
    if not TOKEN.fullmatch(value):
        return "transparent"
    if value in SINGULAR:
        return f"var(--color-{value})"
    return f"var(--color-{value}-{shade})"
