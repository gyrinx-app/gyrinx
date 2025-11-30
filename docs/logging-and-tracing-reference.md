# Logging and Tracing Reference

This reference documents the logging, tracing, and event tracking systems in Gyrinx.

---

## Logging System

### Configuration

Gyrinx uses Python's standard logging module with environment-specific handlers.

#### Base Configuration

Location: `gyrinx/settings.py` (lines 309-351)

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

Location: `gyrinx/settings_prod.py` (lines 15-27)

In production, the logging handler is replaced with `google.cloud.logging_v2.handlers.StructuredLogHandler`, which outputs JSON to stdout. Cloud Run captures this output and sends it to Cloud Logging.

```python
GCP_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or "windy-ellipse-440618-p9"

LOGGING["handlers"]["structured_console"] = {
    "class": "google.cloud.logging_v2.handlers.StructuredLogHandler",
    "project_id": GCP_PROJECT_ID,
}

LOGGING["loggers"]["django.request"]["handlers"] = ["structured_console"]
LOGGING["loggers"]["django.request"]["propagate"] = False

LOGGING["loggers"]["gyrinx"]["handlers"] = ["structured_console"]
LOGGING["loggers"]["gyrinx"]["propagate"] = False

LOGGING["root"]["handlers"] = ["structured_console"]
```

The `project_id` parameter is required for proper trace ID formatting in Cloud Logging.

### Trace Correlation

The `RequestMiddleware` from `google.cloud.logging_v2.handlers.middleware` correlates log entries with Cloud Trace spans.

Location: `gyrinx/settings.py` (lines 127-147)

```python
MIDDLEWARE = [
    "google.cloud.sqlcommenter.django.middleware.SqlCommenter",
    "google.cloud.logging_v2.handlers.middleware.RequestMiddleware",
    # ... other middleware
]
```

### Logger Names

| Logger | Purpose |
|--------|---------|
| `gyrinx` | Application-level logging |
| `gyrinx.tracker` | Structured event tracking |
| `gyrinx.tracing` | OpenTelemetry tracing status |
| `gyrinx.query` | SQL query capture utilities |
| `django.request` | HTTP request errors |
| `django.db.backends` | SQL query logging (development) |
| `django.security.DisallowedHost` | Suppressed (null handler) |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GYRINX_LOG_LEVEL` | Log level for `gyrinx` logger and root logger | `INFO` |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID for trace correlation | None |
| `GCP_PROJECT_ID` | Fallback for GCP project ID | None |

---

## SQL Debugging

Location: `gyrinx/settings_dev.py` (lines 43-155)

Development configuration adds SQL query logging with slow query detection and EXPLAIN plan capture.

### Log Files

| File | Description |
|------|-------------|
| `logs/sql.log` | All SQL queries (rotating, 10 MB max, 5 backups) |
| `logs/slow_sql.log` | Slow queries with EXPLAIN plans |

If `logs/` is not writable, falls back to `$TMPDIR/gyrinx_logs/`.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SQL_DEBUG` | Enable SQL query logging (`True`/`False`) | `False` |
| `SQL_MIN_DURATION` | Slow query threshold in seconds | `0.01` |
| `SQL_EXPLAIN_ANALYZE` | Include ANALYZE in EXPLAIN (`True`/`False`) | `False` |
| `SQL_EXPLAIN_DB_ALIAS` | Database alias for EXPLAIN queries | `default` |

### SlowQueryFilter

Class: `gyrinx.settings_dev.SlowQueryFilter`

Filters log records to only include queries with `duration >= SQL_MIN_DURATION`.

### ExplainFileHandler

Class: `gyrinx.settings_dev.ExplainFileHandler`

Extends `RotatingFileHandler`. Appends EXPLAIN plans to slow query log entries.

**Behavior:**

- Only runs EXPLAIN on SELECT statements
- Skips EXPLAIN queries to avoid recursion
- Uses `SQL_EXPLAIN_DB_ALIAS` for database connection
- When `SQL_EXPLAIN_ANALYZE=True`, executes the query (use with caution)

**Output format:**

```
{log_message}
{EXPLAIN plan line 1}
{EXPLAIN plan line 2}
...
--------------------------------------------------------------------------------
```

See [SQL Debugging Guide](sql-debugging.md) for usage instructions.

---

## SqlCommenter Middleware

Location: `gyrinx/settings.py` (lines 128, 439-442)

Adds SQL comments containing request metadata for Cloud SQL Query Insights.

```python
MIDDLEWARE = [
    "google.cloud.sqlcommenter.django.middleware.SqlCommenter",
    # ...
]

SQLCOMMENTER_WITH_CONTROLLER = True
SQLCOMMENTER_WITH_FRAMEWORK = True
SQLCOMMENTER_WITH_ROUTE = True
SQLCOMMENTER_WITH_APP_NAME = True
```

### Configuration Options

