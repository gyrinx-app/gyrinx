"""JSON props for the hire dialog's price box."""

from django import template

from n26.core.views.equip import PRICE_CEILING

register = template.Library()


def _whole(value, fallback):
    try:
        return int(value)
    except TypeError, ValueError:
        return fallback


@register.simple_tag
def hire_price_props(field, quoted, label="", price_cap="", element_id=""):
    """The quote the box starts at, and the bounds the server will accept."""
    amount = _whole(quoted, 0)
    cap = _whole(price_cap, PRICE_CEILING)
    return {
        "field": "" if field is None else str(field),
        "quoted": amount,
        "label": "" if label is None else str(label),
        "min": min(0, amount),
        "max": cap,
        "id": "" if element_id is None else str(element_id),
    }
