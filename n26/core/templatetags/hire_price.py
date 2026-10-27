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


@register.simple_tag
def equip_purchase_props(row, price_cap="", repeat=False):
    """Purchase controls from the prepared listing, without querying content."""
    from n26.core.listing import pick_group_props

    return price_box_props(row.price_field, row.price, row.marked_name, price_cap) | {
        "choices": pick_group_props(row.choices),
        "purchase": {
            "name": row.marked_name,
            "repeat": bool(repeat),
            "tradePoints": row.trade_points,
            "exclusive": row.is_exclusive,
            "buy": {"label": row.buy.label, "target": row.buy.target},
        },
    }
