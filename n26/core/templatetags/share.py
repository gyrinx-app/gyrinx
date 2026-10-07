"""JSON props for the share control React draws over the fallback link."""

from django import template

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
        "url": "" if url is None else str(url),
        "message": "Link copied." if message is None else str(message),
        "size": size if size in SIZES else "xs",
        "variant": variant if variant in VARIANTS else "ghost",
        "label": ("" if label is None else str(label).strip()) or "Share",
        "compact": bool(compact),
    }


@register.simple_tag
def share_host_class(css_class=""):
    """The row that holds the link and, after a copy, its status message."""
    extra = "" if css_class is None else str(css_class).strip()
    base = "inline-flex items-center gap-2"
    return f"{base} {extra}" if extra else base
