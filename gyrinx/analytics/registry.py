"""Register edition-specific series for the cumulative growth chart.

Editions supply daily counts; the platform accumulates them and prepares
Chart.js data. Register from edition admin packages during autodiscovery.
An empty registry produces an empty chart.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from django.db.models import Count, QuerySet
from django.db.models.functions import TruncDate

__all__ = [
    "GrowthSeries",
    "daily_counts_by_date",
    "growth_series",
    "register_growth_series",
]


@dataclass(frozen=True)
class GrowthSeries:
    """A cumulative chart series with its edition and daily count function.

    The function receives the window start datetime and returns counts by
    date. Missing dates are treated as zero. The edition field allows the
    dashboard to filter series without combining editions.
    """

    key: str
    label: str
    border_color: str
    background_color: str
    daily_counts: Callable[[datetime], Mapping[date, int]]
    edition: str


_series: dict[str, GrowthSeries] = {}


def register_growth_series(series: GrowthSeries) -> None:
    """Add a line to the growth chart, replacing any earlier one with its key.

    Re-registering a key keeps the original chart position, so a series can be
    overridden without reshuffling the chart.
    """
    _series[series.key] = series


def growth_series(edition: str | None = None) -> tuple[GrowthSeries, ...]:
    """Every registered series, in registration order.

    Narrowed to one edition's lines when ``edition`` is given.
    """
    series = tuple(_series.values())
    if edition is None:
        return series
    return tuple(s for s in series if s.edition == edition)


def daily_counts_by_date(
    queryset: QuerySet, start_date: datetime, field: str = "created"
) -> dict[date, int]:
    """Count queryset records by calendar date from start_date, inclusive."""
    rows = (
        queryset.filter(**{f"{field}__gte": start_date})
        .annotate(_day=TruncDate(field))
        .values("_day")
        .annotate(_count=Count("id"))
        .order_by("_day")
    )
    return {row["_day"]: row["_count"] for row in rows}
