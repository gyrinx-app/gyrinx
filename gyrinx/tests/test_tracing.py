"""Tests for OpenTelemetry tracing utilities."""

import pytest

from gyrinx import tracing


def test_span_context_manager_works_when_disabled():
    """span() should work as a no-op when tracing is disabled."""
    # In tests, GOOGLE_CLOUD_PROJECT is not set, so tracing is disabled
    with tracing.span("test_operation", test_key="test_value") as span_obj:
        result = 1 + 1

    assert result == 2
    assert span_obj is None  # No-op returns None


def test_span_propagates_exceptions():
    """span() should re-raise exceptions."""
    with pytest.raises(ValueError, match="Test error"):
        with tracing.span("failing_operation"):
            raise ValueError("Test error")


def test_traced_decorator_works():
    """@traced should work as a function decorator."""

    @tracing.traced("test_function")
    def sample_function(x, y):
        return x + y

    result = sample_function(2, 3)
    assert result == 5


def test_traced_decorator_with_attributes():
    """@traced should support default attributes."""

    @tracing.traced("cache_op", cache_type="list_cost")
    def cache_operation(key, value):
        return f"{key}={value}"

    result = cache_operation("test_key", "test_value")
    assert result == "test_key=test_value"


def test_traced_uses_function_name_by_default():
    """@traced should use function name if no name provided."""

    @tracing.traced()
    def my_custom_function():
        return "ok"

    result = my_custom_function()
    assert result == "ok"


def test_traced_preserves_function_metadata():
    """@traced should preserve function name and docstring."""

    @tracing.traced()
    def documented_function():
        """This is a docstring."""
        return True

    assert documented_function.__name__ == "documented_function"
    assert documented_function.__doc__ == "This is a docstring."


def test_is_tracing_enabled():
    """is_tracing_enabled() should return False when not configured."""
    # In tests, GOOGLE_CLOUD_PROJECT is not set
    assert tracing.is_tracing_enabled() is False


def test_nested_spans_work():
    """Nested spans should work correctly."""
    results = []

    with tracing.span("outer") as outer_span:
        results.append("outer_start")
        with tracing.span("inner") as inner_span:
            results.append("inner")
        results.append("outer_end")

    assert results == ["outer_start", "inner", "outer_end"]
    assert outer_span is None
    assert inner_span is None


def test_traced_decorator_propagates_exceptions():
    """@traced should propagate exceptions."""

    @tracing.traced("failing_function")
    def failing_function():
        raise RuntimeError("Function failed")

    with pytest.raises(RuntimeError, match="Function failed"):
        failing_function()
