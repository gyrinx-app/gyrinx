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
    query_keys=None,
):
    """Build the shared URL and button props."""
    props = {
        "url": "" if url is None else str(url),
        "label": "Share" if label is None else str(label),
        "compact": bool(compact),
        "message": "Link copied." if message is None else str(message),
        "size": size if size in SIZES else "xs",
        "variant": variant if variant in VARIANTS else "ghost",
    }
    if query_keys:
        props["queryKeys"] = list(query_keys)
    return props


@register.simple_tag
def share_host_class(css_class=""):
    """Return classes for the row containing the share link and copy status."""
    extra = "" if css_class is None else str(css_class).strip()
    base = "inline-flex items-center gap-2"
    return f"{base} {extra}" if extra else base
