"""Map platform banner icon and colour keys to N26 presentation values.

Resolve edition-neutral icon meanings through the platform registry and map
Bootstrap contexts to announcement tones. Both filters accept unknown stored
values and return valid component inputs rather than raising during page rendering.
"""

from django import template

from gyrinx.site import icons as banner_icons

register = template.Library()

#: Bootstrap's contextual colours against the announcement's five tones.
#:
#: The four that carry the same meaning in both map across; the rest are
#: degrees of "no particular meaning" and become the tone that says so.
#: primary is the exception — it is Bootstrap's "this is the important one"
#: rather than a sentiment, and a site banner using it wants the informational
#: blue, which is what info already is.
TONES: dict[str, str] = {
    "primary": "info",
    "secondary": "neutral",
    "success": "success",
    "danger": "danger",
    "warning": "warning",
    "info": "info",
    "light": "neutral",
    "dark": "neutral",
}


@register.filter
def banner_tone(colour):
    """The announcement tone for a banner's Bootstrap colour."""
    return TONES.get(colour or "", "info")


@register.filter
def banner_icon(key):
    """Return the N26 icon for a platform banner key, or empty for tone-based fallback."""
    return banner_icons.n26_name(key or "")
