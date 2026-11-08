"""JSON props for the checkbox card React draws over the server markup."""

from html import unescape

from django import template
from django.utils.safestring import SafeData

from n26.core.checkbox_card import CheckboxCardItem

register = template.Library()


def _flag(value):
    """Parse a Cotton boolean or its rendered string value."""
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return False
    return str(value).strip().lower() in {"true", "1", "on", "yes"}


@register.filter
def checkbox_card_flag(value):
    """Return the same checked boolean for server markup and React props."""
    return _flag(value)


def _filled(value):
    """Check rendered content because Cotton attrs objects are truthy even when empty."""
    return bool(str(value or "").strip())


def _text(value):
    """Return plain text for React, decoding escaped SafeData once.

    Preserve entities in ordinary Python strings because they are literal text.
    """
    if value is None:
        return ""
    return unescape(str(value)) if isinstance(value, SafeData) else str(value)


def _item(item):
    if not isinstance(item, CheckboxCardItem):
        raise TypeError(
            f"A checkbox card's items are CheckboxCardItem, not {type(item).__name__}"
        )
    return {
        "name": item.name,
        "value": item.value,
        "label": item.label,
        "checked": item.checked,
        "meta": item.meta,
    }


@register.simple_tag
def checkbox_card_props(
    name="",
    value="",
    checked=False,
    label="",
    description="",
    css_class="",
    meta="",
    items=None,
    body="",
    attrs="",
):
    """Build checkbox-card props from text and typed nested items.

    Preserve an empty checkbox value so submission does not use the browser
    default of on. None and the string false disable the checked flag.

    React uses these props without retaining server markup as children. Reject
    body content, HTML in meta and extra root attributes; use static rendering
    when those are required.
    """
    if _filled(body):
        raise ValueError(
            "<c-n26.checkbox-card> draws its nested ticks from :items, not from "
            'markup in its body. Pass CheckboxCardItem rows, or :static="True".'
        )
    if "<" in str(meta or ""):
        raise ValueError(
            '<c-n26.checkbox-card> takes meta as text, such as meta="85¢". '
            'Markup in meta needs :static="True".'
        )
    if _filled(attrs):
        raise ValueError(
            "<c-n26.checkbox-card> as a React island draws no extra root "
            f'attributes ({str(attrs).strip()}). Pass :static="True" to keep them.'
        )
    return {
        "name": _text(name),
        "value": _text(value),
        "checked": _flag(checked),
        "label": _text(label),
        "description": _text(description),
        "className": _text(css_class),
        "meta": _text(meta),
        "items": [_item(item) for item in items or ()],
    }
