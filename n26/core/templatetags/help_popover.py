"""Plain-text explanations for the shared React help island."""

from django import template

register = template.Library()


@register.simple_tag
def help_popover_props(label, text):
    return {"label": label, "paragraphs": [text]}
