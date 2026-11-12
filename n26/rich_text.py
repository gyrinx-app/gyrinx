"""Use the platform element parser with the N26 authored-HTML sanitiser."""

from django.template.defaultfilters import linebreaks
from django.utils.html import escape

from gyrinx.accounts.rich_text import rich_text_nodes as parse_nodes
from n26.core.templatetags.richtext import safe_rich_text


def plain_html(value):
    return safe_rich_text(linebreaks(str(escape(value or ""))))


def authored_html(value):
    # Plain-text drafts retain paragraph breaks when opened in the editor.
    value = value or ""
    return safe_rich_text(value) if "<" in value else plain_html(value)


def rich_text_nodes(value):
    return parse_nodes(value, sanitize=authored_html)