| Setting | Description | Value |
|---------|-------------|-------|
| `SQLCOMMENTER_WITH_CONTROLLER` | Include view/controller name | `True` |
| `SQLCOMMENTER_WITH_FRAMEWORK` | Include framework identifier | `True` |
| `SQLCOMMENTER_WITH_ROUTE` | Include URL route | `True` |
| `SQLCOMMENTER_WITH_APP_NAME` | Include Django app name | `True` |

### Output Format

SQL queries are annotated with comments:

```sql
SELECT * FROM core_list /*controller='list_detail',framework='django',route='/list/%s/'*/
```

---

## Query Debugging Utilities

Module: `gyrinx/query.py`

Utilities for capturing and profiling SQL queries during development and testing.

### QueryInfo

Dataclass containing captured query information.

```python
@dataclass
class QueryInfo:
    count: int              # Number of SQL statements
    total_time: float       # Sum of execution times (seconds)
    queries: List[Dict]     # Raw query entries with "sql" and "time" keys
```

### capture_queries()

Capture SQL queries executed by a callable.

```python
def capture_queries(
    func: Callable[[], Any],
    *,
    using: str = "default"
) -> Tuple[Any, QueryInfo]
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `func` | `Callable[[], Any]` | Zero-argument callable to execute |
| `using` | `str` | Database alias to capture. Default: `"default"` |

**Returns:** Tuple of `(result, QueryInfo)`

**Behavior:**

- Works even when `DEBUG=False` (forces debug cursor)
- Only captures queries for the specified database alias
- Time values in `queries` list are strings; `total_time` is converted to float

### with_query_capture()

Decorator that logs query information after function execution.

```python
def with_query_capture(
    using: str = "default",
    *log_args,
    **log_kwargs
) -> Callable
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `using` | `str` | Database alias to capture. Default: `"default"` |
| `*log_args` | | Passed to `log_query_info()` |
| `**log_kwargs` | | Passed to `log_query_info()` |

**Returns:** The original function's return value (not a tuple)

### log_query_info()

Log captured query information.

```python
def log_query_info(
    info: QueryInfo,
    *,
    limit: Optional[int] = 10,
    level: int = logging.DEBUG
) -> None
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `info` | `QueryInfo` | Query information to log |
| `limit` | `Optional[int]` | Max queries to display. `None` shows all. Default: `10` |
| `level` | `int` | Logging level. Default: `logging.DEBUG` |

---

## Structured Event Tracking

Module: `gyrinx/tracker.py`

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

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `event` | `str` | Event name (e.g., `stat_config_fallback_used`) |
| `n` | `int` | Count increment. Default: `1` |
| `value` | `Optional[float]` | Numeric value for distributions |
| `**labels` | `Any` | Arbitrary key-value metadata |

**Behavior:**

- In production: Outputs JSON via `StructuredLogHandler` for Cloud Logging
- In development: Logs JSON string to console via `gyrinx.tracker` logger
- Non-serializable label values are handled:
  - Objects with `id` attribute: converted to `str(obj.id)`
  - `UUID` instances: converted to string
  - Other non-serializable values: dropped with debug log

**Output format:**

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

---

## Event System

Module: `gyrinx/core/models/events.py`

Database-persisted event logging with structured event types.

### EventNoun

Enum of objects that can be acted upon.

| Value | Label |
|-------|-------|
| `list` | List |
| `list_fighter` | List Fighter |
| `campaign` | Campaign |
| `campaign_invitation` | Campaign Invitation |
| `battle` | Battle |
| `equipment_assignment` | Equipment Assignment |
| `skill_assignment` | Skill Assignment |
| `user` | User |
| `upload` | Upload |
| `fighter_advancement` | Fighter Advancement |
| `campaign_action` | Campaign Action |
| `campaign_resource` | Campaign Resource |
| `campaign_asset` | Campaign Asset |
| `banner` | Banner |
| `print_config` | Print Config |

### EventVerb

Enum of actions that can be performed.

| Value | Label | Category |
|-------|-------|----------|
| `create` | Create | CRUD |
| `update` | Update | CRUD |
| `delete` | Delete | CRUD |
| `view` | View | CRUD |
| `archive` | Archive | Deletion |
| `restore` | Restore | Deletion |
| `submit` | Submit | Forms |
| `confirm` | Confirm | Forms |
| `join` | Join | User actions |
| `leave` | Leave | User actions |
| `assign` | Assign | Assignment |
| `unassign` | Unassign | Assignment |
| `activate` | Activate | Activation |
| `deactivate` | Deactivate | Activation |
| `approve` | Approve | Approvals |
| `reject` | Reject | Approvals |
| `import` | Import | IO |
| `export` | Export | IO |
| `add` | Add | Modification |
| `remove` | Remove | Modification |
| `clone` | Clone | Modification |
| `reset` | Reset | Modification |
| `login` | Login | Accounts |
| `logout` | Logout | Accounts |
| `signup` | Signup | Accounts |
| `click` | Click | Click tracking |

### EventField

Enum of fields that can be modified.

| Value | Label |
|-------|-------|
| `password` | Password |
| `email` | Email |
| `mfa` | Multi-Factor Authentication |
| `session` | Session |
| `info` | Info |
| `stats` | Stats |

### log_event()

Create and persist an Event record.

```python
def log_event(
    user,
    noun: EventNoun,
    verb: EventVerb,
    object=None,
    request=None,
    ip_address=None,
    field=None,
    **context
) -> Optional[Event]
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `user` | `User` | User performing the action |
| `noun` | `EventNoun` | Object type being acted upon |
| `verb` | `EventVerb` | Action being performed |
| `object` | `Model` | Optional Django model instance |
| `request` | `HttpRequest` | Optional request for session/IP extraction |
| `ip_address` | `str` | Optional IP (overrides request extraction) |
| `field` | `EventField` | Optional field for UPDATE events |
| `**context` | | Additional JSON-serializable context |

