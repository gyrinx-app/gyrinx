from gyrinx.core.templatetags.color_tags import (
    list_with_theme,
    theme_square,
)


def test_theme_square_with_color():
    """Test theme square generation with a theme color."""

    class MockList:
        name = "Test Gang"
        theme_color = "#386b33"

    square = theme_square(MockList())
    assert 'class="d-inline-block rounded "' in square
    assert "background-color: #386b33;" in square
    assert "border: 1px solid rgba(0,0,0,0.15);" in square


def test_theme_square_without_color():
    """Test theme square with no color returns empty."""

    class MockList:
        name = "Test Gang"
        theme_color = None

    square = theme_square(MockList())
    assert square == ""


def test_list_with_theme_colored():
    """Test list display with theme color."""

    class MockList:
        name = "Test Gang"
        theme_color = "#386b33"

    display = list_with_theme(MockList())
    assert "Test Gang</span>" in display
    assert "background-color: #386b33;" in display


def test_list_with_theme_no_color():
    """Test list display without theme color."""

    class MockList:
        name = "Test Gang"
        theme_color = None

    display = list_with_theme(MockList())
    assert display == '<span class="">Test Gang</span>'


def test_list_with_theme_escapes_name():
    """A malicious list name must be HTML-escaped, not rendered as markup."""

    class MockList:
        name = "<script>alert(1)</script>"
        theme_color = "#386b33"

    display = list_with_theme(MockList())
    assert "<script>" not in display
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in display


def test_list_with_theme_escapes_name_no_color():
    """Name escaping also applies on the no-theme-color branch."""

    class MockList:
        name = "<script>alert(1)</script>"
        theme_color = None

    display = list_with_theme(MockList())
    assert "<script>" not in display
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in display


def test_list_with_theme_escapes_extra_classes():
    """extra_classes is interpolated into markup and must be escaped."""

    class MockList:
        name = "Test Gang"
        theme_color = None

    display = list_with_theme(MockList(), extra_classes='"><script>alert(1)</script>')
    assert "<script>" not in display
    # The payload must be escaped in place, not silently dropped.
    assert "&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in display


def test_theme_square_escapes_extra_classes():
    """extra_classes on theme_square must be escaped."""

    class MockList:
        name = "Test Gang"
        theme_color = "#386b33"

    square = theme_square(MockList(), extra_classes='"><script>alert(1)</script>')
    assert "<script>" not in square
    # The payload must be escaped in place, not silently dropped.
    assert "&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in square
