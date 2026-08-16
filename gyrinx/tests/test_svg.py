"""Tests for the platform's inline-SVG sanitiser.

Both editions draw stored artwork inline, so what this rejects is the whole of
what stops a piece of authored artwork from running script in a reader's page.
"""

from gyrinx.svg import sanitize_inline_svg

SIMPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" '
    'viewBox="0 0 48 48"><path d="M10 10 L20 20" fill="#abc"/></svg>'
)


def test_empty_input_returns_empty():
    assert sanitize_inline_svg("") == ""
    assert sanitize_inline_svg(None) == ""


def test_non_svg_returns_empty():
    assert sanitize_inline_svg("<div>not an svg</div>") == ""


def test_simple_svg_is_normalised():
    out = sanitize_inline_svg(SIMPLE_SVG, root_class="house-icon")
    # Class, currentColor fill, accessibility attrs are injected.
    assert 'class="house-icon"' in out
    assert 'fill="currentColor"' in out
    assert 'aria-hidden="true"' in out
    assert 'role="img"' in out
    # The original path is preserved.
    assert 'd="M10 10 L20 20"' in out


def test_no_class_attribute_when_none_asked_for():
    # A caller that styles the artwork from its container should not be handed
    # an empty class it has to work around.
    out = sanitize_inline_svg(SIMPLE_SVG)
    assert "class=" not in out.split(">", 1)[0]


def test_hardcoded_width_height_stripped():
    out = sanitize_inline_svg(SIMPLE_SVG)
    # The root <svg> must not carry intrinsic width/height (CSS sizes it).
    root = out.split(">", 1)[0]
    assert "width=" not in root
    assert "height=" not in root


def test_viewbox_preserved_with_correct_casing():
    out = sanitize_inline_svg(SIMPLE_SVG)
    assert 'viewBox="0 0 48 48"' in out
    # Must not be lowercased (browsers fix it inline, but we keep it clean).
    assert "viewbox=" not in out


def test_viewbox_synthesised_from_dimensions_when_missing():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">'
        '<circle cx="5" cy="5" r="4"/></svg>'
    )
    out = sanitize_inline_svg(svg)
    assert 'viewBox="0 0 32 32"' in out


def test_unusable_svg_without_viewbox_or_dimensions_returns_empty():
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="5" cy="5" r="4"/></svg>'
    assert sanitize_inline_svg(svg) == ""


def test_script_element_removed():
    svg = '<svg viewBox="0 0 10 10"><script>alert(1)</script><path d="M0 0"/></svg>'
    out = sanitize_inline_svg(svg)
    assert "<script" not in out.lower()
    # The script's text content must not leak through either.
    assert "alert(1)" not in out


def test_event_handler_attributes_removed():
    svg = (
        '<svg viewBox="0 0 10 10"><rect x="1" y="1" width="2" height="2" '
        'onload="evil()" onclick="evil()"/></svg>'
    )
    out = sanitize_inline_svg(svg)
    assert "onload" not in out
    assert "onclick" not in out


def test_foreign_object_removed():
    svg = (
        '<svg viewBox="0 0 10 10"><foreignObject><img src="x" onerror="evil()">'
        '</foreignObject><path d="M0 0"/></svg>'
    )
    out = sanitize_inline_svg(svg)
    assert "foreignobject" not in out.lower()
    assert "onerror" not in out


def test_style_element_removed():
    svg = (
        '<svg viewBox="0 0 10 10"><style>* { fill: url(javascript:alert(1)); }'
        '</style><path d="M0 0"/></svg>'
    )
    out = sanitize_inline_svg(svg)
    assert "<style" not in out.lower()
    assert "javascript" not in out.lower()


def test_extra_classes_appended():
    out = sanitize_inline_svg(
        SIMPLE_SVG, root_class="house-icon", extra_classes="me-1 text-danger"
    )
    assert 'class="house-icon me-1 text-danger"' in out


def test_external_use_href_removed():
    # <use href="https://…"> would make clients fetch remote content inline.
    svg = (
        '<svg viewBox="0 0 10 10"><use href="https://evil.example/x.svg#i"/>'
        '<path d="M0 0"/></svg>'
    )
    out = sanitize_inline_svg(svg)
    assert "evil.example" not in out
    assert "href" not in out


def test_fragment_use_href_preserved():
    # Same-document fragment references are safe and kept.
    svg = '<svg viewBox="0 0 10 10"><use href="#p"/><path d="M0 0"/></svg>'
    out = sanitize_inline_svg(svg)
    assert 'href="#p"' in out


def test_solid_fills_recoloured_to_currentcolor():
    # Child elements with baked-in colours must be recoloured so the icon
    # matches the surrounding text (the feature's core requirement).
    svg = (
        '<svg viewBox="0 0 4 4"><rect x="0" y="0" width="1" height="1" '
        'fill="#000000"/><path d="M0 0" stroke="#ff0000"/></svg>'
    )
    out = sanitize_inline_svg(svg)
    assert "#000000" not in out
    assert "#ff0000" not in out
    assert 'fill="currentColor"' in out
    assert 'stroke="currentColor"' in out


def test_fill_none_and_url_refs_preserved_when_recolouring():
    svg = (
        '<svg viewBox="0 0 4 4"><rect x="0" y="0" width="2" height="2" '
        'fill="none"/><path d="M0 0" fill="url(#g)"/></svg>'
    )
    out = sanitize_inline_svg(svg)
    assert 'fill="none"' in out
    assert "url(#g)" in out


