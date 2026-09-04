"""How a radio card holds a long name and a badge.

No database: a card is a template and a set of props. wrap means a
sentence-long name and the pill after it stay inside the card: the
badge follows the last word, and does not hold the line open.
"""

from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler


def render(source: str, **context) -> str:
    """Compile a call site the way the template loader would, then render it.

    Cotton's `<c-…>` tags are rewritten by a loader, so a template built from a
    string never sees them. Running the compiler by hand is what lets a test
    write the call site it is testing.
    """
    return Template(CottonCompiler().process(source)).render(Context(context))


class TestAWrappedCardLetsTheNameBreak:
    """A kind card's name is a sentence. The badge follows the last word
    rather than holding the whole line open."""

    def test_a_sentence_and_a_pill_are_not_held_on_one_line(self):
        html = render(
            '<c-n26.radio-cards.card name="scope" value="gang" '
            'label="The gang carrying it and all models" '
            'description="Affects the gang." :wrap="True">'
            '<c-slot name="flair"><span>Deprecated</span></c-slot>'
            "</c-n26.radio-cards.card>"
        )

        title = html[html.index("The gang") : html.index("Affects the gang")]
        assert "whitespace-nowrap" not in title
        assert "truncate" not in title
        assert "Deprecated" in title

    def test_a_short_name_still_holds_its_badge_on_one_line(self):
        html = render(
            '<c-n26.radio-cards.card name="type" value="1" '
            'label="Escher (HoB)">'
            '<c-slot name="flair"><svg viewBox="0 0 24 24"></svg></c-slot>'
            "</c-n26.radio-cards.card>"
        )

        assert "whitespace-nowrap" in html
        assert "truncate" in html
        assert html.index("Escher") < html.index("<svg")


class TestTheGridGivesEachCardRoomToShrink:
    """A nowrap name must not widen the track past the card. min-w-0 on
    every child is what lets the card keep its border around its content.
    """

    def test_each_child_can_shrink_below_its_content(self):
        html = render(
            '<c-n26.radio-cards label="Who it reaches">'
            '<c-n26.radio-cards.card name="scope" value="gang" '
            'label="The gang carrying it and all models" />'
            "</c-n26.radio-cards>"
        )

        assert "[&>*]:min-w-0" in html
        assert "min-w-0" in html
