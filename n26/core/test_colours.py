import pytest
from bs4 import BeautifulSoup
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

from n26.core.colours import GANG_COLOURS, palette_colour
from n26.core.templatetags.theme import css_color


@pytest.mark.parametrize(
    ("value", "drawn"),
    [
        ("red", "var(--color-red-500)"),
        ("accent", "var(--color-accent)"),
        ("#8d9900", "#8d9900"),
        ("oklch(0.7 0.1 200)", "oklch(0.7 0.1 200)"),
        ("var(--color-accent)", "var(--color-accent)"),
        ("", "transparent"),
    ],
)
def test_a_theme_name_or_a_colour_literal_is_drawn(value, drawn):
    assert css_color(value) == drawn


@pytest.mark.parametrize(
    "value",
    [
        "red; background-image: url(https://example.com/x)",
        "url(https://example.com/x)",
        "#fff; color: red",
        'red"',
        "red blue",
    ],
)
def test_anything_else_is_transparent(value):
    assert css_color(value) == "transparent"


def test_only_a_gang_colour_passes_the_palette():
    assert palette_colour("teal") == "teal"
    assert palette_colour("accent") == ""
    assert palette_colour("#8d9900") == ""


@pytest.mark.django_db
def test_the_colour_picker_offers_exactly_the_gang_colours():
    drawn = Template(CottonCompiler().process("<c-n26.colour-picker />")).render(
        Context({})
    )
    offered = [
        radio["value"]
        for radio in BeautifulSoup(drawn, "html.parser").find_all("input", type="radio")
        if radio["value"]
    ]
    assert offered == list(GANG_COLOURS)
