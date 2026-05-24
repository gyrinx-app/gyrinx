"""Sanitisation for admin-uploaded SVG house icons.

Uploaded SVGs are untrusted: they can carry ``<script>`` elements, ``on*``
event handlers, ``<foreignObject>`` HTML payloads and ``javascript:`` URLs.
Because house icons are rendered *inline* (so ``fill: currentColor`` can match
the surrounding text colour), we cannot lean on the browser treating them as an
opaque ``<img>``. We therefore sanitise the markup with an explicit SVG
allowlist before it is ever marked safe.

Sanitisation runs at render time (cached), not upload time, so tightening the
allowlist later re-secures content that is already stored.

Implementation note: ``bleach`` produces correctly-cased SVG markup (it
preserves ``viewBox`` and other camelCase attributes), so we keep its output
verbatim and only rewrite the root ``<svg>`` *start tag* via a bounded regex.
We avoid round-tripping through BeautifulSoup's ``html.parser``, which would
lowercase ``viewBox`` and the gradient/clipPath attributes and corrupt the icon.
"""

import re

import bleach

# Only structural/presentational SVG elements. Notably excludes <script>,
# <style>, <foreignObject>, <a> and anything that can execute or embed HTML.
SVG_ALLOWED_TAGS = {
    "svg",
    "g",
    "path",
    "circle",
    "ellipse",
    "rect",
    "line",
    "polyline",
    "polygon",
    "defs",
    "use",
    "symbol",
    "title",
    "desc",
    "linearGradient",
    "radialGradient",
    "stop",
    "clipPath",
    "mask",
}


def _use_attr_allowed(tag, name, value):
    """Attribute filter for ``<use>``: only same-document fragment ``href``.

    Allowing arbitrary ``href`` on ``<use>`` would let an uploaded icon
    reference external resources (``<use href="https://…">``), causing clients
    to fetch third-party content when the inline icon renders. Restrict ``href``
    to fragment-only references (``#id``) and otherwise fall back to the shared
    geometry/presentation allowlist.
    """
    if name == "href":
        return value.strip().startswith("#")
    return name in _USE_ALLOWED_ATTRS


# Geometry/presentation attributes only. bleach drops any attribute not listed
# here, which removes every ``on*`` event handler. ``style`` is deliberately
# omitted to avoid a CSS attack surface — icons colour themselves via fill.
_PRESENTATION_ATTRS = [
    "fill",
    "fill-rule",
    "fill-opacity",
    "clip-rule",
    "clip-path",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-dasharray",
    "stroke-opacity",
    "opacity",
    "transform",
    "class",
]

# Non-href attributes permitted on <use>; href is handled by _use_attr_allowed.
_USE_ALLOWED_ATTRS = _PRESENTATION_ATTRS + ["x", "y", "width", "height"]

SVG_ALLOWED_ATTRS = {
    "*": _PRESENTATION_ATTRS,
    "svg": _PRESENTATION_ATTRS
    + ["xmlns", "viewBox", "width", "height", "preserveAspectRatio"],
    "path": _PRESENTATION_ATTRS + ["d"],
    "rect": _PRESENTATION_ATTRS + ["x", "y", "width", "height", "rx", "ry"],
    "circle": _PRESENTATION_ATTRS + ["cx", "cy", "r"],
    "ellipse": _PRESENTATION_ATTRS + ["cx", "cy", "rx", "ry"],
    "line": _PRESENTATION_ATTRS + ["x1", "y1", "x2", "y2"],
    "polyline": _PRESENTATION_ATTRS + ["points"],
    "polygon": _PRESENTATION_ATTRS + ["points"],
    "use": _use_attr_allowed,
    "symbol": _PRESENTATION_ATTRS + ["viewBox"],
    "stop": _PRESENTATION_ATTRS + ["offset", "stop-color", "stop-opacity"],
    "linearGradient": _PRESENTATION_ATTRS
    + ["x1", "y1", "x2", "y2", "gradientUnits", "gradientTransform"],
    "radialGradient": _PRESENTATION_ATTRS
    + ["cx", "cy", "r", "fx", "fy", "gradientUnits", "gradientTransform"],
    "clipPath": _PRESENTATION_ATTRS + ["clipPathUnits"],
    "mask": _PRESENTATION_ATTRS + ["maskUnits", "x", "y", "width", "height"],
}

_SVG_START_TAG_RE = re.compile(r"<svg\b([^>]*)>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"')
_SVG_NS = "http://www.w3.org/2000/svg"

# bleach's strip=True removes the <script>/<style> *tags* but keeps their text
# content (inert, but ugly). Drop those elements wholesale before sanitising.
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|foreignObject)\b.*?</\1>", re.IGNORECASE | re.DOTALL
)


def _find_attr(attrs, name):
    """Case-insensitive attribute lookup; returns the value or ``None``."""
    lowered = name.lower()
    for key, value in attrs.items():
        if key.lower() == lowered:
            return value
    return None


def sanitize_house_icon_svg(raw: str, extra_classes: str = "") -> str:
    """Return inline-safe SVG markup for a house icon, or ``""`` if unusable.

    Strips scripts/event handlers/foreign content via a bleach allowlist, then
    normalises the root ``<svg>``: removes hardcoded ``width``/``height`` (so
    CSS sizing wins), guarantees a ``viewBox`` for correct scaling, applies
    ``fill="currentColor"`` so the icon matches surrounding text, and tags it
    ``class="house-icon"`` + ``aria-hidden="true"``.
    """
    if not raw:
        return ""

    raw = _SCRIPT_STYLE_RE.sub("", raw)

    cleaned = bleach.clean(
        raw,
        tags=SVG_ALLOWED_TAGS,
        attributes=SVG_ALLOWED_ATTRS,
        protocols=["http", "https"],
        strip=True,
        strip_comments=True,
    )

    match = _SVG_START_TAG_RE.search(cleaned)
    if not match:
        return ""

    attrs = dict(_ATTR_RE.findall(match.group(1)))

    # Resolve a viewBox: keep the source's if present, else synthesise one from
    # the intrinsic width/height so the icon still scales correctly.
    view_box = _find_attr(attrs, "viewBox")
    if not view_box:
        try:
            w = float(str(_find_attr(attrs, "width")).replace("px", "").strip())
            h = float(str(_find_attr(attrs, "height")).replace("px", "").strip())
        except (TypeError, ValueError):
            # No usable intrinsic size and no viewBox — can't scale reliably.
            return ""
        view_box = f"0 0 {w:g} {h:g}"

    classes = ["house-icon"]
    if extra_classes:
        classes.extend(extra_classes.split())

    preserve = _find_attr(attrs, "preserveAspectRatio")

    # Rebuild the root start tag with a curated attribute set. Width/height are
    # intentionally dropped (CSS controls size); fill/class/role/aria are set by
    # us so they can't be overridden by the upload.
    parts = [
        f'xmlns="{_SVG_NS}"',
        f'viewBox="{view_box}"',
        f'class="{" ".join(classes)}"',
        'fill="currentColor"',
        'role="img"',
        'aria-hidden="true"',
    ]
    if preserve:
        parts.insert(2, f'preserveAspectRatio="{preserve}"')

    start_tag = f"<svg {' '.join(parts)}>"

    return start_tag + cleaned[match.end() :]
