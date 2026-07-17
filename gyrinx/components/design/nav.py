"""Navigation components: nav-tabs and search bar.

From docs/DESIGN-SYSTEM.md § Nav Tabs and § Search Pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..elements import Element, Node
from ..tags import a, button, div, form, input_, li, span, ul
from .icons import Icon

__all__ = ["NavTabs", "Tab", "SearchBar"]


@dataclass(frozen=True)
class Tab:
    """A single nav tab. ``href`` renders an anchor tab; omit for a button tab."""

    label: Any
    href: str | None = None
    active: bool = False
    id: str | None = None
    attrs: dict[str, Any] | None = None


def NavTabs(
    tabs: Iterable[Tab], *, compact: bool = False, class_: Any = None, **attrs: Any
) -> Element:
    """Bootstrap ``nav nav-tabs``. ``compact`` adds ``fs-7 px-2 py-1`` to links
    (fighter-card tab style)."""
    link_extra = "fs-7 px-2 py-1" if compact else None
    items: list[Node] = []
    for tab in tabs:
        link_classes = ["nav-link", link_extra, {"active": tab.active}]
        extra = tab.attrs or {}
        if tab.href is not None:
            node = a(class_=link_classes, href=tab.href, id=tab.id, **extra)[tab.label]
        else:
            node = button(class_=link_classes, type="button", id=tab.id, **extra)[
                tab.label
            ]
        items.append(li(class_="nav-item")[node])
    return ul(class_=["nav nav-tabs", class_], **attrs)[tuple(items)]


def SearchBar(
    *,
    name: str = "q",
    value: Any = "",
    placeholder: str = "Search...",
    action: str | None = None,
    method: str = "get",
    button_text: str = "Search",
    class_: Any = None,
    **attrs: Any,
) -> Element:
    """The standard search bar (design system § Search Pattern).

    Icon in an ``input-group-text`` prepend; submit is ``btn-primary`` (search
    is navigation, not creation). Wrapped in a ``<form>`` when ``action`` given."""
    group = div(class_=["input-group", class_], **attrs)[
        span(class_="input-group-text")[Icon("search")],
        input_(
            class_="form-control",
            type="search",
            placeholder=placeholder,
            name=name,
            value=value or "",
        ),
        button(class_="btn btn-primary", type="submit")[button_text],
    ]
    if action is None:
        return group
    return form(action=action, method=method, role="search")[group]
