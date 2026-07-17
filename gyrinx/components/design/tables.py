"""Table components using the canonical design-system table classes.

Canonical: ``table table-sm table-borderless mb-0`` (docs/DESIGN-SYSTEM.md § Tables).
"""

from __future__ import annotations

from typing import Any, Iterable

from ..elements import Element, Node
from ..tags import table, tbody, td, th, thead, tr

__all__ = ["Table", "Tr", "Td", "Th"]

# Re-export tag primitives under design names for readability at call sites.
Tr = tr
Td = td
Th = th


def Table(
    *children: Any,
    headers: Iterable[Any] | None = None,
    fixed: bool = False,
    compact: bool = False,
    class_: Any = None,
    **attrs: Any,
) -> Element:
    """Design-system table. ``fixed`` adds ``table-fixed`` (stat grids), ``compact``
    adds ``fs-7``. ``headers`` builds a ``<thead>`` of ``<th>`` cells."""
    classes = [
        "table table-sm table-borderless mb-0",
        "table-fixed" if fixed else None,
        "fs-7" if compact else None,
        class_,
    ]
    head: Node = None
    if headers is not None:
        head = thead[tr[tuple(th[h] for h in headers)]]
    return table(class_=classes, **attrs)[head, tuple(children)]


def TBody(*rows: Any, **attrs: Any) -> Element:
    return tbody(**attrs)[tuple(rows)]
