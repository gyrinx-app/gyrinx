"""JSON props for the checkbox card React draws over the server markup."""

from html import unescape

from django import template
from django.utils.safestring import SafeData

from n26.core.checkbox_card import CheckboxCardItem

register = template.Library()


def _flag(value):
    """A cotton boolean, or the string a template printed for one."""
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return False
    return str(value).strip().lower() in {"true", "1", "on", "yes"}


@register.filter
def checkbox_card_flag(value):
    """checked as a boolean, for the server-drawn face and the props alike."""
    return _flag(value)


def _filled(value):
    """Whether a slot or attrs renders to anything.

    Cotton's attrs is an object, truthy even when it holds no attribute, so
    it is judged by what it prints.
    """
    return bool(str(value or "").strip())


def _text(value):
    """Plain text for React.

    A Cotton string attribute arrives already escaped, and React escapes again
    when it draws, so that is decoded here, once. A plain Python string, as a
    :prop passes it, is left alone: its entities are its text.
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
    """The card's checkbox, its header words, and the nested ticks it holds.

    None and the string false are off. An empty value stays empty: a missing
    value attribute would post the browser's default of on.

    React draws the card from these props alone. It does not take
    server-drawn markup as children, so a body slot, markup in meta, or extra
    root attributes are refused: pass the nested ticks as items and meta as
    text, or draw the card static.
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
