"""Edition-independent template tags for navigation, query state and formatting.

Keep edition imports out of this module. N23 custom_tags re-exports these
registrations; platform templates load platform_tags directly.
"""

import random
import re
from urllib.parse import urlencode

import bleach
import bleach.css_sanitizer
import qrcode
import qrcode.image.svg
from django import template
from django.conf import settings
from django.template.context import RequestContext
from django.urls import resolve
from django.urls.exceptions import Resolver404
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import SafeData, mark_safe

register = template.Library()


def is_active(context: RequestContext, name):
    """Return whether this request resolves to the named view."""
    try:
        match = resolve(context.request.path)
        return name == match.view_name
    except Resolver404:
        # Unresolvable paths, including 404 pages, cannot match an active view.
        return False


@register.simple_tag(takes_context=True)
def active_view(context: RequestContext, name):
    return "active" if is_active(context, name) else ""


@register.simple_tag(takes_context=True)
def active_path(context: RequestContext, *prefixes):
    """Return 'active' if the current path starts with any of the given prefixes."""
    try:
        path = context.request.path
        return "active" if any(path.startswith(p) for p in prefixes) else ""
    except AttributeError, Resolver404:
        return ""


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
    if dictionary is None:
        return None
    if isinstance(dictionary, list):
        # List inputs must contain regroup entries with grouper and list attributes.
        item = next((item for item in dictionary if item.grouper == key), None)
        return item.list if item else None
    return dictionary.get(key)


@register.filter
def get_item(obj, key):
    """Read an indexed value, returning None for an absent key, invalid index or unsupported access."""
    if obj is None:
        return None
    try:
        return obj[key]
    except KeyError, TypeError, IndexError:
        return None


@register.filter
def join_names(items, attr="name"):
    """Join each object's named attribute, falling back to the object itself."""
    return ", ".join(str(getattr(item, attr, item)) for item in items)


@register.simple_tag
def qt(request, **kwargs):
    updated = request.GET.copy()
    for k, v in kwargs.items():
        if v is not None:
            updated[k] = v
        else:
            updated.pop(k, 0)  # Remove or return 0 - aka, delete safely this key

    return updated.urlencode()


def _qt_drop(querydict, drop):
    """Remove comma-separated query keys that an edited selection invalidates."""
    if not drop:
        return
    for key in str(drop).split(","):
        querydict.pop(key, 0)


@register.simple_tag
def qt_nth(request, drop=None, **kwargs):
    nth = kwargs.pop("nth")
    updated = request.GET.copy()
    _qt_drop(updated, drop)
    for k, v in kwargs.items():
        current = updated.getlist(k)
        if nth < len(current):
            current[nth] = v
        else:
            current.append(v)
        updated.setlist(k, current)

    return updated.urlencode()


@register.simple_tag
def qt_rm_nth(request, drop=None, **kwargs):
    nth = kwargs.pop("nth")
    updated = request.GET.copy()
    _qt_drop(updated, drop)
    for k, v in kwargs.items():
        if str(v) != "1":
            continue
        current = updated.getlist(k)
        if nth < len(current):
            current.pop(nth)
            updated.setlist(k, current)

    return updated.urlencode()


@register.simple_tag
def qt_append(request, drop=None, **kwargs):
    updated = request.GET.copy()
    _qt_drop(updated, drop)
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
def qt_getlist(request, key):
    """Return all query values for a key, including repeated parameters."""
    return request.GET.getlist(key)


@register.simple_tag
def qt_contains(request, key, value):
    value = str(value)
    return key in request.GET and value in request.GET.getlist(key, list)


@register.simple_tag
def qt_has_key(request, key):
    """Return whether the query contains this key, including an empty value."""
    return key in request.GET


