from django import template
from django.core.cache import cache
from django.utils.safestring import mark_safe

from gyrinx.content.svg import sanitize_house_icon_svg

register = template.Library()

# Prototype gate: house icons are only displayed to members of this group.
# The group is created by a core data migration. Remove the gate (and this
# constant's use) when the feature graduates to general availability.
HOUSE_ICONS_ALPHA_GROUP = "House Icons Alpha"


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


def _user_in_house_icons_alpha(request, user):
    """Memoised per-request check for House Icons Alpha membership.

    A gated page can call ``house_icon`` many times (once per list/fighter), so
    cache the group lookup on the request to avoid a query per call.
    """
    if not hasattr(request, "_house_icons_alpha_member"):
        request._house_icons_alpha_member = user.groups.filter(
            name=HOUSE_ICONS_ALPHA_GROUP
        ).exists()
    return request._house_icons_alpha_member


def _house_icon_svg(icon, extra_classes):
    """Read + sanitise a house icon's SVG, caching the result.

    Cached by the stored file name (which changes when a new icon is uploaded,
    so re-uploads bust the cache) and the requested extra classes. Failures are
    cached as empty strings to avoid re-reading broken files every request.
    """
    cache_key = f"house_icon_svg:{icon.name}:{extra_classes}"
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


@register.simple_tag(takes_context=True)
def house_icon(context, house, extra_classes=""):
    """Render a house's inline SVG icon, gated to the House Icons Alpha group.

    Renders nothing (no markup, no layout shift) for anonymous users, users
    outside the group, houses without an icon, or unreadable/invalid icons —
    so non-members see house names exactly as before.

    Usage:
        {{ list.content_house_name }}{% house_icon list.content_house_cached %}
    """
    if house is None:
        return ""

    # Check the icon field (already loaded on the house, no query) before the
    # group membership lookup, so houses without an icon — the common case
    # during the prototype — add zero queries to hot paths like the list view.
    icon = getattr(house, "icon", None)
    if not icon:
        return ""

    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return ""

    if not _user_in_house_icons_alpha(request, user):
        return ""

    svg = _house_icon_svg(icon, extra_classes)
    # nosec B703 B308 - svg is sanitised by sanitize_house_icon_svg (bleach
    # allowlist) before reaching here; raw upload content never marked safe.
    return mark_safe(svg) if svg else ""  # nosec B703 B308
