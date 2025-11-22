# Logging Trace Correlation - Implementation Examples

This document provides concrete code examples for implementing trace correlation in production.

## Recommended: Google Cloud Logging Integration

### Option 1A: Simple Setup (Easiest)

Modify `gyrinx/settings.py`:

```python
# At the end of settings.py, after LOGGING configuration

# Setup Google Cloud Logging for production trace correlation
if not DEBUG:
    try:
        import google.cloud.logging
        import logging

        # Create a Cloud Logging client
        client = google.cloud.logging.Client()

        # Integrate Cloud Logging with Python logging
        # This automatically adds trace context from X-Cloud-Trace-Context header
        client.setup_logging(log_level=logging.INFO)

        logger.info("Google Cloud Logging configured successfully")
    except Exception as e:
        logger.error(f"Failed to setup Google Cloud Logging: {e}")
```

**What this does:**
- Automatically extracts trace ID from `X-Cloud-Trace-Context` header
- Converts all logs to structured JSON
- Adds `logging.googleapis.com/trace` field
- Correlates logs in Cloud Logging UI
- Works with existing Django logging

**Pros:**
- 3 lines of code
- Zero configuration
- Automatic trace correlation

**Cons:**
- Less control over log format
- All logs go to Cloud Logging (may increase costs)

### Option 1B: Fine-grained Control

For more control over which logs go to Cloud Logging:

```python
# In gyrinx/settings.py

if not DEBUG:
    import google.cloud.logging

    # Create client
    gcp_logging_client = google.cloud.logging.Client()

    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "{levelname} {asctime} {module} {message}",
                "style": "{",
            },
        },
        "handlers": {
            "cloud_logging": {
                "class": "google.cloud.logging.handlers.CloudLoggingHandler",
                "client": gcp_logging_client,
                "name": "gyrinx-app",  # Custom log name
            },
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "verbose",
            },
        },
        "loggers": {
            # Send Django request errors to Cloud Logging
            "django.request": {
                "handlers": ["cloud_logging"],
                "level": "ERROR",
                "propagate": False,
            },
            # Send app logs to Cloud Logging
            "gyrinx": {
                "handlers": ["cloud_logging"],
                "level": "INFO",
                "propagate": False,
            },
        },
        "root": {
            "handlers": ["cloud_logging"],
            "level": "INFO",
        },
    }
else:
    # Development logging (existing configuration)
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
            "gyrinx": {
                "handlers": ["console"],
                "level": "DEBUG",
                "propagate": True,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "INFO",
        },
    }
```

**Pros:**
- Control over which logs go to Cloud Logging
- Can keep console output for debugging
- Different configs for dev/prod

**Cons:**
- More configuration
- Need to manage two LOGGING configs

## Alternative: Custom Middleware (Full Control)

If you want complete control without using Google Cloud Logging library.

### Step 1: Create Middleware

Create `gyrinx/core/middleware/trace.py`:

```python
"""
Middleware to extract and store GCP trace context for request correlation.
"""
import logging
import os
from threading import local

logger = logging.getLogger(__name__)

# Thread-local storage for trace context
_thread_locals = local()


class TraceContextMiddleware:
    """
    Extract GCP trace context from X-Cloud-Trace-Context header
    and make it available to logging.

    Cloud Run provides this header in format: TRACE_ID/SPAN_ID;o=TRACE_TRUE
    Example: 5e62ee48c832efae1c38cd5656fb4a63/0370fc3c6f434fa6;o=1
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.project_id = os.getenv("GCP_PROJECT_ID", "")

        if not self.project_id:
            logger.warning(
                "GCP_PROJECT_ID not set - trace correlation will not work"
            )

    def __call__(self, request):
        # Extract trace context from header
        trace_header = request.META.get("HTTP_X_CLOUD_TRACE_CONTEXT", "")

        if trace_header and self.project_id:
            try:
                # Parse: TRACE_ID/SPAN_ID;o=TRACE_TRUE
                parts = trace_header.split("/")
                trace_id = parts[0]

                span_parts = parts[1].split(";") if len(parts) > 1 else [""]
                span_id = span_parts[0]

                # Format for Cloud Logging
                _thread_locals.trace = f"projects/{self.project_id}/traces/{trace_id}"
                _thread_locals.span_id = span_id

                logger.debug(f"Trace context set: {_thread_locals.trace}")
            except (IndexError, AttributeError) as e:
                logger.warning(f"Failed to parse trace header: {trace_header} - {e}")
                _thread_locals.trace = None
                _thread_locals.span_id = None
        else:
            _thread_locals.trace = None
            _thread_locals.span_id = None

        try:
            response = self.get_response(request)
        finally:
            # Clean up thread-local storage
            _thread_locals.trace = None
            _thread_locals.span_id = None

        return response


def get_trace_context():
    """
    Get current request's trace context.

    Returns:
        tuple: (trace, span_id) or (None, None)
    """
    return (
        getattr(_thread_locals, "trace", None),
        getattr(_thread_locals, "span_id", None),
    )
```

### Step 2: Create Custom Formatter

Create `gyrinx/core/logging/formatters.py`:

