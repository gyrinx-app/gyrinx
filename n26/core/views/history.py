"""The gang's history page — everything done to it, newest first.

The owner's page: the history says when notes were edited and what
things were renamed from, which is the owner's business before it is a
reader's. The roster itself stays the shareable surface.

Every narrowing lives in the URL — ``?q=``, ``?kind=``, ``?model=`` —
so a filtered view is an address someone can keep, and the page works
with no script at all.
"""

from dataclasses import dataclass

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from n26.core import history
from n26.core.views.permissions import _own_gang_or_404

#: The filter's buckets, in the order the select offers them. The words
#: are the reader's: which button they clicked, not how it was stored.
KINDS = {
    "money": "Money",
    "kit": "Equipment",
    "model": "Models",
    "gang": "The gang",
}


@dataclass
class Day:
    """One date's worth of acts, newest act first."""

    date: object
    acts: list


@login_required
def gang_history(request, pk):
    gang = _own_gang_or_404(request, pk)
    acts = history.build(gang, viewer=request.user)
    total = len(acts)

    query = request.GET.get("q", "").strip()
    kind = request.GET.get("kind", "")
    if kind not in KINDS:
        kind = ""
    model = request.GET.get("model", "")

    #: Every model the history names, whether or not it is still on the
    #: roster — a filter that cannot find the dead cannot explain them.
    #: Which option is selected is decided here: the template only reads
    #: flags.
    named = sorted(
        {(a.miniature_pk, a.miniature_name) for a in acts if a.miniature_pk},
        key=lambda pair: pair[1].casefold(),
    )
    model_options = [
        {"value": pk, "label": name, "selected": pk == model} for pk, name in named
    ]
    kind_options = [
        {"value": value, "label": label, "selected": value == kind}
        for value, label in KINDS.items()
    ]

    if query:
        want = query.casefold()
        acts = [a for a in acts if want in a.search]
    if kind:
        acts = [a for a in acts if a.category == kind]
    if model:
        acts = [a for a in acts if a.miniature_pk == model]

    return render(
        request,
        "n26/gang_history.html",
        {
            "gang": gang,
            "days": _by_day(acts),
            "shown": len(acts),
            "total": total,
            "query": query,
            "kind_options": kind_options,
            "model_options": model_options,
            "narrowed": bool(query or kind or model),
        },
    )


def _by_day(acts):
    """Newest first, gathered under the local date each act landed on."""
    days = []
    for act in reversed(acts):
        date = timezone.localtime(act.when).date()
        if not days or days[-1].date != date:
            days.append(Day(date=date, acts=[]))
        days[-1].acts.append(act)
    return days
