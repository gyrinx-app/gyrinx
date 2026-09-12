"""Which slider a range menu draws, and with whose variables.

No database: a component is a template and a set of props. The menu draws
<c-n26.range-slider> from inside itself and chooses between one thumb and
two, and the choice has to be made where the slider reads its props — not
by an if block around them in the tag. Cotton reads a tag's attributes as
words: a block in attribute position turns `if`, `else` and `endif` into
attribute names on the slider's root element, and whichever branch was meant
to be left out is not.
"""

import re

from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler


def render(source: str) -> str:
    """Compile a call site the way the template loader would, then render it."""
    return Template(CottonCompiler().process(source)).render(Context({}))


def slider_root(html: str) -> str:
    return re.search(r"<div[^>]*n26-range-slider [^>]*>", html, re.S).group(0)


class TestOneThumbOrTwo:
    """`model` alone is a ceiling; `model_min` with `model_max` is a floor and
    a ceiling. The slider draws one input or two accordingly."""

    def test_a_ceiling_draws_one_thumb_bound_to_the_ceiling(self):
        html = render(
            '<c-n26.range-menu label="Price" model="cap" min="0" max="200" step="5" />'
        )

        assert html.count('type="range"') == 1
        assert ':value="cap"' in html
        assert "Minimum" not in html

    def test_a_floor_and_a_ceiling_draw_two_thumbs_bound_to_each(self):
        html = render(
            '<c-n26.range-menu label="Price" model_min="lo" model_max="hi" '
            'min="0" max="200" step="5" />'
        )

        assert html.count('type="range"') == 2
        assert ':value="lo"' in html
        assert ':value="hi"' in html


class TestNothingLeaksIntoTheSlider:
    """The slider's root carries the menu's attributes and nothing from the
    template that drew it."""

    def test_no_template_word_becomes_an_attribute(self):
        for call in (
            '<c-n26.range-menu label="Price" model="cap" min="0" max="200" />',
            '<c-n26.range-menu label="Price" model_min="lo" model_max="hi" '
            'min="0" max="200" />',
        ):
            root = slider_root(render(call))

            assert "{%" not in root and "{{" not in root
            assert not re.search(r"\s(if|else|endif|and)[\s>]", root), root
