# Debugging SQL Queries

We have some utilities that let you capture and inspect the SQL Django executes during a function call.
They are built on `CaptureQueriesContext` and work even when `DEBUG=False`.

## Capturing queries around a function call

```python
from gyrinx.query import capture_queries, log_query_info
from gyrinx.core.models import MyModel

# Capture queries executed inside the lambda
result, info = capture_queries(lambda: MyModel.objects.filter(foo="bar").count())

print(info.count, "queries in", info.total_time, "seconds")
for q in info.queries:
    print(q["time"], q["sql"])

# Or log them nicely
log_query_info(info)
```

Example log output:

```
DEBUG:gyrinx.db:Captured 3 queries in 0.012 seconds
DEBUG:gyrinx.db:    1. (0.003s) SELECT ...
DEBUG:gyrinx.db:    2. (0.004s) SELECT ...
DEBUG:gyrinx.db:    3. (0.005s) SELECT ...
```

## Using as a decorator

```python
from gyrinx.query import with_query_capture

@with_query_capture()
def load_stuff():
    return list(MyModel.objects.all())
```

Now when you call:

```python
result = load_stuff()
```

you’ll see a summary of the queries automatically logged.

The decorator logs query info but returns only the original function result (unlike `capture_queries`, which returns `(result, info)`).

## Options

* **Database alias**: Pass `using="replica"` to target a different connection.
* **Logging verbosity**: `log_query_info(info, limit=5, level=logging.INFO)`
  * `limit`: max number of queries to show (None = show all).
  * `level`: logging level (defaults to DEBUG).

## When to use
* Profiling views or functions in local dev.
* Writing tests that assert on query counts.
* Inspecting query behavior in management commands.

⚠️ **Note**: Avoid leaving decorators or capture calls in production code paths, since they alter return values and add logging noise. They're best for temporary diagnostics and tests.

## Using in pytest tests

You can use `capture_queries` inside tests to make assertions about the number or cost of queries.
This helps catch N+1 issues or overly expensive ORM patterns.

```python
import pytest
from gyrinx.query import capture_queries
from gyrinx.core.models import MyModel


@pytest.mark.django_db
def test_list_view_queries(client):
    # Example: ensure hitting the list view doesn't explode into N+1 queries
    def call_view():
        return client.get("/mymodels/")

    response, info = capture_queries(call_view)

    assert response.status_code == 200
    # Fail the test if more than 5 queries are executed
    assert info.count <= 5, f"Too many queries: {info.count}\n{info.queries}"


@pytest.mark.django_db
def test_queryset_is_prefetched():
    def run_query():
        return list(MyModel.objects.select_related("author")[:10])

    result, info = capture_queries(run_query)

    assert len(result) == 10
    # Ensure exactly 1 query was used (no N+1 on author)
    assert info.count == 1
```
