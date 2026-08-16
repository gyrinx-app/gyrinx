"""Template tags for rendering supporter badges inline.

``user_badge`` renders the whole mark in the platform's own markup. Editions
whose component set draws it differently take the two halves instead —
``badge_for`` for which badge, ``badge_svg`` for the artwork — and wrap them
themselves. This library is the only seam an edition needs for badges: the
registry and the eligibility rules stay platform-owned, so a new tier reaches
every edition without either of them changing.
"""

from django import template
from django.core.exceptions import ObjectDoesNotExist
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from gyrinx.badges import badge_by_slug

register = template.Library()


def _badge_svg(badge) -> str:
    """The artwork for a badge, ready to inline, or ``""``.

    Which of the two kinds of badge this is — one that ships with the app or
    one somebody uploaded — is the badge's own business; both answer this.
    """
    return badge.inline_svg()


@register.simple_tag
def badge_for(profile_user):
    """The badge a user displays, as a ``BadgeDef``, or ``None``.

    The registry's answer to "which badge", with no markup attached, so an
    edition that draws the mark in its own components asks the same question the
    platform does instead of re-deriving eligibility from ``is_staff``::

        {% badge_for gang.owner as badge %}

    ``None`` for an anonymous viewer, a user with no profile, and anyone whose
    selection has lapsed. Reads the profile and the user's badge grants, so call
    sites rendering this over a queryset of users MUST
    ``select_related("…__profile").prefetch_related("…__badge_grants")`` —
    without the prefetch this is a query per row.
    """
    if profile_user is None:
        return None

    # A missing reverse one-to-one raises rather than returning None, and an
    # anonymous user has no ``profile`` attribute at all.
    try:
        profile = profile_user.profile
    except AttributeError, ObjectDoesNotExist:
        return None
    if profile is None:
        return None

    return profile.display_badge


@register.simple_tag
def badge_svg(badge):
    """A badge's artwork, inline and unwrapped.

    Accepts a ``BadgeDef`` or a slug string; empty for anything unknown. The
    wrapper — sizing, accessible name, tooltip — belongs to whoever is drawing
    it, which differs between the two editions' component sets.
    """
    if isinstance(badge, str):
        badge = badge_by_slug(badge)
    if badge is None:
        return ""

    # Committed artwork is a trusted repo asset; uploaded artwork has been
    # through the platform's SVG allowlist on the way out of storage.
    return mark_safe(_badge_svg(badge))  # nosec B308 B703


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
    # Either committed and trusted, or uploaded and already sanitised.
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
    ``select_related("…__profile").prefetch_related("…__badge_grants")`` to
    avoid a query per row.
    """
    badge = badge_for(profile_user)
    if badge is None:
        return ""

    svg = _badge_svg(badge)
    if not svg:
        return ""

    classes = f"user-badge {extra_classes}".strip()
    # Bootstrap tooltip (initialised globally in index.js) shows the short,
    # user-facing description on hover. No underline — the badge is an icon-only
    # span, so we deliberately avoid the `.tooltipped` link styling.
    # Either committed and trusted, or uploaded and already sanitised.
    return format_html(
        '<span class="{}" data-bs-toggle="tooltip" data-bs-title="{}" '
        'role="img" aria-label="{}">{}</span>',
        classes,
        badge.description,
        badge.description,
        mark_safe(svg),  # nosec B308 B703
    )
