"""HTML tag factories for the component system.

Each name here is a ready-to-use :class:`~gyrinx.components.elements.Element`
(or :class:`~gyrinx.components.elements.VoidElement` for void tags)::

    from gyrinx.components.tags import div, a, i

    div(class_="card")[a(href="/x")["link"], i(class_="bi-star")]

Because ``class`` / ``for`` / ``async`` / ``del`` are Python keywords, use the
trailing-underscore form (``class_``, ``for_`` ...). Hyphenated attributes use
underscores (``hx_get`` -> ``hx-get``); see ``elements._normalise_key``.
"""

from __future__ import annotations

from .elements import VOID_ELEMENTS, Element, VoidElement

# Non-void elements we use across the app. Add here as needed.
_ELEMENT_TAGS = [
    "a",
    "abbr",
    "address",
    "article",
    "aside",
    "b",
    "blockquote",
    "body",
    "button",
    "caption",
    "cite",
    "code",
    "colgroup",
    "datalist",
    "dd",
    "details",
    "dialog",
    "div",
    "dl",
    "dt",
    "em",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "head",
    "header",
    "html",
    "i",
    "iframe",
    "kbd",
    "label",
    "legend",
    "li",
    "main",
    "mark",
    "menu",
    "nav",
    "noscript",
    "ol",
    "optgroup",
    "option",
    "output",
    "p",
    "picture",
    "pre",
    "s",
    "section",
    "select",
    "small",
    "span",
    "strong",
    "style",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "template",
    "textarea",
    "tfoot",
    "th",
    "thead",
    "time",
    "title",
    "tr",
    "u",
    "ul",
    "script",
    "svg",
    "path",
    "g",
    "use",
    "symbol",
]

# Python-keyword tag names get a trailing underscore (``del_``, ``object_``).
_KEYWORD_ALIASES = {
    "del_": "del",
    "input_": "input",
    "map_": "map",
    "object_": "object",
}

__all__ = list(_ELEMENT_TAGS) + list(VOID_ELEMENTS) + list(_KEYWORD_ALIASES)

_globals = globals()

for _name in _ELEMENT_TAGS:
    _globals[_name] = Element(_name)

for _name in VOID_ELEMENTS:
    _globals[_name] = VoidElement(_name)

for _alias, _real in _KEYWORD_ALIASES.items():
    _globals[_alias] = (VoidElement if _real in VOID_ELEMENTS else Element)(_real)

del _name, _alias, _real, _globals
