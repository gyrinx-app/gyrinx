"""Tracing context managers, decorators and exception propagation in enabled and disabled modes."""

from unittest.mock import MagicMock, Mock, call

import pytest
from django.conf import settings

from gyrinx import tracing


@pytest.fixture
def tracing_disabled():
    """Ensure tracing is disabled for a test."""
    original_mode = settings.TRACING_MODE
    original_enabled = tracing._tracing_enabled
    original_tracer = tracing._tracer
    original_initialized = tracing._initialized

    settings.TRACING_MODE = "off"
    tracing._reset_tracing()
    tracing._init_tracing()

    yield

    settings.TRACING_MODE = original_mode
    tracing._tracing_enabled = original_enabled
    tracing._tracer = original_tracer
    tracing._initialized = original_initialized


@pytest.fixture
def tracing_enabled():
    """Enable tracing for a test with a mock tracer."""
    original_mode = settings.TRACING_MODE
    original_enabled = tracing._tracing_enabled
    original_tracer = tracing._tracer
    original_initialized = tracing._initialized

    # Use console mode without requiring Google Cloud credentials.
    settings.TRACING_MODE = "console"
    tracing._reset_tracing()

    # Keep real spans out of these unit tests.
    mock_tracer = Mock()
    mock_span = MagicMock()
    mock_span.__enter__ = Mock(return_value=mock_span)
    mock_span.__exit__ = Mock(return_value=False)
    mock_tracer.start_as_current_span = Mock(return_value=mock_span)

    tracing._init_tracing()

    tracing._tracer = mock_tracer

    yield mock_span

    settings.TRACING_MODE = original_mode
    tracing._tracing_enabled = original_enabled
    tracing._tracer = original_tracer
    tracing._initialized = original_initialized


def test_span_context_manager_works_when_disabled(tracing_disabled):

    with tracing.span("test_operation", test_key="test_value") as span_obj:
        result = 1 + 1

    assert result == 2
    assert span_obj is None  # No-op returns None


def test_span_propagates_exceptions_when_disabled(tracing_disabled):

    with pytest.raises(ValueError, match="Test error"):
        with tracing.span("failing_operation"):
            raise ValueError("Test error")


def test_traced_decorator_works_when_disabled(tracing_disabled):

    @tracing.traced("test_function")
    def sample_function(x, y):
        return x + y

    result = sample_function(2, 3)
    assert result == 5


def test_traced_decorator_with_attributes_when_disabled(tracing_disabled):

    @tracing.traced("cache_op", cache_type="list_cost")
    def cache_operation(key, value):
        return f"{key}={value}"

    result = cache_operation("test_key", "test_value")
    assert result == "test_key=test_value"


def test_traced_uses_function_name_by_default_when_disabled(tracing_disabled):

    @tracing.traced()
    def my_custom_function():
        return "ok"

    result = my_custom_function()
    assert result == "ok"


def test_traced_preserves_function_metadata_when_disabled(tracing_disabled):

    @tracing.traced()
    def documented_function():
        """This is a docstring."""
        return True

    assert documented_function.__name__ == "documented_function"
    assert documented_function.__doc__ == "This is a docstring."


def test_is_tracing_disabled(tracing_disabled):

    assert tracing.is_tracing_enabled() is False


def test_nested_spans_work_when_disabled(tracing_disabled):

    results = []

    with tracing.span("outer") as outer_span:
        results.append("outer_start")
        with tracing.span("inner") as inner_span:
            results.append("inner")
        results.append("outer_end")

    assert results == ["outer_start", "inner", "outer_end"]
    assert outer_span is None
    assert inner_span is None


def test_traced_decorator_propagates_exceptions_when_disabled(tracing_disabled):

    @tracing.traced("failing_function")
    def failing_function():
        raise RuntimeError("Function failed")

    with pytest.raises(RuntimeError, match="Function failed"):
        failing_function()


def test_span_context_manager_works_when_enabled(tracing_enabled):

    mock_span = tracing_enabled

    with tracing.span("test_operation", test_key="test_value") as span_obj:
        result = 1 + 1

    assert result == 2
    assert span_obj is mock_span
    tracing._tracer.start_as_current_span.assert_called_once_with("test_operation")
    mock_span.set_attribute.assert_called_once_with("test_key", "test_value")


def test_span_propagates_exceptions_when_enabled(tracing_enabled):

    mock_span = tracing_enabled

    with pytest.raises(ValueError, match="Test error"):
        with tracing.span("failing_operation"):
            raise ValueError("Test error")

    mock_span.record_exception.assert_called_once()
    mock_span.set_status.assert_called_once()


def test_traced_decorator_works_when_enabled(tracing_enabled):

    @tracing.traced("test_function")
    def sample_function(x, y):
        return x + y

    result = sample_function(2, 3)
    assert result == 5
    tracing._tracer.start_as_current_span.assert_called_with("test_function")


def test_traced_decorator_with_attributes_when_enabled(tracing_enabled):

    mock_span = tracing_enabled

    @tracing.traced("cache_op", cache_type="list_cost")
    def cache_operation(key, value):
        return f"{key}={value}"

    result = cache_operation("test_key", "test_value")
    assert result == "test_key=test_value"
    mock_span.set_attribute.assert_called_once_with("cache_type", "list_cost")


def test_traced_uses_function_name_by_default_when_enabled(tracing_enabled):

    @tracing.traced()
    def my_custom_function():
        return "ok"

    result = my_custom_function()
    assert result == "ok"
    tracing._tracer.start_as_current_span.assert_called_with("my_custom_function")


def test_is_tracing_enabled_returns_true(tracing_enabled):

    assert tracing.is_tracing_enabled() is True


def test_nested_spans_work_when_enabled(tracing_enabled):

    mock_span = tracing_enabled
    results = []

    with tracing.span("outer") as outer_span:
        results.append("outer_start")
        with tracing.span("inner") as inner_span:
            results.append("inner")
        results.append("outer_end")

    assert results == ["outer_start", "inner", "outer_end"]
    assert outer_span is mock_span
    assert inner_span is mock_span
    assert tracing._tracer.start_as_current_span.call_count == 2
    tracing._tracer.start_as_current_span.assert_has_calls(
        [call("outer"), call("inner")], any_order=False
    )


def test_traced_decorator_propagates_exceptions_when_enabled(tracing_enabled):

    mock_span = tracing_enabled

    @tracing.traced("failing_function")
    def failing_function():
        raise RuntimeError("Function failed")

    with pytest.raises(RuntimeError, match="Function failed"):
        failing_function()

    mock_span.record_exception.assert_called_once()
    mock_span.set_status.assert_called_once()
