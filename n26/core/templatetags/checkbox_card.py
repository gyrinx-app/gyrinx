"""JSON props for the checkbox card React draws over the server markup."""

from html import unescape

from django import template

register = template.Library()


def _flag(value):
    """A cotton boolean, or the string a template printed for one."""
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return False
    return str(value).strip().lower() in {"true", "1", "on", "yes"}


def _text(value):
    """Plain text for React. Cotton attribute values arrive already escaped."""
    return "" if value is None else unescape(str(value))


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
    """
    return {
        "name": _text(name),
        "value": _text(value),
        "checked": _flag(checked),
        "label": _text(label),
        "description": _text(description),
        "className": _text(css_class),
    }
