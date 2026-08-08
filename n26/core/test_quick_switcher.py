"""What the quick switcher must put in the HTML, whatever else it draws.

No database: a component is a template and a set of props, and everything
claimed here is decided before a request exists. The assertions are substrings
that can only be there if the behaviour worked — a destination that is a real
link, a current row that says so without relying on the tick, and a chevron
that has a name of its own when there is nothing beside it to borrow one from.
"""

from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

ITEMS = """
    <c-n26.quick-switcher.item label="The Ashen Choir" href="/n26/gangs/1/" :current="True" />
    <c-n26.quick-switcher.item label="Pit of Teeth" href="/n26/gangs/2/" />
"""


def render(source: str) -> str:
    """Compile a call site the way the template loader would, then render it.

    Cotton's `<c-…>` tags are rewritten by a loader, so a template built from a
    string never sees them. Running the compiler by hand is what lets a test
    write the call site it is testing instead of keeping a fixture file beside
    it.
    """
    return Template(CottonCompiler().process(source)).render(Context({}))


class TestTheLeadingLink:
    """The identifier button is a variant, and both halves of that variant have
    to be whole controls."""

    def test_the_label_is_a_link_to_the_thing_it_names(self):
        html = render(
            f"""
            <c-n26.quick-switcher label="The Ashen Choir" href="/n26/gangs/1/"
                                  heading="Switch gang">{ITEMS}</c-n26.quick-switcher>
            """
        )
        assert 'href="/n26/gangs/1/"' in html
        assert "The Ashen Choir" in html

    def test_omitting_the_label_leaves_only_the_chevron(self):
        with_label = render(
            f"""
            <c-n26.quick-switcher label="The Ashen Choir" href="/n26/gangs/current/"
                                  heading="Switch gang">{ITEMS}</c-n26.quick-switcher>
            """
        )
        without = render(
            f"""
            <c-n26.quick-switcher heading="Switch gang">{ITEMS}</c-n26.quick-switcher>
            """
        )
        # The identifier's own link goes; the destinations it sat above stay,
        # and the chevron is still the one control in the group rather than
        # the surviving half of a pair — which is what makes the group round
        # both its ends instead of leaving a shape cut in half.
        assert 'href="/n26/gangs/current/"' in with_label
        assert 'href="/n26/gangs/current/"' not in without
        assert 'href="/n26/gangs/2/"' in without
        assert without.count("n26-button-group") == 1
        assert without.count('aria-haspopup="menu"') == 1

    def test_both_halves_are_ghost_buttons_in_one_group(self):
        """Ghost is the whole affordance: no fill and no rule until the
        pointer is on one of them, so the control reads as words beside a
        heading and the hover says which half you are about to press. Two
        of them, joined, and the group is what makes them one object."""
        html = render(
            f"""
            <c-n26.quick-switcher label="The Ashen Choir" href="/n26/gangs/1/"
                                  heading="Switch gang">{ITEMS}</c-n26.quick-switcher>
            """
        )
        assert html.count("n26-button-group") == 1
        # bg-transparent is the ghost variant and nothing else in here uses
        # it, so the count is the number of ghost halves.
        assert html.count("bg-transparent") == 2
        assert html.count("hover:bg-ink-100") >= 2

    def test_the_lone_chevron_is_ghost_too(self):
        html = render('<c-n26.quick-switcher heading="Switch gang" />')
        assert html.count("bg-transparent") == 1

    def test_the_chevron_is_named_even_with_no_label_beside_it(self):
        html = render('<c-n26.quick-switcher heading="Switch gang" />')
        assert 'aria-label="Switch gang"' in html

    def test_the_chevron_takes_its_own_name_when_given_one(self):
        html = render(
            '<c-n26.quick-switcher heading="Switch gang" menu_label="Your other gangs" />'
        )
        assert 'aria-label="Your other gangs"' in html


class TestTheList:
    """Every destination is in the HTML before any script runs, and the panel
    says which one you are on."""

    def test_the_current_row_is_marked_without_the_tick(self):
        html = render(f"<c-n26.quick-switcher>{ITEMS}</c-n26.quick-switcher>")
        assert 'aria-current="page"' in html

    def test_only_the_current_row_is_marked(self):
        html = render(f"<c-n26.quick-switcher>{ITEMS}</c-n26.quick-switcher>")
        # Once in the panel and once in the scriptless strip, and no more:
        # a second marked row would mean `current` had leaked between items.
        assert html.count('aria-current="page"') == 2

    def test_the_rows_are_drawn_again_for_a_reader_with_no_script(self):
        html = render(f"<c-n26.quick-switcher>{ITEMS}</c-n26.quick-switcher>")
        strip = html.split("<noscript>")[1]
        assert 'href="/n26/gangs/1/"' in strip
        assert 'href="/n26/gangs/2/"' in strip

    def test_the_filter_matches_on_the_row_label(self):
        html = render(f"<c-n26.quick-switcher>{ITEMS}</c-n26.quick-switcher>")
        # Lowercased at render time, because the query is lowercased before the
        # comparison and doing it per keystroke would be work per row per key.
        assert "pit of teeth" in html


class TestStayingOnTheScreen:
    """A panel hung from a trigger in the middle of a narrow window runs off
    the edge, and the destinations past the edge cannot be pressed. Nothing a
    server-rendered test can see says whether that happened, so what is pinned
    here is the two pieces that stop it — one CSS, one script — because either
    can be dropped in an edit and leave a page that still serves 200."""

    def test_the_panel_can_never_be_wider_than_the_window(self):
        html = render(f"<c-n26.quick-switcher>{ITEMS}</c-n26.quick-switcher>")
        assert "max-w-[calc(100vw-1rem)]" in html

    def test_a_minimum_width_is_capped_at_the_window_too(self):
        """A minimum beats a maximum in CSS, so a minimum wider than the screen
        would undo the cap above it."""
        html = render(
            f'<c-n26.quick-switcher min_width="24rem">{ITEMS}</c-n26.quick-switcher>'
        )
        assert "min(24rem, calc(100vw - 1rem))" in html

    def test_the_placement_is_corrected_when_the_panel_opens_and_on_resize(self):
        html = render(f"<c-n26.quick-switcher>{ITEMS}</c-n26.quick-switcher>")
        assert "this.fit()" in html
        assert "window.addEventListener('resize', this.refit)" in html

    def test_the_scriptless_strip_gives_up_its_width_rather_than_overflow(self):
        html = render(f"<c-n26.quick-switcher>{ITEMS}</c-n26.quick-switcher>")
        strip = html.split("<noscript>")[1]
        assert "max-w-full" in strip
