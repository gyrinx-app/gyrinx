"""What ``safe_artwork`` promises about artwork it did not write.

The stored value is whatever an author typed into a form. These pin the two
halves of the contract: nothing dangerous survives, and nothing survives being
absent — a gang type with no artwork must produce no markup at all, because a
placeholder would hold space in a list where most rows have nothing to draw.
"""

from unittest import mock

from django.core.cache import cache
from django.template import Context, Template
from django.utils.safestring import SafeString

from n26.core.templatetags.artwork import safe_artwork

SIMPLE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><path d="M0 0h8v8H0Z"/></svg>'


class TestNothingToDraw:
    """Absent artwork produces no markup, not an empty box."""

    def test_a_gang_type_with_no_artwork_renders_nothing(self):
        assert safe_artwork("") == ""

    def test_so_does_a_null_column(self):
        assert safe_artwork(None) == ""

    def test_and_so_does_something_that_is_not_an_svg(self):
        assert safe_artwork("<div>a paragraph someone pasted</div>") == ""


class TestWhatSurvives:
    """Real artwork comes through, normalised for drawing inline."""

    def test_the_drawing_itself_is_kept(self):
        cache.clear()
        out = safe_artwork(SIMPLE)
        assert 'd="M0 0h8v8H0Z"' in out
        assert 'viewBox="0 0 8 8"' in out

    def test_it_is_marked_safe_so_the_template_needs_no_filter_of_its_own(self):
        cache.clear()
        assert isinstance(safe_artwork(SIMPLE), SafeString)

    def test_it_follows_the_surrounding_text_colour(self):
        cache.clear()
        assert 'fill="currentColor"' in safe_artwork(SIMPLE)

    def test_the_same_markup_twice_is_cleaned_once(self):
        """Cached against a hash of the markup, so a table of gangs
        sharing a type pays for the cleaning once. Editing the artwork
        lands on a different key, so nothing has to be invalidated."""
        cache.clear()
        with mock.patch(
            "n26.core.templatetags.artwork.sanitize_inline_svg",
            return_value="<svg></svg>",
        ) as cleaner:
            safe_artwork(SIMPLE)
            safe_artwork(SIMPLE)
        assert cleaner.call_count == 1

    def test_different_markup_is_cleaned_again(self):
        cache.clear()
        other = SIMPLE.replace("M0 0h8v8H0Z", "M1 1h6v6H1Z")
        with mock.patch(
            "n26.core.templatetags.artwork.sanitize_inline_svg",
            return_value="<svg></svg>",
        ) as cleaner:
            safe_artwork(SIMPLE)
            safe_artwork(other)
        assert cleaner.call_count == 2


class TestWhatDoesNot:
    """Artwork is user input that has been round-tripped through a database.

    The allowlist is the platform's and has its own suite; these check that
    this filter is really wired to it rather than marking raw markup safe.
    """

    def test_a_script_and_its_contents_are_gone(self):
        cache.clear()
        out = safe_artwork(
            '<svg viewBox="0 0 8 8"><script>fetch("//evil")</script>'
            '<path d="M0 0"/></svg>'
        )
        assert "<script" not in out.lower()
        assert "evil" not in out

    def test_an_event_handler_is_gone(self):
        cache.clear()
        out = safe_artwork(
            '<svg viewBox="0 0 8 8"><path d="M0 0" onmouseover="steal()"/></svg>'
        )
        assert "onmouseover" not in out

    def test_a_link_out_of_the_page_is_gone(self):
        cache.clear()
        out = safe_artwork(
            '<svg viewBox="0 0 8 8"><a href="https://evil.example">'
            '<path d="M0 0"/></a></svg>'
        )
        assert "evil.example" not in out

    def test_foreign_html_is_gone(self):
        cache.clear()
        out = safe_artwork(
            '<svg viewBox="0 0 8 8"><foreignObject>'
            '<img src="x" onerror="steal()"></foreignObject></svg>'
        )
        assert "onerror" not in out
        assert "foreignobject" not in out.lower()


class TestThroughATemplate:
    """The filter as a template uses it, since that is its only caller."""

    def test_hostile_markup_does_not_reach_the_page(self):
        cache.clear()
        rendered = Template("{% load artwork %}{{ icon|safe_artwork }}").render(
            Context({"icon": '<svg viewBox="0 0 8 8"><script>alert(1)</script></svg>'})
        )
        assert "<script" not in rendered.lower()
        assert "alert(1)" not in rendered

    def test_and_a_blank_field_renders_an_empty_string(self):
        rendered = Template("{% load artwork %}[{{ icon|safe_artwork }}]").render(
            Context({"icon": ""})
        )
        assert rendered == "[]"
