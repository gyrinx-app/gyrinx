"""Show owner-only gang history, filtered and paginated through URL state.

History includes earlier names and note-edit activity, so it is not part of
the shareable roster. Filter by query, kind and model before paginating
complete acts newest first.
"""

from dataclasses import dataclass

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone

from n26.core import history
from n26.core.views.gangs import _pages
from n26.core.views.permissions import _own_gang_or_404

#: Complete history acts per page, after folding their events.
PER_PAGE = 50

#: User-facing filter categories in menu order.
KINDS = {
    "credits": "Credits",
    "kit": "Equipment",
    "model": "Models",
    "gang": "The gang",
}


@dataclass
class Day:
    """History acts grouped by local date, retaining newest-first order."""

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

    #: Include archived or absent roster models still named by history.
    #: Resolve selected flags before rendering.
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

    # Reverse before pagination so the first page contains the latest acts.
    matched = len(acts)
    page = Paginator(list(reversed(acts)), PER_PAGE).get_page(request.GET.get("page"))

    return render(
        request,
        "n26/gang_history.html",
        {
            "gang": gang,
            "days": by_day(page.object_list),
            # Keep displayed, matched and unfiltered totals separate.
            "shown": len(page.object_list),
            "matched": matched,
            "total": total,
            "pages": _pages(request, page) if page.paginator.num_pages > 1 else None,
            "query": query,
            "kind_options": kind_options,
            "model_options": model_options,
            "narrowed": bool(query or kind or model),
        },
    )


def by_day(acts):
    """Group newest-first acts by local date for gang history and campaign logs."""
    days = []
    for act in acts:
        date = timezone.localtime(act.when).date()
        if not days or days[-1].date != date:
            days.append(Day(date=date, acts=[]))
        days[-1].acts.append(act)
    return days


def filter_campaign_acts(request, acts):
    """Narrow complete acts, retaining folded transfers and their identities."""
    from django.contrib.auth.models import User

    from n26.core.forms import CampaignLogFilterForm
    from n26.core.models import Gang

    def actor_of(act):
        if act.actor_pk is not None:
            return act.actor_pk
        if act.actor_user is not None:
            return act.actor_user.pk
        return request.user.pk if act.actor == "You" else None

    def gangs_of(act):
        return {act.gang_pk, *act.related_gang_pks} - {""}

    people = {actor_of(act) for act in acts} - {None}
    gang_ids = {pk for act in acts for pk in gangs_of(act)}
    players = sorted(
        User.objects.filter(pk__in=people).values_list("pk", "username"),
        key=lambda row: row[1].casefold(),
    )
    gangs = sorted(
        Gang.objects.filter(pk__in=gang_ids).values_list("pk", "name"),
        key=lambda row: row[1].casefold(),
    )
    kinds = {**KINDS, "gang": "Gang changes", "campaign": "Campaign activity"}
    form = CampaignLogFilterForm(
        request.GET or None, players=players, gangs=gangs, kinds=kinds.items()
    )
    filtered = acts
    if form.is_bound:
        if not form.is_valid():
            filtered = []
        else:
            data = form.cleaned_data
            if data["player"]:
                filtered = [
                    act for act in filtered if str(actor_of(act)) == data["player"]
                ]
            if data["gang"]:
                filtered = [act for act in filtered if data["gang"] in gangs_of(act)]
            if data["kind"]:
                filtered = [act for act in filtered if act.category == data["kind"]]
            if data["from_date"]:
                filtered = [
                    act
                    for act in filtered
                    if timezone.localdate(act.when) >= data["from_date"]
                ]
            if data["to_date"]:
                filtered = [
                    act
                    for act in filtered
                    if timezone.localdate(act.when) <= data["to_date"]
                ]
    narrowed = any(request.GET.get(name) for name in form.fields)
    return form, filtered, narrowed
