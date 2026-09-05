"""Where a dropdown menu is placed when it sits inside something that scrolls.

What does the placing is JavaScript, and nothing here runs it. What can be
checked from Python is the wiring, and each of these breaks in silence: a
shell that stops loading the file, a component that calls a function no
longer defined under that name, or a card menu that quietly goes back to
being placed the ordinary way and is cut off at the table's edges again.
"""

from pathlib import Path

from django.contrib.staticfiles import finders
from django.template import Context, Template
from django.template.loader import get_template
from django_cotton.compiler_regex import CottonCompiler

MENU_JS = "n26/menu-position.js"

#: The name the component calls and the script defines. Written out rather
#: than derived, so a rename has to be made in both places on purpose.
PLACER = "n26PositionMenu"


def source_of(template_name: str) -> str:
    return Path(get_template(template_name).origin.name).read_text()


def script() -> str:
    found = finders.find(MENU_JS)
    assert found, f"{MENU_JS} is not where the static files are looked for"
    return Path(found).read_text()


class TestEveryPageLoads:
    """A menu asking for the fixed strategy calls the script the moment it
    opens, so a shell that does not load it has menus that cannot place
    themselves."""

    def test_the_app_shell_loads_it(self):
        assert MENU_JS in source_of("n26/layouts/base.html")

    def test_the_gallery_shell_loads_it(self):
        """Otherwise the dropdown page documents a strategy it cannot show."""
        assert MENU_JS in source_of("designsystem/base.html")


class TestTheComponentAndTheScriptAgree:
    def test_both_halves_name_the_same_function(self):
        assert PLACER in source_of("cotton/ui/dropdown/index.html")
        assert PLACER in script()

    def test_the_component_installs_it_over_the_kits_own_placement(self):
        """The kit calls positionDropdown again on every scroll and resize.
        Replacing that method is what keeps an open menu with its trigger;
        placing the menu once at open time would leave it behind."""
        assert "positionDropdown = " in source_of("cotton/ui/dropdown/index.html")

    def test_the_default_leaves_the_kits_placement_alone(self):
        """Only a menu that asks for it is placed against the window."""
        source = source_of("cotton/ui/dropdown/index.html")

        assert 'strategy="absolute"' in source
        assert "{% if strategy == 'fixed' %}" in source

    def test_a_long_menu_does_not_hand_its_scroll_to_the_page(self):
        """overscroll-contain stops a gesture that reached the end of the
        menu from moving the page underneath. overflow=hidden is opt-in
        for a caller that already scrolls something inside the panel."""
        source = source_of("cotton/ui/dropdown/index.html")
        assert "overscroll-contain" in source
        assert 'overflow="auto"' in source
        assert "overflow == 'hidden'" in source
        assert "overflow-y-auto overflow-x-hidden" in source


class TestScriptlessMenus:
    def test_an_opted_in_menu_reveals_its_links_without_duplicating_them(self):
        html = Template(
            CottonCompiler().process(
                '<c-ui.dropdown trigger_text="Actions" :scriptless="True">'
                '<c-ui.dropdown.item href="/clone/">Clone</c-ui.dropdown.item>'
                "</c-ui.dropdown>"
            )
        ).render(Context({}))
        assert "data-dropdown-scriptless" in html
        fallback = html.split("<noscript>")[1].split("</noscript>")[0]
        assert '[x-ref="trigger"] { display: none !important; }' in fallback
        assert '[x-ref="content"][x-cloak] { display: block !important; }' in fallback
        assert html.count('href="/clone/"') == 1

    def test_other_menus_keep_their_existing_behaviour(self):
        html = Template(
            CottonCompiler().process(
                '<c-ui.dropdown trigger_text="Actions">Menu</c-ui.dropdown>'
            )
        ).render(Context({}))
        assert "data-dropdown-scriptless" not in html
        assert "<noscript>" not in html


class TestTheCardMenuAsksForIt:
    def test_the_menu_beside_a_name_escapes_the_weapon_tables_scroll_box(self):
        """The model card draws its weapons in a table that scrolls sideways
        on a narrow screen. A menu placed inside that box loses whatever hangs
        past its edges, which is most of the menu on the last weapon."""
        assert 'strategy="fixed"' in source_of("cotton/n26/owned_actions.html")

    def test_the_weapon_table_is_still_the_box_this_is_about(self):
        """If the table stops scrolling, the strategy above stops earning its
        place — and if it keeps scrolling under a different class, the reason
        written beside the strategy stops being true."""
        assert "overflow-x-auto" in source_of("cotton/n26/model_card/body.html")
