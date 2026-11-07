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
    r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})"
    r"|(?:rgb|rgba|hsl|hsla|oklch|oklab|var)\([-\w\s.,%/]*\)"
)


@register.filter
def css_color(value, shade="500"):
    """Resolve a literal CSS colour or theme token for a style attribute.

    Hex and functional values pass through only when LITERAL validates the full
    string. Valid names use CSS variables and an optional scale shade, preserving
    theme changes. Invalid values are transparent; unknown variable names remain
    unresolved rather than raising.
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
