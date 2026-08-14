"""What the quick switcher must put in the HTML, whatever else it draws.

No database: a component is a template and a set of props, and everything
claimed here is decided before a request exists. The assertions are substrings
that can only be there if the behaviour worked — a destination that is a real
link, a current row that says so without relying on the tick, and a chevron
that has a name of its own when there is nothing beside it to borrow one from.
"""

import re

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


def panel() -> str:
    """The whole component, drawn with two destinations in it."""
    return render(f"<c-n26.quick-switcher>{ITEMS}</c-n26.quick-switcher>")


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
        heading and the hover says which half you are about to click. Two
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


class TestTheTriggerWords:
    """Words in the chevron's own button describe the panel; they never name
    a place. So they are drawn quieter than whatever they sit beside, and on
    one line with the glyph — a strip that has run out of room for its tabs is
    the last place on the screen with height to spare."""

    def test_the_words_are_smaller_and_muted(self):
        html = render(
            '<c-n26.quick-switcher heading="Which section">'
            '<c-slot name="trigger_words">2 tabs</c-slot>'
            "</c-n26.quick-switcher>"
        )
        assert '<span class="text-xs text-muted">2 tabs</span>' in html

    def test_the_button_lays_its_words_out_beside_the_glyph(self):
        """The glyph's wrapper is display:flex, which is block-level: in a
        button laid out as text it takes a line of its own and the words end
        up stacked above the chevron. The row is what puts them side by side,
        and what makes the gap between them mean anything."""
        html = render(
            '<c-n26.quick-switcher heading="Which section">'
            '<c-slot name="trigger_words">2 tabs</c-slot>'
            "</c-n26.quick-switcher>"
        )
        assert "inline-flex items-center gap-1.5" in html

    def test_a_switcher_with_no_words_is_untouched(self):
        """The bar and the page headings pass none, and their chevron stays
        the tight square it was."""
        html = render('<c-n26.quick-switcher heading="Switch gang" />')
        assert "px-1.5!" in html
        assert "inline-flex items-center" not in html
        assert 'class="text-xs text-muted"' not in html


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
    the edge, and the destinations past the edge cannot be clicked. Nothing a
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

    def test_a_list_that_fits_leaves_the_panel_nothing_to_scroll(self):
        """A negative bottom margin on the list shrinks its layout height
        but not the scrollable overflow it leaves behind, so the panel
        around it becomes a scroll container with exactly one pixel of
        scroll — a scrollbar and a wheel jiggle on a list that fits the
        screen."""
        assert "-mb-px" not in panel()


