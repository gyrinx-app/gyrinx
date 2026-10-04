"""Allauth adapters using the rendered N26 controls as presentation recipes."""

from copy import deepcopy
from functools import lru_cache
from html.parser import HTMLParser

from django import template
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

register = template.Library()


@register.simple_tag
def allauth_button_attrs(attrs):
    result = {
        key: attrs[key] for key in ("form", "id", "name", "value") if attrs.get(key)
    }
    # Allauth buttons without a type rely on the native submit default.
    if not attrs.get("href"):
        result["type"] = attrs.get("type") or "submit"
    return result


@lru_cache
def _input_class():
    class InputParser(HTMLParser):
        classes = ""

        def handle_starttag(self, tag, attrs):
            if tag == "input":
                self.classes = dict(attrs).get("class", "")

    source = CottonCompiler().process('<c-ui.input name="recipe" />')
    parser = InputParser()
    parser.feed(Template(source).render(Context()))
    return parser.classes


@register.filter
def n26_widget(field):
    widget = deepcopy(field.field.widget)
    widget.attrs.pop("class", None)
    if getattr(widget, "input_type", "") == "checkbox":
        widget.attrs["class"] = (
            "size-4 rounded border-box-border accent-accent focus-ring"
        )
    else:
        widget.attrs["class"] = _input_class()
    if field.errors:
        widget.attrs["aria-invalid"] = "true"
    return field.as_widget(widget=widget)


@register.simple_tag
def login_name_props(field):
    return {
        "id": field.id_for_label,
        "name": field.html_name,
        "label": field.label,
        "value": str(field.value() or ""),
        "errors": list(field.errors),
        "required": field.field.required,
        "autocomplete": field.field.widget.attrs.get("autocomplete", "username"),
    }
