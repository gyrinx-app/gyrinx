from django.test import SimpleTestCase

from gyrinx.core.templatetags.color_tags import (
    list_with_theme,
    theme_square,
)


class TestColorTags(SimpleTestCase):
    def test_theme_square_with_color(self):
        """Test theme square generation with a theme color."""

        class MockList:
            name = "Test Gang"
            theme_color = "#386b33"

        square = theme_square(MockList())
        assert 'class="d-inline-block rounded "' in square
        assert "background-color: #386b33;" in square
        assert "border: 1px solid rgba(0,0,0,0.15);" in square

    def test_theme_square_without_color(self):
        """Test theme square with no color returns empty."""

        class MockList:
            name = "Test Gang"
            theme_color = None

        square = theme_square(MockList())
        assert square == ""

    def test_list_with_theme_colored(self):
        """Test list display with theme color."""

        class MockList:
            name = "Test Gang"
            theme_color = "#386b33"

        display = list_with_theme(MockList())
        assert "Test Gang</span>" in display
        assert "background-color: #386b33;" in display

    def test_list_with_theme_no_color(self):
        """Test list display without theme color."""

        class MockList:
            name = "Test Gang"
            theme_color = None

        display = list_with_theme(MockList())
        assert display == '<span class="">Test Gang</span>'
