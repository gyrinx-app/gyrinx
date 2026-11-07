"""Capture SQL counts and timings for diagnostics.

capture_queries returns (result, QueryInfo). with_query_capture logs the
summary and preserves the decorated function's return value.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.db import connections
from django.test.utils import CaptureQueriesContext

logger = logging.getLogger(__name__)


@dataclass
class QueryInfo:
    """Captured SQL count, total elapsed query time in seconds and raw query entries.

    Each raw entry retains Django's sql and string-valued time fields.
    """

    count: int
    total_time: float
    queries: list[dict[str, str]]  # each has "sql" and "time" (string seconds)


def capture_queries(
    func: Callable[[], Any], *, using: str = "default"
) -> tuple[Any, QueryInfo]:
    """Run a zero-argument callable and return its result with a SQL summary.

    Capture only the selected database alias. CaptureQueriesContext enables
    the debug cursor even with DEBUG=False. Total time converts the raw
    string timings to seconds; individual query entries remain unchanged.
    """
    conn = connections[using]
    with CaptureQueriesContext(conn) as ctx:
        result = func()

    # Django stores individual timings as strings; convert only the total.
    total_time = sum(float(q.get("time") or 0.0) for q in ctx.captured_queries)

    info = QueryInfo(
        count=len(ctx.captured_queries),
        total_time=total_time,
        queries=ctx.captured_queries,
    )
    return result, info


def with_query_capture(using="default", *log_args, **log_kwargs):
    """Log captured SQL for the selected alias while preserving the function's result.

    Forward log_args and log_kwargs to log_query_info.
    """

    def deco(fn):
        def inner(*args, **kwargs):
            result, info = capture_queries(lambda: fn(*args, **kwargs), using=using)
            log_query_info(info, *log_args, **log_kwargs)
            return result

        return inner

    return deco


def log_query_info(info, *, limit: int | None = 10, level: int = logging.DEBUG):
    """Log query count, total seconds and up to limit individual statements.

    Use limit=None to log every captured statement.
    """
    header = f"Captured {info.count} queries in {info.total_time:.3f} seconds"
    logger.log(level, header)

    queries = info.queries if limit is None else info.queries[:limit]
    for idx, q in enumerate(queries, start=1):
        sql = q.get("sql", "").strip()
        time = q.get("time", "?")
        logger.log(level, f"  {idx:>3}. ({time}s) {sql}")

    if limit is not None and info.count > limit:
        remaining = info.count - limit
        logger.log(level, f"  ... ({remaining} more queries not shown)")
