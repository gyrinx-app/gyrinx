"""What a strip of tab links must put in the HTML.

No database: a component is a template and a set of props, and everything
claimed here is decided before a request exists. The assertions are substrings
that can only be there if the behaviour worked — a destination that is a real
link, and a current tab that says which one it is to something reading the page
aloud rather than only to an eye reading its colour.
"""

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


def render(source: str, **context) -> str:
    """Compile a call site the way the template loader would, then render it.

    Cotton's `<c-…>` tags are rewritten by a loader, so a template built from a
    string never sees them. Running the compiler by hand is what lets a test
    write the call site it is testing.
    """
    return Template(CottonCompiler().process(source)).render(Context(context))


class TestTheStrip:
    """A tab is a link to a page, because what is behind it is a whole
    render rather than a panel already on the screen."""

    def test_every_tab_is_a_link_to_its_own_url(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert 'href="?list=1"' in html
        assert 'href="?list=2"' in html

    def test_the_current_tab_says_so_without_relying_on_its_colour(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert 'aria-current="page"' in html
        # Twice for one current tab — once per strip, since both are always
        # in the HTML and CSS picks which one shows. Never on the other tab:
        # a strip where every tab is current tells a reader nothing about
        # where they are.
        assert html.count('aria-current="page"') == 2

    def test_the_strip_names_what_it_is_choosing_between(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert 'aria-label="Which list"' in html

    def test_a_shortened_label_keeps_its_full_name_as_a_tooltip(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert 'title="Ash Waste Nomads Equipment List"' in html
        # A name that was not shortened gets no tooltip: repeating the label
        # in a hover is a promise of more that turns out to be the same words.
        assert 'title="Trading Post"' not in html


class TestTheNarrowStrip:
    """Below the sm breakpoint the strip never wraps: the current tab stands
    alone, and the rest sit behind a switcher whose rows are the same real
    links."""

    def test_both_strips_are_in_the_html_for_css_to_pick_between(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert "sm:flex" in html
        assert "sm:hidden" in html

    def test_the_switcher_says_how_many_more_there_are(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert "+1 more" in html

    def test_the_other_tab_is_still_a_real_link_behind_the_switcher(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        # The wide strip's copy, the switcher panel's, and the switcher's
        # noscript strip: three real <a>s to the uncurrent tab, so the
        # destination is reachable whichever strip shows and whether or not
        # script ran.
        assert html.count('href="?list=2"') == 3

    def test_a_shortened_tab_keeps_its_tooltip_behind_the_switcher(self):
        flipped = [
            dict(TABS[0], current=False),
            dict(TABS[1], current=True),
        ]
        html = render(
            '<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=flipped
        )
        # The full name rides into the menu: the wide strip's link, then the
        # switcher's row drawn twice — its panel and its noscript strip.
        assert html.count('title="Ash Waste Nomads Equipment List"') == 3

    def test_an_ampersand_in_a_name_survives_the_switcher_once_escaped(self):
        tabs = [
            {"label": "Kit & gear", "href": "?list=1&page=2", "current": False},
            {"label": "Trading Post", "href": "?list=2", "current": True},
        ]
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=tabs)
        # Escaped exactly once: a value written into a component attribute is
        # escaped twice over, the name displays wrong, and the href loses the
        # ampersand between its query parameters.
        assert "Kit &amp; gear" in html
        assert 'href="?list=1&amp;page=2"' in html
        assert "amp;amp;" not in html

    def test_a_single_tab_gets_no_switcher(self):
        html = render(
            '<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS[:1]
        )
        # A menu of nothing is a control that opens to say it had nothing
        # to offer.
        assert "more" not in html
        assert "data-quick-switcher" not in html


class TestTheBusySpinner:
    """A strip whose pages take seconds to build can name the element that
    gives way to a spinner, so a click is seen to have landed."""

    def test_a_busy_strip_carries_the_wait_wiring_and_the_spinner(self):
        html = render(
            '<c-n26.tab-links label="Which list" :tabs="tabs" busy="#listing" />',
            tabs=TABS,
        )
        assert "#listing" in html
        assert 'x-ref="wait"' in html
        assert "animate-spin" in html

    def test_a_plain_strip_carries_none_of_it(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert 'x-ref="wait"' not in html
        assert "animate-spin" not in html


class TestTheSearchBarsButton:
    """The submit appears exactly where clicking it does something. A bar
    that narrows rows already on the page has nothing to submit, and a
    button that does nothing is worse than no button."""

    def test_a_bar_with_somewhere_to_go_keeps_its_button(self):
        html = render('<c-n26.search-bar action="/n26/gangs/" name="q" />')
        assert 'type="submit"' in html

    def test_a_nested_bar_has_no_button(self):
        """Nested is inside somebody else's form: a real submit would post
        theirs, so there is nothing a button here could ever do."""
        html = render('<c-n26.search-bar :live="True" :nested="True" model="query" />')
        assert 'type="submit"' not in html
        # The clear button is the only one left, and it acts on the field's
        # contents rather than pretending to be an action.
        assert html.count("<button") == 1
        # The field itself is untouched — narrowing as you type is the whole
        # behaviour a nested bar has.
        assert 'x-model="query"' in html

    def test_a_live_bar_with_nowhere_to_submit_has_no_button(self):
        html = render('<c-n26.search-bar :live="True" model="query" />')
        assert 'type="submit"' not in html


class TestTheSearchBarsEnterKey:
    """Enter in a live box that has no Search button of its own does
    nothing. The filter already runs as you type; Enter would otherwise
    submit the surrounding form and activate its first Buy or Hire —
    even a row the filter has hidden. A nested bar that is the filter
    of a GET form is not live, so Enter still submits that search."""

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
