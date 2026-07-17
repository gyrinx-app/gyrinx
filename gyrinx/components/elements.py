"""Core rendering engine for the Gyrinx component system.

A small, dependency-light HTML element library inspired by JSX/React and by
Python libraries like ``htpy``. Elements render to static HTML strings and
interoperate fully with Django's autoescaping (``SafeString`` / ``__html__``).

The public surface here is deliberately tiny:

* :class:`Element` / :class:`VoidElement` — HTML tags, built with the
  ``tag(**attrs)[children]`` syntax.
* :class:`Fragment` (and the ``_`` singleton) — group children with no wrapper.
* :func:`render` — turn any node into a ``SafeString`` of HTML.
* :func:`raw` / :func:`safe` — mark a trusted HTML string as safe.
* :func:`classnames` — clsx-style class composition (also available inline via
  ``class_=[...]`` / ``class_={...}``).

Everything else — HTML tag factories, design-system components — is built on
top of these primitives.

Design notes
------------
Elements are **immutable**: ``__call__`` (set attributes) and ``__getitem__``
(set children) each return a *new* element. This makes shared/partial-applied
elements safe to reuse and keeps components free of hidden state.

A "node" (anything renderable) is one of:

* ``None`` / ``True`` / ``False`` — rendered as empty (lets you write
  ``cond and element`` / ``element if cond else None``).
* ``str`` — escaped, unless it is already safe (``SafeString`` or has
  ``__html__``).
* ``int`` / ``float`` / ``Decimal`` — stringified (numbers need no escaping).
* :class:`Node` (``Element``/``Fragment``) — rendered recursively.
* an iterable (list/tuple/generator) of nodes — rendered in order.
* any object with an ``__html__`` method — treated as safe (Django/markupsafe).
* any other object — ``str()``-ified and escaped.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Mapping

from django.utils.html import conditional_escape
from django.utils.safestring import SafeString, mark_safe

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
    "VOID_ELEMENTS",
]

# HTML void elements (no closing tag, no children).
VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


def _normalise_key(key: str) -> str:
    """Map a Python-friendly attribute name to its HTML form.

    * A single trailing underscore is stripped so Python keywords can be used
      (``class_`` -> ``class``, ``for_`` -> ``for``, ``async_`` -> ``async``).
    * Remaining underscores become hyphens (``hx_get`` -> ``hx-get``,
      ``data_bs_toggle`` -> ``data-bs-toggle``, ``aria_label`` -> ``aria-label``).

    To emit an attribute name that must keep underscores or other characters,
    pass it via a literal dict (see :meth:`Element.__call__`).
    """
    if key.endswith("_"):
        key = key[:-1]
    return key.replace("_", "-")


def classnames(*values: Any) -> str:
    """Compose a CSS class string from mixed inputs (clsx/classnames-style).

    Accepts strings, iterables of strings, and mappings ``{class: truthy}``.
    Falsy items are dropped; duplicates are removed preserving first-seen order.

        classnames("btn", ["btn-sm", None], {"active": is_active})
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        token = token.strip()
        if token and token not in seen:
            seen.add(token)
            out.append(token)

    def walk(value: Any) -> None:
        if value is None or value is False or value is True or value == "":
            return
        if isinstance(value, str):
            for token in value.split():
                add(token)
        elif isinstance(value, Mapping):
            for key, cond in value.items():
                if cond:
                    walk(key)
        elif isinstance(value, Iterable):
            for item in value:
                walk(item)
        else:
            walk(str(value))

    for value in values:
        walk(value)
    return " ".join(out)


def _render_style(value: Any) -> str:
    if isinstance(value, Mapping):
        return ";".join(
            f"{_normalise_key(str(k))}:{v}" for k, v in value.items() if v is not None
        )
    return str(value)


def _format_attr(key: str, value: Any) -> str | None:
    """Render a single ``key=value`` attribute, or ``None`` to omit it."""
    if value is None or value is False:
        return None
    if value is True:
        return key
    if key == "class":
        rendered = classnames(value)
        if not rendered:
            return None
        value = rendered
    elif key == "style":
        value = _render_style(value)
    # conditional_escape respects SafeString / __html__ and escapes the rest.
    return f'{key}="{conditional_escape(str(value) if not hasattr(value, "__html__") else value)}"'


def attrs_to_html(attrs: Mapping[str, Any]) -> str:
    """Render an ordered attribute mapping to an HTML attribute string.

    Leading space is included when non-empty so callers can splat it directly
    after the tag name.
    """
    parts: list[str] = []
    for key, value in attrs.items():
        rendered = _format_attr(key, value)
        if rendered is not None:
            parts.append(rendered)
    return (" " + " ".join(parts)) if parts else ""


def _merge_attrs(
    base: dict[str, Any], literal: Mapping[str, Any] | None, kwargs: Mapping[str, Any]
) -> dict[str, Any]:
    merged = dict(base)
    if literal:
        # Literal dict keys are used verbatim (no normalisation).
        for key, value in literal.items():
            _merge_one(merged, key, value)
    for key, value in kwargs.items():
        _merge_one(merged, _normalise_key(key), value)
    return merged