**Returns:** `Event` instance or `None` on error

**Behavior:**

- Extracts session ID from request if available
- Extracts client IP from `X-Forwarded-For`, `X-Real-IP`, or `REMOTE_ADDR`
- Stores object reference via `ContentType` for generic relations
- On save, calls `tracker.track()` with event name `event_{verb}_{noun}`
- Errors are logged but do not raise exceptions

### Event Model

Database model storing event records.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `noun` | `CharField` | EventNoun choice |
| `verb` | `CharField` | EventVerb choice |
| `object_id` | `UUIDField` | UUID of target object |
| `object_type` | `ForeignKey(ContentType)` | Type for generic relation |
| `ip_address` | `GenericIPAddressField` | Client IP address |
| `session_id` | `CharField` | Session key |
| `field` | `CharField` | EventField choice |
| `context` | `JSONField` | Additional context data |

**Indexes:**

- `created` (descending)
- `noun`, `verb` (composite)
- `owner`
- `object_type`, `object_id` (composite)

---

## Tracing System (OpenTelemetry)

Module: `gyrinx/tracing.py`

### Initialization

Tracing initializes automatically on module import. The module is imported in `gyrinx/wsgi.py` and `gyrinx/asgi.py`:

```python
import gyrinx.tracing  # noqa: F401, E402
```

### Exporter Configuration

| Condition | Exporter | Processor |
|-----------|----------|-----------|
| `DEBUG=False` | `CloudTraceSpanExporter` | `BatchSpanProcessor` |
| `DEBUG=True` | `ConsoleSpanExporter` | `SimpleSpanProcessor` |

### Automatic Instrumentation

**DjangoInstrumentor:** Creates spans for all HTTP requests automatically.

**LoggingInstrumentor:** Injects trace context into Python log records. Configured with `set_logging_format=False` to preserve existing format.

### Trace Context Propagation

`CloudTraceFormatPropagator` parses the `X-Cloud-Trace-Context` header from Cloud Run.

**Header format:** `TRACE_ID/SPAN_ID;o=TRACE_TRUE`

Custom spans created with `span()` or `@traced()` appear as children of the request span.

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

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Span name |
| `record_exception` | `bool` | Record exceptions on span. Default: `True` |
| `**attributes` | `Any` | Key-value attributes (converted to strings) |

**Yields:** Span object, or `None` if tracing disabled

**Behavior:**

- When tracing enabled: Creates span, attaches attributes, records exceptions if `record_exception=True`
- When tracing disabled: Yields `None` with no overhead

### traced()

Decorator to trace a function.

```python
def traced(
    name: Optional[str] = None,
    **default_attributes: Any
) -> Callable
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `Optional[str]` | Span name. Default: function name |
| `**default_attributes` | `Any` | Attributes added to every span |

**Returns:** Decorated function

### is_tracing_enabled()

Check if tracing is enabled.

```python
def is_tracing_enabled() -> bool
```

**Returns:** `True` if tracing is initialized and enabled

### Local Tracing

Run the development server with OpenTelemetry instrumentation:

```console
opentelemetry-instrument manage runserver
```

### Dependencies

```
opentelemetry-sdk>=1.28.0
opentelemetry-exporter-gcp-trace>=1.8.0
opentelemetry-instrumentation-django>=0.49b0
opentelemetry-instrumentation-asgi>=0.49b0
opentelemetry-instrumentation-logging
opentelemetry-propagator-gcp
```

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
| `gyrinx/settings.py` | Base logging configuration, SqlCommenter settings |
| `gyrinx/settings_dev.py` | Development SQL debugging configuration |
| `gyrinx/settings_prod.py` | Production logging with StructuredLogHandler |
| `gyrinx/tracker.py` | Structured event tracking module |
| `gyrinx/tracing.py` | OpenTelemetry tracing module |
| `gyrinx/query.py` | SQL query capture utilities |
| `gyrinx/core/models/events.py` | Event model and log_event function |
| `gyrinx/wsgi.py` | Tracing initialization for WSGI |
| `gyrinx/asgi.py` | Tracing initialization for ASGI |

---

## Related Documentation

- [SQL Debugging Guide](sql-debugging.md) - Usage guide for SQL debugging
- [Tracking and Metrics](tracking.md) - Usage guide for event tracking
- [Operational Overview](operations/operational-overview.md) - Infrastructure and monitoring