@register.filter(name="abs")
def fabs(value):
    return abs(int(value))


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
def qr_svg(value):
    code = qrcode.make(
        value, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=0
    ).to_string(encoding="unicode")

    code = re.sub(r'width="\d+mm"', "", code)
    code = re.sub(r'height="\d+mm"', "", code)
    code = re.sub(r"<svg ", '<svg width="100%" height="100%" ', code)

    return mark_safe(code)


@register.simple_tag
def settings_value(name):
    return getattr(settings, name, "")


@register.filter
def subtract(value, arg):
    """Subtract arg from value."""
    try:
        return int(value) - int(arg)
    except ValueError, TypeError:
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


NOWRAP_THRESHOLD = 40


@register.filter
def nowrap_class(value, threshold=NOWRAP_THRESHOLD):
    """Return text-nowrap when the value fits within the character threshold."""
    if value is None:
        return "text-nowrap"
    str_value = str(value)
    return "text-nowrap" if len(str_value) <= threshold else ""


@register.simple_tag
def property_nowrap_class(label, value, threshold=NOWRAP_THRESHOLD):
    """Return text-nowrap when "label: value" fits within the character threshold."""
    combined = f"{label}: {value}"
    return "text-nowrap" if len(combined) <= threshold else ""


@register.simple_tag(takes_context=True)
def safe_referer(context: RequestContext, fallback_url="/"):
    """Return an allowed HTTP_REFERER URL, otherwise the caller's trusted fallback.

    Limit absolute destinations to the current host and require HTTPS for
    secure requests.
    """
    request = context["request"]
    referer = request.META.get("HTTP_REFERER", "")

    if referer and url_has_allowed_host_and_scheme(
        url=referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return referer

    return fallback_url


@register.simple_tag(takes_context=True)
def return_url_param(context: RequestContext):
    """URL-encode the current full path as a return_url query parameter."""
    request = context["request"]
    current_url = request.get_full_path()
    return urlencode({"return_url": current_url})


@register.simple_tag(takes_context=True)
def return_url_field(context: RequestContext):
    """Render an escaped hidden field for return_url from the template context."""
    return_url = context.get("return_url", "")
    if return_url:
        return format_html(
            '<input type="hidden" name="return_url" value="{}">',
            return_url,
        )
    return ""


@register.filter
def plain_text_truncate(value, length=150):
    """Strip HTML, collapse whitespace and truncate with an ellipsis.

    Prefer the last word boundary in the latter half of the available space.
    """
    if not value:
        return ""

    text = bleach.clean(value, tags=[], strip=True)

    text = " ".join(text.split())

    length = int(length)
    if len(text) > length:
        # Prefer a word boundary without discarding more than half the requested length.
        truncated = text[:length]
        last_space = truncated.rfind(" ")
        if last_space > length // 2:  # Only use word boundary if it's reasonable
            truncated = truncated[:last_space]
        return truncated.rstrip() + "…"

    return text


@register.filter
def safe_rich_text(value):
    """Sanitise rich HTML against the tag, attribute, CSS and URL allowlists.

    Return marked-safe HTML ready for rendering. Strip disallowed tags and
    comments; text inside disallowed tags can remain as plain text.
    """
    if not value:
        return ""

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

    ALLOWED_PROTOCOLS = ["http", "https", "mailto", "tel", "/", "#"]

    css_sanitizer = bleach.css_sanitizer.CSSSanitizer(
        allowed_css_properties=ALLOWED_STYLES
    )

    # Strip disallowed tags and comments; Bleach can retain their text content.
    cleaned = bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=css_sanitizer,
        strip=True,  # Remove disallowed tags and their content
        strip_comments=True,  # Remove HTML comments
    )

    return mark_safe(cleaned)


@register.filter(name="strip")
def strip_filter(value):
    """Trim rendered slot whitespace while preserving existing SafeData status.

    This removes padding introduced by template formatting around inline links.
    Plain strings remain unmarked so the template engine still escapes them.
    """
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    stripped = text.strip()
    return mark_safe(stripped) if isinstance(value, SafeData) else stripped
