"""Native selects retain multiple-selection styling and colours for grouped options."""

from pathlib import Path

from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler


def render(source: str, **context) -> str:
    """Compile Cotton tags before rendering an inline template."""
    return Template(CottonCompiler().process(source)).render(Context(context))


class TestAMultipleSelectShowsWhatIsChosen:
    """Multiple selects retain native list styling and selected-option markup."""

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
    """Apply menu colours to optgroup labels and their nested options."""

    def test_menu_colours_cover_grouped_options(self):
        css = (
            Path(__file__).resolve().parents[1] / "designsystem" / "assets" / "app.css"
        ).read_text()

        assert "select:not(.n26-select-multiple) option" in css
        assert "select:not(.n26-select-multiple) optgroup" in css
        dark = css.split(".dark select:not(.n26-select-multiple) option", 1)[1]
        assert "color: var(--color-ink-100)" in dark.split("}", 1)[0]
