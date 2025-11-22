# Logging Trace Correlation - Root Cause Analysis

## TL;DR - The Bug

**Problem**: `settings_prod.py` line 20-22 creates `StructuredLogHandler` without the required `project_id` parameter, causing trace correlation to fail.

**Fix**: Add `project_id` parameter to the handler configuration.

## Current State

### What's Already Configured

`settings_prod.py` already has Google Cloud Logging set up:

1. **Line 10-17**: Creates client and calls `client.setup_logging()`
2. **Line 20-27**: Manually adds `StructuredLogHandler` to Django logging

### The Bug

```python
# Line 20-22 in settings_prod.py - MISSING project_id!
LOGGING["handlers"]["structured_console"] = {
    "class": "google.cloud.logging.handlers.StructuredLogHandler",
}
```

**Why this breaks trace correlation:**

Looking at the Google Cloud Logging library source code:

1. `StructuredLogHandler.__init__()` accepts a `project_id` parameter
2. It creates a `CloudLoggingFilter(project=project_id)`
3. `CloudLoggingFilter.filter()` calls `get_request_data()` to extract trace from Django request
4. **BUT** it only formats the trace properly if BOTH conditions are met:
   ```python
   if inferred_trace is not None and self.project is not None:
       inferred_trace = f"projects/{self.project}/traces/{inferred_trace}"
   ```
5. Without `project_id`, the trace stays as an empty string

## Evidence from Production Logs

From `~/Downloads/logs-251122.json`:

```json
{
  "textPayload": "Error ID: 80cdf223-a63a-4c56-89b9-e6ab6924f001...",
  "labels": {
    "python_logger": "django.request"
  },
  "logName": "projects/.../logs/run.googleapis.com%2Fstderr"
  // NO "logging.googleapis.com/trace" field!
}
```

The log comes from stderr (good - StructuredLogHandler writes to stderr), but the trace field is missing/empty.

## Additional Issues Found

### 1. Duplicate Logging Setup

`settings_prod.py` has TWO logging setups that may conflict:

**Setup 1** (line 12-17): `client.setup_logging()`
- Automatically attaches a handler to Python's root logger
- On Cloud Run, this uses `StructuredLogHandler` with proper `project_id`
- **This should work!**

**Setup 2** (line 20-27): Manual Django LOGGING configuration
- Overrides Django loggers to use custom `StructuredLogHandler`
- **Missing `project_id` - this is broken!**

These two setups may conflict or duplicate logs.

### 2. Confusion Between Handlers

There are TWO similar handlers:
- `CloudLoggingHandler` - Sends logs to Cloud Logging API directly
- `StructuredLogHandler` - Writes JSON to stdout/stderr for Cloud Run to collect

For Cloud Run, `StructuredLogHandler` is correct (which is what `setup_logging()` automatically uses).

### 3. tracker.py System

There's already a separate structured logging system in `tracker.py`:
```python
if IS_GOOGLE_CLOUD:
    _logger = client.logger("tracker")
    _logger.log_struct(payload, severity="INFO")
```

This uses `log_struct()` which sends directly to Cloud Logging API. It's currently only used in tests, not production code.

## How Google Cloud Logging SHOULD Work

### The Proper Flow

1. **Cloud Run** sends `X-Cloud-Trace-Context` header with every request
   - Format: `TRACE_ID/SPAN_ID;o=TRACE_TRUE`
   - Example: `5e62ee48c832efae1c38cd5656fb4a63/12345;o=1`

2. **CloudLoggingFilter.filter()** extracts trace from request:
   ```python
   # From google.cloud.logging_v2.handlers._helpers
   def get_request_data_from_django():
       request = _get_django_request()
       header = request.META.get("HTTP_X_CLOUD_TRACE_CONTEXT")
       trace_id, span_id, trace_sampled = _parse_xcloud_trace(header)
       return http_request, trace_id, span_id, trace_sampled
   ```

3. **CloudLoggingFilter** formats it for GCP:
   ```python
   if inferred_trace is not None and self.project is not None:
       inferred_trace = f"projects/{self.project}/traces/{inferred_trace}"
   record._trace = inferred_trace
   ```

4. **StructuredLogHandler** outputs JSON with trace:
   ```json
   {
     "message": "Error occurred",
     "severity": "ERROR",
     "logging.googleapis.com/trace": "projects/PROJECT_ID/traces/TRACE_ID",
     "logging.googleapis.com/spanId": "SPAN_ID"
   }
   ```

5. **Cloud Run** collects stdout/stderr and parses JSON
6. **Cloud Logging** groups logs by matching trace IDs

