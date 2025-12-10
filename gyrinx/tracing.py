"""
OpenTelemetry tracing utilities for Google Cloud Run.

This module provides tracing capabilities that integrate with Google Cloud Trace.
Tracing mode is controlled by the TRACING_MODE setting:
- "off": Tracing is disabled (no-op)
- "console": Traces are printed to stdout (for development)
- "gcp": Traces are exported to Google Cloud Trace (for production)

Typical usage:

    # Context manager for custom spans
    from gyrinx.tracing import span

    with span("database_query", query_type="select"):
        results = Model.objects.filter(...)

    # Decorator for tracing functions
    from gyrinx.tracing import traced

    @traced("process_fighter_stats")
    def calculate_stats(fighter):
        return fighter.get_stats()

Error handling is automatic - exceptions are recorded on spans and re-raised.
"""

import logging
import os
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Generator, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Module-level state
_tracing_enabled = False
_tracer = None
_initialized = False


def _get_project_id():
    """Get GCP project ID with fallback for Cloud Run."""
    return os.getenv("GOOGLE_CLOUD_PROJECT") or "windy-ellipse-440618-p9"


def _get_tracing_mode():
    """Get the tracing mode from settings.

    Returns one of: "off", "console", "gcp"
    """
    return getattr(settings, "TRACING_MODE", "off")


def _get_exporter():
    """Get the appropriate span exporter based on TRACING_MODE setting.

    "console": ConsoleSpanExporter for local debugging
    "gcp": CloudTraceSpanExporter for Google Cloud Trace
    """
    tracing_mode = _get_tracing_mode()

    if tracing_mode == "console":
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        return ConsoleSpanExporter()

    # Default to GCP exporter for "gcp" mode
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

    project_id = _get_project_id()
    return CloudTraceSpanExporter(project_id=project_id)


def _get_processor(exporter):
    tracing_mode = _get_tracing_mode()

    if tracing_mode == "console":
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        logger.info("Using SimpleSpanProcessor for tracing (console mode)")
        return SimpleSpanProcessor(exporter)
    else:
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        logger.info("Using BatchSpanProcessor for tracing")
        return BatchSpanProcessor(exporter)


def _init_tracing() -> None:
    """Initialize OpenTelemetry tracing based on TRACING_MODE setting.

    TRACING_MODE options:
    - "off": Tracing is disabled (no-op) - no OpenTelemetry imports or setup
    - "console": Traces are printed to stdout (for development)
    - "gcp": Traces are exported to Google Cloud Trace (for production)

    This configures:
    1. CloudTraceFormatPropagator - parses X-Cloud-Trace-Context header from Cloud Run
    2. Appropriate exporter based on mode
    3. Django auto-instrumentation (automatic request spans)

    Called automatically on module import.
    """
    global _tracing_enabled, _tracer, _initialized

    if _initialized:
        return

    _initialized = True

    tracing_mode = _get_tracing_mode()

    # If tracing is off, do nothing - this is a no-op
    if tracing_mode == "off":
        logger.debug("Tracing disabled (TRACING_MODE=off)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.propagators.cloud_trace_propagator import (
            CloudTraceFormatPropagator,
        )
        from opentelemetry.sdk.trace import TracerProvider

        # Configure Cloud Trace propagator FIRST
        # This tells OpenTelemetry to parse X-Cloud-Trace-Context header (GCP format)
        # instead of the default W3C traceparent format
        set_global_textmap(CloudTraceFormatPropagator())

        # Create tracer provider
        provider = TracerProvider()

        # Add exporter with appropriate processor based on mode
        exporter = _get_exporter()
        processor = _get_processor(exporter)
        provider.add_span_processor(processor)

        # Set as global tracer provider
        trace.set_tracer_provider(provider)

        # Auto-instrument Django (adds automatic request spans)
        DjangoInstrumentor().instrument()

        # Auto-instrument logging (injects trace context into log records)
        # This ensures StructuredLogHandler uses OpenTelemetry span IDs
        LoggingInstrumentor().instrument(set_logging_format=False)

        # Get tracer for manual spans
        _tracer = trace.get_tracer("gyrinx.tracing")
        _tracing_enabled = True

        logger.info(
            f"OpenTelemetry tracing enabled (mode={tracing_mode}) "
            f"with {exporter.__class__.__name__}"
        )

    except ImportError as e:
        logger.warning(f"OpenTelemetry packages not installed: {e}")
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry tracing: {e}", exc_info=True)


@contextmanager
def span(
    name: str, *, record_exception: bool = True, **attributes: Any
) -> Generator[Optional[Any], None, None]:
    """Create a custom span as a context manager.

    Args:
        name: Span name (e.g., "database_query", "process_fighter")
        record_exception: If True, record exceptions on the span before re-raising
        **attributes: Key-value attributes to attach to span

    Yields:
        The span object (or None if tracing disabled)

    Example:
        with span("calculate_list_cost", list_id=str(lst.id)):
            total = sum(fighter.cost for fighter in lst.fighters.all())
    """
    if not _tracing_enabled or _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(name) as current_span:
        # Add attributes
        for key, value in attributes.items():
            current_span.set_attribute(key, str(value))

        try:
            yield current_span
        except Exception as e:
            if record_exception:
                from opentelemetry.trace import Status, StatusCode

                current_span.record_exception(e)
                current_span.set_status(Status(StatusCode.ERROR))
            raise


def traced(name: Optional[str] = None, **default_attributes: Any) -> Callable:
    """Decorator to automatically trace a function.

    Args:
        name: Optional span name (defaults to function name)
        **default_attributes: Default attributes to add to span

    Returns:
        Decorated function

    Example:
        @traced("process_advancement")
        def apply_stat_advancement(fighter, stat):
            return fighter.apply_advancement(stat)

        # With default attributes
        @traced("cache_operation", cache_type="list_cost")
        def update_cache(key, value):
            cache.set(key, value)
    """

    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(span_name, **default_attributes):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def is_tracing_enabled() -> bool:
    """Check if tracing is currently enabled.

    Returns:
        True if tracing is enabled and initialized, False otherwise.
    """
    return _tracing_enabled


def _reset_tracing() -> None:
    """Reset tracing state for testing purposes.

    This is intended for test scenarios where you need to re-initialize
    tracing with different settings. It clears the initialization state
    and resets all module-level variables.

    WARNING: This should only be used in tests!
    """
    global _tracing_enabled, _tracer, _initialized
    _tracing_enabled = False
    _tracer = None
    _initialized = False


# Initialize tracing on module import
_init_tracing()
