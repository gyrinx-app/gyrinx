"""N26 analytics registration and the edition boundary to the shared event log. Record
events after the domain transaction commits so analytics failures cannot roll back the
operation.

Nouns uniquely identify their edition across the platform; N26 declares its nouns and
growth series here.
"""

from django.db import models

from gyrinx.analytics.models import EventVerb, log_event
from gyrinx.analytics.nouns import Edition, register_nouns
from gyrinx.analytics.registry import (
    GrowthSeries,
    daily_counts_by_date,
    register_growth_series,
)

__all__ = ["EventVerb", "N26Noun", "record"]


class N26Noun(models.TextChoices):
    """Registered subjects for N26 analytics events."""

    GANG = "gang", "Gang"
    # Use an edition-specific stored campaign noun because analytics derives each
    # event's edition from its noun.
    CAMPAIGN = "n26_campaign", "Campaign"
    MODEL = "model", "Model"
    ASSIGNMENT = "assignment", "Assignment"
    CHOICE = "choice", "Choice"
    PRINT_RUN = "print_run", "Print Run"
    INGEST = "ingest", "Ingest"


register_nouns(Edition.N26, N26Noun)


def record(request, noun, verb, obj=None, **context):
    """Record one event with an optional subject and additional context, ignoring prefetch
    requests. For bulk operations, report aggregate counts in one event rather than
    recording each affected assignment.
    """
    if request.headers.get("Sec-Purpose", "").startswith("prefetch"):
        return None
    return log_event(
        user=request.user,
        noun=noun,
        verb=verb,
        object=obj,
        request=request,
        **context,
    )


def _gangs(start_date):
    from n26.core.models import Gang

    return daily_counts_by_date(Gang.objects.all(), start_date)


def _models(start_date):
    from n26.core.models import Miniature

    return daily_counts_by_date(Miniature.objects.all(), start_date)


# Count archived records in cumulative creation totals. Import models inside callbacks
# because registration runs while the app registry is loading.
register_growth_series(
    GrowthSeries(
        key="n26_gangs",
        label="N26 Gangs (Cumulative)",
        border_color="rgb(255, 159, 64)",
        background_color="rgba(255, 159, 64, 0.2)",
        daily_counts=_gangs,
        edition=Edition.N26,
    )
)
register_growth_series(
    GrowthSeries(
        key="n26_models",
        label="N26 Models (Cumulative)",
        border_color="rgb(153, 102, 255)",
        background_color="rgba(153, 102, 255, 0.2)",
        daily_counts=_models,
        edition=Edition.N26,
    )
)
