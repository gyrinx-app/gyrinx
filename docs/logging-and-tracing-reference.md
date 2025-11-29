# Logging and Tracing Reference

This reference documents the logging and tracing systems used in Gyrinx for production observability and debugging.

## Logging System

### Configuration

Gyrinx uses Python's standard logging module with environment-specific handlers.

#### Development Configuration

Location: `gyrinx/settings.py` (lines 305-347)

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "null": {
            "class": "logging.NullHandler",
        },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django.security.DisallowedHost": {
            "handlers": ["null"],
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "gyrinx": {
            "handlers": ["console"],
            "level": "INFO",  # Configurable via GYRINX_LOG_LEVEL
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",  # Configurable via GYRINX_LOG_LEVEL
    },
}
```

#### Production Configuration

Location: `gyrinx/settings_prod.py`

In production, the logging handler is replaced with `google.cloud.logging_v2.handlers.StructuredLogHandler`, which outputs JSON to stdout. Cloud Run captures this output and sends it to Cloud Logging.

```python
GCP_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("GCP_PROJECT_ID", ""))

LOGGING["handlers"]["structured_console"] = {
    "class": "google.cloud.logging_v2.handlers.StructuredLogHandler",
    "project_id": GCP_PROJECT_ID,
}

LOGGING["loggers"]["django.request"]["handlers"] = ["structured_console"]
LOGGING["loggers"]["gyrinx"]["handlers"] = ["structured_console"]
LOGGING["root"]["handlers"] = ["structured_console"]
```

### Trace Correlation

The `RequestMiddleware` from `google.cloud.logging_v2.handlers.middleware` correlates log entries with Cloud Trace spans. This middleware must be placed early in the middleware stack to capture request context.

Location: `gyrinx/settings.py` (line 127)

```python
MIDDLEWARE = [
    "google.cloud.sqlcommenter.django.middleware.SqlCommenter",
    "google.cloud.logging_v2.handlers.middleware.RequestMiddleware",
    # ... other middleware
]
```

The `project_id` parameter in `StructuredLogHandler` is required for proper trace ID formatting in Cloud Logging.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GYRINX_LOG_LEVEL` | Log level for `gyrinx` logger and root logger | `INFO` |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID for trace correlation | None |
| `GCP_PROJECT_ID` | Fallback for GCP project ID | None |

### Logger Names

| Logger | Purpose |
|--------|---------|
| `gyrinx` | Application-level logging |
| `gyrinx.tracker` | Structured event tracking |
| `gyrinx.tracing` | OpenTelemetry tracing status |
| `django.request` | HTTP request errors |
| `django.security.DisallowedHost` | Suppressed (null handler) |

---

## Structured Event Tracking

The `gyrinx.tracker` module provides structured event logging for metrics and analytics.

### Module Location

`gyrinx/tracker.py`

### track()

Emit a structured log event.

```python
def track(
    event: str,
    n: int = 1,
    value: Optional[float] = None,
    **labels: Any
) -> None
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `event` | `str` | Event name (e.g., `stat_config_fallback_used`) |
| `n` | `int` | Count increment. Default: `1` |
| `value` | `Optional[float]` | Numeric value for distributions |
| `**labels` | `Any` | Arbitrary key-value metadata |

#### Return Value

None

#### Behavior

- In production: Outputs JSON via `StructuredLogHandler` for Cloud Logging
- In development: Logs JSON string to console via `gyrinx.tracker` logger
- Non-serializable label values are converted: objects with `id` attribute or `UUID` instances become strings; other non-serializable values are dropped with a debug log

#### Output Format

```json
{
    "event": "stat_config_fallback_used",
    "n": 1,
    "labels": {
        "stat_name": "ammo",
        "model_type": "ContentModStatApply"
    }
}
```

#### Examples

```python
from gyrinx.tracker import track

# Simple event
track("user_login")

# Event with count
track("api_call", n=5)

# Event with distribution value
track("response_time", value=123.45)

# Event with labels
track("stat_config_fallback_used", stat_name="ammo", model_type="ContentModStatApply")

