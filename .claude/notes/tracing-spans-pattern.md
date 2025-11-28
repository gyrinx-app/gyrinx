# OpenTelemetry Tracing for Cloud Trace

## Setup

Dependencies added to `requirements.txt`:
```
opentelemetry-sdk>=1.28.0
opentelemetry-exporter-gcp-trace>=1.8.0
opentelemetry-instrumentation-django>=0.49b0
```

Tracing is initialized in `gyrinx/wsgi.py` and `gyrinx/asgi.py` via import of `gyrinx.tracing`.

## Usage

### Context Manager

```python
from gyrinx.tracing import span

def process_list(list_obj):
    with span("process_list", list_id=str(list_obj.id)):
        for fighter in list_obj.fighters.all():
            with span("process_fighter", fighter_id=str(fighter.id)):
                calculate_fighter_cost(fighter)
```

### Decorator

```python
from gyrinx.tracing import traced

@traced("calculate_cost")
def calculate_fighter_cost(fighter):
    return fighter.calculate_cost()

# With default attributes
@traced("cache_operation", cache_type="list_cost")
def update_cache(key, value):
    cache.set(key, value)
```

### Check if Enabled

```python
from gyrinx.tracing import is_tracing_enabled

if is_tracing_enabled():
    # Do something tracing-specific
    pass
```

## How It Works

1. **Automatic enablement** - Tracing is only enabled when `GOOGLE_CLOUD_PROJECT` env var is set (automatic on Cloud Run)
2. **Django auto-instrumentation** - All HTTP requests automatically get spans
3. **Trace context propagation** - Custom spans appear as children of the Cloud Run request span via `X-Cloud-Trace-Context` header
4. **Exception recording** - Exceptions are automatically recorded on spans and marked as errors
5. **Zero overhead when disabled** - `span()` and `@traced()` are no-ops in development

## Viewing Traces

1. Go to GCP Console > Cloud Trace
2. Find traces by time range or trace ID
3. Click to see span hierarchy and timing

## References

- [Cloud Trace Python Setup](https://cloud.google.com/trace/docs/setup/python-ot)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [Django Instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/django/django.html)
