from django import template
from django.forms import widgets

register = template.Library()


@register.filter
def add_bootstrap_class(field):
    """Add Bootstrap classes to form field widgets."""
    widget = field.field.widget
    css_classes = widget.attrs.get("class", "")

    if isinstance(
        widget,
        (
            widgets.TextInput,
            widgets.EmailInput,
            widgets.PasswordInput,
            widgets.NumberInput,
            widgets.URLInput,
            widgets.DateInput,
            widgets.DateTimeInput,
            widgets.TimeInput,
            widgets.Textarea,
        ),
    ):
        css_classes = f"{css_classes} form-control".strip()
    elif isinstance(widget, widgets.Select):
        css_classes = f"{css_classes} form-select".strip()
    elif isinstance(widget, (widgets.CheckboxInput, widgets.RadioSelect)):
        css_classes = f"{css_classes} form-check-input".strip()

    widget.attrs["class"] = css_classes
    return field


@register.filter
def is_checkbox(field):
    """Check if field is a checkbox."""
    return isinstance(field.field.widget, widgets.CheckboxInput)


@register.filter
def add_label_class(field):
    """Add Bootstrap label classes based on widget type."""
    if isinstance(field.field.widget, widgets.CheckboxInput):
        return "form-check-label"
    return "form-label"
