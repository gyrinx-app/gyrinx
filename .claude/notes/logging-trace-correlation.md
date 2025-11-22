# Logging Trace Correlation Analysis

## Problem Statement

Currently, logs generated within a single HTTP request in production (Cloud Run) are split across multiple log entries with no way to correlate them:

1. HTTP request log (from `run.googleapis.com/requests`)
2. Application error log (from `run.googleapis.com/stderr`)
3. Error ID log (from `run.googleapis.com/stderr`)

This makes it difficult to trace what happened within a single request.

## Current Log Structure

### Example from Production Logs

For a single error, we get THREE separate log entries:

**1. HTTP Request Log** (has trace ID)
```json
{
  "httpRequest": {
    "requestMethod": "GET",
    "requestUrl": "https://gyrinx.app/list/.../fighter/.../delete",
    "status": 500
  },
  "trace": "projects/windy-ellipse-440618-p9/traces/5e62ee48c832efae1c38cd5656fb4a63",
  "spanId": "0370fc3c6f434fa6",
  "logName": "projects/.../logs/run.googleapis.com%2Frequests"
}
```

**2. Error ID Log** (NO trace ID)
```json
{
  "textPayload": "Error ID: 80cdf223-a63a-4c56-89b9-e6ab6924f001 - User can reference this when reporting issues",
  "labels": {
    "python_logger": "django.request"
  },
  "logName": "projects/.../logs/run.googleapis.com%2Fstderr",
  "sourceLocation": {
    "file": "/app/gyrinx/pages/views.py",
    "line": "78",
    "function": "error_500"
  }
}
```

**3. Error Traceback Log** (NO trace ID)
```json
{
  "textPayload": "Internal Server Error: /list/.../fighter/.../delete\nTraceback...",
  "labels": {
    "python_logger": "django.request"
  },
  "logName": "projects/.../logs/run.googleapis.com%2Fstderr"
}
```

**Problem**: Logs #2 and #3 don't have the `trace` field, so they can't be correlated with log #1.

## Root Cause

1. **GCP Cloud Run automatically** generates HTTP request logs with trace IDs
2. **Application logs** (stderr) don't include the trace field
3. Without the trace field, GCP can't correlate the logs in the UI

## How GCP Trace Correlation Works

### X-Cloud-Trace-Context Header

Cloud Run includes this header in every request:
```
X-Cloud-Trace-Context: TRACE_ID/SPAN_ID;o=TRACE_TRUE
```

Example: `5e62ee48c832efae1c38cd5656fb4a63/0370fc3c6f434fa6;o=1`

### Required Log Format

To correlate logs, application logs must:

1. Be in **structured JSON format** (not plain text)
2. Include the field: `"logging.googleapis.com/trace"`
3. With value: `"projects/PROJECT_ID/traces/TRACE_ID"`

Example structured log:
```json
{
  "message": "Error ID: 80cdf223-a63a-4c56-89b9-e6ab6924f001",
  "severity": "ERROR",
  "logging.googleapis.com/trace": "projects/windy-ellipse-440618-p9/traces/5e62ee48c832efae1c38cd5656fb4a63",
  "logging.googleapis.com/spanId": "0370fc3c6f434fa6"
}
```

When this is done correctly, GCP automatically groups logs in parent-child format in the Cloud Logging UI.

## Current Application Setup

### Installed Packages

✅ `google-cloud-logging==3.12.1` - already installed!

### Current Logging Configuration

From `gyrinx/settings.py`:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
```

**Issues:**
- Uses plain text format (not JSON)
- No trace field injection
- No span ID

## Solution Options

### Option 1: Google Cloud Logging Integration (RECOMMENDED)

Use the official `google-cloud-logging` library that's already installed.

**Pros:**
- Automatic trace correlation
- Handles JSON formatting
- Integrates with Cloud Trace
- Production-ready
- Minimal code changes

**Cons:**
- Adds dependency (already installed!)
- May have slight performance overhead

### Option 2: Custom Middleware + Logging Filter

Create custom middleware to extract trace ID and a logging filter to inject it.

**Pros:**
- Full control
- No additional dependencies
- Lightweight

**Cons:**
- More code to maintain
- Need to handle JSON formatting
- Need to handle edge cases

### Option 3: Third-party Package (django-gcp-log-groups)

Use the `django-gcp-log-groups` package found during research.

**Pros:**
- Django-specific
- Handles trace correlation automatically

**Cons:**
- Another dependency
- Less maintained (last update unknown)
- May not support latest Django/Python

## Recommended Implementation: Option 1

Use Google Cloud Logging's built-in Django integration.

### Implementation Steps

1. **Configure Google Cloud Logging in settings.py**

```python
# In settings.py (production only)
if not DEBUG:
    import google.cloud.logging

    client = google.cloud.logging.Client()
    client.setup_logging()
