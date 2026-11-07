"""OpenTelemetry tracing for Django and Cloud Run.

TRACING_MODE selects off, console output or Google Cloud Trace. Use span
as a context manager or traced as a decorator for application spans.
"""

import logging
import os
import sys
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import wraps
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

_tracing_enabled = False
_tracer = None
_initialized = False


def _get_project_id():
    """Read GOOGLE_CLOUD_PROJECT or fall back to the hard-coded project ID."""
    return os.getenv("GOOGLE_CLOUD_PROJECT") or "windy-ellipse-440618-p9"


def _get_tracing_mode():
    """Read TRACING_MODE, defaulting to off."""
    return getattr(settings, "TRACING_MODE", "off")


def _get_exporter():
    """Build a console exporter in console mode, otherwise a Cloud Trace exporter."""
    tracing_mode = _get_tracing_mode()

    if tracing_mode == "console":
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        return ConsoleSpanExporter()

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


def _should_force_sampling() -> bool:
    """Force sampling when DEBUG is enabled and tracing mode is gcp."""
    from django.conf import settings

    return getattr(settings, "DEBUG", False) and _get_tracing_mode() == "gcp"


def _init_tracing() -> None:
    """Initialise tracing once unless mode is off.

    Configure Cloud Trace propagation, a mode-specific exporter, Django spans
    and logging context. Force sampling in DEBUG with gcp mode. Log setup
    failures and leave tracing disabled.
    """
    global _tracing_enabled, _tracer, _initialized

    if _initialized:
        return

    _initialized = True

    tracing_mode = _get_tracing_mode()

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
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON

        # Use Cloud Run's X-Cloud-Trace-Context format instead of W3C traceparent.
        set_global_textmap(CloudTraceFormatPropagator())

        # Force sampling only for DEBUG with gcp tracing.
        sampler = ALWAYS_ON if _should_force_sampling() else None
        provider = TracerProvider(sampler=sampler)

        exporter = _get_exporter()
        processor = _get_processor(exporter)
        provider.add_span_processor(processor)

        trace.set_tracer_provider(provider)

        DjangoInstrumentor().instrument()

        # Inject OpenTelemetry span IDs into log records without replacing the log format.
        LoggingInstrumentor().instrument(set_logging_format=False)

        _tracer = trace.get_tracer("gyrinx.tracing")
        _tracing_enabled = True

        sampler_info = ", forced sampling" if _should_force_sampling() else ""
        logger.info(
            f"OpenTelemetry tracing enabled (mode={tracing_mode}{sampler_info}) "
            f"with {exporter.__class__.__name__}"
        )

    except ImportError as e:
        logger.warning(f"OpenTelemetry packages not installed: {e}")
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry tracing: {e}", exc_info=True)


@contextmanager
def span(
    name: str, *, record_exception: bool = True, **attributes: Any
) -> Generator[Any | None]:
    """Yield an application span, or None when tracing is disabled.

    Convert attributes to strings. With record_exception=True, record raised
    exceptions and mark the span as failed before propagating the exception.
    """
    if not _tracing_enabled or _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(name) as current_span:
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


def traced(name: str | None = None, **default_attributes: Any) -> Callable:
    """Wrap a function in a span with optional name and default attributes.

    Default to the function name and preserve its metadata.
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
    """Return whether tracing initialisation succeeded."""
    return _tracing_enabled


def get_gcp_trace_url(trace_id: str) -> str:
    """Build a Cloud Trace console URL for a hexadecimal trace ID."""
    project_id = _get_project_id()
    return (
        f"https://console.cloud.google.com/traces/explorer"
        f";traceId={trace_id}?project={project_id}"
    )


class TraceURLLoggingMiddleware:
    """Log the current request's Cloud Trace URL in DEBUG with gcp tracing."""

    def __init__(self, get_response):
        self.get_response = get_response
        self._should_log = _should_force_sampling()
        if self._should_log:
            logger.info("TraceURLLoggingMiddleware active - will log GCP trace URLs")

    def __call__(self, request):
        response = self.get_response(request)

        if self._should_log and _tracing_enabled:
            self._log_trace_url(request, response)

        return response

    def _log_trace_url(self, request, response) -> None:
        """Log the GCP trace URL for the current request."""
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            span_context = span.get_span_context()

            if span_context.is_valid:
                trace_id = format(span_context.trace_id, "032x")
                url = get_gcp_trace_url(trace_id)
                logger.info(
                    f"Trace {request.method} {request.path} {response.status_code} {url}"
                )
        except Exception as e:
            logger.debug(f"Could not log trace URL: {e}")


def _reset_tracing() -> None:
    """Reset module state so tests can initialise tracing again.

    This does not remove global instrumentors, providers, processors or active
    spans. Use only in isolated tests, normally with mock tracers.
    """
    global _tracing_enabled, _tracer, _initialized
    _tracing_enabled = False
    _tracer = None
    _initialized = False


# Skip the runserver watcher process to avoid duplicate tracing initialisation.
if os.environ.get("RUN_MAIN") == "true" or "runserver" not in sys.argv:
    _init_tracing()
