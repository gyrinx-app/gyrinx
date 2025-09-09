"""
Lightweight helpers to capture SQL executed by a callable (function, method, view)
using Django's CaptureQueriesContext. Designed for quick diagnostics in tests,
management commands, or ad-hoc profiling.

Typical usage:

    result, info = capture_queries(lambda: MyModel.objects.filter(...).list())
    print(info.count, info.total_time)
    for q in info.queries:
        print(q["time"], q["sql"])

Or as a decorator:

    @with_query_capture(using="replica")
    def do_work():
        ...
        return "ok"

    (result, info) = do_work()
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from django.db import connections
from django.test.utils import CaptureQueriesContext

logger = logging.getLogger(__name__)


@dataclass
class QueryInfo:
    """Summary of SQL captured during a function call.

    Attributes:
        count: Total number of SQL statements executed.
        total_time: Sum of execution times across all captured statements, in seconds.
        queries: Raw entries as emitted by Django's CaptureQueriesContext. Each dict has:
            - "sql": The SQL string sent to the database (driver-rendered).
            - "time": Execution time as a string in seconds (e.g., "0.003").
    """

    count: int
    total_time: float
    queries: List[Dict[str, str]]  # each has "sql" and "time" (string seconds)


def capture_queries(
    func: Callable[[], Any], *, using: str = "default"
) -> Tuple[Any, QueryInfo]:
    """Run a callable with SQL query capture enabled.

    This wraps the callable in Django's ``CaptureQueriesContext`` for the specified
    database connection and returns both the callable's result and a structured
    summary of the SQL executed.

    Works even if ``DEBUG=False`` because the context forces a debug cursor
    for the duration of the capture.

    Args:
        func: Zero-argument callable to execute (wrap with ``lambda`` if needed to
            bind arguments).
        using: Django database alias to capture against (defaults to ``"default"``).

    Returns:
        A tuple ``(result, info)`` where:
            - ``result`` is whatever ``func()`` returns.
            - ``info`` is a :class:`QueryInfo` containing count, total_time (seconds),
              and the raw captured queries.

    Notes:
        * The time per query is captured as strings by Django; this function converts
          them to ``float`` only when computing ``total_time``. Individual entries in
          ``info.queries`` keep the original string values.
        * Nested calls that also use ``CaptureQueriesContext`` will aggregate at the
          outermost level; Django appends to the same list during the context.
        * If your callable issues queries to multiple database aliases, only queries
          executed via the specified ``using`` connection are captured.

    Examples:
        >>> result, info = capture_queries(lambda: MyModel.objects.count())
        >>> info.count
        1
        >>> round(info.total_time, 6) >= 0.0
        True
    """
    conn = connections[using]
    with CaptureQueriesContext(conn) as ctx:
        result = func()

    # ctx.captured_queries is a list of {"sql": "...", "time": "..."} (time as string seconds)
    total_time = sum(float(q.get("time") or 0.0) for q in ctx.captured_queries)

    info = QueryInfo(
        count=len(ctx.captured_queries),
        total_time=total_time,
        queries=ctx.captured_queries,
    )
    return result, info


def with_query_capture(using="default", *log_args, **log_kwargs):
    """Decorator that returns ``(result, QueryInfo)`` when the function is called.

    Apply to any function to execute it under query capture for the given database
    alias. The decorated function’s *runtime return value* becomes a tuple of the
    original result and the accompanying :class:`QueryInfo`.

    Args:
        using: Django database alias to capture against (defaults to ``"default"``).

    Returns:
        A decorator that, when applied, causes the wrapped function to return
        ``(result, QueryInfo)`` instead of just ``result``.

    Example:
        >>> @with_query_capture()
        ... def do_work(n):
        ...     return n * 2
        ...
        >>> (value, info) = do_work(5)
        >>> value
        10
        >>> isinstance(info.count, int)
        True

    Caution:
        Because the decorator changes the return type at runtime, avoid applying it
        directly to production code paths that callers expect to return a specific
        type. It’s ideal for tests, diagnostics, shell use, and management commands.
    """

    def deco(fn):
        def inner(*args, **kwargs):
            result, info = capture_queries(lambda: fn(*args, **kwargs), using=using)
            log_query_info(info, *log_args, **log_kwargs)
            return result

        return inner

    return deco


def log_query_info(info, *, limit: Optional[int] = 10, level: int = logging.DEBUG):
    """Pretty-print a QueryInfo object to the Python logger.

    Args:
        info: QueryInfo instance.
        limit: Optional max number of queries to show (defaults to 10).
               Set to None to show all.
        level: Logging level to use (default DEBUG).
    """
    header = f"Captured {info.count} queries in {info.total_time:.3f} seconds"
    logger.log(level, header)

    # Show queries up to limit
    queries = info.queries if limit is None else info.queries[:limit]
    for idx, q in enumerate(queries, start=1):
        sql = q.get("sql", "").strip()
        time = q.get("time", "?")
        logger.log(level, f"  {idx:>3}. ({time}s) {sql}")

    if limit is not None and info.count > limit:
        remaining = info.count - limit
        logger.log(level, f"  ... ({remaining} more queries not shown)")
