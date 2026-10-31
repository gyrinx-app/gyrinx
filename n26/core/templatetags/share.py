"""JSON props for the share control React draws over the fallback link."""

from html import unescape

from django import template
from django.utils.safestring import SafeData

register = template.Library()

SIZES = ("xs", "sm", "md", "lg", "xl", "2xl")
VARIANTS = (
    "default",
    "primary",
    "success",
    "danger",
    "ghost",
    "subtle",
    "text",
    "text-danger",
)


def _text(value):
    """Plain text for the island.

    A Cotton string attribute arrives already escaped, and the island
    escapes again when it draws, so that is decoded here, once. A plain
    Python string, as a :prop passes it, is left alone: its entities are
    its text. A query string's & stays & in the props either way.
    """
    if value is None:
        return ""
    return unescape(str(value)) if isinstance(value, SafeData) else str(value)


@register.simple_tag
def share_props(
    url="",
    message="Link copied.",
    size="xs",
    variant="ghost",
    label="Share",
    compact=True,
):
    """The link React shares, and the button shape it draws."""
    return {
        "url": _text(url),
        "label": "Share" if label is None else _text(label),
        "compact": bool(compact),
        "message": "Link copied." if message is None else _text(message),
        "size": size if size in SIZES else "xs",
        "variant": variant if variant in VARIANTS else "ghost",
    }


@register.simple_tag
def share_host_class(css_class=""):
    """The row that holds the link and, after a copy, its status message."""
    extra = "" if css_class is None else str(css_class).strip()
    base = "inline-flex items-center gap-2"
    return f"{base} {extra}" if extra else base
