"""JSON props for the checkbox card React draws over the server markup."""

from html import unescape

from django import template
from django.utils.safestring import SafeData

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


@register.filter
def checkbox_card_filled(value):
    """Whether a slot, meta or attrs renders to anything.

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


@register.simple_tag
def checkbox_card_props(
    name="",
    value="",
    checked=False,
    label="",
    description="",
    css_class="",
):
    """The checkbox the card posts, and the words drawn in its header.

    None and the string false are off. An empty value stays empty: a missing
    value attribute would post the browser's default of on.

    Only a card with no body, meta or extra root attributes is an island, so
    these are all it draws.
    """
    return {
        "name": _text(name),
        "value": _text(value),
        "checked": _flag(checked),
        "label": _text(label),
        "description": _text(description),
        "className": _text(css_class),
    }
