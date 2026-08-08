"""Where a player lands, what they own, and founding one more."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from n26.core.views.permissions import _own_gang_or_404


@login_required
def dashboard(request):
    """The edition's front page: your gangs, and what changed lately.

    Assembled entirely from the design system's components — the view
    supplies rows and the components draw them, so this page and the
    gallery's shell can only drift by someone editing the library. The
    gang search and the type filter are the gang-table's own; the rows
    just register their facets.
    """
    from gyrinx.site.models import ChangelogEntry

    return render(
        request,
        "n26/dashboard.html",
        {
            **_gang_table_context(request),
            "changelog": ChangelogEntry.objects.filter(archived=False)[:5],
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
    gangs, and the types present among them for the filter."""
    from n26.core.models import Gang

    owned = (
        Gang.objects.filter(owner=request.user, archived=False)
        .select_related("gang_type", "stash")
        .order_by("name")
    )
    return {
        "gangs": owned,
        # Deduplicated in order rather than sorted: the filter reads
        # better in the order the reader saw the types down the list.
        "gang_type_options": [
            {"value": name, "label": name}
            for name in dict.fromkeys(str(gang.gang_type) for gang in owned)
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
    """
    from n26.core.render import render_gang

    gang = _own_gang_or_404(request, pk)
    return render(
        request,
        "n26/gang_sheet.html",
        {"gang": gang, "sheet": render_gang(gang)},
    )


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
