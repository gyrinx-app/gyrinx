"""JSON props for the colour-scheme choice React draws in the account menu."""

from django import template

register = template.Library()

# Each scheme with its words and drawing, in the order the control shows them.
CHOICES = (
    ("light", "Light", "sun"),
    ("dark", "Dark", "moon"),
    ("system", "System", "monitor"),
)


@register.simple_tag
def theme_choice_props(storage_key="theme", css=""):
    """Where the choice is kept, which the page's head script must share,
    the schemes offered, and a caller's classes for the group."""
    return {
        "storageKey": str(storage_key or "theme"),
        "defaultMode": "system",
        "choices": [list(choice) for choice in CHOICES],
        "className": str(css or ""),
    }