def test_id_preserved_for_internal_references():
    # Internal refs (gradients, <use>, clipPath) need the target's id to survive.
    svg = (
        '<svg viewBox="0 0 10 10"><defs>'
        '<linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient>'
        '</defs><rect x="0" y="0" width="10" height="10" fill="url(#g)" id="r"/></svg>'
    )
    out = sanitize_inline_svg(svg)
    assert 'id="g"' in out
    assert 'id="r"' in out
    assert 'fill="url(#g)"' in out


def test_gradient_camelcase_attributes_preserved():
    svg = (
        '<svg viewBox="0 0 2 2"><linearGradient gradientUnits="userSpaceOnUse">'
        '<stop offset="0" stop-color="#fff"/></linearGradient>'
        '<path d="M0 0"/></svg>'
    )
    out = sanitize_inline_svg(svg)
    assert 'gradientUnits="userSpaceOnUse"' in out


def test_root_tag_attributes_cannot_be_overridden_by_the_source():
    # The root start tag is rebuilt rather than patched, so artwork claiming its
    # own class, role or fill does not get to keep them.
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2" '
        'class="pwned" role="button" onload="evil()" fill="#123456">'
        '<path d="M0 0"/></svg>'
    )
    out = sanitize_inline_svg(svg, root_class="artwork")
    root = out.split(">", 1)[0]
    assert 'class="artwork"' in root
    assert "pwned" not in root
    assert 'role="img"' in root
    assert "button" not in root
    assert "onload" not in out


def test_animation_elements_that_can_set_attributes_are_dropped():
    # <animate> can rewrite any attribute of its target over time, which puts a
    # href or a fill back after the allowlist has taken it away.
    svg = (
        '<svg viewBox="0 0 2 2"><rect x="0" y="0" width="1" height="1">'
        '<animate attributeName="href" to="javascript:alert(1)"/></rect></svg>'
    )
    out = sanitize_inline_svg(svg)
    assert "animate" not in out.lower()
    assert "javascript" not in out.lower()


def test_anchor_elements_are_dropped():
    # <a> inside an SVG is a real, clickable link; an allowlisted icon must not
    # be able to navigate the reader anywhere.
    svg = (
        '<svg viewBox="0 0 2 2"><a href="https://evil.example">'
        '<path d="M0 0"/></a></svg>'
    )
    out = sanitize_inline_svg(svg)
    assert "evil.example" not in out
    assert "<a " not in out


def test_unclosed_script_tag_still_loses_the_script_element():
    # The regex that drops script wholesale needs a closing tag; bleach is the
    # boundary that catches what it misses.
    svg = '<svg viewBox="0 0 2 2"><script>alert(1)</svg>'
    out = sanitize_inline_svg(svg)
    assert "<script" not in out.lower()


# --- Keeping the artwork's own colours ---


COLOURED_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2" '
    'shape-rendering="crispEdges">'
    '<rect width="1" height="1" fill="#B1873F"/>'
    '<rect width="1" height="1" x="1" stroke="rebeccapurple" fill="none"/>'
    "</svg>"
)


def test_colours_are_flattened_by_default():
    out = sanitize_inline_svg(COLOURED_SVG)
    assert "#B1873F" not in out
    assert "rebeccapurple" not in out
    assert 'fill="currentColor"' in out


def test_preserve_colour_keeps_the_palette():
    out = sanitize_inline_svg(COLOURED_SVG, preserve_colour=True)
    assert 'fill="#B1873F"' in out
    assert 'stroke="rebeccapurple"' in out
    # "none" means deliberately unpainted and is not a colour to keep or drop.
    assert 'fill="none"' in out


def test_shape_rendering_survives_the_root_tag_rebuild():
    # The root tag is rebuilt from a curated list, so an attribute being in the
    # allowlist is not enough on its own — pixel art keeps its hard edges only
    # if this is carried across explicitly.
    assert 'shape-rendering="crispEdges"' in sanitize_inline_svg(COLOURED_SVG)
    assert 'shape-rendering="crispEdges"' in sanitize_inline_svg(
        COLOURED_SVG, preserve_colour=True
    )


def test_a_made_up_shape_rendering_value_is_dropped():
    svg = '<svg viewBox="0 0 2 2" shape-rendering="javascript:x"><path d="M0 0"/></svg>'
    assert "javascript" not in sanitize_inline_svg(svg)


def test_preserve_colour_still_refuses_an_external_paint_server():
    svg = (
        '<svg viewBox="0 0 2 2">'
        '<rect width="1" height="1" fill="url(https://evil.example/x#a)"/>'
        "</svg>"
    )
    out = sanitize_inline_svg(svg, preserve_colour=True)
    assert "evil.example" not in out


def test_preserve_colour_keeps_a_same_document_paint_server():
    svg = (
        '<svg viewBox="0 0 2 2"><defs><linearGradient id="g">'
        '<stop offset="0" stop-color="#fff"/></linearGradient></defs>'
        '<rect width="1" height="1" fill="url(#g)"/></svg>'
    )
    assert 'fill="url(#g)"' in sanitize_inline_svg(svg, preserve_colour=True)


def test_preserve_colour_does_not_reopen_the_script_hole():
    svg = (
        '<svg viewBox="0 0 2 2"><script>alert(1)</script>'
        '<rect width="1" height="1" fill="#abc" onclick="steal()"/></svg>'
    )
    out = sanitize_inline_svg(svg, preserve_colour=True)
    assert "<script" not in out.lower()
    assert "onclick" not in out.lower()
    assert 'fill="#abc"' in out
