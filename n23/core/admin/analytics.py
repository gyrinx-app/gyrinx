"""What this edition contributes to the platform's analytics dashboard.

The dashboard's growth chart used to query ``List``/``ListFighter``/``Campaign``
directly from ``gyrinx/analytics/admin.py``, which made the platform import the
edition. The lines are declared here instead and pushed into the platform's
registry; the platform accumulates them without knowing what they count.

Imported by ``n23.core.admin`` — which Django imports during
``admin.autodiscover()`` — so the series are registered before any request is
served. Keep the import in ``n23/core/admin/__init__.py``: dropping it does not
break anything loudly, it just empties the chart.
"""

from gyrinx.analytics.nouns import Edition
from gyrinx.analytics.registry import (
    GrowthSeries,
    daily_counts_by_date,
    register_growth_series,
)
from n23.core.models import Campaign, List, ListFighter

__all__ = []


def _fighters_in_list_building(start_date):
    return daily_counts_by_date(
        ListFighter.objects.filter(list__status=List.LIST_BUILDING), start_date
    )


def _list_building_lists(start_date):
    return daily_counts_by_date(
        List.objects.filter(status=List.LIST_BUILDING), start_date
    )


def _campaigns(start_date):
    return daily_counts_by_date(Campaign.objects.all(), start_date)


# Registration order is chart order. The labels name the edition because the
# chart carries both editions' lines, and "Fighters" beside "Models" says
# nothing about which game either belongs to.
register_growth_series(
    GrowthSeries(
        key="n23_fighters",
        label="N23 Fighters (Cumulative)",
        border_color="rgb(75, 192, 192)",
        background_color="rgba(75, 192, 192, 0.2)",
        daily_counts=_fighters_in_list_building,
        edition=Edition.N23,
    )
)
register_growth_series(
    GrowthSeries(
        key="n23_lists",
        label="N23 Lists (Cumulative)",
        border_color="rgb(54, 162, 235)",
        background_color="rgba(54, 162, 235, 0.2)",
        daily_counts=_list_building_lists,
        edition=Edition.N23,
    )
)
register_growth_series(
    GrowthSeries(
        key="n23_campaigns",
        label="N23 Campaigns (Cumulative)",
        border_color="rgb(255, 99, 132)",
        background_color="rgba(255, 99, 132, 0.2)",
        daily_counts=_campaigns,
        edition=Edition.N23,
    )
)
