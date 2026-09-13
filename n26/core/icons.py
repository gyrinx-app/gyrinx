"""Resolve n26 icon names to trusted inline SVG bodies.

General-purpose icons come from the pinned Lucide package. The package stays on
the server: each response contains only the drawings its templates render, with
no icon font, sprite, stylesheet or JavaScript bundle sent to the browser.

The Cotton component owns the SVG element's presentation and accessibility.
This module supplies only the package-controlled child geometry, the canvas it
was drawn on, and whether the closed set of brand marks is filled.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from io import BytesIO
from zipfile import ZipFile

import lucide
from defusedxml import ElementTree
from django.utils.html import format_html_join
from django.utils.safestring import SafeString, mark_safe

from n26.core.brand_icons import BRAND_ICONS

DEFAULT_VIEWBOX = "0 0 24 24"

# Keep dynamic and stored names working while templates move to Lucide's names.
ALIASES: dict[str, str] = {
    "arrow-top-right-on-square": "external-link",
    "arrow-up-tray": "upload",
    "arrow-uturn-left": "undo-2",
    "bars-3": "menu",
    "check-circle": "circle-check",
    "cog-6-tooth": "settings",
    "computer-desktop": "monitor",
    "dice": "dice-6",
    "exclamation-triangle": "triangle-alert",
    "information-circle": "info",
    "magnifying-glass": "search",
    "photo": "image",
    "question-mark-circle": "circle-question-mark",
    "user-group": "users",
    "x-mark": "x",
}

_ALLOWED_TAGS = frozenset(
    {"circle", "ellipse", "line", "path", "polygon", "polyline", "rect"}
)
_ALLOWED_ATTRIBUTES = frozenset(
    {
        "cx",
        "cy",
        "d",
        "fill",
        "height",
        "points",
        "r",
        "rx",
        "ry",
        "width",
        "x",
        "x1",
        "x2",
        "y",
        "y1",
        "y2",
    }
)


@dataclass(frozen=True)
class Icon:
    """A resolved drawing ready for the n26 icon component."""

    name: str
    body: SafeString
    viewbox: str = DEFAULT_VIEWBOX
    solid: bool = False
    brand: bool = False


@cache
def _lucide_archive() -> ZipFile:
    """Open the in-memory package archive for process-lifetime reuse."""

    archive = files(lucide).joinpath("lucide.zip").read_bytes()
    return ZipFile(BytesIO(archive))


@cache
def _lucide_names() -> tuple[str, ...]:
    """Read the archive index without inflating every drawing."""

    return tuple(
        sorted(
            filename.removesuffix(".svg")
            for filename in _lucide_archive().namelist()
            if filename.endswith(".svg")
        )
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@cache
def _lucide_body(name: str) -> SafeString:
    """Extract and validate child geometry from a packaged Lucide SVG."""

    root = ElementTree.fromstring(_lucide_archive().read(f"{name}.svg"))  # noqa: S314
    if _local_name(root.tag) != "svg" or root.attrib.get("viewBox") != DEFAULT_VIEWBOX:
        raise ValueError(f"Lucide icon {name!r} has an unexpected SVG canvas")

    for node in root:
        for descendant in node.iter():
            descendant.tag = _local_name(descendant.tag)
            if descendant.tag not in _ALLOWED_TAGS:
                raise ValueError(
                    f"Lucide icon {name!r} contains unsupported {descendant.tag!r} geometry"
                )
            unsupported = set(descendant.keys()) - _ALLOWED_ATTRIBUTES
            if unsupported:
                raise ValueError(
                    f"Lucide icon {name!r} contains unsupported attributes: "
                    f"{', '.join(sorted(unsupported))}"
                )
            if descendant.attrib.get("fill") not in {None, "currentColor"}:
                raise ValueError(f"Lucide icon {name!r} contains an unsupported fill")

    return mark_safe(  # nosec B308 B703 - strict geometry allowlist, XML-escaped
        "".join(
            ElementTree.tostring(node, encoding="unicode", short_empty_elements=True)
            for node in root
        )
    )


@cache
def resolve(name: str) -> Icon:
    """Return a Lucide or approved brand icon, accepting legacy n26 aliases."""

    canonical = ALIASES.get(name, name)
    if brand := BRAND_ICONS.get(canonical):
        viewbox, paths = brand
        body = format_html_join("", '<path d="{}"></path>', ((path,) for path in paths))
        return Icon(canonical, body, viewbox=viewbox, solid=True, brand=True)

    if canonical not in _lucide_names():
        raise KeyError(
            f"no icon {name!r}; choose a Lucide name from /n26/design/c/icon/"
        )
    return Icon(canonical, _lucide_body(canonical))


def names() -> tuple[str, ...]:
    """Return every canonical icon name shown in the design library."""

    return (*_lucide_names(), *BRAND_ICONS)
