"""Tests for OpenTelemetry tracing utilities."""

from unittest.mock import MagicMock, Mock, call

import pytest
from django.conf import settings

from gyrinx import tracing


@pytest.fixture
def tracing_disabled():
    """Ensure tracing is disabled for a test."""
    # Save original state
    original_mode = settings.TRACING_MODE
    original_enabled = tracing._tracing_enabled
    original_tracer = tracing._tracer
    original_initialized = tracing._initialized

    # Disable tracing
    settings.TRACING_MODE = "off"
    tracing._reset_tracing()
    tracing._init_tracing()

    yield

    # Restore original state
    settings.TRACING_MODE = original_mode
    tracing._tracing_enabled = original_enabled
    tracing._tracer = original_tracer
    tracing._initialized = original_initialized


@pytest.fixture
def tracing_enabled():
    """Enable tracing for a test with a mock tracer."""
    # Save original state
    original_mode = settings.TRACING_MODE
    original_enabled = tracing._tracing_enabled
    original_tracer = tracing._tracer
    original_initialized = tracing._initialized

    # Enable tracing with console mode (doesn't require GCP)
    settings.TRACING_MODE = "console"
    tracing._reset_tracing()

    # Mock the tracer to avoid actually creating spans
    mock_tracer = Mock()
    mock_span = MagicMock()
    mock_span.__enter__ = Mock(return_value=mock_span)
    mock_span.__exit__ = Mock(return_value=False)
    mock_tracer.start_as_current_span = Mock(return_value=mock_span)

    # Initialize tracing (this will import OpenTelemetry modules)
    tracing._init_tracing()

    # Replace the tracer with our mock
    tracing._tracer = mock_tracer

    yield mock_span

    # Restore original state
    settings.TRACING_MODE = original_mode
    tracing._tracing_enabled = original_enabled
    tracing._tracer = original_tracer
    tracing._initialized = original_initialized


# Tests with tracing DISABLED (default in tests)


def test_span_context_manager_works_when_disabled(tracing_disabled):
    """span() should work as a no-op when tracing is disabled."""
    with tracing.span("test_operation", test_key="test_value") as span_obj:
        result = 1 + 1

    assert result == 2
    assert span_obj is None  # No-op returns None


def test_span_propagates_exceptions_when_disabled(tracing_disabled):
    """span() should re-raise exceptions when disabled."""
    with pytest.raises(ValueError, match="Test error"):
        with tracing.span("failing_operation"):
            raise ValueError("Test error")


def test_traced_decorator_works_when_disabled(tracing_disabled):
    """@traced should work as a function decorator when disabled."""

    @tracing.traced("test_function")
    def sample_function(x, y):
        return x + y

    result = sample_function(2, 3)
    assert result == 5


def test_traced_decorator_with_attributes_when_disabled(tracing_disabled):
    """@traced should support default attributes when disabled."""

    @tracing.traced("cache_op", cache_type="list_cost")
    def cache_operation(key, value):
        return f"{key}={value}"

    result = cache_operation("test_key", "test_value")
    assert result == "test_key=test_value"


def test_traced_uses_function_name_by_default_when_disabled(tracing_disabled):
    """@traced should use function name if no name provided when disabled."""

    @tracing.traced()
    def my_custom_function():
        return "ok"

    result = my_custom_function()
    assert result == "ok"


def test_traced_preserves_function_metadata_when_disabled(tracing_disabled):
    """@traced should preserve function name and docstring when disabled."""

    @tracing.traced()
    def documented_function():
        """This is a docstring."""
        return True

    assert documented_function.__name__ == "documented_function"
    assert documented_function.__doc__ == "This is a docstring."


def test_is_tracing_disabled(tracing_disabled):
    """is_tracing_enabled() should return False when disabled."""
    assert tracing.is_tracing_enabled() is False


def test_nested_spans_work_when_disabled(tracing_disabled):
    """Nested spans should work correctly when disabled."""
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
    """@traced should propagate exceptions when disabled."""

    @tracing.traced("failing_function")
    def failing_function():
        raise RuntimeError("Function failed")

    with pytest.raises(RuntimeError, match="Function failed"):
        failing_function()


# Tests with tracing ENABLED


def test_span_context_manager_works_when_enabled(tracing_enabled):
    """span() should create actual spans when tracing is enabled."""
    mock_span = tracing_enabled

    with tracing.span("test_operation", test_key="test_value") as span_obj:
        result = 1 + 1

    assert result == 2
    assert span_obj is mock_span
    # Verify span was created with correct name
    tracing._tracer.start_as_current_span.assert_called_once_with("test_operation")
    # Verify attributes were set
    mock_span.set_attribute.assert_called_once_with("test_key", "test_value")


def test_span_propagates_exceptions_when_enabled(tracing_enabled):
    """span() should record exceptions and re-raise when enabled."""
    mock_span = tracing_enabled

    with pytest.raises(ValueError, match="Test error"):
        with tracing.span("failing_operation"):
            raise ValueError("Test error")

    # Verify exception was recorded
    mock_span.record_exception.assert_called_once()
    mock_span.set_status.assert_called_once()


def test_traced_decorator_works_when_enabled(tracing_enabled):
    """@traced should create spans for decorated functions when enabled."""

    @tracing.traced("test_function")
    def sample_function(x, y):
        return x + y

    result = sample_function(2, 3)
    assert result == 5
    tracing._tracer.start_as_current_span.assert_called_with("test_function")


def test_traced_decorator_with_attributes_when_enabled(tracing_enabled):
    """@traced should set default attributes when enabled."""
    mock_span = tracing_enabled

    @tracing.traced("cache_op", cache_type="list_cost")
    def cache_operation(key, value):
        return f"{key}={value}"

    result = cache_operation("test_key", "test_value")
    assert result == "test_key=test_value"
    mock_span.set_attribute.assert_called_once_with("cache_type", "list_cost")


def test_traced_uses_function_name_by_default_when_enabled(tracing_enabled):
    """@traced should use function name if no name provided when enabled."""

    @tracing.traced()
    def my_custom_function():
        return "ok"

    result = my_custom_function()
    assert result == "ok"
    tracing._tracer.start_as_current_span.assert_called_with("my_custom_function")


def test_is_tracing_enabled_returns_true(tracing_enabled):
    """is_tracing_enabled() should return True when enabled."""
    assert tracing.is_tracing_enabled() is True


def test_nested_spans_work_when_enabled(tracing_enabled):
    """Nested spans should work correctly when enabled."""
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
    # Verify both spans were created with correct names in order
    assert tracing._tracer.start_as_current_span.call_count == 2
    tracing._tracer.start_as_current_span.assert_has_calls(
        [call("outer"), call("inner")], any_order=False
    )


def test_traced_decorator_propagates_exceptions_when_enabled(tracing_enabled):
    """@traced should propagate exceptions and record them when enabled."""
    mock_span = tracing_enabled

    @tracing.traced("failing_function")
    def failing_function():
        raise RuntimeError("Function failed")

    with pytest.raises(RuntimeError, match="Function failed"):
        failing_function()

    # Verify exception was recorded
    mock_span.record_exception.assert_called_once()
    mock_span.set_status.assert_called_once()
