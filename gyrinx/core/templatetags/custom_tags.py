import hashlib
import random
import re

import bleach
import bleach.css_sanitizer
import qrcode
import qrcode.image.svg
from django import template
from django.conf import settings
from django.core.cache import cache
from django.template.context import RequestContext
from django.urls import resolve
from django.urls.exceptions import Resolver404
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe

from gyrinx.content.models import ContentPageRef
from gyrinx.core import url

register = template.Library()


def is_active(context: RequestContext, name):
    """Check if the current view is active."""
    try:
        match = resolve(context.request.path)
        return name == match.view_name
    except Resolver404:
        # We can't resolve the request path (e.g. on a 404 page!)
        # so it can't be active.
        return False


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


@register.simple_tag
def qt_contains(request, key, value):
    value = str(value)
    return key in request.GET and value in request.GET.getlist(key, list)


@register.filter(name="min")
def fmin(value, arg):
    return min(int(value), int(arg))


@register.filter(name="max")
def fmax(value, arg):
    return max(int(value), int(arg))


def identity(value):
    return value


@register.filter
def to_str(value):
    """converts int to string"""
    return str(value)


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


@register.simple_tag
def get_skill(skill_id):
    """Get a ContentSkill by its ID."""
    from gyrinx.content.models import ContentSkill

    try:
        return ContentSkill.objects.get(pk=skill_id)
    except ContentSkill.DoesNotExist:
        return None


@register.filter
def subtract(value, arg):
    """Subtract arg from value."""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return 0


@register.simple_tag
def random_404_message():
    """Return a random 404 error message."""
    messages = [
        "…or maybe that's what the Delaque want you to believe.",
        "But none can escape Helmawr's justice forever.",
        "We blame the Caryatids.",
        "Please direct all queries to your local Archeotek.",
        "It might have wandered too far into Hive Secundus.",
        "You probably shouldn't have paid the Whisper Merchant in advance.",
        "[REDACTED BY ORDER OF LORD HELMAWR]",
        "Never trust directions from a Goliath.",
        "You're never going to make it as a Technomancer.",
        "My cyber-mastiff ate it.",
        "Check your dome runner map is the right way up.",
        "Someone might have been at it with a data-thief.",
        "Guess it wasn't master-crafted after all.",
        "The engiseer said it was 'working as intended'.",
        "Nobody knows what happened to it.",
        "Try adjusting your augmetics.",
        "Lost in the Ash Wastes without a rebreather.",
        "Your data-slate was confiscated by Palanite Enforcers.",
        "Corpse Grinders ate this page. And the server.",
        "The Redemptionists burned it for heresy.",
        "Sold to the Mercator Slavers for two credits.",
        "Currently being digested by a sump kroc.",
        "Kal Jericho shot first. The page didn't make it.",
        "Van Saar's tech failed. Again.",
        "I was trying out some chems and accidentally dissolved the data.",
        "It fell through a rusted gantry.",
        "The Genestealers doesn't want you to see this.",
        "Scragged by a juve on their first raid.",
        "Your access codes expired 10,000 years ago.",
        "Currently under quarantine.",
        "Hunted for sport.",
        "There was an unscheduled rapid disassembly of the data shaft.",
        "Lost in transit.",
        "Eaten by rats. Big ones. With extra eyes.",
        "The manufactorum quota doesn't include this page.",
        "Chaos corruption detected. Purge initiated.",
        "Traded for a rusty stub gun.",
        "House Cawdor recycled it into a holy flamer.",
        "The Guilders repo'd it for unpaid tolls.",
        "A rogue servitor deleted the cache.",
        "Caught in the crossfire?",
        "Your dome runner gave you the wrong coordinates.",
        "Our exovator is still digging for it.",
        "Currently fermenting in a Goliath still.",
        "The arbitrator ruled against your access request.",
        "Lost during the Fall of Hive Secundus.",
        "Venators claimed the bounty on this page.",
    ]
    return random.choice(messages)  # nosec


@register.simple_tag
def cachebuster():
    """
    Generate a cachebuster string.

    This is used to force browsers to reload forms even if other params don't change.
    """
    return hex(int(random.random() * 1e8))[2:]  # nosec


@register.simple_tag
def dot():
    return mark_safe("&nbsp;·&nbsp;")


