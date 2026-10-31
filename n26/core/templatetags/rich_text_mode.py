"""Props for the Edit and Preview switch beside a rich text field."""

from django import template

from n26.core.templatetags.richtext import safe_rich_text

register = template.Library()


@register.simple_tag
def rich_text_mode_props(initial=""):
    """The sanitised starting HTML, used only when the textarea is absent.

    Preview of a live editor reads that editor. This string is the fallback
    for a switch rendered without one, and it has already been through
    safe_rich_text.
    """
    return {"initial": str(safe_rich_text(initial) or "")}
