"""Where a player lands, what they own, and founding one more."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

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

    The way into a fighter's skills is pointed the same way, and costs
    one query for the whole roster: which collections hold what a model
    learns is asked once, and each card already carries the collections
    its own grid reaches. A fighter with no grid gets no control, which
    is a content gap showing rather than a screen being withheld.
    """
    from n26.core.render import render_gang
    from n26.core.views.choose import link_slots
    from n26.core.views.learn import link_skills

    gang = _own_gang_or_404(request, pk)
    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    link_skills(*sheet.models)
    # One question at a time: a URL naming two dialogs draws the leaving
    # one, because two open modals is not a state the page can mean.
    leaving = _leaving(request, gang)
    return render(
        request,
        "n26/gang_sheet.html",
        {
            "gang": gang,
            "sheet": sheet,
            "renaming": None if leaving else _renaming(request, gang),
            "leaving": leaving,
        },
    )


def _renaming(request, gang):
    """The model ``?rename=`` says is being renamed, if it is on this roster.

    Open is a server state: the sheet draws the rename dialog only when
    the URL names one of the gang's own live members. Anything else — a
    stale link, somebody else's fighter, a pk that is not a ULID — is a
    page without a dialog rather than an error worth a screen.
    """
    return _fighter_named(request, gang, "rename")


def _fighter_named(request, gang, param):
    """The live member ``param`` names in this gang, or None.

    The same shrug as ``_renaming``'s: a stale link, somebody else's
    fighter, or a pk that is not a ULID is a page without a dialog.
    """
    from django.core.exceptions import ValidationError

    from n26.core.models import Miniature

    named = request.GET.get(param)
    if not named:
        return None
    try:
        return Miniature.objects.select_related("membership").get(
            pk=named, membership__gang=gang, membership__archived=False
        )
    except Miniature.DoesNotExist, ValidationError:
        return None


def _kit_roots(miniature):
    """The live root assignments the model carries — its own kit, not
    the parts hanging off it."""
    from n26.core.models import Assignment

    return list(
        Assignment.objects.filter(
            miniature=miniature, parent__isnull=True, archived=False
        ).select_related("ledger_entry")
    )


def _leaving(request, gang):
    """The delete or refund question ``?delete=``/``?refund=`` says is open.

    The dialog quotes its own arithmetic, so everything it says is
    computed here from the same functions the act will use: what a full
    refund returns, what the fighter alone returns, and how many kit
    lines a stash disposal would move — only lines money was paid for,
    because a built-in knife moved to the stash is clutter the next hire
    re-arms for free.
    """
    from n26.core.operations import refund_of, subtree

    for kind in ("delete", "refund"):
        miniature = _fighter_named(request, gang, kind)
        if miniature is not None:
            break
    else:
        return None

    membership = miniature.membership
    in_hire = {membership.pk, *(row.pk for row in subtree(membership))}
    roots = _kit_roots(miniature)
    _, fighter_paid = refund_of(membership)
    extra_paid = sum(refund_of(root)[1] for root in roots if root.pk not in in_hire)
    stashable = sum(1 for root in roots if refund_of(root)[1] > 0)
    return {
        "kind": kind,
        "miniature": miniature,
        "full_paid": fighter_paid + extra_paid,
        "fighter_paid": fighter_paid,
        "stashable": stashable,
    }


@login_required
def delete_fighter(request, pk):
    """Delete one model: the fighter goes, and what was paid stays spent."""
    return _dismiss(request, pk, kind="delete")


@login_required
def refund_fighter(request, pk):
    """Refund one model: the fighter goes, and what was paid comes back.

    Paid, not worth: a refund undoes purchases, so what returns is the
    ledger's own figure — free and granted things return nothing.
    """
    return _dismiss(request, pk, kind="refund")


