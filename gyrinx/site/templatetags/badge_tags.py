"""Shared badge selection and SVG template tags.

user_badge supplies platform markup. Editions can use badge_for and
badge_svg with their own components while retaining shared eligibility.
"""

from django import template
from django.core.exceptions import ObjectDoesNotExist
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from gyrinx.badges import badge_by_slug

register = template.Library()


def _badge_svg(badge) -> str:
    """Return a badge's inline artwork, or an empty string when unavailable."""
    return badge.inline_svg()


@register.simple_tag
def badge_for(profile_user):
    """Return the user's resolved display badge, or None without a profile or eligible selection.

    UserProfile.display_badge applies explicit choices, opt-out and eligible
    defaults. Preload profile and badge_grants when rendering many users
    to avoid per-user queries.
    """
    if profile_user is None:
        return None

    # Missing profiles raise ObjectDoesNotExist; anonymous users have no profile attribute.
    try:
        profile = profile_user.profile
    except AttributeError, ObjectDoesNotExist:
        return None
    if profile is None:
        return None

    return profile.display_badge


@register.simple_tag
def badge_image_url(badge):
    """Use the badge picker's image representation without inheriting icon CSS."""
    if badge is None:
        return ""
    return badge.image_url()


@register.simple_tag
def badge_svg(badge):
    """Return unwrapped artwork for a BadgeDef or slug, or an empty string if unknown.

    The caller supplies sizing, tooltip and accessible name.
    """
    if isinstance(badge, str):
        badge = badge_by_slug(badge)
    if badge is None:
        return ""

    # Trust committed SVG; uploaded artwork is sanitised before marking it safe.
    return mark_safe(_badge_svg(badge))  # nosec B308 B703


@register.simple_tag
def badge_icon(badge, extra_classes=""):
    """Render supplied badge artwork without checking user eligibility.

    Accept a BadgeDef or slug; use user_badge for a person's resolved selection.
    """
    if isinstance(badge, str):
        badge = badge_by_slug(badge)
    if badge is None:
        return ""

    svg = _badge_svg(badge)
    if not svg:
        return ""

    classes = f"badge-icon {extra_classes}".strip()
    # Trust committed SVG; uploaded artwork is already sanitised.
    return format_html(
        '<span class="{}" role="img" aria-label="{}">{}</span>',
        classes,
        badge.title,
        mark_safe(svg),  # nosec B308 B703
    )


@register.simple_tag
def user_badge(profile_user, extra_classes=""):
    """Render a user's resolved display badge for all viewers.

    Selection includes eligible defaults and fallback from a lapsed choice.
    Return no markup without a display badge or artwork. Preload profile and
    badge_grants when rendering a queryset of users.
    """
    badge = badge_for(profile_user)
    if badge is None:
        return ""

    svg = _badge_svg(badge)
    if not svg:
        return ""

    classes = f"user-badge {extra_classes}".strip()
    # Use the global Bootstrap tooltip without the link-specific .tooltipped styling.
    # Trust committed SVG; uploaded artwork is already sanitised.
    return format_html(
        '<span class="{}" data-bs-toggle="tooltip" data-bs-title="{}" '
        'role="img" aria-label="{}">{}</span>',
        classes,
        badge.description,
        badge.description,
        mark_safe(svg),  # nosec B308 B703
    )
