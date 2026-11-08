"""Build JSON props for the React form switch."""

from django import template

register = template.Library()

SIZES = ("xs", "sm", "md", "lg", "xl", "2xl")


def _flag(value, default):
    """Parse a Cotton boolean or its rendered string value, using the supplied default for None or empty input."""
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
    """Build the switch's initial state, using each flag's default for None or empty input."""
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
