"""Form-page headings forward declared slots to the page header.

Undeclared slots can resolve to enclosing context variables. Empty heading slots
must instead use their declared defaults.
"""

from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler


def render(source: str, **context) -> str:
    """Compile Cotton tags before rendering an inline template."""
    return Template(CottonCompiler().process(source)).render(Context(context))


class TestTheHeadingIsAPageHeading:
    """Form pages forward heading content and separate header actions from footer
    actions.
    """

    def test_a_control_can_sit_beside_the_title(self):
        html = render(
            '<c-n26.form-page action="/gangs/1/skills/" title="Doug">'
            '<c-slot name="trailing"><a href="/others/">Switch</a></c-slot>'
            "</c-n26.form-page>"
        )

        assert 'href="/others/"' in html
        assert html.index("Doug") < html.index('href="/others/"')

    def test_slot_markup_survives_the_forwarding(self):
        """Forward markup through a slot so it is rendered rather than escaped as an
        attribute.
        """
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
        """header_actions belongs beside the heading; actions belongs beside the
        footer submit button.
        """
        html = render(
            '<c-n26.form-page action="/x/" title="Print" submit_label="Print">'
            '<c-slot name="header_actions"><a href="/help/">Help</a></c-slot>'
            '<c-slot name="actions"><button name="preview">Preview</button></c-slot>'
            "</c-n26.form-page>"
        )

        assert html.index('href="/help/"') < html.index("Preview")


class TestNothingArrivesUninvited:
    """Empty heading slots must not inherit similarly named enclosing context
    variables.
    """

    def test_a_page_that_fills_none_of_them_gets_a_bare_heading(self):
        html = render('<c-n26.form-page action="/x/" title="Doug" />')

        assert "Doug" in html
        assert "<a" not in html

    def test_a_variable_of_the_same_name_in_the_page_is_not_a_slot(self):
        """Declare empty slot defaults so surrounding view or loop variables cannot
        appear in the heading.
        """
        for name in ["trailing", "leading", "actions", "header_actions"]:
            html = render(
                '<c-n26.form-page action="/x/" title="Doug" />',
                **{name: "SMUGGLED"},
            )

            assert "SMUGGLED" not in html, f"`{name}` fell through from the page"
