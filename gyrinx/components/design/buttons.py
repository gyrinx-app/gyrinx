"""Button and link components.

Encapsulates the design-system button vocabulary so call sites stop hand-writing
``btn btn-primary btn-sm`` strings. A :func:`Button` renders as ``<a>`` when given
``href`` and ``<button>`` otherwise — matching how the templates use both.
"""

from __future__ import annotations

from typing import Any

from ..elements import Element, Node
from ..tags import a, button
from .icons import Icon

__all__ = ["Button", "SubmitButton", "ButtonGroup"]


def Button(
    *children: Any,
    variant: str = "primary",
    size: str | None = "sm",
    href: str | None = None,
    type: str = "button",
    icon: str | Node | None = None,
    icon_after: str | Node | None = None,
    class_: Any = None,
    outline: bool = False,
    **attrs: Any,
) -> Element:
    """A Bootstrap button or button-styled link.

    * ``variant`` — ``primary``/``success``/``danger``/``secondary``/... maps to
      ``btn-{variant}`` (or ``btn-outline-{variant}`` when ``outline=True``).
    * ``size`` — ``"sm"`` (default) / ``"lg"`` / ``None`` for default size.
    * ``href`` — when set, renders an ``<a>`` acting as a button; otherwise a
      ``<button type=...>``.
    * ``icon`` / ``icon_after`` — a Bootstrap icon name or icon node placed
      before/after the label (with a separating space, matching the templates).
    """
    variant_class = f"btn-outline-{variant}" if outline else f"btn-{variant}"
    classes = ["btn", variant_class, f"btn-{size}" if size else None, class_]

    body: list[Any] = []
    if icon is not None:
        body.append(Icon(icon) if isinstance(icon, str) else icon)
        if children:
            body.append(" ")
    body.extend(children)
    if icon_after is not None:
        if children:
            body.append(" ")
        body.append(Icon(icon_after) if isinstance(icon_after, str) else icon_after)

    if href is not None:
        return a(class_=classes, href=href, **attrs)[tuple(body)]
    return button(class_=classes, type=type, **attrs)[tuple(body)]


def SubmitButton(*children: Any, variant: str = "success", **attrs: Any) -> Element:
    """Form submit button. Defaults to ``btn-success`` per the design system
    (save/create/confirm)."""
    attrs.setdefault("size", None)
    return Button(*children, variant=variant, type="submit", **attrs)


def ButtonGroup(
    *children: Any, class_: Any = None, nav: bool = False, **attrs: Any
) -> Element:
    """A Bootstrap ``btn-group``. Pass ``nav=True`` for the page-header
    ``nav btn-group flex-nowrap`` pattern."""
    from ..tags import div, nav as nav_el

    tag = nav_el if nav else div
    classes = ["nav btn-group flex-nowrap" if nav else "btn-group", class_]
    if not nav:
        attrs.setdefault("role", "group")
    return tag(class_=classes, **attrs)[tuple(children)]