def _dismiss(request, pk, kind):
    """The act behind both leaving dialogs.

    ``kit=stash`` first moves every kit line money was paid for to the
    stash — where each keeps its pinned rating, because a move never
    re-prices — and then the fighter leaves with whatever is left: the
    built-ins, and anything their gear brought in. GET reopens the
    dialog instead of acting.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import operation, refund_of, subtree
    from n26.core.views.permissions import _own_miniature_or_404

    miniature = _own_miniature_or_404(request, pk)
    membership = miniature.membership
    gang = membership.gang
    sheet_url = reverse("n26-gang", args=[gang.pk])
    if request.method != "POST":
        return redirect(f"{sheet_url}?{kind}={miniature.pk}")

    was = miniature.name
    stash_kit = request.POST.get("kit") == "stash"
    with operation(gang, actor=request.user) as op:
        moved = 0
        if stash_kit:
            for root in _kit_roots(miniature):
                if refund_of(root)[1] > 0:
                    op.move(root, gang.stash, note=f"{was} left it behind")
                    moved += 1
        # What the whole departure returns, asked before anything is
        # archived: refund_of skips archived rows, so asking afterwards
        # would answer zero.
        in_hire = {membership.pk, *(row.pk for row in subtree(membership))}
        remaining = [root for root in _kit_roots(miniature) if root.pk not in in_hire]
        paid_back = 0
        if kind == "refund":
            paid_back = refund_of(membership)[1] + sum(
                refund_of(root)[1] for root in remaining
            )
        act = op.refund if kind == "refund" else op.remove
        act(membership)
        for root in remaining:
            if not root.archived:
                act(root)

    record(
        request,
        N26Noun.MODEL,
        EventVerb.DELETE,
        miniature,
        kind=kind,
        kit="stash" if stash_kit else "with",
        refunded=paid_back,
    )
    stashed = f" Their kit is in the stash ({moved} line{'s' if moved != 1 else ''})."
    if kind == "refund":
        messages.success(
            request,
            f"Refunded {was} — {paid_back}¢ back." + (stashed if moved else ""),
        )
    else:
        messages.success(request, f"Deleted {was}." + (stashed if moved else ""))
    return redirect(sheet_url)


@login_required
def rename_fighter(request, pk):
    """Rename one model: the act behind the gang sheet's dialog.

    The name is the model's own and nothing the books watch — no rating
    moves, no ledger row is written — so this is a plain save rather
    than an operation. GET reopens the dialog instead of acting, so the
    address can be followed, sent, or reloaded without renaming anyone.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.forms import RenameFighterForm
    from n26.core.views.permissions import _own_miniature_or_404

    miniature = _own_miniature_or_404(request, pk)
    sheet_url = reverse("n26-gang", args=[miniature.membership.gang_id])
    if request.method != "POST":
        return redirect(f"{sheet_url}?rename={miniature.pk}")

    form = RenameFighterForm(request.POST)
    if not form.is_valid():
        messages.error(request, "A model needs a name.")
        return redirect(f"{sheet_url}?rename={miniature.pk}")

    was = miniature.name
    miniature.name = form.cleaned_data["name"]
    if miniature.name == was:
        return redirect(sheet_url)
    miniature.save(update_fields=["name"])
    record(request, N26Noun.MODEL, EventVerb.UPDATE, miniature, renamed_from=was)
    messages.success(request, f"Renamed {was} to {miniature.name}.")
    return redirect(sheet_url)


@login_required
def create_gang(request):
    """Found a gang: the design system's create form, wired to write.

    POST founds for real — the Gang row, then its founding assignment
    and whatever the type's built-ins bring, in one operation — and
    lands back on the dashboard where the new gang is now a row.
    """
    from n26.analytics import EventVerb, N26Noun, record
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
            # Recorded after the founding has committed: an event written
            # inside the operation would vanish with it if it unwound.
            record(
                request,
                N26Noun.GANG,
                EventVerb.CREATE,
                gang,
                gang_type=gang_type.name,
                starting_credits=budget,
            )
            messages.success(request, f"Founded {gang.name}.")
            # Straight to the new gang's own sheet: hiring is the next
            # thing a founder does, and the dashboard is a detour past
            # every gang they already have.
            return redirect("n26-gang", pk=gang.pk)
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
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.models import Miniature

    gang = _own_gang_or_404(request, pk)
    if request.method == "POST":
        gang.archive()
        # Recorded as a deletion, which is what the player did. That the row
        # survives is how the ledger stays true, not something they asked for.
        record(request, N26Noun.GANG, EventVerb.DELETE, gang)
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
