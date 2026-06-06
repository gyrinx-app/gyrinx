from hashlib import sha256

from django import template
from django.core.cache import cache
from django.utils.safestring import mark_safe

from gyrinx.content.svg import sanitize_house_icon_svg

register = template.Library()


@register.simple_tag
def theme_square(list_obj, size="0.8em", extra_classes=""):
    """
    Generate a small color square for a list's theme color.
    Shows just the color indicator without the list name.
    """
    if not list_obj:
        return ""

    theme_color = getattr(list_obj, "theme_color", None)

    if theme_color:
        return mark_safe(
            f'<span class="d-inline-block rounded {extra_classes}" '
            f'style="width: {size}; height: {size}; '
            f"background-color: {theme_color}; "
            f'border: 1px solid rgba(0,0,0,0.15);"></span>'
        )
    else:
        return ""


@register.simple_tag
def list_with_theme(list_obj, extra_classes="", square_size="0.8em"):
    """
    Display a list name with its theme color square.
    """
    if not list_obj:
        return ""

    name = getattr(list_obj, "name", str(list_obj))
    theme_color = getattr(list_obj, "theme_color", None)

    if theme_color:
        square = theme_square(list_obj, extra_classes="me-1", size=square_size)
        return mark_safe(f'<span class="{extra_classes}">{square}{name}</span>')
    else:
        return mark_safe(f'<span class="{extra_classes}">{name}</span>')


def _house_icon_svg(icon, extra_classes):
    """Read + sanitise a house icon's SVG, caching the result.

    Cached by the stored file name (which changes when a new icon is uploaded,
    so re-uploads bust the cache) and the requested extra classes. Failures are
    cached as empty strings to avoid re-reading broken files every request.
    """
    # Hash the variable key material (file name + classes) so the cache key is
    # safe for all backends (memcached rejects spaces/control chars and caps
    # length), matching the hashing approach used by the `ref` tag.
    digest = sha256(f"{icon.name}|{extra_classes}".encode("utf-8")).hexdigest()
    cache_key = f"house_icon_svg:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        with icon.open("rb") as fh:
            raw = fh.read().decode("utf-8")
        svg = sanitize_house_icon_svg(raw, extra_classes=extra_classes)
    except (OSError, ValueError, UnicodeDecodeError):
        svg = ""

    cache.set(cache_key, svg)
    return svg


@register.simple_tag
def house_icon(house, extra_classes=""):
    """Render a house's inline SVG icon.

    Renders nothing (no markup, no layout shift) for houses without an icon or
    unreadable/invalid icons, so those houses show their name exactly as before.

    Usage:
        {{ list.content_house_name }}{% house_icon list.content_house_cached %}
    """
    if house is None:
        return ""

    # The icon field is already loaded on the house (no query), so houses
    # without an icon add zero queries to hot paths like the list view.
    icon = getattr(house, "icon", None)
    if not icon:
        return ""

    svg = _house_icon_svg(icon, extra_classes)
    # nosec B703 B308 - svg is sanitised by sanitize_house_icon_svg (bleach
    # allowlist) before reaching here; raw upload content never marked safe.
    return mark_safe(svg) if svg else ""  # nosec B703 B308
