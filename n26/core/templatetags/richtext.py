"""Rendering rich text without trusting it.

Adapted from ``safe_rich_text`` in the main gyrinx app. Anything a rich text
editor produces is user input that has been round-tripped through a database, so
it is sanitised at render time rather than on the way in: the stored value stays
faithful to what the author wrote, and a change to the allowlist takes effect on
existing content instead of only on whatever is saved next.
"""

import re

import bleach
from bleach.css_sanitizer import CSSSanitizer
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# What the editor can produce, and nothing else. Notably absent: script, style,
# iframe, object, embed, form and the input family.
ALLOWED_TAGS = {
    # Text
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
    # Headings
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
    # Semantics
    "article",
    "section",
    "nav",
    "aside",
    "header",
    "footer",
    "address",
    "time",
    # Misc
    "hr",
    "abbr",
    "acronym",
    "cite",
    "q",
    "del",
    "ins",
}

# No on* handlers anywhere: an allowlist means onclick and friends are dropped
# without having to name them.
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height", "class"],
    "table": ["class", "border", "cellpadding", "cellspacing"],
    "td": ["class", "colspan", "rowspan", "align", "valign"],
    "th": ["class", "colspan", "rowspan", "align", "valign"],
    "*": ["class", "id", "style"],
}

# style is allowed, so its contents need their own allowlist — otherwise it is a
# way back in, through url() and expression().
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

# Keeps javascript: and data: out of href and src.
ALLOWED_PROTOCOLS = ["http", "https", "mailto", "tel"]

_CSS_SANITIZER = CSSSanitizer(allowed_css_properties=ALLOWED_STYLES)

# bleach with strip=True drops a disallowed *tag* but keeps the text inside it,
# so "<script>alert(1)</script>" comes out as the visible words "alert(1)".
# Inert, but it spills source into the page, so these two are removed whole first.
#
# This is tidying, not the security boundary — bleach below is, and it still runs
# on everything. A regex over HTML is only safe to lean on in that order.
_DROP_WITH_CONTENT = re.compile(
    r"<\s*(script|style)\b[^>]*>.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL
)


@register.filter
def safe_rich_text(value):
    """Sanitise editor HTML and mark the result safe.

    Usage::

        {{ page.body|safe_rich_text }}

    No trailing ``|safe`` — the return is already marked, and adding one to the
    *unsanitised* value by mistake is exactly the failure this exists to prevent.
    """
    if not value:
        return ""

    return mark_safe(  # nosec B703 B308 - bleach.clean is the sanitiser
        bleach.clean(
            _DROP_WITH_CONTENT.sub("", str(value)),
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            protocols=ALLOWED_PROTOCOLS,
            css_sanitizer=_CSS_SANITIZER,
            # Drop disallowed tags and their contents, rather than escaping them
            # into visible angle brackets.
            strip=True,
            strip_comments=True,
        )
    )
