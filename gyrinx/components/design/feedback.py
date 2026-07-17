"""Alerts and flash-message rendering.

Implements the design-system alert pattern: ``alert alert-{variant} alert-icon``
with a pinned leading icon, per docs/DESIGN-SYSTEM.md § Feedback.
"""

from __future__ import annotations

from typing import Any

from ..elements import Element, Node, fragment
from ..tags import button, div
from .icons import Icon

__all__ = ["Alert", "Messages", "ALERT_ICONS"]

# Default icon per alert variant (design system § Feedback).
ALERT_ICONS = {
    "success": "check-lg",
    "danger": "exclamation-triangle",
    "warning": "exclamation-triangle",
    "info": "info-circle",
    "secondary": "info-circle",
    "primary": "info-circle",
}

# Django message tag -> Bootstrap alert variant (mirrors base.html mapping).
MESSAGE_VARIANTS = {
    "debug": "secondary",
    "info": "info",
    "success": "success",
    "warning": "warning",
    "error": "danger",
}


def Alert(
    *children: Any,
    variant: str = "info",
    icon: str | Node | bool | None = None,
    dismissible: bool = False,
    class_: Any = None,
    role: str = "alert",
    **attrs: Any,
) -> Element:
    """A design-system alert.

    * ``variant`` — ``success``/``danger``/``warning``/``info``/``secondary``.
    * ``icon`` — icon name, icon node, ``None`` for the variant default, or
      ``False`` to omit the icon (and the ``alert-icon`` flex layout).
    * ``dismissible`` — add the fade/close-button treatment (flash messages).
    """
    show_icon = icon is not False
    icon_node: Node | None = None
    if show_icon:
        name = (
            icon
            if isinstance(icon, str)
            else (ALERT_ICONS.get(variant, "info-circle") if icon is None else None)
        )
        icon_node = Icon(name) if name is not None else icon  # type: ignore[assignment]

    classes = [
        "alert",
        f"alert-{variant}",
        "alert-icon" if show_icon else None,
        "alert-dismissible fade show" if dismissible else None,
        class_,
    ]
    close = (
        button(
            type="button",
            class_="btn-close",
            data_bs_dismiss="alert",
            aria_label="Close",
        )
        if dismissible
        else None
    )
    # The design system wraps the message body in a <div> next to the icon.
    body = div[tuple(children)] if show_icon else fragment[tuple(children)]
    return div(class_=classes, role=role, **attrs)[icon_node, body, close]


def Messages(messages: Any) -> Node:
    """Render Django's ``messages`` framework list as dismissible alerts,
    matching the block in ``base.html``. Returns nothing when empty."""
    items = list(messages) if messages else []
    if not items:
        return None
    return div[
        tuple(
            Alert(
                str(message),
                variant=MESSAGE_VARIANTS.get(message.tags, "info"),
                dismissible=True,
            )
            for message in items
        )
    ]
