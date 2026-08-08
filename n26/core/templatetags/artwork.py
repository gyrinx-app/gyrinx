"""Drawing stored artwork without trusting it.

A gang type's badge is a block of SVG that somebody uploaded and storage handed
back, so it is user input however staff-only the surface was. Drawn inline —
which is what lets it take the colour of the text it sits in — the browser will
run whatever is in it, so it goes through the platform's allowlist on the way
out. Cleaning at render rather than at save means the stored file stays
faithful to what the author made, and a tighter allowlist takes effect on
artwork that is already there.

The sanitiser is ``gyrinx.svg`` rather than a copy here. What is safe to put in
a page is a property of SVG and of the browser, not of either edition's content
model, and a security boundary is the last thing that should exist twice and
drift.
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
    """Sanitise stored SVG markup and mark the result safe.

    Usage::

        {{ gang_type.artwork|safe_artwork }}

    Returns an empty string for anything blank or unusable, so a gang type with
    no artwork draws nothing at all rather than an empty box. No trailing
    ``|safe`` — the return is already marked, and adding one to the *raw* value
    by mistake is exactly what this exists to prevent.
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
