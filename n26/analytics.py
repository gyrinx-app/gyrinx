"""What this edition records about what players do, and the one door it
records it through.

Activity tracking is the site's, not an edition's: one events table serves
both, and the dashboards, the log stream and every question anyone asks of
them are built on that one table. A second store here would answer none of
those questions — it would only make "how many people did X this week"
impossible to answer for the site as a whole.

So this module is the whole of n26's dependency on the platform's analytics.
Every n26 call site goes through :func:`record`; nothing else in ``n26/``
imports ``gyrinx.analytics``. Keeping it to one file means the seam can be
read, tested and moved in one place, and it is the reason the boundary rule in
``n26/CLAUDE.md`` names this file rather than a package.

The words are ours. A noun claimed by one edition cannot be claimed by
another, so "gang" here and "list" next door stay different things and the
edition each row belongs to follows from the noun alone — nothing to pass, so
nothing to forget.

Recording never interferes with what it observes: ``log_event`` swallows its
own failures and returns ``None``. Call it *after* the operation has
committed, never inside ``operation(...)`` — an event written inside the
transaction would be rolled back with a refused purchase, and a database error
raised while writing it would take the purchase down with it.
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
    """The things a player acts on in this edition."""

    GANG = "gang", "Gang"
    # The stored value carries the edition because the other one claimed the
    # bare word first, and a noun says which edition an event came from. The
    # label is what anybody reads, and both editions call this a campaign.
    CAMPAIGN = "n26_campaign", "Campaign"
    MODEL = "model", "Model"
    ASSIGNMENT = "assignment", "Assignment"
    CHOICE = "choice", "Choice"
    PRINT_RUN = "print_run", "Print Run"
    INGEST = "ingest", "Ingest"


register_nouns(Edition.N26, N26Noun)


def record(request, noun, verb, obj=None, **context):
    """Record one thing a player did.

    ``obj`` is the row the action was about, when there is one; anything else
    worth asking a question about later goes in ``context``.

    One click, one event. An action that touches many rows — a print of a
    whole roster, an ingest of a whole spreadsheet — is still one event
    carrying counts, because a row-by-row loop turns a page into as many
    writes as it has rows.

    A speculative fetch is not a click. Browsers prefetch and prerender
    pages nobody has opened yet — tab strips ask for it — and an event
    recorded then would count readers who never arrived.
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


# Lines on the dashboard's growth chart. Archived rows are counted too: the
# chart is about what people made, and a gang deleted last week was still
# founded the week before.
#
# The models are imported inside the callables, not at the top of this file,
# because the app registry imports this module while it is still loading them.
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
