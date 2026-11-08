"""Tab-link markup provides navigable destinations, accessible current-page state and
responsive overflow controls.
"""

import json

from bs4 import BeautifulSoup
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

TABS = [
    {
        "label": "Ash Waste Nomads",
        "title": "Ash Waste Nomads Equipment List",
        "href": "?list=1",
        "current": True,
    },
    {
        "label": "Trading Post",
        "title": "Trading Post",
        "href": "?list=2",
        "current": False,
    },
]

#: Three tabs exceed the default narrow-strip limit of two.
THREE = TABS + [
    {
        "label": "Dust Falls",
        "title": "Dust Falls Trade Agreement Equipment List",
        "href": "?list=3",
        "current": False,
    },
]


def render(source: str, **context) -> str:
    """Compile Cotton tags before rendering an inline template."""
    return Template(CottonCompiler().process(source)).render(Context(context))


def overflow(html):
    """Read the narrow-strip switcher items from its React props."""
    soup = BeautifulSoup(html, "html.parser")
    host = soup.select_one("[data-react-module*='/quick-switcher-']")
    return json.loads(soup.find(id=host["data-react-props"]).string)["items"]


class TestTheStrip:
    """Tabs link to server-rendered pages rather than switching local panels."""

    def test_every_tab_is_a_link_to_its_own_url(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert 'href="?list=1"' in html
        assert 'href="?list=2"' in html

    def test_the_current_tab_says_so_without_relying_on_its_colour(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert 'aria-current="page"' in html
        # Wide and narrow strips both render; each marks only the current tab.
        assert html.count('aria-current="page"') == 2

    def test_the_strip_names_what_it_is_choosing_between(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert 'aria-label="Which list"' in html

    def test_a_shortened_label_keeps_its_full_name_as_a_tooltip(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert 'title="Ash Waste Nomads Equipment List"' in html
        # Omit tooltips when they would repeat an unshortened label.
        assert 'title="Trading Post"' not in html


class TestTheNarrowStrip:
    """Show all tabs up to narrow_tabs, defaulting to two.

    Above that threshold, show the current tab and a switcher containing the
    remaining links.
    """

    def test_two_tabs_are_both_drawn_rather_than_one_and_a_menu(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert "more" not in html
        assert "data-quick-switcher" not in html
        assert html.count('href="?list=2"') == 2

    def test_the_switcher_says_how_many_more_there_are(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=THREE)
        assert "+2 more" in html
        assert "data-quick-switcher" in html

    def test_the_other_tab_is_still_a_real_link_behind_the_switcher(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=THREE)
        # Both the wide strip and noscript fallback retain links; the island receives
        # the same destinations.
        assert html.count('href="?list=2"') == 2
        assert {"label": "Trading Post", "href": "?list=2"} in overflow(html)

    def test_a_shortened_tab_keeps_its_tooltip_behind_the_switcher(self):
        flipped = [
            dict(THREE[0], current=False),
            dict(THREE[1], current=True),
            THREE[2],
        ]
        html = render(
            '<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=flipped
        )
        # Keep full tooltips in both rendered links and switcher props.
        assert html.count('title="Ash Waste Nomads Equipment List"') == 2
        assert overflow(html)[0]["title"] == "Ash Waste Nomads Equipment List"

    def test_an_ampersand_in_a_name_survives_the_switcher_once_escaped(self):
        tabs = [
            {"label": "Kit & gear", "href": "?list=1&page=2", "current": False},
            {"label": "Trading Post", "href": "?list=2", "current": True},
            {"label": "Dust Falls", "href": "?list=3", "current": False},
        ]
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=tabs)
        # Escape labels and query strings once so names and parameter separators
        # survive.
        assert "Kit &amp; gear" in html
        assert 'href="?list=1&amp;page=2"' in html
        assert "amp;amp;" not in html

    def test_a_strip_that_holds_three_draws_three_tabs_whole(self):
        html = render(
            '<c-n26.tab-links label="Which list" :tabs="tabs" :narrow_tabs="3" />',
            tabs=THREE,
        )
        assert "more" not in html
        assert "data-quick-switcher" not in html
        assert html.count('href="?list=3"') == 2

    def test_a_strip_that_holds_three_pads_its_narrow_tabs_less(self):
        def padding(html):
            soup = BeautifulSoup(html, "html.parser")
            narrow = soup.select_one('div[class~="sm:hidden"]')
            return {
                cls
                for link in narrow.find_all("a")
                for cls in link["class"]
                if cls in ("px-2", "px-3")
            }

        three = render(
            '<c-n26.tab-links label="Which list" :tabs="tabs" :narrow_tabs="3" />',
            tabs=THREE,
        )
        two = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        # Reduce padding so three short labels fit a 320px viewport.
        assert padding(three) == {"px-2"}
        assert padding(two) == {"px-3"}

    def test_narrow_tabs_without_the_colon_still_counts(self):
        html = render(
            '<c-n26.tab-links label="Which list" :tabs="tabs" narrow_tabs="3" />',
            tabs=THREE,
        )
        # Coerce a literal narrow_tabs attribute from text before comparing counts.
        assert "more" not in html
        assert html.count('href="?list=3"') == 2

    def test_a_strip_that_holds_three_still_folds_a_fourth(self):
        four = THREE + [{"label": "Hive Scum", "href": "?list=4", "current": False}]
        html = render(
            '<c-n26.tab-links label="Which list" :tabs="tabs" :narrow_tabs="3" />',
            tabs=four,
        )
        assert "+3 more" in html
        assert "data-quick-switcher" in html

    def test_a_single_tab_gets_no_switcher(self):
        html = render(
            '<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS[:1]
        )
        assert "more" not in html
        assert "data-quick-switcher" not in html


class TestTheBusySpinner:
    """Optional busy wiring identifies the content replaced by a loading indicator."""

    def test_a_busy_strip_carries_the_wait_wiring_and_the_spinner(self):
        html = render(
            '<c-n26.tab-links label="Which list" :tabs="tabs" busy="#listing" />',
            tabs=TABS,
        )
        assert "#listing" in html
        assert 'x-ref="wait"' in html

    def test_a_plain_strip_carries_none_of_it(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert 'x-ref="wait"' not in html


class TestTheSearchBarsButton:
    """Search bars need submit controls only when they have a destination."""

    def test_a_bar_with_somewhere_to_go_keeps_its_button(self):
        html = render('<c-n26.search-bar action="/n26/gangs/" name="q" />')
        assert 'type="submit"' in html

    def test_a_nested_bar_has_no_button(self):
        """A nested live filter must not submit the surrounding form."""
        html = render('<c-n26.search-bar :live="True" :nested="True" model="query" />')
        assert 'type="submit"' not in html
        assert len(BeautifulSoup(html, "html.parser").find_all("button")) == 1
        assert 'x-model="query"' in html

    def test_a_live_bar_with_nowhere_to_submit_has_no_button(self):
        html = render('<c-n26.search-bar :live="True" model="query" />')
        assert 'type="submit"' not in html


class TestTheSearchBarsEnterKey:
    """Prevent Enter in live filters without a search destination so it cannot submit
    an unrelated surrounding form.

    Allow Enter when the search has a submit destination or belongs to a non-live
    GET form.
    """

    def test_a_nested_live_bar_swallows_enter(self):
        html = render('<c-n26.search-bar :live="True" :nested="True" model="query" />')
        assert "@keydown.enter.prevent" in html

    def test_a_live_bar_with_nowhere_to_submit_swallows_enter(self):
        html = render('<c-n26.search-bar :live="True" model="query" />')
        assert "@keydown.enter.prevent" in html

    def test_a_nested_bar_that_filters_a_get_form_still_submits_on_enter(self):
        html = render(
            '<c-n26.search-bar :nested="True" name="q" placeholder="Search the history" />'
        )
        assert "@keydown.enter.prevent" not in html

    def test_a_live_bar_with_a_search_button_still_submits_on_enter(self):
        html = render(
            '<c-n26.search-bar :live="True" model="query" action="/n26/gangs/" />'
        )
        assert 'type="submit"' in html
        assert "@keydown.enter.prevent" not in html
