"""Tests for the house-icon SVG sanitiser."""

from gyrinx.content.svg import sanitize_house_icon_svg

SIMPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" '
    'viewBox="0 0 48 48"><path d="M10 10 L20 20" fill="#abc"/></svg>'
)


def test_empty_input_returns_empty():
    assert sanitize_house_icon_svg("") == ""
    assert sanitize_house_icon_svg(None) == ""


def test_non_svg_returns_empty():
    assert sanitize_house_icon_svg("<div>not an svg</div>") == ""


def test_simple_svg_is_normalised():
    out = sanitize_house_icon_svg(SIMPLE_SVG)
    # Class, currentColor fill, accessibility attrs are injected.
    assert 'class="house-icon"' in out
    assert 'fill="currentColor"' in out
    assert 'aria-hidden="true"' in out
    assert 'role="img"' in out
    # The original path is preserved.
    assert 'd="M10 10 L20 20"' in out


def test_hardcoded_width_height_stripped():
    out = sanitize_house_icon_svg(SIMPLE_SVG)
    # The root <svg> must not carry intrinsic width/height (CSS sizes it).
    root = out.split(">", 1)[0]
    assert "width=" not in root
    assert "height=" not in root


def test_viewbox_preserved_with_correct_casing():
    out = sanitize_house_icon_svg(SIMPLE_SVG)
    assert 'viewBox="0 0 48 48"' in out
    # Must not be lowercased (browsers fix it inline, but we keep it clean).
    assert "viewbox=" not in out


def test_viewbox_synthesised_from_dimensions_when_missing():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32">'
        '<circle cx="5" cy="5" r="4"/></svg>'
    )
    out = sanitize_house_icon_svg(svg)
    assert 'viewBox="0 0 32 32"' in out


def test_unusable_svg_without_viewbox_or_dimensions_returns_empty():
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="5" cy="5" r="4"/></svg>'
    assert sanitize_house_icon_svg(svg) == ""


def test_script_element_removed():
    svg = '<svg viewBox="0 0 10 10"><script>alert(1)</script><path d="M0 0"/></svg>'
    out = sanitize_house_icon_svg(svg)
    assert "<script" not in out.lower()
    # The script's text content must not leak through either.
    assert "alert(1)" not in out


def test_event_handler_attributes_removed():
    svg = (
        '<svg viewBox="0 0 10 10"><rect x="1" y="1" width="2" height="2" '
        'onload="evil()" onclick="evil()"/></svg>'
    )
    out = sanitize_house_icon_svg(svg)
    assert "onload" not in out
    assert "onclick" not in out


def test_foreign_object_removed():
    svg = (
        '<svg viewBox="0 0 10 10"><foreignObject><img src="x" onerror="evil()">'
        '</foreignObject><path d="M0 0"/></svg>'
    )
    out = sanitize_house_icon_svg(svg)
    assert "foreignobject" not in out.lower()
    assert "onerror" not in out


def test_style_element_removed():
    svg = (
        '<svg viewBox="0 0 10 10"><style>* { fill: url(javascript:alert(1)); }'
        '</style><path d="M0 0"/></svg>'
    )
    out = sanitize_house_icon_svg(svg)
    assert "<style" not in out.lower()
    assert "javascript" not in out.lower()


def test_extra_classes_appended():
    out = sanitize_house_icon_svg(SIMPLE_SVG, extra_classes="me-1 text-danger")
    assert 'class="house-icon me-1 text-danger"' in out


def test_external_use_href_removed():
    # <use href="https://…"> would make clients fetch remote content inline.
    svg = (
        '<svg viewBox="0 0 10 10"><use href="https://evil.example/x.svg#i"/>'
        '<path d="M0 0"/></svg>'
    )
    out = sanitize_house_icon_svg(svg)
    assert "evil.example" not in out
    assert "href" not in out


def test_fragment_use_href_preserved():
    # Same-document fragment references are safe and kept.
    svg = '<svg viewBox="0 0 10 10"><use href="#p"/><path d="M0 0"/></svg>'
    out = sanitize_house_icon_svg(svg)
    assert 'href="#p"' in out


def test_id_preserved_for_internal_references():
    # Internal refs (gradients, <use>, clipPath) need the target's id to survive.
    svg = (
        '<svg viewBox="0 0 10 10"><defs>'
        '<linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient>'
        '</defs><rect x="0" y="0" width="10" height="10" fill="url(#g)" id="r"/></svg>'
    )
    out = sanitize_house_icon_svg(svg)
    assert 'id="g"' in out
    assert 'id="r"' in out
    assert 'fill="url(#g)"' in out


def test_gradient_camelcase_attributes_preserved():
    svg = (
        '<svg viewBox="0 0 2 2"><linearGradient gradientUnits="userSpaceOnUse">'
        '<stop offset="0" stop-color="#fff"/></linearGradient>'
        '<path d="M0 0"/></svg>'
    )
    out = sanitize_house_icon_svg(svg)
    assert 'gradientUnits="userSpaceOnUse"' in out
