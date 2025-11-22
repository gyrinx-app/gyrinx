# Logging Trace Correlation - Complete Fix

## Summary

**Problem**: Logs from a single HTTP request in production appear as separate, uncorrelated entries in Cloud Logging.

**Root Cause**: TWO missing pieces in the configuration:
1. ❌ `project_id` parameter missing from `StructuredLogHandler`
2. ❌ `RequestMiddleware` not installed to capture Django requests

**Solution**: Added both missing pieces.

## Changes Made

### 1. Added `project_id` to StructuredLogHandler

**File**: `gyrinx/settings_prod.py` (line 22)

```python
LOGGING["handlers"]["structured_console"] = {
    "class": "google.cloud.logging.handlers.StructuredLogHandler",
    "project_id": client.project,  # ← Added this
}
```

**Why needed**: The `CloudLoggingFilter` inside `StructuredLogHandler` needs the project ID to format trace fields correctly:

```python
# From CloudLoggingFilter.filter()
if inferred_trace is not None and self.project is not None:
    inferred_trace = f"projects/{self.project}/traces/{inferred_trace}"
```

Without `self.project`, the trace never gets formatted even if extracted.

### 2. Added RequestMiddleware

**File**: `gyrinx/settings.py` (line 127)

```python
MIDDLEWARE = [
    "google.cloud.sqlcommenter.django.middleware.SqlCommenter",
    "google.cloud.logging_v2.handlers.middleware.RequestMiddleware",  # ← Added this
    "django.middleware.security.SecurityMiddleware",
    # ... rest of middleware
]
```

**Why needed**: The middleware stores the Django request in thread-local storage so that `get_request_data_from_django()` can extract the `X-Cloud-Trace-Context` header:

```python
# From RequestMiddleware
def middleware(request):
    _thread_locals.request = request  # ← Stores for later access
    return get_response(request)
```

Without this, `_get_django_request()` returns `None`, so no trace is extracted.

## The Flow (How It Works Now)

### 1. Request Arrives
Cloud Run adds `X-Cloud-Trace-Context` header:
```
X-Cloud-Trace-Context: 5e62ee48c832efae1c38cd5656fb4a63/12345;o=1
```

### 2. Middleware Captures Request
`RequestMiddleware` stores the request in thread-local storage:
```python
_thread_locals.request = request
```

### 3. Logging Filter Extracts Trace
When a log is emitted, `CloudLoggingFilter.filter()` is called:
```python
def filter(self, record):
    # Get request from thread local (set by middleware)
    request = _get_django_request()

    # Extract trace from request header
    trace_id = request.META.get("HTTP_X_CLOUD_TRACE_CONTEXT")

    # Format with project_id
    if trace_id and self.project:
        record._trace = f"projects/{self.project}/traces/{trace_id}"
```

### 4. Handler Outputs JSON
`StructuredLogHandler` formats the log with trace field:
```json
{
  "message": "Error ID: ...",
  "severity": "ERROR",
  "logging.googleapis.com/trace": "projects/windy-ellipse-440618-p9/traces/5e62ee48...",
  "logging.googleapis.com/spanId": "12345"
}
```

### 5. Cloud Run Correlates
Cloud Logging sees matching trace IDs and groups logs together in the UI.

## Test Results

Comprehensive testing confirmed the fix:

```
1. Current prod (no project_id, no middleware): ❌ No trace
2. With project_id only: ❌ No trace (middleware needed!)
3. With BOTH project_id + middleware: ✅ Trace present!
```

## Why Both Are Required

### Without project_id:
- Trace is extracted: `"5e62ee48c832efae1c38cd5656fb4a63"`
- But formatting fails (project is None)
- Output: `"logging.googleapis.com/trace": ""`

### Without middleware:
- `_get_django_request()` returns `None`
- `get_request_data()` returns `(None, None, None, False)`
- No trace extracted, so nothing to format
- Output: `"logging.googleapis.com/trace": ""`

### With both:
- Middleware provides request
- Trace extracted: `"5e62ee48c832efae1c38cd5656fb4a63"`
- Project ID formats it: `"projects/windy-ellipse-440618-p9/traces/5e62ee48..."`
- Output: ✅ Full trace field

## Validation

- ✅ Python syntax valid
- ✅ All formatters passed
- ✅ Comprehensive tests confirm fix
- ✅ No conflicts with existing systems (tracker.py, setup_logging())

## Deployment Verification

After deploying, verify in Cloud Logging:

1. Trigger any request (even successful)
2. Find the HTTP request log
3. Click the triangle (▶) icon
4. Should see nested application logs underneath

Example log structure after fix:
```
▶ GET /list/... 200
  ├─ INFO: Processing request
  ├─ ERROR: Error ID: 80cdf223...
  └─ ERROR: Internal Server Error traceback
```

All logs will share the same trace ID, enabling perfect correlation.

## Related Systems

### tracker.py
- Purpose: Structured metrics/events
- Method: `log_struct()` directly to Cloud Logging API
- Status: Unchanged, works independently

### client.setup_logging()
- Purpose: Attach handler to root logger
- Method: Automatically creates StructuredLogHandler for Cloud Run
- Status: Unchanged, provides baseline logging

### Manual LOGGING config
- Purpose: Override specific Django loggers
- Method: Custom StructuredLogHandler config
- Status: ✅ Fixed with project_id parameter

All three systems now work together correctly without conflicts.

## References

- [Cloud Run Logging](https://cloud.google.com/run/docs/logging)
- [Google Cloud Logging Python](https://cloud.google.com/python/docs/reference/logging/latest)
- [Structured Logging](https://cloud.google.com/logging/docs/structured-logging)