# Event with model object (ID extracted automatically)
track("fighter_created", fighter=fighter_instance)
```

---

## Tracing System (OpenTelemetry)

The `gyrinx.tracing` module provides OpenTelemetry tracing integration with Google Cloud Trace.

To trace locally:

```console
> opentelemetry-instrument manage runserver
```

### Initialization

Tracing is initialized automatically when the module is imported. The module is imported in `gyrinx/wsgi.py` and `gyrinx/asgi.py` before Django loads:

```python
import gyrinx.tracing  # noqa: F401, E402
```

### Configuration

| Condition | Result |
|-----------|--------|
| `GOOGLE_CLOUD_PROJECT` set | Tracing using batch cloud exporter |
| `GOOGLE_CLOUD_PROJECT` not set | Tracing using console settings |

### Dependencies

Required packages for tracing:

```
opentelemetry-sdk>=1.28.0
opentelemetry-exporter-gcp-trace>=1.8.0
opentelemetry-instrumentation-django>=0.49b0
opentelemetry-instrumentation-asgi>=0.49b0
```

### span()

Create a custom span as a context manager.

```python
@contextmanager
def span(
    name: str,
    *,
    record_exception: bool = True,
    **attributes: Any
) -> Generator[Optional[Any], None, None]
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Span name (e.g., `database_query`, `process_fighter`) |
| `record_exception` | `bool` | Record exceptions on span before re-raising. Default: `True` |
| `**attributes` | `Any` | Key-value attributes to attach to span. Values are converted to strings. |

#### Yields

The span object, or `None` if tracing is disabled.

#### Behavior

- When tracing is enabled: Creates a span, attaches attributes, records exceptions if `record_exception=True`
- When tracing is disabled: Yields `None` immediately with no overhead

#### Examples

```python
from gyrinx.tracing import span

# Basic span
with span("calculate_list_cost", list_id=str(lst.id)):
    total = sum(fighter.cost for fighter in lst.fighters.all())

# Nested spans
def process_list(list_obj):
    with span("process_list", list_id=str(list_obj.id)):
        for fighter in list_obj.fighters.all():
            with span("process_fighter", fighter_id=str(fighter.id)):
                calculate_fighter_cost(fighter)

# Exception handling (automatic)
with span("risky_operation"):
    raise ValueError("Something went wrong")  # Recorded on span, then re-raised
```

---

### traced()

Decorator to automatically trace a function.

```python
def traced(
    name: Optional[str] = None,
    **default_attributes: Any
) -> Callable
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `Optional[str]` | Span name. Default: function name |
| `**default_attributes` | `Any` | Default attributes to add to every span |

#### Returns

Decorated function with tracing.

#### Examples

```python
from gyrinx.tracing import traced

# Basic usage (span name = function name)
@traced()
def calculate_fighter_cost(fighter):
    return fighter.calculate_cost()

# Custom span name
@traced("process_advancement")
def apply_stat_advancement(fighter, stat):
    return fighter.apply_advancement(stat)

# With default attributes
@traced("cache_operation", cache_type="list_cost")
def update_cache(key, value):
    cache.set(key, value)
```

---

### is_tracing_enabled()

Check if tracing is currently enabled.

```python
def is_tracing_enabled() -> bool
```

#### Returns

`True` if tracing is enabled and initialized, `False` otherwise.

#### Example

```python
from gyrinx.tracing import is_tracing_enabled

if is_tracing_enabled():
    # Perform tracing-specific logic
    pass
```

---

## Automatic Instrumentation

### Django Request Spans

When tracing is enabled, `DjangoInstrumentor` automatically creates spans for all HTTP requests. These appear in Cloud Trace as the root span for each request.

### Trace Context Propagation

The `X-Cloud-Trace-Context` header is automatically parsed by OpenTelemetry's Django instrumentation. Custom spans created with `span()` or `@traced()` appear as children of the request span in Cloud Trace.

Header format: `TRACE_ID/SPAN_ID;o=TRACE_TRUE`

---

## Cloud Logging Queries

Query events in Cloud Logging:

```
resource.type="cloud_run_revision"
jsonPayload.event="stat_config_fallback_used"
```

Filter by labels:

```
resource.type="cloud_run_revision"
jsonPayload.event="api_call"
jsonPayload.labels.endpoint="..."
```

---

## File Locations

| File | Purpose |
|------|---------|
| `gyrinx/settings.py` | Base logging configuration |
| `gyrinx/settings_prod.py` | Production logging with StructuredLogHandler |
| `gyrinx/tracker.py` | Structured event tracking module |
| `gyrinx/tracing.py` | OpenTelemetry tracing module |
| `gyrinx/wsgi.py` | Tracing initialization for WSGI |
| `gyrinx/asgi.py` | Tracing initialization for ASGI |

---

## Related Documentation

- [Tracking and Metrics](tracking.md) - Usage guide for event tracking
- [Operational Overview](operations/operational-overview.md) - Infrastructure and monitoring
