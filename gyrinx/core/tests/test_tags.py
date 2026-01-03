import pytest
from django.template.context import make_context as django_make_context

from gyrinx.core.templatetags.custom_tags import (
    credits,
    is_active,
    return_url_field,
    return_url_param,
)
from gyrinx.core.utils import get_return_url


@pytest.fixture
def make_context(rf):
    def make_context_(path):
        return django_make_context(None, rf.get(path))

    return make_context_


def test_is_active(make_context):
    context = make_context("/")
    assert is_active(context, "core:index")


def test_credits_basic_formatting():
    """Test basic credits formatting."""
    assert credits(100) == "100¢"
    assert credits(0) == "0¢"
    assert credits(1500) == "1500¢"


def test_credits_negative_values():
    """Test credits formatting with negative values."""
    assert credits(-50) == "-50¢"
    assert credits(-100) == "-100¢"


def test_credits_show_sign_positive():
    """Test credits formatting with show_sign=True for positive values."""
    assert credits(100, show_sign=True) == "+100¢"
    assert credits(50, show_sign=True) == "+50¢"


def test_credits_show_sign_negative():
    """Test credits formatting with show_sign=True for negative values."""
    # Negative values should show minus sign regardless of show_sign
    assert credits(-100, show_sign=True) == "-100¢"


def test_credits_show_sign_zero():
    """Test credits formatting with show_sign=True for zero."""
    # Zero gets a + sign when show_sign=True (matches format_cost_display behavior)
    assert credits(0, show_sign=True) == "+0¢"


# Tests for get_return_url utility function


def test_get_return_url_from_get_params(rf):
    """Test extracting return_url from GET parameters."""
    request = rf.get("/some-page/", {"return_url": "/campaign/123/"})
    result = get_return_url(request, "/default/")
    assert result == "/campaign/123/"


def test_get_return_url_from_post_params(rf):
    """Test extracting return_url from POST parameters."""
    request = rf.post("/some-page/", {"return_url": "/campaign/456/"})
    result = get_return_url(request, "/default/")
    assert result == "/campaign/456/"


def test_get_return_url_post_takes_priority(rf):
    """Test that POST return_url takes priority over GET."""
    request = rf.post(
        "/some-page/?return_url=/from-get/", {"return_url": "/from-post/"}
    )
    result = get_return_url(request, "/default/")
    assert result == "/from-post/"


def test_get_return_url_falls_back_to_default(rf):
    """Test fallback to default_url when return_url is missing."""
    request = rf.get("/some-page/")
    result = get_return_url(request, "/default-fallback/")
    assert result == "/default-fallback/"


def test_get_return_url_rejects_external_url(rf):
    """Test that external URLs are rejected and fall back to default."""
    request = rf.get("/some-page/", {"return_url": "https://evil.com/steal-data"})
    result = get_return_url(request, "/safe-default/")
    assert result == "/safe-default/"


def test_get_return_url_rejects_javascript_protocol(rf):
    """Test that javascript: URLs are rejected."""
    request = rf.get("/some-page/", {"return_url": "javascript:alert('xss')"})
    result = get_return_url(request, "/safe-default/")
    assert result == "/safe-default/"


def test_get_return_url_handles_special_characters(rf):
    """Test that URLs with query strings are handled correctly."""
    request = rf.get(
        "/some-page/", {"return_url": "/campaign/123/?filter=active&page=2"}
    )
    result = get_return_url(request, "/default/")
    assert result == "/campaign/123/?filter=active&page=2"


# Tests for return_url_param template tag


def test_return_url_param_generates_encoded_param(rf):
    """Test that return_url_param generates properly URL-encoded query parameter."""
    request = rf.get("/current/page/")
    context = django_make_context({"request": request})
    result = return_url_param(context)
    assert result == "return_url=%2Fcurrent%2Fpage%2F"


def test_return_url_param_includes_query_string(rf):
    """Test that return_url_param includes query string from current URL."""
    request = rf.get("/current/page/?filter=active")
    context = django_make_context({"request": request})
    result = return_url_param(context)
    # The full path including query string should be encoded
    assert "return_url=" in result
    assert "%2Fcurrent%2Fpage%2F" in result
    assert "filter" in result


# Tests for return_url_field template tag


def test_return_url_field_renders_hidden_input(rf):
    """Test that return_url_field renders hidden form field."""
    request = rf.get("/")
    context = django_make_context({"request": request, "return_url": "/back/to/here/"})
    result = return_url_field(context)
    assert '<input type="hidden"' in result
    assert 'name="return_url"' in result
    assert 'value="/back/to/here/"' in result


def test_return_url_field_returns_empty_when_missing(rf):
    """Test that return_url_field returns empty string when return_url not in context."""
    request = rf.get("/")
    context = django_make_context({"request": request})
    result = return_url_field(context)
    assert result == ""


def test_return_url_field_escapes_html(rf):
    """Test that return_url_field properly escapes HTML in the value."""
    request = rf.get("/")
    context = django_make_context(
        {"request": request, "return_url": '/page/?q=<script>alert("xss")</script>'}
    )
    result = return_url_field(context)
    # Django's format_html should escape the angle brackets
    assert "<script>" not in result
    assert "&lt;script&gt;" in result or "&#" in result