```

This automatically:
- Converts logs to JSON
- Extracts trace ID from X-Cloud-Trace-Context
- Adds `logging.googleapis.com/trace` field
- Correlates logs in Cloud Logging UI

2. **Alternative: More Fine-grained Control**

For more control over what gets logged to Cloud Logging:

```python
# In settings.py
if not DEBUG:
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "cloud_logging": {
                "class": "google.cloud.logging.handlers.CloudLoggingHandler",
                "client": google.cloud.logging.Client(),
            },
            "console": {
                "class": "logging.StreamHandler",
            },
        },
        "loggers": {
            "django.request": {
                "handlers": ["cloud_logging"],
                "level": "ERROR",
                "propagate": False,
            },
            "gyrinx": {
                "handlers": ["cloud_logging"],
                "level": "INFO",
            },
        },
        "root": {
            "handlers": ["cloud_logging"],
            "level": "INFO",
        },
    }
```

### Custom Middleware Approach (Alternative)

If we want full control without Google Cloud Logging library:

```python
# gyrinx/core/middleware/trace.py
import json
import logging
import os
from threading import local

_thread_locals = local()

class TraceContextMiddleware:
    """Extract GCP trace context and make it available to logging"""

    def __init__(self, get_response):
        self.get_response = get_response
        self.project_id = os.getenv("GCP_PROJECT_ID", "")

    def __call__(self, request):
        # Extract trace context from header
        trace_header = request.META.get("HTTP_X_CLOUD_TRACE_CONTEXT", "")

        if trace_header:
            trace_id = trace_header.split("/")[0]
            span_id = trace_header.split("/")[1].split(";")[0] if "/" in trace_header else ""

            # Store in thread-local storage
            _thread_locals.trace = f"projects/{self.project_id}/traces/{trace_id}"
            _thread_locals.span_id = span_id
        else:
            _thread_locals.trace = None
            _thread_locals.span_id = None

        response = self.get_response(request)

        # Clean up
        _thread_locals.trace = None
        _thread_locals.span_id = None

        return response

def get_trace_context():
    """Get current trace context for logging"""
    return getattr(_thread_locals, "trace", None), getattr(_thread_locals, "span_id", None)
```

```python
# gyrinx/core/logging/formatters.py
import json
import logging
from gyrinx.core.middleware.trace import get_trace_context

class GCPStructuredFormatter(logging.Formatter):
    """Format logs as structured JSON for GCP Cloud Logging"""

    def format(self, record):
        log_obj = {
            "message": record.getMessage(),
            "severity": record.levelname,
            "timestamp": self.formatTime(record),
        }

        # Add trace context if available
        trace, span_id = get_trace_context()
        if trace:
            log_obj["logging.googleapis.com/trace"] = trace
        if span_id:
            log_obj["logging.googleapis.com/spanId"] = span_id

        # Add source location
        if record.pathname:
            log_obj["logging.googleapis.com/sourceLocation"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        return json.dumps(log_obj)
```

Then configure in settings:

```python
MIDDLEWARE = [
    "gyrinx.core.middleware.trace.TraceContextMiddleware",  # Add near the top
    # ... rest of middleware
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "gcp_json": {
            "()": "gyrinx.core.logging.formatters.GCPStructuredFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "gcp_json",
        },
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
        },
    },
}
```

## Testing the Solution

### 1. Local Testing

Set environment variable:
```bash
export GCP_PROJECT_ID="windy-ellipse-440618-p9"
```

Add the X-Cloud-Trace-Context header manually in tests:
```python
response = client.get(
    "/some/url/",
    headers={"X-Cloud-Trace-Context": "test-trace-id/test-span-id;o=1"}
)
```

Check logs are in JSON format with trace field.

### 2. Production Testing

1. Deploy the change
2. Trigger an error
3. View logs in Cloud Logging
4. Verify:
   - Logs are in JSON format
   - Application logs have `logging.googleapis.com/trace` field
   - Clicking the triangle icon in request log shows nested app logs

## Performance Considerations

### Google Cloud Logging Library
- Adds minimal overhead (< 5ms per log)
- Batches logs for efficiency
- Async by default

### Custom Implementation
- Near-zero overhead
- Full control over what gets logged
- More maintenance burden

## Recommendation

**Use Option 1: Google Cloud Logging Integration**

Reasons:
1. Package already installed (`google-cloud-logging==3.12.1`)
2. Minimal code changes
3. Production-ready and well-tested
4. Automatic trace correlation
5. Future-proof (handles GCP updates)

Start with the simple approach:
```python
if not DEBUG:
    import google.cloud.logging
    client = google.cloud.logging.Client()
    client.setup_logging()
```

If we need more control later, we can switch to the custom handlers approach or implement custom middleware.

## Next Steps

1. Test in development environment
2. Update settings.py with trace correlation
3. Deploy to production
4. Verify trace correlation in Cloud Logging UI
5. Document for team in production runbook

## References

- [Cloud Run Logging Documentation](https://cloud.google.com/run/docs/logging)
- [Cloud Logging Python Setup](https://cloud.google.com/logging/docs/setup/python)
- [Structured Logging in Cloud Run](https://cloud.google.com/run/docs/samples/cloudrun-manual-logging)
- [Stack Overflow: Correlate Request Logs](https://stackoverflow.com/questions/57557884/how-do-i-correlate-request-logs-in-cloud-run)