@register.simple_tag(takes_context=True)
def safe_referer(context: RequestContext, fallback_url="/"):
    """
    Get a safe redirect URL from HTTP_REFERER.

    This tag validates the referer header to prevent open redirect vulnerabilities.
    If the referer is not safe or missing, returns the fallback URL.

    Args:
        context: The template context containing the request
        fallback_url: The URL to use if referer is invalid (default: "/")

    Returns:
        A safe URL string that can be used for redirects
    """
    request = context["request"]
    referer = request.META.get("HTTP_REFERER", "")

    # Validate the referer URL is safe
    if referer and url_has_allowed_host_and_scheme(
        url=referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return referer

    # Fall back to the provided fallback URL
    return fallback_url


@register.filter
def safe_rich_text(value):
    """
    Sanitize and render rich text content safely.

    This filter sanitizes HTML content to prevent XSS attacks while preserving
    formatting from TinyMCE. It allows safe HTML tags and attributes commonly
    used in rich text editing but removes potentially dangerous content like
    script tags, event handlers, and javascript: URLs.

    Usage:
        {{ content|safe_rich_text|safe }}

    Note: The |safe filter is still needed after this to render the HTML,
    but the content has been sanitized first.
    """
    if not value:
        return ""

    # Define allowed tags for rich text content
    ALLOWED_TAGS = [
        # Text formatting
        "p",
        "br",
        "span",
        "div",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "s",
        "strike",
        "sub",
        "sup",
        "mark",
        # Headers
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        # Lists
        "ul",
        "ol",
        "li",
        # Quotes and code
        "blockquote",
        "pre",
        "code",
        "kbd",
        "samp",
        "var",
        # Links and media
        "a",
        "img",
        # Tables
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "th",
        "td",
        "caption",
        "colgroup",
        "col",
        # Semantic HTML
        "article",
        "section",
        "nav",
        "aside",
        "header",
        "footer",
        "address",
        "time",
        # Formatting
        "hr",
        "abbr",
        "acronym",
        "cite",
        "q",
        "del",
        "ins",
    ]

    # Define allowed attributes for specific tags
    ALLOWED_ATTRIBUTES = {
        # Links - only allow href and title, no event handlers
        "a": ["href", "title", "target", "rel"],
        # Images - basic attributes only, no event handlers
        "img": ["src", "alt", "title", "width", "height", "class"],
        # Tables
        "table": ["class", "border", "cellpadding", "cellspacing"],
        "td": ["class", "colspan", "rowspan", "align", "valign"],
        "th": ["class", "colspan", "rowspan", "align", "valign"],
        # General styling (but no inline JS)
        "*": ["class", "id", "style"],
    }

    # Define allowed CSS properties to prevent CSS-based attacks
    ALLOWED_STYLES = [
        "color",
        "background-color",
        "font-size",
        "font-weight",
        "font-style",
        "text-decoration",
        "text-align",
        "vertical-align",
        "margin",
        "margin-top",
        "margin-bottom",
        "margin-left",
        "margin-right",
        "padding",
        "padding-top",
        "padding-bottom",
        "padding-left",
        "padding-right",
        "border",
        "border-width",
        "border-color",
        "border-style",
        "width",
        "height",
        "max-width",
        "max-height",
        "min-width",
        "min-height",
        "display",
        "float",
        "clear",
        "position",
        "top",
        "left",
        "right",
        "bottom",
        "line-height",
        "white-space",
        "list-style-type",
    ]

    # Define allowed URL schemes to prevent javascript: and data: URLs
    ALLOWED_PROTOCOLS = ["http", "https", "mailto", "tel", "/", "#"]

    # Create CSS sanitizer for style attributes
    css_sanitizer = bleach.css_sanitizer.CSSSanitizer(
        allowed_css_properties=ALLOWED_STYLES
    )

    # Sanitize the HTML content
    # First pass: clean with escaping to preserve content structure
    cleaned = bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=css_sanitizer,
        strip=False,  # Escape disallowed tags first
        strip_comments=True,  # Remove HTML comments
    )

    # Second pass: strip any remaining escaped dangerous content patterns
    # This removes escaped script tags, style tags, etc. that would just be visual noise
    # Remove escaped script tags and their content
    cleaned = re.sub(
        r"&lt;script[^&]*&gt;.*?&lt;/script&gt;",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Remove escaped style tags and their content
    cleaned = re.sub(
        r"&lt;style[^&]*&gt;.*?&lt;/style&gt;",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Remove escaped iframe tags
    cleaned = re.sub(
        r"&lt;iframe[^&]*&gt;.*?&lt;/iframe&gt;",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Remove escaped form tags
    cleaned = re.sub(
        r"&lt;form[^&]*&gt;.*?&lt;/form&gt;",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Remove any remaining escaped tags that we don't want to show
    cleaned = re.sub(
        r"&lt;/?(?:meta|link|object|embed|svg)[^&]*&gt;",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    return mark_safe(cleaned)
