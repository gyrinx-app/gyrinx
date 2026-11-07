"""Adapt bound fields for generated authoring forms and design-system controls.

Expose widget kind, dash-keyed attributes and selected values to the dispatch
include so generated fields use the appropriate control.
"""

from django import template
from django.forms import widgets

register = template.Library()


@register.filter
def widget_kind(field):
    """One word naming the kit control this bound field wants."""
    widget = field.field.widget
    if isinstance(widget, widgets.SelectMultiple):
        return "selectmultiple"
    if isinstance(widget, widgets.Select):
        return "select"
    if isinstance(widget, widgets.CheckboxInput):
        return "checkbox"
    if isinstance(widget, widgets.Textarea):
        return "textarea"
    if isinstance(widget, widgets.NumberInput):
        return "number"
    if isinstance(widget, widgets.FileInput):
        return "file"
    return "text"


@register.filter
def widget_attr(field, name):
    """Read widget attributes whose dash-keyed names cannot use template dot lookup."""
    return field.field.widget.attrs.get(name, "")


@register.simple_tag
def file_input_props(field):
    """JSON-safe display data for the React-owned authoring file control."""
    return {
        "htmlName": field.html_name,
        "id": field.auto_id,
        "accept": str(field.field.widget.attrs.get("accept", "")),
    }


@register.filter
def selected_values(field):
    """Normalise single or multiple selected values to strings for option comparison."""
    value = field.value()
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]
