"""Page-level layout patterns.

From docs/DESIGN-SYSTEM.md § Page Patterns, Page Shells, Inline Action Menus,
Buttons (back link).
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Iterable

from ..elements import Element, Node, fragment
from ..tags import a, div, h1, li, nav, ol, span
from .icons import Icon
from .typography import Dot

__all__ = [
    "PageHeader",
    "BackLink",
    "MetaItem",
    "MetaRow",
    "InfoColumn",
    "InfoColumns",
    "InlineActionMenu",
    "ActionLink",
    "PageShell",
]


def PageHeader(
    title: Any,
    *,
    actions: Node | None = None,
    meta: Node | None = None,
    subtitle_level: bool = False,
    title_class: Any = None,
    **attrs: Any,
) -> Node:
    """Standard list/detail page header: title left, actions right, meta below.

    ``subtitle_level=True`` renders the ``<h1 class="h3">`` sub-page size.
    ``actions`` is typically a :func:`~gyrinx.components.design.ButtonGroup`.
    """
    heading_classes = ["mb-0", "h3" if subtitle_level else None, title_class]
    header_row = div(
        class_="d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2 mb-2",
        **attrs,
    )[
        h1(class_=heading_classes)[title],
        nav(class_="nav btn-group flex-nowrap ms-md-auto")[actions]
        if actions is not None
        else None,
    ]
    return fragment[header_row, meta]


def BackLink(
    *,
    url: str | None = None,
    text: Any = "Back",
    **attrs: Any,
) -> Element:
    """Back navigation as a breadcrumb (matches ``core/includes/back.html``).

    Pass an explicit ``url``. When rendered from a page component the caller can
    resolve the referer fallback and pass it in.
    """
    return nav(aria_label="breadcrumb", **attrs)[
        ol(class_="breadcrumb")[
            li(class_="breadcrumb-item active", aria_current="page")[
                Icon("chevron-left"),
                a(href=url or "/")[text],
            ]
        ]
    ]


@dataclass(frozen=True)
class MetaItem:
    """One metadata pill: an icon + text, shown in the header meta row."""

    text: Any
    icon: str | None = None


def MetaRow(
    items: Iterable[MetaItem | Node], *, class_: Any = None, **attrs: Any
) -> Element:
    """Header metadata row: ``d-flex flex-wrap gap-2 text-secondary fs-7``."""
    rendered: list[Node] = []
    for item in items:
        if isinstance(item, MetaItem):
            rendered.append(
                span[
                    Icon(item.icon) if item.icon else None,
                    " " if item.icon else None,
                    item.text,
                ]
            )
        else:
            rendered.append(item)
    return div(class_=["d-flex flex-wrap gap-2 text-secondary fs-7", class_], **attrs)[
        tuple(rendered)
    ]


@dataclass(frozen=True)
class InfoColumn:
    """A label/value pair in the campaign info-columns row."""

    label: Any
    value: Any
    action: Node | None = None


def InfoColumns(
    columns: Iterable[InfoColumn], *, class_: Any = None, **attrs: Any
) -> Element:
    """Campaign info columns: label/value pairs in a bordered flex row."""
    from .typography import CapsLabel

    cols: list[Node] = []
    for col in columns:
        cols.append(
            div(class_="flex-grow-1 col-md-3 flex-md-grow-0")[
                CapsLabel(col.label),
                div[col.value],
                col.action,
            ]
        )
    return div(
        class_=["d-flex flex-wrap gap-3 border-bottom pb-3 mb-2", class_], **attrs
    )[tuple(cols)]


@dataclass(frozen=True)
class ActionLink:
    """A single inline action-menu link."""

    text: Any
    href: str | None = None
    variant: str = "secondary"  # secondary | danger | warning
    attrs: dict[str, Any] = dc_field(default_factory=dict)


def InlineActionMenu(
    links: Iterable[ActionLink],
    *,
    wrap: str = "div",  # "div" | "row" (table row full-width td)
    colspan: int | None = None,
    class_: Any = None,
) -> Element:
    """Contextual action links below gear/weapons on fighter cards.

    ``bi-arrow-90deg-up`` connector, ``{% dot %}`` separators, ``link-{variant}``
    links (secondary for edit/cost/reassign, danger for delete, warning for sell).
    """
    links = list(links)
    inner: list[Node] = [Icon("arrow-90deg-up", class_="text-secondary me-1")]
    for index, link in enumerate(links):
        if index:
            inner.append(Dot())
        inner.append(
            a(class_=f"link-{link.variant}", href=link.href, **link.attrs)[link.text]
        )
    body = div(class_=["d-flex flex-wrap", class_])[tuple(inner)]
    if wrap == "row":
        from ..tags import td, tr

        return tr[td(colspan=colspan, class_="text-end")[body]]
    return body


def PageShell(
    *children: Any, kind: str = "list", class_: Any = None, **attrs: Any
) -> Element:
    """A page content shell (goes inside the layout ``content`` block).

    ``kind`` selects the width/gap preset (or pass an explicit class string):

    * ``list`` / ``detail`` — ``col-lg-12 px-0 vstack gap-4``
    * ``form`` — ``col-12 col-md-8 col-lg-6 vstack gap-3``
    * ``narrow`` — ``col-12 col-xl-6 vstack gap-3``
    """
    shells = {
        "list": "col-lg-12 px-0 vstack gap-4",
        "detail": "col-lg-12 px-0 vstack gap-4",
        "form": "col-12 col-md-8 col-lg-6 vstack gap-3",
        "narrow": "col-12 col-xl-6 vstack gap-3",
    }
    return div(class_=[shells.get(kind, kind), class_], **attrs)[tuple(children)]
