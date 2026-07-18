"""Gyrinx component system.

A Python component library that renders static HTML. Components are plain
callables returning nodes; nodes are built from HTML tag factories using a
JSX-like ``tag(**attrs)[children]`` syntax and rendered with :func:`render`.

    from gyrinx.components import div, p, render
    from gyrinx.components.design import Button

    render(div(class_="card")[p["Hello"], Button(variant="primary")["Save"]])

See the module docstrings in this package (``elements``, ``tags``, ``layout``)
and the design-system components under ``gyrinx.components.design``.
"""

from __future__ import annotations

from . import tags
from .elements import (
    Element,
    Fragment,
    Node,
    VoidElement,
    attrs_to_html,
    classnames,
    fragment,
    raw,
    render,
    safe,
)
from .tags import *  # noqa: F401,F403  (re-export all HTML tag factories)

__all__ = [
    "Node",
    "Element",
    "VoidElement",
    "Fragment",
    "fragment",
    "render",
    "raw",
    "safe",
    "classnames",
    "attrs_to_html",
    *tags.__all__,
]
