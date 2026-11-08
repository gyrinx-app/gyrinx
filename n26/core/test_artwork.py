"""Artwork passes through the shared SVG sanitiser; absent or invalid SVG produces no
markup.
"""

from unittest import mock

from django.core.cache import cache
from django.template import Context, Template
from django.utils.safestring import SafeString

from n26.core.templatetags.artwork import safe_artwork

SIMPLE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><path d="M0 0h8v8H0Z"/></svg>'


class TestNothingToDraw:
    """Absent or invalid SVG produces no markup."""

    def test_a_gang_type_with_no_artwork_renders_nothing(self):
        assert safe_artwork("") == ""

    def test_so_does_a_null_column(self):
        assert safe_artwork(None) == ""

    def test_and_so_does_something_that_is_not_an_svg(self):
        assert safe_artwork("<div>a paragraph someone pasted</div>") == ""


class TestWhatSurvives:
    """Valid SVG retains its geometry and uses the surrounding text colour."""

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
        """Cache by markup so repeated drawings are sanitised once and edited markup
        uses a different key.
        """
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
    """Treat stored artwork as untrusted input and enforce the shared SVG allowlist."""

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
    """Template rendering uses sanitised artwork and preserves empty output."""

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
