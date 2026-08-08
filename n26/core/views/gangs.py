"""Where a player lands, what they own, and founding one more."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from n26.core.views.permissions import _own_gang_or_404

# The changelog belongs to the site and both editions read the same
# table, so an entry reaches this dashboard only if someone tagged it for
# this edition. An entry nobody tagged appears on neither dashboard: a
# reader should not have to work out which edition a change was about.
CHANGELOG_TAG = "N26"


@login_required
def dashboard(request):
    """The edition's front page: your gangs, and what changed lately.

    Assembled entirely from the design system's components — the view
    supplies rows and the components draw them, so this page and the
    gallery's shell can only drift by someone editing the library. The
    type filter is the gang-table's own — the rows just register their
    facets — and its search box lands on the gangs page, so a query
    typed here and submitted is answered by the same view that answers
    ``/n26/gangs/?q=``.

    The changelog is the site's, narrowed to the entries tagged for this
    edition.
    """
    from gyrinx.site.models import ChangelogEntry

    return render(
        request,
        "n26/dashboard.html",
        {
            **_gang_table_context(request),
            # Tag names are unique but case-sensitively so: "N26" and "n26"
            # are two rows an admin can create, and an entry tagged with
            # either is meant for this page. Matching both is also why the
            # rows need deduplicating — an entry carrying both spellings
            # matches the join twice and would otherwise be listed twice,
            # taking two of the five places.
            "changelog": ChangelogEntry.objects.filter(
                archived=False, tags__name__iexact=CHANGELOG_TAG
            ).distinct()[:5],
        },
    )


@login_required
def gangs(request):
    """Every gang you own, on a page of its own.

    The dashboard's gangs tab shows the same rows in two thirds of a
    column beside the changelog; this is where the bar's Gangs link
    lands, so the list gets the whole width and nothing else competes
    with it. Same context, same component — the two cannot disagree
    about what a gang row looks like.
    """
    return render(request, "n26/gangs.html", _gang_table_context(request))


def _gang_table_context(request):
    """The rows and facets <c-n26.gang-table> needs: the viewer's own
    gangs, narrowed by ``?q=`` when there is one, and the types present
    among what survives.

    Name and gang type are searched because they are the two things a row
    shows, and the two the table's own in-page filter reads — a query that
    works in the box works after pressing Search.

    The matching is the platform's ``search_queryset``: full-text plus a
    substring fallback on every field, so "scav" finds "Scavvies". It
    knows nothing about either edition, and writing a second one here is
    how the two come to disagree about what a search means.
    """
    from gyrinx.querysets import search_queryset
    from n26.core.models import Gang

    query = request.GET.get("q", "").strip()
    owned = (
        Gang.objects.filter(owner=request.user, archived=False)
        .select_related("gang_type", "stash")
        .order_by("name")
    )
    found = search_queryset(owned, query, ["name", "gang_type__name"])
    return {
        "gangs": found,
        "query": query,
        # Deduplicated in order rather than sorted: the filter reads
        # better in the order the reader saw the types down the list.
        "gang_type_options": [
            {"value": name, "label": name}
            for name in dict.fromkeys(str(gang.gang_type) for gang in found)
        ],
    }


@login_required
def gang_sheet(request, pk):
    """One gang, whole: what it is worth, what it owns, who is in it.

    The design system's gang sheet over real rows. ``render_gang``
    already does the derivation — the gang's own lines, its choices and
    counters, the stash, a card per member — in a fixed number of
    queries however big the roster, so this view is the lookup and
    nothing else, and the page draws the same component the gallery's
    shell does.

    Scoped to the owner, and a gang belonging to someone else is a 404
    rather than a 403: which gangs exist is not something a stranger
    should be able to probe for.

    Every choice slot on the sheet — the gang's own and every member's —
    is pointed at its picker here, in one pass over what has already been
    derived. No queries, so a roster of sixteen costs what a roster of one
    does.
    """
    from n26.core.render import render_gang
    from n26.core.views.choose import link_slots

    gang = _own_gang_or_404(request, pk)
    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    return render(request, "n26/gang_sheet.html", {"gang": gang, "sheet": sheet})


@login_required
def create_gang(request):
    """Found a gang: the design system's create form, wired to write.

    POST founds for real — the Gang row, then its founding assignment
    and whatever the type's built-ins bring, in one operation — and
    lands back on the dashboard where the new gang is now a row.
    """
    from n26.core.forms import CreateGangForm
    from n26.core.models import Gang
    from n26.core.operations import operation

    if request.method == "POST":
        form = CreateGangForm(request.POST)
        if form.is_valid():
            budget = form.cleaned_data["starting_credits"]
            gang_type = form.cleaned_data["gang_type"]
            if budget is None:
                budget = gang_type.starting_credits
            gang = Gang.objects.create(
                name=form.cleaned_data["name"],
                gang_type=gang_type,
                owner=request.user,
                starting_credits=budget,
                credits=budget or 0,
                colour=form.cleaned_data["colour"],
            )
            with operation(gang, actor=request.user) as op:
                op.found(gang_type)
            messages.success(request, f"Founded {gang.name}.")
            return redirect("n26-dashboard")
    else:
        form = CreateGangForm()

    return render(
        request,
        "n26/create_gang.html",
        {"form": form, "gang_types": form.gang_type_choices()},
    )


@login_required
def delete_gang(request, pk):
    """Deleting a gang: the question at its own address, then the act.

    GET asks and changes nothing; the POST from that page archives. Two
    steps rather than one because the press is not reversible by the
    player who made it, and because a link that deleted what it pointed
    at would be deleted by anything that follows links.

    Archiving is the whole of it — the gang stops being listed, stops
    being searched, stops being drawn in the drawer, and its own pages
    stop opening, because every one of those readers already asks for
    live gangs only. Nothing underneath is touched: an assignment's
    rating and a ledger entry's paid credits are true statements about
    what happened, and they stay true whether or not the roster they
    describe is still on show.

    The confirmation counts the roster because the name alone is a weak
    thing to check a decision against, and a reader with two gangs of
    similar names deserves a second fact.
    """
    from n26.core.models import Miniature

    gang = _own_gang_or_404(request, pk)
    if request.method == "POST":
        gang.archive()
        messages.success(request, f"Deleted {gang.name}.")
        return redirect("n26-gangs")

    return render(
        request,
        "n26/delete_gang.html",
        {
            "gang": gang,
            # Live memberships only: a fighter already off the roster is
            # not one of the things this press takes away.
            "roster": Miniature.objects.filter(
                membership__gang=gang, membership__archived=False
            ).count(),
        },
    )
