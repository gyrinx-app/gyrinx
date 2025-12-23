"""Tests for TraceAwareCloudLoggingFilter."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from gyrinx.logging_filter import (
    TraceAwareCloudLoggingFilter,
    TraceAwareStructuredLogHandler,
)


class TestTraceAwareCloudLoggingFilter:
    """Tests for TraceAwareCloudLoggingFilter."""

    @pytest.fixture
    def filter_instance(self):
        """Create a filter instance with a test project."""
        return TraceAwareCloudLoggingFilter(
            project="test-project", default_labels={"env": "test"}
        )

    @pytest.fixture
    def log_record(self):
        """Create a basic log record."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        return record

    def test_request_level_log_uses_header_span_id(self, filter_instance, log_record):
        """Request-level logs should use parent spanId from header."""
        header_span_id = "abc123header"
        header_trace_id = "trace123"
        otel_span_id = "def456otel"

        # Mock Django request data to return header context
        with patch("gyrinx.logging_filter.get_request_data_from_django") as mock_django:
            mock_django.return_value = (
                {"method": "GET"},  # http_request
                header_trace_id,  # trace_id
                header_span_id,  # span_id
                True,  # sampled
            )

            # Mock OpenTelemetry context with SERVER span kind (root request)
            with patch.object(filter_instance, "_get_otel_context") as mock_otel:
                mock_otel.return_value = (
                    header_trace_id,  # trace_id (same as header)
                    otel_span_id,  # span_id (different - child)
                    True,  # sampled
                    False,  # is_custom_span = False (SERVER span)
                )

                result = filter_instance.filter(log_record)

                assert result is True
                # Should use header span_id (parent) for request-level logs
                assert log_record._span_id == header_span_id
                assert (
                    log_record._trace
                    == f"projects/test-project/traces/{header_trace_id}"
                )
                assert log_record._trace_sampled is True

    def test_custom_span_log_uses_otel_span_id(self, filter_instance, log_record):
        """Custom span logs should use child spanId from OpenTelemetry."""
        header_span_id = "abc123header"
        header_trace_id = "trace123"
        otel_span_id = "def456otel"

        with patch("gyrinx.logging_filter.get_request_data_from_django") as mock_django:
            mock_django.return_value = (
                {"method": "GET"},
                header_trace_id,
                header_span_id,
                True,
            )

            with patch.object(filter_instance, "_get_otel_context") as mock_otel:
                mock_otel.return_value = (
                    header_trace_id,
                    otel_span_id,
                    True,
                    True,  # is_custom_span = True (INTERNAL span)
                )

                result = filter_instance.filter(log_record)

                assert result is True
                # Should use OTel span_id (child) for custom span logs
                assert log_record._span_id == otel_span_id

    def test_fallback_to_header_when_no_otel_context(self, filter_instance, log_record):
        """Falls back to header when OpenTelemetry context is not available."""
        header_span_id = "abc123header"
        header_trace_id = "trace123"

        with patch("gyrinx.logging_filter.get_request_data_from_django") as mock_django:
            mock_django.return_value = (
                {"method": "GET"},
                header_trace_id,
                header_span_id,
                True,
            )

            with patch.object(filter_instance, "_get_otel_context") as mock_otel:
                # No OTel context
                mock_otel.return_value = (None, None, False, False)

                result = filter_instance.filter(log_record)

                assert result is True
                assert log_record._span_id == header_span_id
                assert (
                    log_record._trace
                    == f"projects/test-project/traces/{header_trace_id}"
                )

    def test_fallback_to_otel_when_no_header(self, filter_instance, log_record):
        """Falls back to OTel when no header context available."""
        otel_span_id = "def456otel"
        otel_trace_id = "trace456"

        with patch("gyrinx.logging_filter.get_request_data_from_django") as mock_django:
            # No header context
            mock_django.return_value = (None, None, None, False)

            with patch.object(filter_instance, "_get_otel_context") as mock_otel:
                mock_otel.return_value = (
                    otel_trace_id,
                    otel_span_id,
                    True,
                    False,
                )

                result = filter_instance.filter(log_record)

                assert result is True
                assert log_record._span_id == otel_span_id
                assert (
                    log_record._trace == f"projects/test-project/traces/{otel_trace_id}"
                )

    def test_manual_override_via_extra(self, filter_instance, log_record):
        """Manual override via extra= parameter takes precedence."""
        header_span_id = "abc123header"
        override_span_id = "override123"
        override_trace = "projects/test-project/traces/override_trace"

        # Set manual overrides on record (simulating extra= parameter)
        log_record.span_id = override_span_id
        log_record.trace = override_trace

        with patch("gyrinx.logging_filter.get_request_data_from_django") as mock_django:
            mock_django.return_value = (
                {"method": "GET"},
                "trace123",
                header_span_id,
                True,
            )

            with patch.object(filter_instance, "_get_otel_context") as mock_otel:
                mock_otel.return_value = ("trace123", "otel456", True, False)

                result = filter_instance.filter(log_record)

                assert result is True
                # Manual overrides should be used
                assert log_record._span_id == override_span_id
                assert log_record._trace == override_trace

    def test_labels_are_merged(self, filter_instance, log_record):
        """Default labels and user labels should be merged."""
        log_record.labels = {"user_label": "value"}

        with patch("gyrinx.logging_filter.get_request_data_from_django") as mock_django:
            mock_django.return_value = (None, None, None, False)

            with patch.object(filter_instance, "_get_otel_context") as mock_otel:
                mock_otel.return_value = (None, None, False, False)

                filter_instance.filter(log_record)

                # Should have both default and user labels
                assert log_record._labels == {"env": "test", "user_label": "value"}

    def test_no_context_available(self, filter_instance, log_record):
        """Handles case where no context is available at all."""
        with patch("gyrinx.logging_filter.get_request_data_from_django") as mock_django:
            mock_django.return_value = (None, None, None, False)

            with patch.object(filter_instance, "_get_otel_context") as mock_otel:
                mock_otel.return_value = (None, None, False, False)

                result = filter_instance.filter(log_record)

                assert result is True
                assert log_record._span_id is None
                assert log_record._trace is None
                assert log_record._trace_sampled is False


