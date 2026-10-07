"""Menus of links, as the action-menu island's props.

The server decides which links a reader gets, in what order, and where a
separator falls. React only draws them and handles the keys.
"""

from html import unescape

from django import template
from django.utils.safestring import SafeData

from n26.core.listing import DANGER, LINK, Action

register = template.Library()

TRIGGERS = ("ellipsis", "chevron")
VARIANTS = ("default", "ghost")
ALIGNS = ("start", "end")


def _text(value):
    # A Cotton string attribute arrives already escaped: "O'Brien" is
    # O&#x27;Brien by the time a component sees it. React escapes again when
    # it draws, so decode it here, once. Plain Python strings are left alone.
    if value is None:
        return ""
    return unescape(str(value)) if isinstance(value, SafeData) else str(value)


def _entry(item):
    if isinstance(item, Action):
        if item.kind != LINK:
            raise ValueError(f"An action menu draws links only, not {item.kind!r}")
        return {
            "label": _text(item.label),
            "href": _text(item.target),
            "tone": "danger" if item.tone == DANGER else "default",
            "separatorBefore": False,
        }
    return {
        "label": _text(item["label"]),
        "href": _text(item.get("href", "")),
        "tone": "danger" if item.get("tone") == "danger" else "default",
        "separatorBefore": bool(item.get("separator_before")),
    }


def _choice(value, allowed, name):
    value = str(value)
    if value not in allowed:
        raise ValueError(
            f"An action menu's {name} must be one of {allowed}, not {value!r}"
        )
    return value


@register.simple_tag
def action_menu_props(
    items,
    label,
    trigger="ellipsis",
    variant="default",
    align="start",
    min_width="12rem",
):
    """The action-menu island's props.

    ``items`` are :class:`Action` links or entries from :func:`link_actions`,
    kept in the order given. An item with no address is left out. The props
    name the trigger's text ``label``, never ``aria-label``: pages count that
    attribute and the fallback button already carries it.
    """
    return {
        "label": _text(label),
        "trigger": _choice(trigger, TRIGGERS, "trigger"),
        "variant": _choice(variant, VARIANTS, "variant"),
        "align": _choice(align, ALIGNS, "align"),
        "minWidth": str(min_width),
        "items": [entry for entry in map(_entry, items or ()) if entry["href"]],
    }


@register.simple_tag
def link_actions(*pairs, danger_label="", danger_href="", danger_separator=False):
    """``{% link_actions "View gang" href "Edit gang settings" edit_href as menu_ %}``

    Label and address pairs, in the order they are drawn. An empty address
    drops its link later, in :func:`action_menu_props`. The danger link, when
    it has an address, goes last, with a separator above it only when
    ``danger_separator`` is set.
    """
    if len(pairs) % 2:
        raise template.TemplateSyntaxError("link_actions takes label and href pairs")
    entries = [
        {"label": label, "href": href, "tone": "default", "separator_before": False}
        for label, href in zip(pairs[::2], pairs[1::2], strict=True)
    ]
    if danger_label and danger_href:
        entries.append(
            {
                "label": danger_label,
                "href": danger_href,
                "tone": "danger",
                "separator_before": bool(danger_separator),
            }
        )
    return entries
