# Tracking and Metrics

Gyrinx uses structured logging to track application events and metrics, which can be used for monitoring, debugging, and analytics.

## Overview

The `gyrinx.tracker` module provides a simple, unified interface for emitting structured log events. These events are automatically sent to Google Cloud Logging when running in production, and fall back to JSON logging for local development.

## Usage

### Basic Usage

```python
from gyrinx.tracker import track

# Track a simple event
track("user_login")

# Track with count
track("api_call", n=5)

# Track with distribution value
track("response_time", value=123.45)
```

### Adding Context with Labels

Labels provide additional context to your events and are useful for filtering and analysis:

```python
# Track an API call with context
track("api_call", endpoint="/api/v1/fighters", method="GET", status=200)

# Track a feature usage
track("feature_used", feature="bulk_import", user_type="premium", items_count=50)

# Track an error
track("error_occurred", error_type="ValidationError", endpoint="/lists/create", code=400)
```

### Common Patterns

#### Feature Usage Tracking

```python
# Track when a feature is used
track("feature_used", feature="equipment_upgrade", list_id=str(list.id))

# Track backward compatibility code
track("stat_config_fallback_used", stat_name="ammo", model_class="ContentModStatApply")
```

#### Performance Metrics

```python
# Track response times
import time

start_time = time.time()
# ... do work ...
elapsed = (time.time() - start_time) * 1000  # Convert to milliseconds

track("operation_duration", value=elapsed, operation="generate_report")
```

#### User Events

User actions are automatically tracked through the Event model, which uses the tracker internally:

```python
# This happens automatically when Event objects are saved
track(
    "user_event",
    noun="list",
    verb="create",
    user_id="123",
    username="player1"
)
```

## Event Naming Conventions

- Use snake_case for event names
- Be descriptive but concise
- Use consistent naming patterns:
  - `{resource}_{action}` for resource operations (e.g., `list_created`)
  - `{feature}_used` for feature usage
  - `{process}_duration` for performance metrics
  - `{error_type}_occurred` for errors

## Environment Detection

The tracker automatically detects whether it's running in Google Cloud by checking for the `GOOGLE_CLOUD_PROJECT` environment variable:

- **Google Cloud**: Events are sent to Cloud Logging using the `tracker` log name
- **Local Development**: Events are logged as JSON to the `gyrinx.tracker` Python logger

## Querying Events in Google Cloud

When running in production, events can be queried using Cloud Logging queries:

```
resource.type="cloud_run_revision"
jsonPayload.event="stat_config_fallback_used"
```

You can filter by labels:

```
resource.type="cloud_run_revision"
jsonPayload.event="api_call"
jsonPayload.labels.endpoint="/api/v1/fighters"
```

## Best Practices

1. **Don't Track Sensitive Data**: Avoid including passwords, API keys, or personal information in events
2. **Use Consistent Labels**: Establish standard label names across your application
3. **Track Sparingly**: Focus on important events that provide business value
4. **Include Context**: Add enough labels to make events useful for debugging and analysis
5. **Handle Failures Gracefully**: The tracker is designed not to crash your application if logging fails

## Implementation Details

The tracker module:
- Attempts to import `google-cloud-logging` when in Google Cloud environment
- Falls back to JSON logging if the import fails or in local development
- Structures all events with `event`, `n` (count), optional `value`, and `labels`
- Logs at INFO level to ensure events are captured in production

## Future Considerations

As the tracking system evolves, consider:
- Adding sampling for high-frequency events
- Creating dashboards for key metrics
- Setting up alerts based on event patterns
- Implementing event schemas for validation