### Why It's Not Working

**Step 3 fails** because `self.project` is `None` (no `project_id` passed to StructuredLogHandler).

## The Fix

### Minimal Fix (Recommended)

Simply add `project_id` to the handler config:

```python
# In settings_prod.py, replace lines 20-22:
LOGGING["handlers"]["structured_console"] = {
    "class": "google.cloud.logging.handlers.StructuredLogHandler",
    "project_id": client.project,  # ADD THIS LINE
}
```

This fixes the handler that Django loggers use.

### Alternative: Remove Duplicate Setup

Since `client.setup_logging()` already configures logging correctly, we could remove the manual handler setup entirely:

```python
# In settings_prod.py

# Configure Google Cloud Logging - this is all you need!
client = google.cloud.logging.Client()
client.setup_logging(
    excluded_loggers=(
        "django.security.DisallowedHost",
        "django.db.backends",
    )
)

# REMOVE lines 19-27 (the manual LOGGING configuration)
# setup_logging() already handles everything!
```

But this might change which loggers get structured logging, so the minimal fix is safer.

### Complete Unified Solution

For a clean, unified approach:

```python
# In settings_prod.py

import os
import google.cloud.logging

from .settings import *  # noqa: F403
from .settings import LOGGING, STORAGES
from .storage_settings import configure_gcs_storage

# Get project ID from environment or detect it
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID") or "windy-ellipse-440618-p9"

# Configure Google Cloud Logging
client = google.cloud.logging.Client(project=PROJECT_ID)

# Option 1: Let setup_logging() handle everything (simplest)
client.setup_logging(
    excluded_loggers=(
        "django.security.DisallowedHost",
        "django.db.backends",
    )
)

# Option 2: Manual control with correct project_id (if you need specific Django logger config)
# LOGGING["handlers"]["structured_console"] = {
#     "class": "google.cloud.logging.handlers.StructuredLogHandler",
#     "project_id": PROJECT_ID,  # CRITICAL: Must include this
# }
# LOGGING["loggers"]["django.request"]["handlers"] = ["structured_console"]
# LOGGING["loggers"]["gyrinx"]["handlers"] = ["structured_console"]
# LOGGING["root"]["handlers"] = ["structured_console"]
```

## Relationship with tracker.py

`tracker.py` is for **metrics/events**, not error logging:

- **tracker.py**: Structured events for monitoring/analytics
  - Example: `track("stat_config_fallback_used", stat_name="ammo")`
  - Uses `log_struct()` to send directly to Cloud Logging API
  - For intentional tracking, not errors

- **Django logging**: Application logs and errors
  - Example: `logger.error("Something failed")`
  - Uses `StructuredLogHandler` to write JSON to stderr
  - Cloud Run collects and sends to Cloud Logging

Both use Google Cloud Logging, but for different purposes. They should coexist without conflict.

## Testing the Fix

### 1. Local Testing

```python
# Test that handler has project_id
import logging
from google.cloud.logging.handlers import StructuredLogHandler

handler = StructuredLogHandler(project_id="test-project")
logger = logging.getLogger("test")
logger.addHandler(handler)

# Simulate Django request with trace header
from unittest.mock import Mock
from google.cloud.logging_v2.handlers.middleware import _get_django_request

mock_request = Mock()
mock_request.META = {
    "HTTP_X_CLOUD_TRACE_CONTEXT": "test-trace-id/12345;o=1"
}

# Log something - should include trace
logger.error("Test error")
# Output should have: "logging.googleapis.com/trace": "projects/test-project/traces/test-trace-id"
```

### 2. Production Testing

1. Deploy the fix
2. Trigger an error (or any request)
3. Check Cloud Logging
4. Verify logs now have `logging.googleapis.com/trace` field
5. Click triangle icon on request log - should show nested app logs

## Recommended Implementation

**Use the minimal fix**:

1. Change line 20-22 in `settings_prod.py` to include `project_id`
2. Keep everything else the same
3. Test in production
4. If it works, optionally clean up the duplicate setup later

This is the safest approach with minimal risk.

## Summary

**Root cause**: Missing `project_id` parameter in `StructuredLogHandler` configuration

**Impact**: Trace correlation completely broken - can't link logs from same request

**Fix**: Add one line: `"project_id": client.project,`

**Complexity**: Literally a one-line fix

**Risk**: Very low - just adding the missing parameter that should have been there

The existing infrastructure is actually correct and well-designed. It just has one missing parameter that breaks the whole thing.
