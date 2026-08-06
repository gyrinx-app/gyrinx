"""Extension point: the lines plotted on the dashboard's growth chart.

The platform owns the analytics dashboard, but it has no idea what a gang or a
fighter is — only an edition does. So the dashboard asks: each edition
registers one :class:`GrowthSeries` per line it wants on the cumulative-growth
chart, carrying a callable that answers "how many of these were created on each
day since <date>?". The platform does the cumulating and the Chart.js shaping.

Editions register from their admin package, which Django imports during
``admin.autodiscover()`` — see ``n23/core/admin/analytics.py``. Registration is
therefore complete long before any dashboard request is served.

An empty registry is not an error: the chart simply has no lines.
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
    """One line on the cumulative-growth chart.

    ``daily_counts`` is called with the window's start datetime and returns a
    mapping of day to "how many were created that day". Days with none may be
    omitted — the platform accumulates the values and fills the gaps.
    """

    key: str
    label: str
    border_color: str
    background_color: str
    daily_counts: Callable[[datetime], Mapping[date, int]]


_series: dict[str, GrowthSeries] = {}


def register_growth_series(series: GrowthSeries) -> None:
    """Add a line to the growth chart, replacing any earlier one with its key.

    Re-registering a key keeps the original chart position, so a series can be
    overridden without reshuffling the chart.
    """
    _series[series.key] = series


def growth_series() -> tuple[GrowthSeries, ...]:
    """Every registered series, in registration order."""
    return tuple(_series.values())


def daily_counts_by_date(
    queryset: QuerySet, start_date: datetime, field: str = "created"
) -> dict[date, int]:
    """Count rows per calendar day since ``start_date`` — the usual series body.

    Offered here so editions don't each re-derive the ``TruncDate``/``Count``
    incantation, and so every series groups days the same way.
    """
    rows = (
        queryset.filter(**{f"{field}__gte": start_date})
        .annotate(_day=TruncDate(field))
        .values("_day")
        .annotate(_count=Count("id"))
        .order_by("_day")
    )
    return {row["_day"]: row["_count"] for row in rows}
