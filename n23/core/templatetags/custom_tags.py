"""The N23 edition's template tags.

Two kinds of thing live here:

1. The tags that genuinely need edition code — rulebook page references, the
   credit formatter, gang/campaign helpers. These cannot move to the platform
   without dragging ``n23.*`` imports into ``gyrinx/``.

2. A re-export of every tag in the platform's ``platform_tags`` library, so that
   the ~215 edition templates already writing ``{% load custom_tags %}`` keep
   working unchanged. ``{% load %}`` resolves by library NAME across all
   installed apps, and a name may only be provided once, so ``custom_tags``
   stays the edition's single entry point and takes the union.

Direction of travel: edition depends on platform, never the reverse. Add generic
tags to ``gyrinx/site/templatetags/platform_tags.py``, not here.
"""

import hashlib

from django import template
from django.core.cache import cache
from django.template.context import RequestContext
from django.utils.html import format_html

from gyrinx.site.templatetags import platform_tags
from n23.content.models import ContentPageRef
from n23.core import url
from n23.models import format_cost_display

register = template.Library()

# Take the platform's generic tags wholesale. Done before this module registers
# anything of its own, so an edition tag would deliberately shadow a platform
# one of the same name (there are none today).
register.tags.update(platform_tags.register.tags)
register.filters.update(platform_tags.register.filters)


@register.simple_tag
def ref(*args, category=None, value=None):
    """
    Render a reference to a rulebook page.

    This tag takes a list of arguments and returns a link to the most similar
    rulebook page. If no similar page is found, the original string is returned.

    This tag is cached, so it can be called multiple times with the same arguments
    without incurring a performance penalty. The references almost never change,
    so this should be very safe to do.
    """
    search_value = " ".join(args)
    if not value:
        value = search_value

    search_value_hash = hashlib.sha1(search_value.encode("utf-8")).hexdigest()
    cache_key = f"ref_{search_value_hash}"

    kwargs = {}
    if category:
        kwargs["category"] = category
        cat_hash = hashlib.sha1(category.encode("utf-8")).hexdigest()
        cache_key += f"_{cat_hash}"

    if cache.has_key(cache_key):
        return cache.get(cache_key)

    refs = ContentPageRef.find_similar(search_value, **kwargs)

    if not refs:
        cache.set(cache_key, value)
        return value

    ref_str = ", ".join(ref.bookref() for ref in refs)

    full_ref = format_html(
        '<span data-bs-toggle="tooltip" data-bs-title="{}" class="tooltipped">{}</span>',
        ref_str,
        value,
    )
    cache.set(cache_key, full_ref)
    return full_ref


@register.simple_tag(takes_context=True)
def fullurl(context: RequestContext, path):
    return url.fullurl(context["request"], path)


@register.simple_tag
def get_skill(skill_id):
    """Get a ContentSkill by its ID."""
    from n23.content.models import ContentSkill

    try:
        return ContentSkill.objects.get(pk=skill_id)
    except ContentSkill.DoesNotExist:
        return None


@register.simple_tag
def credits(value, show_sign=False):
    """
    Format an integer cost value with the credits symbol.

    Args:
        value: Integer cost value
        show_sign: If True, show '+' for positive values (default: False)

    Usage:
        {% credits list.wealth_current %}
        {% credits delta show_sign=True %}
    """
    return format_cost_display(value, show_sign=show_sign)


@register.filter
def pack_name(obj_id, pack_content_map):
    """Get the pack name(s) for a content object ID, or empty string.

    Usage:
        {% with assign.equipment.id|pack_name:pack_content_map as pname %}
    """
    if not pack_content_map or not isinstance(pack_content_map, dict):
        return ""
    names = pack_content_map.get(obj_id, [])
    if isinstance(names, list):
        return ", ".join(names)
    return names


@register.filter
def is_campaign_admin(campaign, user):
    """True when user administers campaign (owner or shared admin). None-safe."""
    return campaign is not None and campaign.is_admin(user)
