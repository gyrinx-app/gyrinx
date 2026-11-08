"""Map catalogue action tones to design-system button variants.

The primary purchase action uses success because it submits the form.
Other actions navigate to confirmation through menus without button colour.
"""

from django import template
from django.utils.text import slugify

from n26.core.listing import DANGER, PRIMARY, SECONDARY

register = template.Library()


@register.filter
def row_dom_id(key):
    """Build the shared DOM ID for a catalogue entry and its partial replacement.

    Slugify content keys so colons and dots need no CSS selector escaping.
    """
    return f"n26-row-{slugify(key)}"


TONE_VARIANTS = {
    PRIMARY: "success",
    DANGER: "danger",
    SECONDARY: "default",
}


@register.filter
def tone_variant(tone):
    """Map an action tone to its button variant, using a plain fallback for unknown tones."""
    return TONE_VARIANTS.get(tone, "default")
