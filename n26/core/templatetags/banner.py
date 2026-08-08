"""The site banner, translated from the platform's vocabulary into ours.

`Banner` is platform-owned and older than this edition: it stores its icon as
a Bootstrap Icons class and its colour as a Bootstrap contextual colour, both
of which the n23 templates hand straight to Bootstrap. n26 has neither — its
icons are the hand-kept set in core/icons.py and its announcement takes one of
five tones — so the two attributes have to be translated on the way in.

Doing it here rather than in the template keeps the mapping somewhere it can be
read and tested, and keeps the shell to one filter per attribute.

Both filters are total: any value at all, including the ones nobody has typed
yet, resolves to something the components accept. That is the point of them. A
live banner set to an icon this edition does not have took every n26 page down
with a KeyError, because the icon component raises on an unknown name — which
is right for a name a template author wrote, and wrong for one an admin typed.
"""

from django import template

from n26.core import icons

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
def banner_icon(name):
    """The icon name for a banner's Bootstrap icon class.

    Empty when there is no equivalent, which leaves <c-n26.site.announcement>
    to draw the icon its tone implies — a better answer than no icon at all,
    since the bar's colour and its icon are meant to say the same thing.
    """
    return icons.from_bootstrap(name or "")
