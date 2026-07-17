"""Container, section-header, and card components.

From docs/DESIGN-SYSTEM.md § Containers & Cards. The default grouping container
is ``border rounded p-3`` (NOT a Bootstrap card — cards are reserved for fighter
grids and equipment categories).
"""

from __future__ import annotations

from typing import Any

from ..elements import Element, Node
from ..tags import a, div, h2, h3
from .icons import Icon

__all__ = [
    "Container",
    "SectionHeader",
    "Card",
    "CardHeader",
    "CardBody",
]


def Container(
    *children: Any, compact: bool = False, class_: Any = None, **attrs: Any
) -> Element:
    """Standard grouping container: ``border rounded p-3`` (``p-2`` when
    ``compact``). Use for grouped content, forms, callouts."""
    classes = ["border rounded", "p-2" if compact else "p-3", class_]
    return div(class_=classes, **attrs)[tuple(children)]


def SectionHeader(
    title: Any,
    *,
    action: Node | None = None,
    action_href: str | None = None,
    action_text: str | None = None,
    action_icon: str | None = None,
    level: int = 2,
    heading_class: Any = "h5 mb-0",
    class_: Any = None,
    **attrs: Any,
) -> Element:
    """Section header bar: title left, optional action right.

    ``bg-body-secondary rounded px-2 py-1`` with a flex layout. Provide an
    ``action`` node, or ``action_href`` (+ ``action_text``/``action_icon``) to
    build the standard ``icon-link linked`` add/edit link.
    """
    heading_tag = {2: h2, 3: h3}.get(level, h2)
    if action is None and action_href is not None:
        action = a(class_="fs-7 icon-link linked", href=action_href)[
            Icon(action_icon) if action_icon else None,
            action_text,
        ]
    classes = [
        "d-flex justify-content-between align-items-center",
        "bg-body-secondary rounded px-2 py-1",
        class_,
    ]
    return div(class_=classes, **attrs)[
        heading_tag(class_=heading_class)[title],
        action,
    ]


def Card(*children: Any, class_: Any = None, **attrs: Any) -> Element:
    """A Bootstrap ``card`` — reserved for fighter grids / equipment categories."""
    return div(class_=["card", class_], **attrs)[tuple(children)]


def CardHeader(*children: Any, class_: Any = None, **attrs: Any) -> Element:
    return div(class_=["card-header", class_], **attrs)[tuple(children)]


def CardBody(*children: Any, class_: Any = None, **attrs: Any) -> Element:
    return div(class_=["card-body", class_], **attrs)[tuple(children)]
