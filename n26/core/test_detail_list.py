"""How a detail-list value stays inside the sheet.

No database: a row is a template and a set of props. A list of pickables
is still one control, and that control must wrap rather than push the
page wider than the column it sits in. The kit button is whitespace-nowrap;
the override and the min-w-0 chain are what let the string break.
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


LONG = "Genestealer Cult Corrupted, Chaos Corrupted, Malstrain Corrupted"


class TestALongValueWrapsInsideTheControl:
    """A comma-separated list of picks is one control, and it wraps."""

    def test_a_linked_value_may_break_across_lines(self):
        html = render(
            f'<c-n26.detail-list.row label="Variant" value="{LONG}" href="/choose/" />'
        )

        assert LONG in html
        assert "whitespace-normal!" in html
        assert "min-w-0" in html
        assert "max-w-full" in html
        # The kit still writes nowrap; the important override is what wins.
        assert "whitespace-nowrap" in html

    def test_a_dialog_value_may_break_across_lines(self):
        html = render(
            f'<c-n26.detail-list.row label="Variant" value="{LONG}">'
            '<c-slot name="dialog"><p>picker</p></c-slot>'
            "</c-n26.detail-list.row>"
        )

        assert LONG in html
        assert "whitespace-normal!" in html
        assert "min-w-0" in html

    def test_a_settled_fact_may_also_wrap(self):
        html = render(
            f'<c-n26.detail-list.row label="Rules" value="{LONG}" :editable="False" />'
        )

        assert LONG in html
        assert "max-w-full" in html
        assert "min-w-0" in html
        # A fact is a span, not the kit button, so nowrap is only on the label.
        value = html[html.index("<dd") : html.index("</dd>")]
        assert "whitespace-nowrap" not in value


class TestTheListCanShrinkBelowItsContent:
    """A nowrap value must not set the list's min-content to the full string."""

    def test_the_list_and_each_row_can_shrink(self):
        html = render(
            "<c-n26.detail-list>"
            f'<c-n26.detail-list.row label="Variant" value="{LONG}" href="#" />'
            "</c-n26.detail-list>"
        )

        opening = html[: html.index("<dt")]
        assert "min-w-0 max-w-full flex-wrap" in opening
        assert 'class="flex min-w-0 max-w-full items-baseline' in html
