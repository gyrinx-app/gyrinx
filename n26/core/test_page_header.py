"""How a page heading yields to its own controls.

No database: a component is a template and a set of props, and everything
claimed here is decided before a request exists. The heading's contract is
that the title keeps the first rows on a phone and the actions sit under
it — a wrapping row with min-w-0 lets a wide strip shrink the heading
beside it, and the name then reads as a second block under the numbers.
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
    """Actions sit under the heading rather than squeezing it."""

    def test_the_heading_is_a_column_until_there_is_room_beside_it(self):
        html = render(
            '<c-n26.page-header title="Hello, player">'
            '<c-slot name="actions"><a href="/gangs/new/">Create Gang</a></c-slot>'
            "</c-n26.page-header>"
        )

        heading = html[html.index("<h1") : html.index("</h1>")]
        before = html[: html.index("<h1")]
        # flex-col is what stacks: wrapping with min-w-0 lets the heading
        # shrink beside the actions and the name drops under them. sm:flex-row
        # gives the side-by-side layout back once there is room.
        assert (
            "flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-start "
            "sm:justify-between sm:gap-x-4"
        ) in before
        assert 'class="min-w-0 w-full sm:w-auto sm:flex-1"' in before
        assert "Hello, player" in heading
        assert html.index("Hello, player") < html.index("Create Gang")

    def test_a_gang_sheet_keeps_its_figures_under_the_name_and_type(self):
        """The wealth strip is wide enough that sharing a row with the
        heading pushes the name under the numbers. Source order is the
        phone's — name, type, then the figures — and flex-col is what
        keeps that order on the screen."""
        html = render(
            '<c-n26.page-header title="Ozostium\'s War Host">'
            '<c-slot name="lead">Outcast</c-slot>'
            '<c-slot name="actions"><span>1000¢</span></c-slot>'
            "</c-n26.page-header>"
        )

        assert html.index("Ozostium") < html.index("Outcast") < html.index("1000¢")
        assert (
            "flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-start "
            "sm:justify-between sm:gap-x-4"
        ) in html
        assert '<p class="flex items-center text-muted">' in html

    def test_whitespace_alone_does_not_draw_an_actions_row(self):
        """A slot written across several lines is still whitespace, and
        Django treats that as true. The row is w-full below sm, so an
        empty one is a blank band under the title."""
        html = render(
            '<c-n26.page-header title="Hello, player">'
            '<c-slot name="actions">\n  \n</c-slot>'
            "</c-n26.page-header>"
        )

        assert "Hello, player" in html
        assert "w-full shrink-0" not in html


class TestTheTitleKeepsItsControl:
    """A switcher after the name stays on the name's line. flex-wrap plus a
    block h1 put it on a line of its own under the heading, which then
    read as part of the type underneath."""

    def test_the_control_does_not_wrap_under_the_heading(self):
        html = render(
            '<c-n26.page-header title="Ozostium\'s War Host">'
            '<c-slot name="trailing"><button type="button">Switch</button></c-slot>'
            "</c-n26.page-header>"
        )

        group = html[html.index("<h1") - 80 : html.index("</h1>") + 80]
        assert "flex flex-nowrap items-start gap-2" in html
        assert "flex-wrap items-center gap-2" not in html
        assert 'class="min-w-0 text-2xl' in group
        assert "shrink-0" in html
        assert html.index("Ozostium") < html.index("Switch")


class TestTheTypeKeepsItsMark:
    """The badge sits after the type on the same line. An inline-block after
    a short word still wraps under it when the drawing is larger than the
    line — which is how a gang type's icon ended up on a row of its own."""

    def test_the_badge_is_held_on_the_text_s_line(self):
        html = render(
            '<c-n26.flair-link text="Outcast"><svg viewBox="0 0 24 24"></svg>'
            "</c-n26.flair-link>"
        )

        assert "inline-flex items-center whitespace-nowrap" in html
        assert "n26-icon-inline" in html
        assert "[--n26-icon-size:1em]" in html
        assert html.index("Outcast") < html.index("<svg")
