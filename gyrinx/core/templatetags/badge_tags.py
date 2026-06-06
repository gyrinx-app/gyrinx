"""Template tags for rendering supporter badges inline."""

from hashlib import sha256

from django import template
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from gyrinx.core.badges import BadgeDef, badge_by_slug

register = template.Library()


def _badge_svg(badge: BadgeDef) -> str:
    """Read a badge's static SVG, cached by slug.

    The committed SVGs are already inline-ready (``currentColor`` outlines,
    ``viewBox``, ``aria-hidden``), so there's nothing to sanitise — they're
    trusted repo assets, not user uploads. Failures cache as an empty string so a
    missing/broken file doesn't re-hit the filesystem every render.
    """
    cache_key = f"badge_svg:{sha256(badge.slug.encode('utf-8')).hexdigest()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    svg = ""
    path = finders.find(badge.svg)
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                svg = fh.read()
        except OSError:
            svg = ""

    cache.set(cache_key, svg)
    return svg


@register.simple_tag
def badge_icon(badge, extra_classes=""):
    """Render a badge's inline SVG icon (no eligibility check).

    Accepts a ``BadgeDef`` or a slug string. Used by the badge picker; for
    rendering a user's chosen badge next to their name use ``user_badge``.
    """
    if isinstance(badge, str):
        badge = badge_by_slug(badge)
    if badge is None:
        return ""

    svg = _badge_svg(badge)
    if not svg:
        return ""

    classes = f"badge-icon {extra_classes}".strip()
    # svg is a trusted static repo asset (no user input), pre-sanitised at commit
    # time — safe to mark_safe.
    return format_html(
        '<span class="{}" role="img" aria-label="{}">{}</span>',
        classes,
        badge.title,
        mark_safe(svg),  # nosec B308 B703
    )


@register.simple_tag
def user_badge(profile_user, extra_classes=""):
    """Render the supporter badge a user has chosen, if any.

    Renders nothing (no markup) when the user has no profile, hasn't selected a
    badge, or is no longer eligible for their selection. Visible to all viewers —
    badge visibility is a property of the profile owner, not the viewer.

    Call sites that render this over a queryset of users MUST
    ``select_related("…__profile")`` to avoid a query per row.
    """
    if profile_user is None:
        return ""

    # A missing reverse one-to-one raises rather than returning None, and an
    # anonymous user has no ``profile`` attribute at all.
    try:
        profile = profile_user.profile
    except (AttributeError, ObjectDoesNotExist):
        return ""
    if profile is None:
        return ""

    badge = profile.display_badge
    if badge is None:
        return ""

    svg = _badge_svg(badge)
    if not svg:
        return ""

    classes = f"user-badge {extra_classes}".strip()
    # Bootstrap tooltip (initialised globally in index.js) shows the short,
    # user-facing description on hover. No underline — the badge is an icon-only
    # span, so we deliberately avoid the `.tooltipped` link styling.
    # svg is a trusted static repo asset (no user input) — safe to mark_safe.
    return format_html(
        '<span class="{}" data-bs-toggle="tooltip" data-bs-title="{}" '
        'role="img" aria-label="{}">{}</span>',
        classes,
        badge.description,
        badge.description,
        mark_safe(svg),  # nosec B308 B703
    )
