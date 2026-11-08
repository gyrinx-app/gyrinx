"""The semantic content carried by a radio card."""

from bs4 import BeautifulSoup
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler


def render(source: str, **context) -> str:
    """Compile Cotton tags before rendering an inline template."""
    return Template(CottonCompiler().process(source)).render(Context(context))


class TestACardCanCarryLinesOfDetail:
    """Render the body after the description inside the label so every detail line
    selects the radio card.
    """

    def test_the_body_is_drawn_after_the_description(self):
        html = render(
            '<c-n26.radio-cards.card name="type" value="1" '
            'label="Territory campaign" description="Gangs fight for Territory." '
            ':wrap="True">'
            '<span class="block">Territories change hands.</span>'
            "</c-n26.radio-cards.card>"
        )

        label = BeautifulSoup(html, "html.parser").find("label")
        assert label is not None
        words = " ".join(label.stripped_strings)
        assert words.index("Gangs fight for Territory.") < words.index(
            "Territories change hands."
        )
