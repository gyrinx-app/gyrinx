"""The filter menu posts its ticks, and React draws the same menu over the trigger."""

import json

from bs4 import BeautifulSoup
from django.template import Context, Template
from django.utils.safestring import mark_safe
from django_cotton.compiler_regex import CottonCompiler

from n26.core.templatetags.filter_menu import filter_menu_props


def render(source: str, **context) -> str:
    """Compile a call site the way the template loader would, then render it."""
    return Template(CottonCompiler().process(source)).render(Context(context))


def island(html: str):
    soup = BeautifulSoup(html, "html.parser")
    host = soup.select_one("[data-react-name='filter-menu']")
    assert host is not None
    props = json.loads(soup.find(id=host["data-react-props"]).string)
    return host, props


OPTIONS = [
    {"value": "house", "label": "House"},
    {"value": "kit", "label": "Kit & gear"},
]


def test_an_empty_selection_with_select_all_stays_empty_in_the_props():
    assert filter_menu_props(options=OPTIONS)["selectAll"] is True
    assert filter_menu_props(options=OPTIONS)["selected"] == []
    assert filter_menu_props(select_all="false")["selectAll"] is False
    assert filter_menu_props(select_all=None)["selectAll"] is True


def test_a_cotton_label_is_unescaped_once_and_the_width_is_pixels():
    props = filter_menu_props(
        label=mark_safe("Kit &amp; gear"),
        options=[{"value": "a", "label": mark_safe("A &amp; B")}],
        min_width="20rem",
        size="xs",
        align="end",
    )
    assert props["label"] == "Kit & gear"
    assert props["options"] == [{"value": "a", "label": "A & B"}]
    assert props["width"] == 320
    assert props["size"] == "xs"
    assert props["align"] == "end"


def test_the_menu_is_an_island_and_the_fallback_does_not_open():
    html = render(
        '<c-n26.filter-menu label="Category" name="category" :options="options" '
        'size="xs" @filter-apply="applied = $event.detail" />',
        options=OPTIONS,
    )
    host, props = island(html)
    assert props["name"] == "category"
    assert props["size"] == "xs"
    assert props["options"][1]["label"] == "Kit & gear"
    assert host.select("[x-data], [x-show], [x-model], [x-text]") == []
    button = host.find("button")
    assert button["aria-expanded"] == "false"
    assert "Category" in button.get_text()
    # The caller's listener sits outside the island, where Alpine still runs.
    assert host.parent["@filter-apply"] == "applied = $event.detail"
