"""The busy state a control takes on while its click is being served.

What it does is JavaScript, and nothing here runs that. What can be checked
from Python is the wiring it needs to work at all, and every one of these
would fail silently in a browser: a shell that stops loading the file, a
stylesheet that draws an attribute the script no longer writes, or a link
button that loses the class the script recognises buttons by.
"""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.template import Context, Template
from django.template.loader import get_template
from django_cotton.compiler_regex import CottonCompiler

BUSY_JS = "n26/busy.js"

#: The state the script writes and the stylesheet draws. Written out here
#: rather than derived, so a rename has to be made in three places on purpose.
BUSY_STATE = 'data-busy="on"'

#: What the script takes to mean "this link is a button".
BUTTON_CLASS = "rounded-button"


def source_of(template_name: str) -> str:
    return Path(get_template(template_name).origin.name).read_text()


def script() -> str:
    found = finders.find(BUSY_JS)
    assert found, f"{BUSY_JS} is not where the static files are looked for"
    return Path(found).read_text()


def stylesheet() -> str:
    """The Tailwind input, not the build: the build is generated and gitignored,
    so a worktree that has not run the CSS build has no copy of it."""
    return (
        Path(__file__).resolve().parents[1] / "designsystem" / "assets" / "app.css"
    ).read_text()


class TestEveryPageLoads:
    """Neither shell may drop the script: it listens at the document and no
    call site opts in, so a page that does not load it has no busy state
    anywhere and says nothing about it."""

    def test_the_app_shell_loads_it(self):
        assert BUSY_JS in source_of("n26/layouts/base.html")

    def test_the_gallery_shell_loads_it(self):
        """Otherwise the button page documents behaviour it cannot show."""
        assert BUSY_JS in source_of("designsystem/base.html")


class TestTheScriptAndTheStylesheetAgree:
    """The script writes one attribute; the stylesheet is the only thing that
    turns it into something a reader can see. Renaming either half alone leaves
    a button that goes quiet and never looks busy."""

    def test_both_halves_name_the_same_state(self):
        assert BUSY_STATE in script()
        assert BUSY_STATE in stylesheet()

    def test_the_stylesheet_hides_the_label_without_taking_the_spinner(self):
        """The spinner is drawn in the button's own colour. Hiding the label
        with `color: transparent` would hide the spinner too, and the colour
        would have to be measured in the browser and handed back."""
        assert "-webkit-text-fill-color: transparent" in stylesheet()


class TestWhatTheScriptCanReach:
    """A click reaches a control through what the component renders."""

    def test_a_link_button_carries_the_class_the_script_looks_for(self):
        """The script marks a navigating link only when it is a button rather
        than a word in a sentence, and this class is how it tells."""
        html = Template(
            CottonCompiler().process('<c-ui.button href="/gangs/">Gangs</c-ui.button>')
        ).render(Context())

        assert "<a" in html
        assert BUTTON_CLASS in html
        assert BUTTON_CLASS in script()

    def test_a_control_can_be_kept_out_of_it(self):
        """The escape hatch is a plain attribute, which means it has to survive
        the component: an undeclared prop that the template swallowed would
        leave the control going busy with nothing to say why."""
        html = Template(
            CottonCompiler().process(
                '<c-ui.button type="submit" data-busy="off">Stay</c-ui.button>'
            )
        ).render(Context())

        assert 'data-busy="off"' in html
