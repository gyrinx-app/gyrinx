"""The checkbox card posts its box, and React draws the same card over it."""

import json

import pytest
from bs4 import BeautifulSoup
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

from n26.core.templatetags.checkbox_card import checkbox_card_props


def render(source: str, **context) -> str:
    """Compile a call site the way the template loader would, then render it."""
    return Template(CottonCompiler().process(source)).render(Context(context))


def island(html: str):
    soup = BeautifulSoup(html, "html.parser")
    host = soup.select_one("[data-react-name='checkbox-card']")
    assert host is not None
    props = json.loads(soup.find(id=host["data-react-props"]).string)
    return host, props


def test_none_and_the_string_false_are_off():
    assert checkbox_card_props(
        name=None,
        value=None,
        checked="false",
        label=None,
        description=None,
        css_class=None,
    ) == {
        "name": "",
        "value": "",
        "checked": False,
        "label": "",
        "description": "",
        "className": "",
    }


def test_a_known_tick_and_an_empty_value_are_kept():
    assert checkbox_card_props(
        name="open",
        value="",
        checked=True,
        label="Goliath",
        description="D6",
        css_class="h-full",
    ) == {
        "name": "open",
        "value": "",
        "checked": True,
        "label": "Goliath",
        "description": "D6",
        "className": "h-full",
    }


def test_the_card_is_an_island_over_the_same_checkbox():
    html = render(
        '<c-n26.checkbox-card name="open" value="table-1" label="Goliath" '
        'description="D6" :checked="True" class="h-full" />'
    )
    host, props = island(html)
    box = host.find("input", attrs={"name": "open"})

    assert props == {
        "name": "open",
        "value": "table-1",
        "checked": True,
        "label": "Goliath",
        "description": "D6",
        "className": "h-full",
    }
    assert host.has_attr("data-react-fallback")
    assert box["value"] == "table-1"
    assert box.has_attr("checked")
    assert "h-full" in box.find_parent("div", class_="rounded-box")["class"]
    assert "border-accent" in box.find_parent("div", class_="rounded-box")["class"]
    assert host.find(attrs={"data-checkbox-body": True}) is None
    # The host is transparent to layout, so the card stays the grid's item.
    assert "contents" in host["class"]
    assert "x-data" not in html
    assert ":inert" not in html
    assert "@change" not in html


@pytest.mark.parametrize("static", [False, True])
def test_root_attributes_stay_on_the_card(static):
    flag = ' :static="True"' if static else ""
    html = render(
        f'<c-n26.checkbox-card{flag} name="open" value="1" label="L" '
        'id="pick" data-row="7" />'
    )
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find(id="pick")

    assert soup.select_one("[data-react-name='checkbox-card']") is None
    assert card["data-row"] == "7"
    assert card.find("input", attrs={"name": "open"}) is not None


@pytest.mark.parametrize(
    "inside",
    [
        '<input type="checkbox" name="extra" value="lasgun">',
        '<c-slot name="meta"><span>85¢</span></c-slot>',
    ],
)
def test_a_card_with_a_body_or_meta_keeps_its_alpine_toggle(inside):
    """React does not take server-drawn markup as children, so this card
    stays as it was: the body dims and goes inert while the box is clear."""
    html = render(
        '<c-n26.checkbox-card name="open" value="table-1" label="Goliath">'
        f"{inside}</c-n26.checkbox-card>"
    )

    assert 'data-react-name="checkbox-card"' not in html
    assert 'x-data="{ picked: false }"' in html
    assert '@change="picked = $event.target.checked"' in html
    if "extra" in inside:
        assert ':inert="!picked"' in html
    else:
        assert "85¢" in html


def test_a_label_is_text_in_the_props_and_the_fallback():
    label = '</script><img src=x onerror="alert(1)">'
    html = render(
        '<c-n26.checkbox-card name="open" value="1" label="{{ label }}" />',
        label=label,
    )
    soup = BeautifulSoup(html, "html.parser")
    host, props = island(html)

    assert props["label"] == label
    assert soup.find("img") is None
    assert label in host.get_text()


@pytest.mark.parametrize("static", [False, True])
def test_a_printed_false_is_clear_in_the_face_and_the_props(static):
    flag = ' :static="True"' if static else ""
    html = render(
        f'<c-n26.checkbox-card{flag} name="open" value="1" label="L" checked="false" />'
    )
    box = BeautifulSoup(html, "html.parser").find("input", attrs={"name": "open"})

    assert box.has_attr("checked") is False
    if not static:
        _host, props = island(html)
        assert props["checked"] is False


def test_a_plain_string_keeps_its_entities():
    """Only escaped template output is decoded. A :prop string is its text."""
    html = render(
        '<c-n26.checkbox-card name="open" value="1" :label="label" />',
        label="Fish &amp; chips",
    )
    _host, props = island(html)

    assert props["label"] == "Fish &amp; chips"


def test_static_draws_the_card_without_an_island():
    html = render(
        '<c-n26.checkbox-card :static="True" name="fighters" value="vex" '
        'label="Vex" :checked="True" class="h-full">'
        '<input type="checkbox" name="weapons" value="lasgun">'
        "</c-n26.checkbox-card>"
    )

    assert "data-react-name" not in html
    assert "x-data" not in html
    soup = BeautifulSoup(html, "html.parser")
    box = soup.find("input", attrs={"name": "fighters"})
    card = box.find_parent("div", class_="rounded-box")
    assert box["value"] == "vex"
    assert box.has_attr("checked")
    assert "h-full" in card["class"]
    assert "border-accent" in card["class"]
    body = soup.find("div", attrs={"data-checkbox-body": True})
    assert body.has_attr("inert") is False
    assert "opacity-50" not in body["class"]
    assert soup.find("input", attrs={"name": "weapons"}) is not None
