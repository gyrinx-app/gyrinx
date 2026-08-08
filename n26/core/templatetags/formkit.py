"""Filters that let a template dispatch a bound field onto the kit.

The authoring forms are spec-generated — nobody can hand-write a
``<c-ui.field>`` per field the way a fixed page does — so a dispatch
include renders each bound field through the right kit control. These
filters answer the three questions the template cannot: what kind of
control the widget wants, what a dash-keyed widget attribute holds, and
which choice values are selected.
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
    return "text"


@register.filter
def widget_attr(field, name):
    """A widget attribute by its real (often dash-keyed) name — the
    union markers live in ``data-union-*``, which dot lookup can't reach."""
    return field.field.widget.attrs.get(name, "")


@register.filter
def selected_values(field):
    """The bound value(s) as strings, so an option template can ask
    "am I selected?" the same way for single and multiple selects."""
    value = field.value()
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]