class TestMovingThroughItFromTheKeyboard:
    """Open, two letters, Down, Enter — and the reader's hands never leave the
    filter box. Nothing a server-rendered test can do presses a key, so what is
    pinned here is the wiring each step of that journey stands on. Every piece
    can be dropped in an edit and leave a page that still serves 200 with a
    switcher whose arrow keys do nothing."""

    def test_the_filter_box_is_what_answers_the_keys(self):
        """Focus lands in the box when the panel opens and stays there, so the
        box is the only element a keystroke reaches. A handler anywhere else
        would never see one."""
        html = panel()
        assert 'x-ref="filter"' in html
        assert '@keydown="keys($event)"' in html

    def test_the_arrows_move_the_highlight_rather_than_the_focus(self):
        """The dropdown this panel sits inside answers an arrow key by putting
        real focus on a row, which takes the caret out of the box mid-word.
        Keeping the key from it is what leaves the reader still typing."""
        html = panel()
        assert "event.key === 'ArrowDown' || event.key === 'ArrowUp'" in html
        assert "event.stopPropagation();" in html
        assert "this.move(event.key === 'ArrowDown' ? 1 : -1);" in html

    def test_home_and_end_stay_with_the_caret(self):
        """The panel would spend them on the list; while the box has focus they
        belong to the words being typed."""
        html = panel()
        assert "event.key === 'Home' || event.key === 'End'" in html

    def test_the_highlight_walks_only_the_rows_the_filter_is_showing(self):
        """A position in the whole list counts rows the query has hidden, and
        lands the highlight on one of them — Enter then goes to a destination
        that is not on the screen."""
        html = panel()
        assert (
            "get visible() { return this.items.filter(row => this.matches(row)) },"
            in html
        )
        assert "const rows = this.visible;" in html

    def test_a_highlight_the_query_has_just_hidden_is_dropped(self):
        """Typing narrows the list under a highlight that was already placed.
        Left alone, Enter would still reach the row it named."""
        html = panel()
        assert "this.$watch('query'" in html
        assert (
            "if (!this.visible.some(row => row.id === this.active)) this.active = '';"
            in html
        )

    def test_moving_the_highlight_scrolls_it_into_view(self):
        """The list is given less height than its rows need, so the row the
        highlight moved to is often below the fold of it."""
        html = panel()
        assert "rows[to].el.scrollIntoView({ block: 'nearest' });" in html
        assert "max-h-72 overflow-y-auto" in html

    def test_enter_presses_the_highlighted_row_s_own_link(self):
        """The same path the pointer takes: the panel's click handler closes
        it and the browser navigates, with nothing said twice."""
        html = panel()
        assert "row.el.click();" in html

    def test_escape_empties_a_filter_that_has_something_in_it_before_closing(self):
        """A filter with a query in it is the smaller thing to undo. A second
        press still leaves."""
        html = panel()
        assert (
            "if (this.query) { this.query = ''; this.active = '' } else { this.close() }"
            in html
        )

    def test_nothing_is_highlighted_until_a_key_asks_for_it(self):
        """The top row is usually the thing the reader is already on, so a
        highlight sitting there on open offers Enter as a way back to where
        they are — and competes with the tick already saying which row that
        is. Each open starts with the highlight cleared along with the
        query."""
        html = panel()
        assert "active: ''," in html
        assert (
            "this.query = '';\n                             this.active = '';" in html
        )

    def test_the_highlighted_row_is_named_aloud_by_the_control_that_has_focus(self):
        """A tint is a highlight only sighted readers have. The box keeps
        focus and names the row instead, so what is spoken and what is
        tinted are the same row."""
        html = panel()
        assert ':aria-activedescendant="active || null"' in html
        assert ":aria-controls=\"$id('n26-switcher') + '-list'\"" in html
        # The name has to reach something: the list the box points at, and
        # rows carrying the ids it names.
        assert ":id=\"$id('n26-switcher') + '-list'\"" in html
        assert html.count(':id="id"') >= 2

    def test_the_box_and_the_rows_mint_their_ids_from_one_root(self):
        """`$id` counts per element left to itself, so the box would point at
        a list id nothing on the page has."""
        html = panel()
        assert "x-id=\"['n26-switcher']\"" in html
        assert "this.$id('n26-switcher') + '-option-'" in html

    def test_the_pointer_moves_the_highlight_as_well(self):
        """A fill under the pointer and a highlight somewhere else are two
        answers to where Enter goes, and Enter can only take one of them."""
        html = panel()
        assert html.count('@mouseenter="highlight(id)"') >= 2

    def test_the_rows_stay_reachable_without_any_of_this(self):
        """None of the above is how the list is reached: every destination is
        a real link in the HTML, in the panel and in the scriptless strip."""
        html = panel()
        assert html.count('href="/n26/gangs/2/"') == 2


