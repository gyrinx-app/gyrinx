"""The semantic content carried by a radio card."""

from bs4 import BeautifulSoup
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler


def render(source: str, **context) -> str:
    """Compile a call site the way the template loader would, then render it.

    Cotton's `<c-…>` tags are rewritten by a loader, so a template built from a
    string never sees them. Running the compiler by hand is what lets a test
    write the call site it is testing.
    """
    return Template(CottonCompiler().process(source)).render(Context(context))


class TestACardCanCarryLinesOfDetail:
    """An option that is a set of rules needs more than one line under its
    name. The body slot draws under the description, inside the label, so
    a click on any line still selects the card."""

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
