"""Presentation-only seams for rendering N26 components without application models.

The sandbox does not initialise the N26 model graph. Gang action menus are empty;
any attempt to build a real domain action here must fail rather than imply access.
"""

from django import template
from django.utils.html import strip_tags
from django.utils.text import Truncator

register = template.Library()


@register.filter
def get_item(value, key):
    return value[key]


@register.filter
def plain_text_truncate(value, length):
    return Truncator(strip_tags(value)).chars(int(length))


@register.simple_tag
def link_actions(**kwargs):
    raise ValueError("Campaign rendering cannot construct application actions.")
