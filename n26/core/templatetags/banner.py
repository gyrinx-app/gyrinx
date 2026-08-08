"""The site banner, resolved into this edition's terms.

`Banner` is platform-owned and shown by every edition, so it stores neither a
drawing nor a colour but a pair of keys: an icon meaning ("news") and a
Bootstrap contextual colour. The first is edition-neutral by design and each
edition looks it up in its own set; the second is Bootstrap's vocabulary, which
n26 does not share, so it is mapped onto the announcement's five tones.

Doing both here rather than in the template keeps the mappings somewhere they
can be read and tested, and keeps the shell to one filter per attribute.

Both filters are total. Any value at all — including a key written before the
choices existed, or one retired from the table since — resolves to something
the components accept. That matters because <c-n26.icon> raises on a name it
does not have, which is right for a name a template author wrote and fatal for
one that arrived from a database column: it once took every page of the
edition down at once.
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
    """This edition's icon name for a banner's icon key.

    Empty when the key has no drawing here, which leaves
    <c-n26.site.announcement> to draw the icon its tone implies — a better
    answer than no icon at all, since the bar's colour and its icon are meant
    to say the same thing.
    """
    return banner_icons.n26_name(key or "")