def _merge_one(target: dict[str, Any], key: str, value: Any) -> None:
    """Merge a single attribute, combining ``class`` values additively."""
    if key == "class" and key in target and target[key] not in (None, "", False):
        target[key] = classnames(target[key], value)
    else:
        target[key] = value


class Node:
    """Base for anything that renders to HTML via :func:`render`."""

    __slots__ = ()

    def __html__(self) -> str:  # Django / markupsafe interop: nodes are "safe".
        return render(self)

    def __str__(self) -> str:
        return render(self)


class Element(Node):
    """A normal (non-void) HTML element.

    Build with attributes via ``__call__`` and children via ``__getitem__``::

        div(class_="card")[h1["Title"], p["Body"]]

    Both operations return new elements, so partial application is safe::

        card = div(class_="card")
        card[body_a]   # independent of
        card[body_b]
    """

    __slots__ = ("_name", "_attrs", "_children")

    def __init__(
        self,
        name: str,
        attrs: dict[str, Any] | None = None,
        children: tuple[Any, ...] = (),
    ) -> None:
        self._name = name
        self._attrs = attrs or {}
        self._children = children

    def __call__(
        self, _attrs: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> Element:
        return Element(
            self._name,
            _merge_attrs(self._attrs, _attrs, kwargs),
            self._children,
        )

    def __getitem__(self, children: Any) -> Element:
        if not isinstance(children, tuple):
            children = (children,)
        return Element(self._name, self._attrs, children)

    def _render_into(self, out: list[str]) -> None:
        out.append("<")
        out.append(self._name)
        out.append(attrs_to_html(self._attrs))
        out.append(">")
        for child in self._children:
            _render_child(child, out)
        out.append("</")
        out.append(self._name)
        out.append(">")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Element {self._name} attrs={self._attrs!r} children={len(self._children)}>"


class VoidElement(Element):
    """A void HTML element (``<br>``, ``<img>``, ``<input>`` ...). No children."""

    __slots__ = ()

    def __getitem__(self, children: Any) -> VoidElement:  # pragma: no cover - guard
        raise TypeError(f"<{self._name}> is a void element and cannot have children")

    def __call__(
        self, _attrs: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> VoidElement:
        return VoidElement(self._name, _merge_attrs(self._attrs, _attrs, kwargs))

    def _render_into(self, out: list[str]) -> None:
        out.append("<")
        out.append(self._name)
        out.append(attrs_to_html(self._attrs))
        out.append(">")


class Fragment(Node):
    """A group of children with no wrapping element.

    Use the ``fragment`` singleton::

        fragment[header, main, footer]
    """

    __slots__ = ("_children",)

    def __init__(self, children: tuple[Any, ...] = ()) -> None:
        self._children = children

    def __getitem__(self, children: Any) -> Fragment:
        if not isinstance(children, tuple):
            children = (children,)
        return Fragment(children)

    def __call__(self, *children: Any) -> Fragment:
        return Fragment(tuple(children))

    def _render_into(self, out: list[str]) -> None:
        for child in self._children:
            _render_child(child, out)


fragment = Fragment()


def _render_child(child: Any, out: list[str]) -> None:
    """Append the HTML of a single node to ``out`` (see module docstring)."""
    if child is None or child is True or child is False:
        return
    if isinstance(child, str):
        # SafeString is a str subclass; conditional_escape passes it through.
        out.append(conditional_escape(child))
        return
    if isinstance(child, (Element, Fragment)):
        child._render_into(out)
        return
    if isinstance(child, (int, float, Decimal)):
        out.append(str(child))
        return
    if hasattr(child, "_render_into"):  # other Node subclasses
        child._render_into(out)
        return
    if hasattr(child, "__html__"):  # Django SafeString-alikes / other safe HTML
        out.append(child.__html__())
        return
    if isinstance(child, Mapping):
        # Guard against accidentally passing a context/props dict as a child.
        raise TypeError(f"Cannot render mapping as a child node: {child!r}")
    if isinstance(child, Iterable):
        for item in child:
            _render_child(item, out)
        return
    out.append(conditional_escape(str(child)))


def render(node: Any) -> SafeString:
    """Render any node to a ``SafeString`` of HTML."""
    out: list[str] = []
    _render_child(node, out)
    # Safe by construction: every text/attribute value passed through
    # conditional_escape during assembly (see _render_child / _format_attr).
    return mark_safe("".join(out))  # nosec B703 B308


def raw(html: str) -> SafeString:
    """Mark a trusted HTML string as safe (alias for Django ``mark_safe``).

    Only use on HTML you control or that has already been sanitised.
    """
    return mark_safe(html)  # nosec B703 B308


# ``safe`` reads well at call sites that mean "this is already-safe HTML".
safe = raw
