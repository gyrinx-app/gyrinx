"""Sanitise stored SVG artwork before rendering it inline.

Uploaded artwork remains untrusted even when submitted by staff. Apply
the shared gyrinx.svg allowlist on cache misses, then cache the cleaned
markup by its raw SVG hash. Cache hits reuse that markup; allowlist changes
require expiry or invalidation of existing entries.
"""

from hashlib import sha256

from django import template
from django.core.cache import cache
from django.utils.safestring import mark_safe

from gyrinx.svg import sanitize_inline_svg

register = template.Library()

# Cleaning is not cheap and a page draws one badge per row, so the result is
# kept against a hash of the markup itself: two gangs of the same type share
# the entry, and editing the artwork lands on a different key rather than
# needing anything invalidated.
_CACHE_PREFIX = "n26-artwork:"


@register.filter
def safe_artwork(value):
    """Sanitise SVG markup and return a safe string, or empty for unusable input.

    Usage::

        {{ gang_type.artwork|safe_artwork }}

    Do not append safe to raw artwork; this filter performs the required sanitisation.
    """
    if not value:
        return ""

    raw = str(value)
    key = _CACHE_PREFIX + sha256(raw.encode()).hexdigest()
    cleaned = cache.get(key)
    if cleaned is None:
        cleaned = sanitize_inline_svg(raw)
        cache.set(key, cleaned)

    # nosec B703 B308 - sanitize_inline_svg is the bleach allowlist; the stored
    # value never reaches a template without going through it.
    return mark_safe(cleaned)  # nosec B703 B308
