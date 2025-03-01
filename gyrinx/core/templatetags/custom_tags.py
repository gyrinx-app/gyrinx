import re

import qrcode
import qrcode.image.svg
from django import template
from django.conf import settings
from django.template.context import RequestContext
from django.urls import resolve
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from gyrinx.content.models import ContentPageRef
from gyrinx.core import url

register = template.Library()


def is_active(context: RequestContext, name):
    """Check if the current view is active."""
    return name == resolve(context.request.path).view_name


@register.simple_tag(takes_context=True)
def active_view(context: RequestContext, name):
    return "active" if is_active(context, name) else ""


@register.simple_tag(takes_context=True)
def active_aria(context: RequestContext, name):
    return 'aria-current="page"' if is_active(context, name) else ""


@register.simple_tag(takes_context=True)
def active_query(context: RequestContext, key, value):
    return "active" if context["request"].GET.get(key, "") == value else ""


@register.simple_tag(takes_context=True)
def active_query_aria(context: RequestContext, key, value):
    return 'aria-current="page"' if active_query(context, key, value) else ""


@register.simple_tag(takes_context=True)
def flash(context: RequestContext, id):
    request = context["request"]
    return "flash-warn" if request.GET.get("flash") == str(id) else ""


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


@register.simple_tag
def qt_rm(request, *args):
    updated = request.GET.copy()
    for k in args:
        updated.pop(k, 0)

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
def qr_svg(value):
    code = qrcode.make(
        value, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=0
    ).to_string(encoding="unicode")

    code = re.sub(r'width="\d+mm"', "", code)
    code = re.sub(r'height="\d+mm"', "", code)
    code = re.sub(r"<svg ", '<svg width="100%" height="100%" ', code)

    return mark_safe(code)


@register.simple_tag(takes_context=True)
def fullurl(context: RequestContext, path):
    return url.fullurl(context["request"], path)


@register.simple_tag
def settings_value(name):
    return getattr(settings, name, "")
