"""JSON props for a price box that posts what the reader types."""

from django import template

from n26.core.views.equip import PRICE_CEILING

register = template.Library()


def _whole(value, fallback):
    try:
        return int(value)
    except TypeError, ValueError:
        return fallback


def price_box_props(field, quoted, label="", price_cap="", element_id=""):
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


register.simple_tag(price_box_props, name="hire_price_props")
register.simple_tag(price_box_props, name="equip_price_props")
