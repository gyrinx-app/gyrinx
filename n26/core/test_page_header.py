"""How a page heading yields to its own controls.

No database: a component is a template and a set of props, and everything
claimed here is decided before a request exists. The heading's contract is
that the title keeps the row on a phone and the actions wrap under it —
min-w-0 flex-1 at every width lets the words shrink beside the buttons,
and a greeting that wraps mid-name is the wrong thing to have shortened.
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


class TestTheTitleKeepsTheRowOnAPhone:
    """Actions wrap under the heading rather than squeezing it."""

    def test_the_title_takes_the_full_row_until_there_is_room_beside_it(self):
        html = render(
            '<c-n26.page-header title="Hello, player">'
            '<c-slot name="actions"><a href="/gangs/new/">Create Gang</a></c-slot>'
            "</c-n26.page-header>"
        )

        heading = html[html.index("<h1") : html.index("</h1>")]
        wrapper = html[: html.index("<h1")]
        # The last class list before the h1 is the title's column: basis-full
        # is what forces the wrap, and sm:flex-1 is what gives the slack back
        # once the row is wide enough to hold both. An un-prefixed flex-1
        # beside min-w-0 is the squeeze — the heading would share the row
        # and wrap mid-name rather than keeping it.
        assert 'class="min-w-0 basis-full sm:flex-1"' in wrapper
        assert "Hello, player" in heading
        assert html.index("Hello, player") < html.index("Create Gang")
