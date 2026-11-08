"""JSON props for the colour-scheme choice React draws in the account menu."""

from django import template

register = template.Library()

CHOICES = (
    ("light", "Light", "sun"),
    ("dark", "Dark", "moon"),
    ("system", "System", "monitor"),
)


@register.simple_tag
def theme_choice_props(storage_key="theme", css=""):
    """Build theme choices and group classes using the same storage key as the page's head script."""
    return {
        "storageKey": str(storage_key or "theme"),
        "defaultMode": "system",
        "choices": [list(choice) for choice in CHOICES],
        "className": str(css or ""),
    }
