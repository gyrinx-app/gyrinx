"""JSON props for the filter menu React draws in place of the Alpine dropdown."""

from html import unescape

from django import template
from django.utils.safestring import SafeData

register = template.Library()

SIZES = ("xs", "sm")
ALIGNS = ("start", "end")


def _text(value):
    """Plain text for React.

    A Cotton string attribute arrives already escaped, and React escapes again
    when it draws, so that is decoded here, once.
    """
    if value is None:
        return ""
    return unescape(str(value)) if isinstance(value, SafeData) else str(value)


def _flag(value, default):
    """A cotton boolean, or the string a template printed for one."""
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"true", "1", "on", "yes"}


def _width(value):
    """min_width as pixels. 20rem is the menu's own default, which is 320."""
    text = _text(value) or "20rem"
    if text.endswith("rem"):
        number = text[: -len("rem")]
    elif text.endswith("px"):
        number = text[: -len("px")]
    else:
        return 320
    try:
        width = float(number)
    except ValueError:
        return 320
    if text.endswith("rem"):
        width *= 16
    return int(width) if width > 0 else 320


def _options(options):
    rows = []
    for option in options or []:
        if isinstance(option, dict):
            value = option.get("value", "")
            label = option.get("label", value)
        else:
            value = getattr(option, "value", "")
            label = getattr(option, "label", value)
        rows.append({"value": _text(value), "label": _text(label)})
    return rows


@register.simple_tag
def filter_menu_props(
    label="Filter",
    name="",
    options=None,
    selected=None,
    select_all=True,
    apply_label="OK",
    cancel_label="Cancel",
    size="sm",
    align="start",
    min_width="20rem",
):
    """The menu's ticks and the words on its buttons.

    An empty selected list with select_all on becomes every option once the
    island mounts. None and the string false leave select_all off.
    """
    chosen_size = size if size in SIZES else "sm"
    chosen_align = align if align in ALIGNS else "start"
    return {
        "label": _text(label) or "Filter",
        "name": _text(name),
        "options": _options(options),
        "selected": [_text(item) for item in selected or []],
        "selectAll": _flag(select_all, True),
        "applyLabel": _text(apply_label) or "OK",
        "cancelLabel": _text(cancel_label) or "Cancel",
        "size": chosen_size,
        "align": chosen_align,
        "width": _width(min_width),
    }
