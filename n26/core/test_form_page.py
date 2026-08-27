"""What a form screen's heading must carry.

No database: a component is a template and a set of props, and everything
claimed here is decided before a request exists. The wrapper draws
c-n26.page-header inside itself, so the claim under test is that a form page's
heading is a page heading — the trail, the mark, the control beside the title
and the page's own actions all reach it — and that nothing arrives there by
accident.

That last one is the failure worth pinning. A slot the wrapper does not declare
is not empty when nobody fills it: it resolves to whatever the enclosing scope
happens to hold under that name, so an undeclared `trailing` would draw
something the page never asked for, on a page that still serves 200.
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


class TestTheHeadingIsAPageHeading:
    """Everything c-n26.page-header takes, a form page can hand it."""

    def test_a_control_can_sit_beside_the_title(self):
        """The switcher case: a control about the thing the title names, on
        the title's line."""
        html = render(
            '<c-n26.form-page action="/gangs/1/skills/" title="Doug">'
            '<c-slot name="trailing"><a href="/others/">Switch</a></c-slot>'
            "</c-n26.form-page>"
        )

        assert 'href="/others/"' in html
        # Beside the title rather than after the whole heading: same row,
        # which is the group page-header draws for it.
        assert html.index("Doug") < html.index('href="/others/"')
        assert "flex items-center gap-2" in html

    def test_slot_markup_survives_the_forwarding(self):
        """Handed on as a slot, not written into an attribute — an attribute
        is escaped, and a switcher passed that way would print as source."""
        html = render(
            '<c-n26.form-page action="/x/" title="Doug">'
            '<c-slot name="trailing"><span class="switcher">go</span></c-slot>'
            "</c-n26.form-page>"
        )

        assert '<span class="switcher">go</span>' in html
        assert "&lt;span" not in html

    def test_a_mark_can_sit_before_the_title(self):
        html = render(
            '<c-n26.form-page action="/x/" title="Laagerbonds">'
            '<c-slot name="leading"><i class="swatch"></i></c-slot>'
            "</c-n26.form-page>"
        )

        heading = html[html.index("<h1") : html.index("</h1>")]
        assert '<i class="swatch">' in heading

    def test_the_page_s_own_controls_go_by_the_heading(self):
        """`header_actions`, not `actions`: the wrapper's `actions` is the
        footer's, beside the submit. Two different places, so two names."""
        html = render(
            '<c-n26.form-page action="/x/" title="Print" submit_label="Print">'
            '<c-slot name="header_actions"><a href="/help/">Help</a></c-slot>'
            '<c-slot name="actions"><button name="preview">Preview</button></c-slot>'
            "</c-n26.form-page>"
        )

        assert html.index('href="/help/"') < html.index("Preview")
        # The footer's rule is above the pair and below the fields; the
        # header's controls are on the far side of it.
        assert html.index('href="/help/"') < html.index("border-t")


class TestNothingArrivesUninvited:
    """A heading draws what the page handed it and nothing else."""

    def test_a_page_that_fills_none_of_them_gets_a_bare_heading(self):
        html = render('<c-n26.form-page action="/x/" title="Doug" />')

        assert "Doug" in html
        assert "<a" not in html
        assert "flex items-center gap-2" not in html

    def test_a_variable_of_the_same_name_in_the_page_is_not_a_slot(self):
        """The undeclared-slot trap. A page holding `trailing` for its own
        reasons — a loop variable, a view's context — must not find it drawn
        beside this heading. Declaring the prop is what gives the unfilled
        case a real default of "" instead of the enclosing scope's value.
        """
        for name in ["trailing", "leading", "actions", "header_actions"]:
            html = render(
                '<c-n26.form-page action="/x/" title="Doug" />',
                **{name: "SMUGGLED"},
            )

            assert "SMUGGLED" not in html, f"`{name}` fell through from the page"
