"""Sanitise stored SVG artwork before rendering it inline.

Both editions use this allowlist to remove scripts, event handlers, foreign
content and external references. Sanitise at rendering so policy changes
apply to existing uploads. Callers cache results using their source identity.

Keep bleach's correctly cased SVG output and rewrite only the root start tag.
HTML parser round-trips would lowercase viewBox and other SVG attributes.
"""

import re

import bleach

# Allow structural and presentation elements; exclude executable and embedded HTML content.
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

    Allowing arbitrary ``href`` on ``<use>`` would let stored artwork reference
    external resources (``<use href="https://…">``), causing clients to fetch
    third-party content when the inline icon renders. Restrict ``href`` to
    fragment-only references (``#id``) and otherwise fall back to the shared
    geometry/presentation allowlist.
    """
    if name == "href":
        return value.strip().startswith("#")
    return name in _USE_ALLOWED_ATTRS


# Exclude event handlers and style attributes. Keep IDs for local use, paint, clipPath
# and mask references; IDs in separate inline icons may still collide.
_PRESENTATION_ATTRS = [
    "id",
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
    # Preserve crispEdges so the browser does not blur pixel artwork.
    "shape-rendering",
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

# Remove script and style contents before bleach, which otherwise retains their text.
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|foreignObject)\b.*?</\1>", re.IGNORECASE | re.DOTALL
)

# Recolour child fills and strokes because they override the root currentColor.
_COLOR_ATTR_RE = re.compile(r'\b(fill|stroke)\s*=\s*"([^"]*)"', re.IGNORECASE)

# Restrict preserved colours to characters that cannot close attributes or open tags.
_COLOR_VALUE_RE = re.compile(r"^[#a-zA-Z0-9(),.%\s/-]+$")

# Validate rendering hints before writing them into the rebuilt root tag.
_SHAPE_RENDERING_VALUES = {
    "auto",
    "optimizespeed",
    "crispedges",
    "geometricprecision",
    "inherit",
}


def _is_local_paint_ref(value: str) -> bool:
    """True for ``url(#…)`` — a paint server defined in this same document.

    An external reference (``url(https://…)``) would make the client fetch
    third-party content when the inline artwork renders, so it is never kept,
    on either the monochrome or the colour-preserving path.
    """
    return value.startswith("url(#")


def _normalise_color(match):
    value = match.group(2).strip().lower()
    # Preserve "none" (intentionally unpainted) and same-document paint refs;
    # any concrete colour becomes currentColor.
    if value == "none" or _is_local_paint_ref(value):
        return match.group(0)
    return f'{match.group(1)}="currentColor"'


def _keep_color(match):
    """Preserve allowed colour values and local paint references.

    Replace external references and invalid colour values with currentColor.
    """
    value = match.group(2).strip()
    lowered = value.lower()
    if lowered == "none" or _is_local_paint_ref(lowered):
        return match.group(0)
    if lowered.startswith("url(") or not _COLOR_VALUE_RE.match(value):
        return f'{match.group(1)}="currentColor"'
    return match.group(0)


def _find_attr(attrs, name):
    """Case-insensitive attribute lookup; returns the value or ``None``."""
    lowered = name.lower()
    for key, value in attrs.items():
        if key.lower() == lowered:
            return value
    return None


def sanitize_inline_svg(
    raw: str,
    *,
    root_class: str = "",
    extra_classes: str = "",
    preserve_colour: bool = False,
) -> str:
    """Return sanitised inline SVG markup, or an empty string for unusable input.

    Remove unsafe markup and root width and height. Retain a supplied viewBox
    or derive one from intrinsic dimensions.
    The root is aria-hidden because adjacent text supplies the accessible name.
    By default colours become currentColor; preserve_colour retains valid badge
    colours under the same attribute allowlist.

    root_class and extra_classes supply classes on the rebuilt root tag. Stored
    classes cannot override them. Callers must omit artwork markup when the
    result is empty.
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

    # Recolour child fills and strokes unless preserving the palette; always reject external paint references.
    cleaned = _COLOR_ATTR_RE.sub(
        _keep_color if preserve_colour else _normalise_color, cleaned
    )

    match = _SVG_START_TAG_RE.search(cleaned)
    if not match:
        return ""

    attrs = dict(_ATTR_RE.findall(match.group(1)))

    # Use intrinsic dimensions when the source has no viewBox.
    view_box = _find_attr(attrs, "viewBox")
    if not view_box:
        try:
            w = float(str(_find_attr(attrs, "width")).replace("px", "").strip())
            h = float(str(_find_attr(attrs, "height")).replace("px", "").strip())
        except TypeError, ValueError:
            # Without a viewBox or usable dimensions, the artwork cannot be scaled.
            return ""
        view_box = f"0 0 {w:g} {h:g}"

    classes = root_class.split() + extra_classes.split()

    preserve = _find_attr(attrs, "preserveAspectRatio")

    # Preserve root rendering hints explicitly; the allowlist alone only retains child attributes.
    shape_rendering = _find_attr(attrs, "shape-rendering")
    if (
        shape_rendering
        and shape_rendering.strip().lower() not in _SHAPE_RENDERING_VALUES
    ):
        shape_rendering = None

    # Preserve a valid solid root fill only when retaining the palette.
    root_fill = "currentColor"
    if preserve_colour:
        source_fill = (_find_attr(attrs, "fill") or "").strip()
        if (
            source_fill
            and not source_fill.lower().startswith("url(")
            and _COLOR_VALUE_RE.match(source_fill)
        ):
            root_fill = source_fill

    # CSS controls size; rebuild classes and accessibility attributes independently of stored markup.
    parts = [
        f'xmlns="{_SVG_NS}"',
        f'viewBox="{view_box}"',
        f'fill="{root_fill}"',
        'role="img"',
        'aria-hidden="true"',
    ]
    if shape_rendering:
        parts.insert(2, f'shape-rendering="{shape_rendering.strip()}"')
    if classes:
        parts.insert(2, f'class="{" ".join(classes)}"')
    if preserve:
        parts.insert(2, f'preserveAspectRatio="{preserve}"')

    start_tag = f"<svg {' '.join(parts)}>"

    return start_tag + cleaned[match.end() :]