class TestGetOtelContext:
    """Tests for _get_otel_context method."""

    @pytest.fixture
    def filter_instance(self):
        return TraceAwareCloudLoggingFilter(project="test-project")

    def test_returns_none_when_no_opentelemetry(self, filter_instance):
        """Returns None values when OpenTelemetry is not available."""
        with patch("gyrinx.logging_filter.HAS_OPENTELEMETRY", False):
            result = filter_instance._get_otel_context()
            assert result == (None, None, False, False)

    def test_returns_none_for_invalid_span(self, filter_instance):
        """Returns None values for invalid span."""
        with patch("gyrinx.logging_filter.opentelemetry.trace") as mock_trace:
            mock_trace.get_current_span.return_value = mock_trace.span.INVALID_SPAN
            result = filter_instance._get_otel_context()
            assert result == (None, None, False, False)

    def test_detects_server_span_as_not_custom(self, filter_instance):
        """SERVER span kind should not be detected as custom span."""
        with patch("gyrinx.logging_filter.opentelemetry") as mock_otel:
            mock_span = MagicMock()
            mock_span.kind = mock_otel.trace.SpanKind.SERVER
            mock_context = MagicMock()
            mock_context.trace_id = 12345
            mock_context.span_id = 67890
            mock_context.trace_flags.sampled = True
            mock_span.get_span_context.return_value = mock_context

            mock_otel.trace.get_current_span.return_value = mock_span
            mock_otel.trace.span.INVALID_SPAN = MagicMock()
            mock_otel.trace.format_trace_id.return_value = "trace123"
            mock_otel.trace.format_span_id.return_value = "span456"

            with patch(
                "gyrinx.logging_filter.format_trace_id", return_value="trace123"
            ):
                with patch(
                    "gyrinx.logging_filter.format_span_id", return_value="span456"
                ):
                    result = filter_instance._get_otel_context()

                    # is_custom_span should be False for SERVER spans
                    assert result[3] is False

    def test_detects_internal_span_as_custom(self, filter_instance):
        """INTERNAL span kind should be detected as custom span."""
        with patch("gyrinx.logging_filter.opentelemetry") as mock_otel:
            mock_span = MagicMock()
            mock_span.kind = mock_otel.trace.SpanKind.INTERNAL
            mock_context = MagicMock()
            mock_context.trace_id = 12345
            mock_context.span_id = 67890
            mock_context.trace_flags.sampled = True
            mock_span.get_span_context.return_value = mock_context

            mock_otel.trace.get_current_span.return_value = mock_span
            mock_otel.trace.span.INVALID_SPAN = MagicMock()
            mock_otel.trace.SpanKind.SERVER = "SERVER"

            with patch(
                "gyrinx.logging_filter.format_trace_id", return_value="trace123"
            ):
                with patch(
                    "gyrinx.logging_filter.format_span_id", return_value="span456"
                ):
                    result = filter_instance._get_otel_context()

                    # is_custom_span should be True for INTERNAL spans
                    assert result[3] is True


class TestTraceAwareStructuredLogHandler:
    """Tests for TraceAwareStructuredLogHandler."""

    def test_uses_custom_filter(self):
        """Handler should use TraceAwareCloudLoggingFilter."""
        handler = TraceAwareStructuredLogHandler(
            project_id="test-project", labels={"env": "test"}
        )

        # Should have exactly one filter of our custom type
        custom_filters = [
            f for f in handler.filters if isinstance(f, TraceAwareCloudLoggingFilter)
        ]
        assert len(custom_filters) == 1

        # Check filter configuration
        custom_filter = custom_filters[0]
        assert custom_filter.project == "test-project"
        assert custom_filter.default_labels == {"env": "test"}

    def test_stores_project_id(self):
        """Handler should store project_id attribute."""
        handler = TraceAwareStructuredLogHandler(project_id="my-project")
        assert handler.project_id == "my-project"

    def test_stores_json_encoder(self):
        """Handler should store json_encoder_cls attribute."""
        import json

        handler = TraceAwareStructuredLogHandler(
            project_id="test", json_encoder_cls=json.JSONEncoder
        )
        assert handler._json_encoder_cls == json.JSONEncoder
