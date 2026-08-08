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
        # One of them, not both: a strip where every tab is current tells a
        # reader nothing about where they are.
        assert html.count('aria-current="page"') == 1

    def test_the_strip_names_what_it_is_choosing_between(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert 'aria-label="Which list"' in html

    def test_a_shortened_label_keeps_its_full_name_as_a_tooltip(self):
        html = render('<c-n26.tab-links label="Which list" :tabs="tabs" />', tabs=TABS)
        assert 'title="Ash Waste Nomads Equipment List"' in html
        # A name that was not shortened gets no tooltip: repeating the label
        # in a hover is a promise of more that turns out to be the same words.
        assert 'title="Trading Post"' not in html


class TestTheSearchBarsButton:
    """The submit appears exactly where pressing it does something. A bar
    that narrows rows already on the page has nothing to submit, and a
    button that does nothing is worse than no button."""

    def test_a_bar_with_somewhere_to_go_keeps_its_button(self):
        html = render('<c-n26.search-bar action="/n26/gangs/" name="q" />')
        assert 'type="submit"' in html

    def test_a_nested_bar_has_no_button(self):
        """Nested is inside somebody else's form: a real submit would press
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
