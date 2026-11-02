"""How a native select shows its options.

A one-of-many menu colours options inside an optgroup, not only the
select's direct children. A multiple select is a list, so the chosen row
is marked on its own.
"""

from pathlib import Path

from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler


def render(source: str, **context) -> str:
    """Compile a call site the way the template loader would, then render it.

    Cotton's `<c-…>` tags are rewritten by a loader, so a template built from a
    string never sees them. Running the compiler by hand is what lets a test
    write the call site it is testing.
    """
    return Template(CottonCompiler().process(source)).render(Context(context))


class TestAMultipleSelectShowsWhatIsChosen:
    """A short list stays a native <select multiple>. The chosen row
    has to carry a mark the unchosen rows do not."""

    def test_a_list_is_not_drawn_as_a_dropdown(self):
        html = render(
            '<c-ui.select.native name="types" placeholder="" multiple>'
            '<c-ui.select.option value="fighter" :selected="True">'
            "Fighter</c-ui.select.option>"
            '<c-ui.select.option value="vehicle">Vehicle</c-ui.select.option>'
            "</c-ui.select.native>"
        )

        assert "n26-select-multiple" in html
        assert "appearance-none" not in html
        assert "background-image" not in html
        assert "multiple" in html[html.index("<select") : html.index("</select>")]
        assert "selected" in html
        assert "Fighter" in html
        assert "Vehicle" in html

    def test_a_one_of_many_select_keeps_its_chevron(self):
        html = render(
            '<c-ui.select.native name="gang" placeholder="">'
            '<c-ui.select.option value="escher">Escher</c-ui.select.option>'
            "</c-ui.select.native>"
        )

        assert "n26-select-multiple" not in html
        assert "appearance-none" in html
        assert "background-image" in html
        assert "multiple" not in html[html.index("<select") : html.index(">")]
        assert "[&>option]" not in html


class TestAGroupedMenuKeepsItsTextReadable:
    """Lasting-injury results are options inside an optgroup. The menu
    colours have to reach those rows and the group label."""

    def test_menu_colours_cover_grouped_options(self):
        css = (
            Path(__file__).resolve().parents[1] / "designsystem" / "assets" / "app.css"
        ).read_text()

        assert "select:not(.n26-select-multiple) option" in css
        assert "select:not(.n26-select-multiple) optgroup" in css
        dark = css.split(".dark select:not(.n26-select-multiple) option", 1)[1]
        assert "color: var(--color-ink-100)" in dark.split("}", 1)[0]
