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
    body="",
    meta="",
    attrs="",
):
    """The checkbox the card posts, and the words drawn in its header.

    None and the string false are off. An empty value stays empty: a missing
    value attribute would post the browser's default of on.

    The island draws a header-only card. React does not take server-drawn
    markup as children, so a body or meta is refused: draw that card static,
    or compose CheckboxCard inside the island that owns the form. Extra root
    attributes are refused too, since React would not draw them.
    """
    if str(body or "").strip() or str(meta or "").strip():
        raise ValueError(
            "<c-n26.checkbox-card> draws only a header as a React island. "
            'For nested controls or meta, pass :static="True", or compose '
            "CheckboxCard inside the island that owns the form."
        )
    if str(attrs or "").strip():
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
    }
