"""What the footer of a form must put in the HTML.

No database: a component is a template and a set of props, and everything
claimed here is decided before a request exists. The assertions are substrings
that can only be there if the behaviour worked — a way out that is a real link
rather than a control that posts, and an act that carries the colour of what it
does.
"""

import pytest
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


class TestThePair:
    """A form ends with the way out and the act, in that order."""

    def test_both_are_drawn_when_the_way_out_has_somewhere_to_lead(self):
        html = render(
            '<c-n26.form-actions submit_label="Hire" cancel_url="/gangs/1/hire/" />'
        )

        assert 'href="/gangs/1/hire/"' in html
        assert "Cancel" in html
        assert 'type="submit"' in html
        assert "Hire" in html

    def test_the_way_out_comes_first(self):
        """Right-aligned as a pair, the act last: a reader running down the
        fields meets the alternative on the way to the one they want, and
        buttons that swap places between screens have to be read before
        they are clicked."""
        html = render('<c-n26.form-actions submit_label="Save" cancel_url="/back/" />')

        assert html.index("Cancel") < html.index("Save")

    def test_the_way_out_never_posts(self):
        """Leaving is not a submission. Cancel is an anchor, so clicking it
        goes where it says rather than sending the form somewhere."""
        html = render('<c-n26.form-actions submit_label="Save" cancel_url="/back/" />')

        cancel = html[: html.index("Cancel")]
        assert cancel.rstrip().endswith(">")
        assert "<a" in cancel
        assert 'type="submit"' not in cancel


class TestWhatIsLeftOut:
    """Each half is drawn only when it has been given something to say."""

    def test_no_cancel_url_means_no_cancel(self):
        """A form with nowhere to go back to gets no way out rather than one
        leading somewhere arbitrary."""
        html = render('<c-n26.form-actions submit_label="Save changes" />')

        assert "Cancel" not in html
        assert "<a" not in html
        assert "Save changes" in html

    def test_no_submit_label_means_no_submit(self):
        html = render('<c-n26.form-actions cancel_url="/back/" />')

        assert 'type="submit"' not in html
        assert "Cancel" in html

    def test_the_way_out_can_be_worded_for_the_page(self):
        html = render(
            '<c-n26.form-actions submit_label="Import" cancel_url="/x/" cancel_label="Back to Ingest" />'
        )

        assert "Back to Ingest" in html
        assert "Cancel" not in html


class TestFurtherControls:
    """The rare form answering in more than one way keeps the frame: the
    way out still opens the row, and the form's own act still ends it."""

    def test_the_slot_is_drawn_between_the_way_out_and_the_act(self):
        html = render(
            '<c-n26.form-actions submit_label="Import" cancel_url="/x/">'
            '<c-ui.button type="submit" variant="default">Preview</c-ui.button>'
            "</c-n26.form-actions>"
        )

        assert html.index("Cancel") < html.index("Preview") < html.index("Import")


class TestTheFormPageFooter:
    """A page-sized form draws the same footer as a dialog does, because it
    is the same component with props filled in rather than a second one."""

    def test_the_wrapper_passes_its_props_through(self):
        html = render(
            '<c-n26.form-page action="/gangs/1/delete/" title="Delete?"'
            ' submit_label="Delete gang" submit_variant="danger"'
            ' cancel_url="/gangs/1/" />'
        )

        assert 'href="/gangs/1/"' in html
        assert html.index("Cancel") < html.index("Delete gang")

    @pytest.mark.parametrize("component", ["form-actions", "form-page"])
    @pytest.mark.parametrize("variant", ["success", "danger", "primary"])
    def test_the_submit_variant_reaches_the_button(self, component, variant):
        html = render(
            f'<c-n26.{component} submit_label="Confirm" submit_variant="{variant}"'
            ' cancel_url="/back/" />'
        )
        expected = render(
            f'<c-ui.button type="submit" variant="{variant}" size="md">Confirm</c-ui.button>'
        )
        submit = BeautifulSoup(html, "html.parser").find(
            "button", string=lambda text: text and text.strip() == "Confirm"
        )
        button = BeautifulSoup(expected, "html.parser").find("button")
        assert submit is not None and button is not None
        assert set(submit.get("class", [])) == set(button.get("class", []))

    def test_a_form_with_neither_gets_no_footer(self):
        """The hire screen's list carries a Hire on every row, so a control
        at the bottom would answer a question already answered."""
        html = render('<c-n26.form-page action="/gangs/1/hire/" title="Hire" />')

        assert 'type="submit"' not in html
