from django import template
from django.urls import reverse

register = template.Library()


def is_active(context, name):
    return context["request"].get_full_path() == reverse(name)


@register.simple_tag(takes_context=True)
def active_view(context, name):
    return "active" if is_active(context, name) else ""


@register.simple_tag(takes_context=True)
def active_aria(context, name):
    return 'aria-current="page"' if is_active(context, name) else ""
