from django import template
from django.urls import reverse
from django.utils.html import format_html

from gyrinx.content.models import ContentPageRef

register = template.Library()


def is_active(context, name):
    return context["request"].get_full_path() == reverse(name)


@register.simple_tag(takes_context=True)
def active_view(context, name):
    return "active" if is_active(context, name) else ""


@register.simple_tag(takes_context=True)
def active_aria(context, name):
    return 'aria-current="page"' if is_active(context, name) else ""


@register.filter
def lookup(dictionary, key):
    return dictionary.get(key)


def identity(value):
    return value


@register.simple_tag
def ref(*args, category=None, value=None):
    search_value = " ".join(args)
    if not value:
        value = search_value

    kwargs = {}
    if category:
        kwargs["category"] = category
    refs = ContentPageRef.find_similar(search_value, **kwargs)
    if not refs:
        return value

    ref_str = ", ".join(ref.bookref() for ref in refs)

    return format_html(
        '<a data-bs-toggle="tooltip" data-bs-title="{}" href=\'{}\' class="link-secondary link-underline-opacity-25 link-underline-opacity-100-hover">{}</a>',
        ref_str,
        "#",
        value,
    )
