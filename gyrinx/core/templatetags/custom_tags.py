from django import template
from django.conf import settings
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
    if isinstance(dictionary, list):
        # TODO: This assumes the list is a namedtuple with a 'grouper' attribute. This is a bit of a hack.
        item = next((item for item in dictionary if item.grouper == key), None)
        return item.list if item else None
    return dictionary.get(key)


@register.simple_tag
def qt(request, **kwargs):
    updated = request.GET.copy()
    for k, v in kwargs.items():
        if v is not None:
            updated[k] = v
        else:
            updated.pop(k, 0)  # Remove or return 0 - aka, delete safely this key

    return updated.urlencode()


@register.simple_tag
def qt_nth(request, **kwargs):
    nth = kwargs.pop("nth")
    updated = request.GET.copy()
    for k, v in kwargs.items():
        current = updated.getlist(k)
        if nth < len(current):
            current[nth] = v
        else:
            current.append(v)
        updated.setlist(k, current)

    return updated.urlencode()


@register.simple_tag
def qt_rm_nth(request, **kwargs):
    nth = kwargs.pop("nth")
    updated = request.GET.copy()
    for k, v in kwargs.items():
        if str(v) != "1":
            continue
        current = updated.getlist(k)
        if nth < len(current):
            current.pop(nth)
            updated.setlist(k, current)

    return updated.urlencode()


@register.simple_tag
def qt_append(request, **kwargs):
    updated = request.GET.copy()
    for k, v in kwargs.items():
        current = updated.getlist(k)
        current.append(v)
        updated.setlist(k, current)

    return updated.urlencode()


@register.filter(name="min")
def fmin(value, arg):
    return min(int(value), int(arg))


@register.filter(name="max")
def fmax(value, arg):
    return max(int(value), int(arg))


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


@register.simple_tag
def settings_value(name):
    return getattr(settings, name, "")
