"""Typography helpers: caps labels, comma-separated lists, empty states.

From docs/DESIGN-SYSTEM.md § Typography, Empty States, Comma-Separated Lists.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from ..elements import Element, Node, fragment, raw
from ..tags import div, p, span

__all__ = ["CapsLabel", "CommaList", "EmptyState", "InlineNone", "Dot"]


def CapsLabel(*children: Any, class_: Any = None, **attrs: Any) -> Element:
    """``.caps-label`` — uppercase, tracked, semibold section/metadata label."""
    return div(class_=["caps-label", class_], **attrs)[tuple(children)]


def Dot() -> Node:
    """The ``{% dot %}`` separator: a non-breaking spaced middot."""
    return raw("&nbsp;·&nbsp;")


def CommaList(
    items: Iterable[Any], *, render: Callable[[Any], Node] | None = None
) -> Node:
    """Render items inline, comma-separated, without stray whitespace.

    Mirrors the design-system ``{% spaceless %}`` + ``<span>,&nbsp;</span>``
    pattern so lists don't wrap mid-item. ``render`` maps each item to a node
    (defaults to the item itself)."""
    items = list(items)
    out: list[Node] = []
    for index, item in enumerate(items):
        out.append(span[render(item) if render else item])
        if index != len(items) - 1:
            out.append(span[raw(",&nbsp;")])
    return fragment[tuple(out)]


def EmptyState(
    text: Any = "Nothing here yet.", *, class_: Any = None, **attrs: Any
) -> Element:
    """Standard empty-state line: ``<p class="text-secondary mb-0">``."""
    return p(class_=["text-secondary mb-0", class_], **attrs)[text]


def InlineNone(text: Any = "None") -> Element:
    """Inline empty value for table cells: muted italic ``None``."""
    return span(class_="text-secondary fst-italic")[text]