```python
"""
Custom logging formatters for GCP Cloud Logging structured logs.
"""
import json
import logging
from datetime import datetime

from gyrinx.core.middleware.trace import get_trace_context


class GCPStructuredFormatter(logging.Formatter):
    """
    Format logs as structured JSON for GCP Cloud Logging.

    Output format matches GCP's expected structure:
    https://cloud.google.com/logging/docs/structured-logging
    """

    # Map Python logging levels to GCP severity
    SEVERITY_MAPPING = {
        "DEBUG": "DEBUG",
        "INFO": "INFO",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "CRITICAL": "CRITICAL",
    }

    def format(self, record):
        # Base log structure
        log_obj = {
            "message": record.getMessage(),
            "severity": self.SEVERITY_MAPPING.get(record.levelname, "DEFAULT"),
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
        }

        # Add trace context if available
        trace, span_id = get_trace_context()
        if trace:
            log_obj["logging.googleapis.com/trace"] = trace
        if span_id:
            log_obj["logging.googleapis.com/spanId"] = span_id

        # Add source location for errors
        if record.levelno >= logging.ERROR:
            log_obj["logging.googleapis.com/sourceLocation"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add logger name
        log_obj["logger"] = record.name

        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        if hasattr(record, "http_request"):
            log_obj["httpRequest"] = record.http_request

        return json.dumps(log_obj)
```

### Step 3: Update Settings

Modify `gyrinx/settings.py`:

```python
# Add middleware (near the top of MIDDLEWARE list)
MIDDLEWARE = [
    "google.cloud.sqlcommenter.django.middleware.SqlCommenter",
    "gyrinx.core.middleware.trace.TraceContextMiddleware",  # Add this
    "django.middleware.security.SecurityMiddleware",
    # ... rest of middleware
]

# Update LOGGING configuration
if not DEBUG:
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
                "propagate": False,
            },
            "gyrinx": {
                "handlers": ["console"],
                "level": os.getenv("GYRINX_LOG_LEVEL", "INFO").upper(),
                "propagate": True,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": os.getenv("GYRINX_LOG_LEVEL", "INFO").upper(),
        },
    }
else:
    # Development logging (keep existing)
    LOGGING = {
        # ... existing dev config
    }
```

### Step 4: Set Environment Variable

In production (Cloud Run), set the environment variable:

```bash
GCP_PROJECT_ID=windy-ellipse-440618-p9
```

## Testing

### Local Testing

```python
# Test the middleware and formatter
import logging
from django.test import TestCase

logger = logging.getLogger("gyrinx")

class TraceCorrelationTest(TestCase):
    def test_trace_correlation(self):
        response = self.client.get(
            "/some/url/",
            HTTP_X_CLOUD_TRACE_CONTEXT="test-trace-id/test-span-id;o=1"
        )

        # Log something
        logger.info("Test log message")

        # Check that logs include trace context
        # (You'd need to capture log output to verify)
```

### Manual Testing in Production

1. Deploy the changes
2. Trigger an error (or any request)
3. Go to Cloud Logging console
4. Filter for your logs
5. Verify:
   - Logs are in JSON format
   - `logging.googleapis.com/trace` field is present
   - Clicking triangle on request log shows nested app logs

## Example Log Output

### Before (Plain Text)
```
ERROR 2025-11-22 14:30:15 views 12345 67890 Error ID: 80cdf223-a63a-4c56-89b9-e6ab6924f001
```

### After (Structured JSON)
```json
{
  "message": "Error ID: 80cdf223-a63a-4c56-89b9-e6ab6924f001 - User can reference this when reporting issues",
  "severity": "ERROR",
  "timestamp": "2025-11-22T14:30:15.123456Z",
  "logging.googleapis.com/trace": "projects/windy-ellipse-440618-p9/traces/5e62ee48c832efae1c38cd5656fb4a63",
  "logging.googleapis.com/spanId": "0370fc3c6f434fa6",
  "logging.googleapis.com/sourceLocation": {
    "file": "/app/gyrinx/pages/views.py",
    "line": 78,
    "function": "error_500"
  },
  "logger": "django.request"
}
```

## Recommended Approach

**Start with Option 1A (Simple Google Cloud Logging)**

It's the easiest and most maintainable:

1. Add 3 lines to settings.py
2. Deploy
3. Test

If you need more control later, switch to Option 1B or the custom middleware.

## Migration Path

### Phase 1: Deploy Google Cloud Logging
- Use Option 1A
- Test in production
- Verify trace correlation works

### Phase 2: Optimize (if needed)
- Switch to Option 1B for fine-grained control
- OR switch to custom middleware if you need specific features

### Phase 3: Monitor
- Check Cloud Logging costs
- Verify all logs are correlated
- Update documentation for team

## Common Issues

### Trace field not appearing
- Check `X-Cloud-Trace-Context` header is present
- Verify GCP_PROJECT_ID is set correctly
- Check middleware is in MIDDLEWARE list

### Logs not correlated in UI
- Verify trace field format: `projects/PROJECT_ID/traces/TRACE_ID`
- Check logs are in JSON format
- Ensure logs are from same request

### Performance issues
- Google Cloud Logging batches logs automatically
- Custom middleware adds < 1ms overhead
- Monitor log volume and costs

## Cost Considerations

Cloud Logging pricing (as of 2024):
- First 50 GiB/month: Free
- Additional logs: ~$0.50/GiB

For most applications, the free tier is sufficient. Monitor usage in Cloud Console.

## References

- [Cloud Logging Python Setup](https://cloud.google.com/logging/docs/setup/python)
- [Structured Logging](https://cloud.google.com/logging/docs/structured-logging)
- [Cloud Run Logging](https://cloud.google.com/run/docs/logging)
