"""Badge and pill components (``text-bg-*`` per the design system)."""

from __future__ import annotations

from typing import Any

from ..elements import Element
from ..tags import span

__all__ = ["Badge", "StateBadge", "STATE_VARIANTS"]

# Fighter/campaign state -> Bootstrap contextual colour (design system § Colour).
STATE_VARIANTS = {
    "active": "success",
    "injured": "warning",
    "captured": "warning",
    "dead": "danger",
}


def Badge(
    *children: Any,
    variant: str = "secondary",
    pill: bool = False,
    class_: Any = None,
    **attrs: Any,
) -> Element:
    """A Bootstrap badge using the ``text-bg-{variant}`` pattern (not the
    deprecated ``bg-{variant}``)."""
    classes = ["badge", f"text-bg-{variant}", "rounded-pill" if pill else None, class_]
    return span(class_=classes, **attrs)[tuple(children)]


def StateBadge(state: str, *, label: str | None = None, **attrs: Any) -> Element:
    """A badge coloured by fighter/campaign state (active/injured/captured/dead)."""
    variant = STATE_VARIANTS.get(state.lower(), "secondary")
    return Badge(
        label if label is not None else state.title(), variant=variant, **attrs
    )
