"""The checkbox card posts its box, and React draws the same card over it."""

import json

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
        'description="D6" :checked="True" class="h-full">'
        '<input type="checkbox" name="extra" value="lasgun" checked>'
        "</c-n26.checkbox-card>"
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
    nested = host.find("input", attrs={"name": "extra"})
    assert nested["value"] == "lasgun"
    assert (
        nested.find_parent("div", attrs={"data-checkbox-body": True}).has_attr("inert")
        is False
    )
    assert "x-data" not in html
    assert ":inert" not in html
    assert "@change" not in html


def test_an_unticked_card_dims_its_body_without_making_it_inert():
    html = render(
        '<c-n26.checkbox-card name="open" value="table-1" label="Goliath">'
        "<span>Notes</span></c-n26.checkbox-card>"
    )
    host, props = island(html)
    body = host.find("div", attrs={"data-checkbox-body": True})

    assert props["checked"] is False
    assert "opacity-50" in body["class"]
    assert body.has_attr("inert") is False
    assert host.find("input").has_attr("checked") is False


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
