import pytest
from django.template.context import make_context as django_make_context

from gyrinx.core.templatetags.custom_tags import credits, is_active


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
