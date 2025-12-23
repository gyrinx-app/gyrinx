"""Custom CloudLoggingFilter that handles parent/child spanId correctly.

This module provides a trace-aware logging filter and handler that fixes the spanId
mismatch between Cloud Run request logs and application logs.

Problem:
- Cloud Run request logs use parent spanId from X-Cloud-Trace-Context header
- App logs were using child spanId from OpenTelemetry DjangoInstrumentor
- This caused app logs to not nest under request logs in Cloud Logging

Solution:
- For request-level logs: use parent spanId (nests under Cloud Run logs)
- For custom span logs: use child spanId (correlates with Cloud Trace spans)

Detection is based on span.kind:
- SpanKind.SERVER = Root request span (created by DjangoInstrumentor)
- SpanKind.INTERNAL = Custom/nested span (created by application code)
"""

import logging
from typing import Optional, Tuple

from google.cloud.logging_v2.handlers.handlers import CloudLoggingFilter
from google.cloud.logging_v2.handlers.structured_log import StructuredLogHandler
from google.cloud.logging_v2.handlers._helpers import get_request_data_from_django

try:
    import opentelemetry.trace
    from opentelemetry.trace import format_span_id, format_trace_id

    HAS_OPENTELEMETRY = True
except ImportError:
    HAS_OPENTELEMETRY = False


class TraceAwareCloudLoggingFilter(CloudLoggingFilter):
    """
    CloudLoggingFilter that uses parent spanId for request-level logs
    and child spanId for custom span logs.

    This fixes the spanId mismatch where:
    - Cloud Run request logs have parent spanId from X-Cloud-Trace-Context
    - App logs had child spanId from OpenTelemetry DjangoInstrumentor

    Now:
    - Request-level logs use parent spanId (nests under Cloud Run logs)
    - Custom span logs use child spanId (correlates with Cloud Trace spans)
    """

    def filter(self, record):
        # Get HTTP request data and header-based trace context
        http_request, header_trace_id, header_span_id, header_sampled = (
            get_request_data_from_django()
        )

        # Get OpenTelemetry span context
        otel_trace_id, otel_span_id, otel_sampled, is_custom_span = (
            self._get_otel_context()
        )

        # Determine which spanId to use
        if otel_trace_id and header_span_id:
            # We have both OTel and header context
            # Use child spanId only if we're in a custom span
            if is_custom_span:
                span_id = otel_span_id  # Correlate with custom span in Cloud Trace
            else:
                span_id = header_span_id  # Nest under Cloud Run request log
            trace_id = otel_trace_id
            sampled = otel_sampled
        elif otel_trace_id:
            # Only OTel context (rare - no incoming header)
            span_id = otel_span_id
            trace_id = otel_trace_id
            sampled = otel_sampled
        else:
            # Only header context (OTel not active)
            span_id = header_span_id
            trace_id = header_trace_id
            sampled = header_sampled

        # Format trace path if we have project
        if trace_id and self.project:
            trace_id = f"projects/{self.project}/traces/{trace_id}"

        # Set record attributes (same pattern as CloudLoggingFilter)
        # Manual overrides via extra= take precedence
        record._resource = getattr(record, "resource", None)
        record._trace = getattr(record, "trace", trace_id) or None
        record._span_id = getattr(record, "span_id", span_id) or None
        record._trace_sampled = bool(getattr(record, "trace_sampled", sampled))
        record._http_request = getattr(record, "http_request", http_request)
        record._source_location = CloudLoggingFilter._infer_source_location(record)

        # Handle labels (from parent class logic)
        user_labels = getattr(record, "labels", {})
        record._labels = {**self.default_labels, **user_labels} or None

        return True

    def _get_otel_context(self) -> Tuple[Optional[str], Optional[str], bool, bool]:
        """Get trace context from current OpenTelemetry span.

        Returns:
            Tuple of (trace_id, span_id, sampled, is_custom_span)
        """
        if not HAS_OPENTELEMETRY:
            return None, None, False, False

        span = opentelemetry.trace.get_current_span()
        if span == opentelemetry.trace.span.INVALID_SPAN:
            return None, None, False, False

        context = span.get_span_context()
        trace_id = format_trace_id(context.trace_id)
        span_id = format_span_id(context.span_id)
        sampled = context.trace_flags.sampled

        # Detect if this is a custom span vs root request span
        # DjangoInstrumentor sets SERVER for root requests, INTERNAL for nested
        is_custom_span = (
            getattr(span, "kind", None) != opentelemetry.trace.SpanKind.SERVER
        )

        return trace_id, span_id, sampled, is_custom_span


class TraceAwareStructuredLogHandler(StructuredLogHandler):
    """StructuredLogHandler that uses our custom TraceAwareCloudLoggingFilter.

    This handler is a drop-in replacement for StructuredLogHandler that properly
    handles the parent/child spanId correlation for Cloud Logging.
    """

    def __init__(
        self,
        *,
        labels=None,
        stream=None,
        project_id=None,
        json_encoder_cls=None,
        **kwargs,
    ):
        # Call StreamHandler init directly to skip StructuredLogHandler's filter setup
        logging.StreamHandler.__init__(self, stream=stream)
        self.project_id = project_id

        # Use our custom filter instead of default CloudLoggingFilter
        log_filter = TraceAwareCloudLoggingFilter(
            project=project_id, default_labels=labels
        )
        self.addFilter(log_filter)

        # Store json encoder class (used by StructuredLogHandler.emit)
        self._json_encoder_cls = json_encoder_cls
