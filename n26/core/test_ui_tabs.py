"""Rendered tab markup supplies responsive strips and browser-generated tab controls.

These tests inspect bindings and structure; panel registration creates the actual
tabs in the browser.
"""

from bs4 import BeautifulSoup
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

DEFAULT = """
<c-ui.tabs>
    <c-ui.tabs.tab name="Gangs">A table of gangs.</c-ui.tabs.tab>
    <c-ui.tabs.tab name="Campaigns">Nothing yet.</c-ui.tabs.tab>
</c-ui.tabs>
"""

SEGMENTED = """
<c-ui.tabs variant="segmented" size="sm" :fill="True">
    <c-ui.tabs.tab name="Card">The card.</c-ui.tabs.tab>
    <c-ui.tabs.tab name="Lore">The lore.</c-ui.tabs.tab>
</c-ui.tabs>
"""


def render(source: str, **context) -> str:
    """Compile Cotton tags before rendering an inline template."""
    return Template(CottonCompiler().process(source)).render(Context(context))


class TestTheDefaultStrip:
    """Use wide and narrow strips, with overflow above the configured narrow_tabs
    threshold.
    """

    def test_the_narrow_strip_holds_a_switcher_for_the_other_tabs(self):
        html = render(DEFAULT)
        assert "data-quick-switcher" in html
        # Render loops for wide buttons, narrow buttons, switcher items and the noscript
        # fallback.
        assert html.count('x-for="tab in tabs"') == 4
        assert "$dispatch('quick-switcher-choose'" in html

    def test_the_narrow_strip_draws_two_tabs_whole_and_folds_from_three(self):
        html = render(DEFAULT)
        # Inspect bindings because registered tabs are created only in the browser.
        assert 'x-show="tabs.length <= 2 || isActive(tab.name)"' in html
        assert 'x-show="tabs.length > 2"' in html
        assert "'+' + (tabs.length - 1) + ' more'" in html

    def test_a_strip_can_hold_three_tabs_whole(self):
        html = render(
            """
            <c-ui.tabs :narrow_tabs="3">
                <c-ui.tabs.tab name="Gangs">A table of gangs.</c-ui.tabs.tab>
                <c-ui.tabs.tab name="Campaigns">Nothing yet.</c-ui.tabs.tab>
                <c-ui.tabs.tab name="Content Packs">Nothing yet.</c-ui.tabs.tab>
            </c-ui.tabs>
            """
        )
        assert 'x-show="tabs.length <= 3 || isActive(tab.name)"' in html
        assert 'x-show="tabs.length > 3"' in html

    def test_a_strip_that_holds_three_pads_its_narrow_tabs_less(self):
        def narrow_button(html):
            soup = BeautifulSoup(html, "html.parser")
            return soup.find(
                "button", attrs={"x-show": lambda v: v and "isActive" in v}
            )["class"]

        three = render(
            """
            <c-ui.tabs :narrow_tabs="3">
                <c-ui.tabs.tab name="Gangs">A table of gangs.</c-ui.tabs.tab>
            </c-ui.tabs>
            """
        )
        # Reduce padding so three short labels fit a 320px viewport.
        assert "px-2" in narrow_button(three)
        assert "px-3" not in narrow_button(three)
        assert "px-3" in narrow_button(render(DEFAULT))

    def test_the_panels_still_register_themselves(self):
        html = render(DEFAULT)
        assert html.count("register('Gangs'") + html.count('register("Gangs"') == 1

    def test_an_apostrophe_in_the_default_tab_cannot_break_the_script(self):
        html = render(
            """
            <c-ui.tabs default_tab="Psyker's">
                <c-ui.tabs.tab name="Psyker's">Powers.</c-ui.tabs.tab>
            </c-ui.tabs>
            """
        )
        # Escape apostrophes inside the JavaScript string literal.
        assert "activeTab: 'Psyker\\u0027s'" in html

    def test_noscript_shows_every_panel(self):
        html = render(DEFAULT)
        assert "<noscript>" in html
        assert ".n26-tabs-panel { display: block !important; }" in html
        assert html.count('class="n26-tabs-panel mt-2"') == 2

    def test_select_writes_the_query_string_only_when_param_is_set(self):
        html = render(
            """
            <c-ui.tabs param="tab">
                <c-ui.tabs.tab name="Gangs">A table of gangs.</c-ui.tabs.tab>
            </c-ui.tabs>
            """
        )
        assert "select(tab.name)" in html
        assert "u.searchParams.set(this.param, name)" in html
        assert "param: 'tab'" in html
        # Accept a query value only when it matches a registered tab; unknown values
        # must not hide every panel.
        assert "if (q === name) this.activeTab = q;" in html
        assert "if (q) this.activeTab = q;" not in html


class TestTheSegmentedStrip:
    """Segmented tabs keep one strip with the DOM structure targeted by app.css."""

    def test_no_second_strip_and_no_switcher_appear(self):
        html = render(SEGMENTED)
        assert "data-quick-switcher" not in html
