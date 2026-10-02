"""JSON props for the form switch React draws in place of the Alpine track."""

from django import template

register = template.Library()

SIZES = ("xs", "sm", "md", "lg", "xl", "2xl")


def _flag(value, default):
    """A cotton boolean, or the string a template printed for one."""
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"true", "1", "on", "yes"}


@register.simple_tag
def form_switch_props(
    name="",
    value="on",
    checked=False,
    disabled=False,
    accent=True,
    size="md",
    css_class="",
    input_id="",
):
    """The opening state of one switch. None and the string false are off."""
    chosen = size if size in SIZES else "md"
    return {
        "name": "" if name is None else str(name),
        "value": "on" if value in (None, "") else str(value),
        "checked": _flag(checked, False),
        "disabled": _flag(disabled, False),
        "accent": _flag(accent, True),
        "size": chosen,
        "className": "" if css_class is None else str(css_class),
        "id": "" if input_id is None else str(input_id),
    }
