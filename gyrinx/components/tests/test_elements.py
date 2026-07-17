"""Unit tests for the core rendering engine."""

from __future__ import annotations

import pytest
from django.utils.safestring import SafeString, mark_safe

from gyrinx.components import (
    Fragment,
    classnames,
    fragment,
    raw,
    render,
)
from gyrinx.components.elements import attrs_to_html
from gyrinx.components.tags import (
    a,
    br,
    div,
    i,
    img,
    input_,
    li,
    p,
    span,
    ul,
)


# --------------------------------------------------------------------------
# Basic rendering
# --------------------------------------------------------------------------


def test_empty_element():
    assert render(div) == "<div></div>"


def test_element_with_text_child():
    assert render(div["hello"]) == "<div>hello</div>"


def test_render_returns_safestring():
    assert isinstance(render(div["x"]), SafeString)


def test_nested_elements():
    assert (
        render(div[span["a"], span["b"]]) == "<div><span>a</span><span>b</span></div>"
    )


def test_attributes():
    assert render(a(href="/x")["link"]) == '<a href="/x">link</a>'


def test_class_underscore_maps_to_class():
    assert render(div(class_="card")) == '<div class="card"></div>'


def test_hyphenated_attributes():
    out = render(div(data_bs_toggle="modal", hx_get="/x", aria_label="Close"))
    assert 'data-bs-toggle="modal"' in out
    assert 'hx-get="/x"' in out
    assert 'aria-label="Close"' in out


def test_for_underscore_maps_to_for():
    assert render(div(for_="field")) == '<div for="field"></div>'


def test_literal_attr_dict_not_normalised():
    out = render(div({"data-x_y": "1", ":class": "z"}))
    assert 'data-x_y="1"' in out
    assert ':class="z"' in out


def test_boolean_attr_true_renders_bare():
    assert render(input_(disabled=True)) == "<input disabled>"


def test_boolean_attr_false_omitted():
    assert render(input_(disabled=False)) == "<input>"


def test_none_attr_omitted():
    assert render(div(id=None)) == "<div></div>"


# --------------------------------------------------------------------------
# Void elements
# --------------------------------------------------------------------------


def test_void_element_self_closes():
    assert render(br) == "<br>"
    assert render(img(src="/x.png", alt="x")) == '<img src="/x.png" alt="x">'


def test_void_element_rejects_children():
    with pytest.raises(TypeError):
        br["nope"]


# --------------------------------------------------------------------------
# Escaping / safety
# --------------------------------------------------------------------------


def test_text_is_escaped():
    assert render(div["<script>"]) == "<div>&lt;script&gt;</div>"


def test_attr_value_is_escaped():
    assert render(a(href='"><script>')) == '<a href="&quot;&gt;&lt;script&gt;"></a>'


def test_safe_string_child_not_escaped():
    assert render(div[mark_safe("<b>x</b>")]) == "<div><b>x</b></div>"


def test_raw_not_escaped():
    assert render(div[raw("<b>x</b>")]) == "<div><b>x</b></div>"


def test_element_child_not_double_escaped():
    # An element rendered inside another must not be re-escaped.
    assert render(div[p["<x>"]]) == "<div><p>&lt;x&gt;</p></div>"


def test_ampersand_in_text_escaped():
    assert render(span["Tom & Jerry"]) == "<span>Tom &amp; Jerry</span>"


# --------------------------------------------------------------------------
# Children handling
# --------------------------------------------------------------------------


def test_none_and_bool_children_skipped():
    assert render(div[None, "a", False, "b", True]) == "<div>ab</div>"


def test_number_children():
    assert render(span[42]) == "<span>42</span>"


def test_list_children_flattened():
    items = [li[x] for x in ("a", "b", "c")]
    assert render(ul[items]) == "<ul><li>a</li><li>b</li><li>c</li></ul>"


def test_generator_children():
    assert render(ul[(li[x] for x in "ab")]) == "<ul><li>a</li><li>b</li></ul>"


def test_conditional_child_pattern():
    show = False
    assert render(div[show and span["hidden"]]) == "<div></div>"


def test_mapping_child_rejected():
    with pytest.raises(TypeError):
        render(div[{"a": 1}])


# --------------------------------------------------------------------------
# Fragments
# --------------------------------------------------------------------------


def test_fragment_has_no_wrapper():
    assert render(fragment[span["a"], span["b"]]) == "<span>a</span><span>b</span>"


def test_fragment_call_form():
    assert render(Fragment()(span["a"], span["b"])) == "<span>a</span><span>b</span>"


# --------------------------------------------------------------------------
# Immutability / partial application
# --------------------------------------------------------------------------


def test_call_returns_new_element():
    base = div(class_="a")
    b = base(id="x")
    assert render(base) == '<div class="a"></div>'
    assert render(b) == '<div class="a" id="x"></div>'


def test_getitem_returns_new_element():
    base = div(class_="a")
    filled = base["hi"]
    assert render(base) == '<div class="a"></div>'
    assert render(filled) == '<div class="a">hi</div>'


def test_class_merges_additively_across_calls():
    assert render(div(class_="a")(class_="b")) == '<div class="a b"></div>'


def test_attrs_and_children_compose_either_order():
    assert render(div(class_="a")["x"]) == render(div["x"](class_="a"))


# --------------------------------------------------------------------------
# classnames / clsx
# --------------------------------------------------------------------------


def test_classnames_strings():
    assert classnames("btn", "btn-sm") == "btn btn-sm"


def test_classnames_drops_falsy():
    assert classnames("btn", None, False, "", "btn-lg") == "btn btn-lg"


def test_classnames_list():
    assert classnames(["btn", "btn-sm"], "active") == "btn btn-sm active"


def test_classnames_dict():
    assert classnames("btn", {"active": True, "disabled": False}) == "btn active"


def test_classnames_dedupes_preserving_order():
    assert classnames("btn", "btn", "btn-sm") == "btn btn-sm"


def test_class_attr_accepts_list():
    assert render(div(class_=["a", None, "b"])) == '<div class="a b"></div>'


def test_class_attr_accepts_dict():
    assert render(div(class_={"a": True, "b": False})) == '<div class="a"></div>'


def test_empty_class_omitted():
    assert render(div(class_=[None, False])) == "<div></div>"


# --------------------------------------------------------------------------
# style attribute
# --------------------------------------------------------------------------


def test_style_dict():
    assert render(div(style={"color": "red", "font_size": "1rem"})) == (
        '<div style="color:red;font-size:1rem"></div>'
    )


# --------------------------------------------------------------------------
# attrs_to_html helper
# --------------------------------------------------------------------------


def test_attrs_to_html_leading_space():
    assert attrs_to_html({"id": "x"}) == ' id="x"'


def test_attrs_to_html_empty():
    assert attrs_to_html({}) == ""


# --------------------------------------------------------------------------
# __html__ / __str__ interop
# --------------------------------------------------------------------------


def test_element_str_is_html():
    assert str(div["x"]) == "<div>x</div>"


def test_element_html_method():
    assert div["x"].__html__() == "<div>x</div>"


def test_icon_composition_example():
    out = render(a(class_="btn btn-primary", href="/x")[i(class_="bi-pencil"), " Edit"])
    assert (
        out == '<a class="btn btn-primary" href="/x"><i class="bi-pencil"></i> Edit</a>'
    )
