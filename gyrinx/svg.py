"""Sanitisation for stored SVG artwork that is drawn inline.

Platform-owned rather than an edition's: what is safe to put in a page is a
property of SVG and of the browser, not of any one game's content model. Both
editions store small pieces of artwork somebody typed or uploaded, and two
allowlists that drift apart is the one outcome nobody wants from a security
boundary.

Stored SVGs are untrusted: they can carry ``<script>`` elements, ``on*`` event
handlers, ``<foreignObject>`` HTML payloads and ``javascript:`` URLs. Artwork
that is drawn *inline* — so ``fill: currentColor`` can match the surrounding
text colour — cannot lean on the browser treating it as an opaque ``<img>``, so
the markup goes through an explicit SVG allowlist before it is ever marked safe.

Sanitisation runs at render time, not at save time, so tightening the allowlist
later re-secures content that is already stored. Callers cache the result; this
module does not, because what makes a good cache key depends on where the
markup came from.

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

    Allowing arbitrary ``href`` on ``<use>`` would let stored artwork reference
    external resources (``<use href="https://…">``), causing clients to fetch
    third-party content when the inline icon renders. Restrict ``href`` to
    fragment-only references (``#id``) and otherwise fall back to the shared
    geometry/presentation allowlist.
    """
    if name == "href":
        return value.strip().startswith("#")
    return name in _USE_ALLOWED_ATTRS


# Geometry/presentation attributes only. bleach drops any attribute not listed
# here, which removes every ``on*`` event handler. ``style`` is deliberately
# omitted to avoid a CSS attack surface — icons colour themselves via fill.
# ``id`` is allowed so internal references resolve (``<use href="#x">``,
# ``fill="url(#grad)"``, clipPath/mask targets); without it those refs would
# silently break. Ids from different icons can collide in the DOM, which is a
# cosmetic risk accepted for monochrome artwork of this size.
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
    # Pixel art needs "crispEdges" to survive, or the browser antialiases every
    # edge and a 24x24 drawing turns to mush. Purely a rendering hint.
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

# bleach's strip=True removes the <script>/<style> *tags* but keeps their text
# content (inert, but ugly). Drop those elements wholesale before sanitising.
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|foreignObject)\b.*?</\1>", re.IGNORECASE | re.DOTALL
)

# Rewrite explicit solid fill/stroke colours to currentColor so the icon matches
# the surrounding text colour (the feature's core requirement). Without this, a
# child element's hardcoded ``fill="#000000"`` would override the root's
# currentColor and the icon would render in its baked-in colour.
_COLOR_ATTR_RE = re.compile(r'\b(fill|stroke)\s*=\s*"([^"]*)"', re.IGNORECASE)

# What a fill/stroke may look like once we agree to keep it. Deliberately narrow:
# hex, rgb()/hsl() functions, and the CSS colour keywords are all covered by
# these characters, and nothing here can close an attribute or open a tag.
_COLOR_VALUE_RE = re.compile(r"^[#a-zA-Z0-9(),.%\s/-]+$")

# The rendering hints SVG defines. An allowlist rather than a pattern because
# the value is written straight back into the root tag.
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
    """Colour-preserving counterpart to ``_normalise_color``.

    Concrete colours stay exactly as the artist drew them. Only two things are
    rewritten: an external paint reference, and anything whose value does not
    look like a colour at all — both become ``currentColor``, so the artwork
    still draws rather than vanishing.
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
    """Return inline-safe SVG markup, or ``""`` if the input is unusable.

    Strips scripts/event handlers/foreign content via a bleach allowlist, then
    normalises the root ``<svg>``: removes hardcoded ``width``/``height`` (so
    CSS sizing wins), guarantees a ``viewBox`` for correct scaling, applies
    ``fill="currentColor"`` so the icon matches surrounding text, and marks it
    ``aria-hidden="true"`` — the artwork repeats a name the page already says.

    ``preserve_colour`` keeps the artwork's own palette instead of flattening it
    to the surrounding text colour. Colour is not a security property — the
    attribute allowlist is what holds the line, and ``style`` is not on it — so
    this only changes how the drawing looks. Use it where the artwork *is* the
    identity (a badge) rather than an icon that should read as text (a gang type
    icon, which must recolour to match the heading it sits in).

    ``root_class`` is the caller's own hook for styling the artwork it stores;
    ``extra_classes`` is per-call. Both land on the root tag, which is rebuilt
    from scratch, so nothing in the stored markup can override them.

    An empty return means "draw nothing": the input was blank, was not an SVG
    at all, or could not be scaled reliably. Callers must render no markup in
    that case rather than a placeholder — artwork nobody supplied should hold
    no space.
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

    # Recolour concrete fills/strokes to currentColor so the whole icon takes the
    # surrounding text colour (root fill alone doesn't cascade past child fills).
    # With preserve_colour the palette stays, but external paint refs still go.
    cleaned = _COLOR_ATTR_RE.sub(
        _keep_color if preserve_colour else _normalise_color, cleaned
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
        except TypeError, ValueError:
            # No usable intrinsic size and no viewBox — can't scale reliably.
            return ""
        view_box = f"0 0 {w:g} {h:g}"

    classes = root_class.split() + extra_classes.split()

    preserve = _find_attr(attrs, "preserveAspectRatio")

    # The root tag is rebuilt, so anything on it that the artwork needs has to be
    # carried across explicitly — being in the attribute allowlist only saves it
    # on child elements. "crispEdges" lives on the root of every pixel-art
    # drawing we have, which is why it kept disappearing.
    shape_rendering = _find_attr(attrs, "shape-rendering")
    if (
        shape_rendering
        and shape_rendering.strip().lower() not in _SHAPE_RENDERING_VALUES
    ):
        shape_rendering = None

    # Root fill: normally currentColor so the icon reads as text. When the
    # palette is being kept, the artwork's own root fill wins if it has one and
    # it looks like a colour.
    root_fill = "currentColor"
    if preserve_colour:
        source_fill = (_find_attr(attrs, "fill") or "").strip()
        if (
            source_fill
            and not source_fill.lower().startswith("url(")
            and _COLOR_VALUE_RE.match(source_fill)
        ):
            root_fill = source_fill

    # Rebuild the root start tag with a curated attribute set. Width/height are
    # intentionally dropped (CSS controls size); fill/class/role/aria are set
    # here so the stored markup cannot override them.
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