class TestTheChord:
    """⌥⇧ plus a letter reaches the switcher from anywhere on the page, and
    the page has to say so — a shortcut nothing on the screen mentions is one
    nobody finds. Nothing a server-rendered test can do presses a key, so what
    is pinned is the listener, what it matches, and the words that advertise
    it."""

    def chorded(self) -> str:
        return render(
            f"""
            <c-n26.quick-switcher heading="Switch gang" menu_label="Your other gangs"
                                  hotkey="f">{ITEMS}</c-n26.quick-switcher>
            """
        )

    def test_the_chord_listens_on_the_window_in_the_capture_phase(self):
        """A listener on the switcher itself would only hear keys the reader
        had already brought to it, and the whole point is reaching it from
        wherever focus happens to be. Capture, because on the way up any
        handler between the key's target and the window could stop the
        event, and a chord that works everywhere except inside one widget
        reads as broken."""
        html = self.chorded()
        assert "window.addEventListener('keydown', this.chord, true);" in html

    def test_the_chord_is_alt_shift_and_the_letter_matched_two_ways(self):
        """With ⌥ held, event.key is whatever glyph the layout types on that
        key — not an F — so the letter is found by the physical key or by
        the legacy keyCode, which follows the letter wherever a remapped
        layout put it. ⌘ and Ctrl disqualify the chord: a wider one that
        happens to contain this one is someone else's shortcut."""
        html = self.chorded()
        assert (
            "if (!event.altKey || !event.shiftKey || event.metaKey || event.ctrlKey) return;"
            in html
        )
        assert (
            "if (event.code !== 'KeyF' && event.keyCode !== 'F'.charCodeAt(0)) return;"
            in html
        )

    def test_the_letter_is_written_up_whatever_case_it_was_passed_in(self):
        html = self.chorded()
        assert "'KeyF'" in html
        assert "'Keyf'" not in html

    def test_a_second_press_closes_what_the_first_opened(self):
        html = self.chorded()
        assert "this.dropdownMenu ? this.close() : this.open();" in html

    def test_the_chevron_advertises_the_chord(self):
        """The tooltip for a reader with a pointer to hover, aria-keyshortcuts
        for one whose page is being read aloud."""
        html = self.chorded()
        assert 'title="Your other gangs (⌥⇧F)"' in html
        assert 'aria-keyshortcuts="Alt+Shift+F"' in html

    def test_the_listener_is_removed_with_the_component(self):
        html = self.chorded()
        assert "window.removeEventListener('keydown', this.chord, true);" in html

    def test_a_switcher_with_no_hotkey_carries_none_of_it(self):
        """The chord is opt-in per placement: a page draws several of these,
        and only the ones a chord was spent on may answer one."""
        html = panel()
        assert "this.chord" not in html
        assert 'aria-keyshortcuts="Alt+Shift' not in html
        assert "⌥⇧" not in html


ALPINE_ATTR = re.compile(r'(?:x-data|x-init|x-effect|@[\w.]+|:[\w:.-]+)="([^"]*)"')


def alpine_expressions(html: str) -> list[str]:
    """Every directive value on the page that Alpine will compile."""
    return ALPINE_ATTR.findall(html)


class TestTheDirectivesCompile:
    """Alpine compiles a directive's value as JavaScript and reports a syntax
    error to the browser console and nowhere else. The page still serves 200,
    with the directive silently skipped — so the failures this catches are
    invisible to every other test here."""

    def test_there_is_something_to_check(self):
        """The guard below is worth nothing if the panel stops carrying
        commented JavaScript, which is how it would quietly pass forever."""
        assert any("//" in expr for expr in alpine_expressions(panel()))

    def test_no_comment_swallows_the_expression_it_sits_in(self):
        """A `//` comment runs to the end of its line. Fold a commented
        expression onto one line — an editor, a formatter, a careless rewrite —
        and everything after the first comment becomes part of it, leaving a
        directive that is a syntax error and a switcher whose keys do
        nothing."""
        for expr in alpine_expressions(panel()):
            for comment in re.finditer(r"(?<!:)//", expr):
                assert "\n" in expr[comment.start() :], (
                    "a // comment in an Alpine directive has no newline after "
                    "it, so the rest of the expression is commented out:\n"
                    f"{expr}"
                )
