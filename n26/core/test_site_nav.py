"""What the site's top bar must put in the HTML around the page's own name.

No database: a component is a template and a set of props, and whether the
heading and the switcher give ground in a tight row is decided before a
request exists.
"""

from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler


def render(source: str, **context) -> str:
    """Compile a call site the way the template loader would, then render it.

    Cotton's `<c-…>` tags are rewritten by a loader, so a template built from a
    string never sees them. Running the compiler by hand is what lets a test
    write the call site it is testing.
    """
    return Template(CottonCompiler().process(source)).render(Context(context))


class TestTheNameBesideTheBrand:
    """The heading and the switcher share one box beside the brand mark. The
    bar's row does not wrap, and the actions on the right do not shrink, so
    this box is what gives ground: the word ellipsises and the switcher's
    chevron stays a control."""

    def test_the_box_is_a_shrinking_flex_row(self):
        """Visible at every width: hiding it below sm would keep the edition
        toggle clear, but drop the chevron with it. The word ellipsises
        instead, which is why this is flex min-w-0 and not hidden sm:flex."""
        html = render(
            '<c-n26.site.nav title="Gyrinx">'
            '<c-slot name="heading">The Ashen Choir</c-slot>'
            "</c-n26.site.nav>"
        )
        assert "flex min-w-0 items-center gap-2" in html
        assert "hidden min-w-0 items-center gap-2 sm:flex" not in html

    def test_the_heading_ellipsises_rather_than_pushing_the_actions(self):
        html = render(
            '<c-n26.site.nav title="Gyrinx">'
            '<c-slot name="heading">The Ashen Choir</c-slot>'
            "</c-n26.site.nav>"
        )
        assert "min-w-0 truncate text-ink-600" in html
        assert "The Ashen Choir" in html

    def test_the_switcher_wrap_gives_ground_rather_than_pinning_its_width(self):
        """shrink-0 on this wrap would pin it to the label's full width and
        shove the chevron into the edition toggle. min-w-0 is what lets the
        label inside ellipsis instead."""
        html = render(
            '<c-n26.site.nav title="Gyrinx">'
            '<c-slot name="switcher"><span>The Ashen Choir</span></c-slot>'
            "</c-n26.site.nav>"
        )
        assert (
            "min-w-0 [&amp;_noscript]:hidden" in html
            or "min-w-0 [&_noscript]:hidden" in html
        )
        assert "shrink-0 [&_noscript]:hidden" not in html
        assert "shrink-0 [&amp;_noscript]:hidden" not in html

    def test_no_box_is_drawn_with_neither_slot_filled(self):
        html = render('<c-n26.site.nav title="Gyrinx" />')
        assert "flex min-w-0 items-center gap-2" not in html

    def test_the_brand_mark_stays_outside_the_shrinking_box(self):
        html = render(
            '<c-n26.site.nav title="Gyrinx" href="/n26/">'
            '<c-slot name="heading">The Ashen Choir</c-slot>'
            "</c-n26.site.nav>"
        )
        assert 'href="/n26/" class="n26-site-brand shrink-0 focus-ring"' in html
