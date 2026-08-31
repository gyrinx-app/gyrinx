"""Where a player lands, what they own, and founding one more."""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.safestring import mark_safe

from n26.core.views.changelog import changelog_entries
from n26.core.views.permissions import (
    _any_gang_or_404,
    _own_gang_or_404,
    trade_points_href,
)

#: How many gangs a page of the list holds. A row carries a name, a
#: type, a strip of money and its controls, so this is about a screen
#: and a half of scrolling — enough to read down, few enough that the
#: page is not the whole table.
GANGS_PER_PAGE = 25


#: Drawn beside the Campaigns tab's label when something is waiting there.
#: Safe because it is ours: no part of it comes from anybody's input, and the
#: tab strip takes markup as a string because it is built in the browser.
CAMPAIGNS_WAITING = mark_safe(  # nosec B703 B308 - literal, no user input
    '<span aria-hidden="true" class="inline-block size-2 rounded-full'
    ' bg-accent align-middle"></span>'
)


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
    from n26.core.models import Campaign
    from n26.core.views.campaigns import campaign_rows, invitations_for
    from n26.flags import CAMPAIGNS, enabled

    # The tab is a place this reader can go only where the feature is open to
    # them; for everyone else it keeps saying it is being worked on. Asking
    # here rather than in the template keeps the decision where the rows are
    # fetched — a tab with rows nobody may reach would be the worse bug.
    campaigns_open = enabled(CAMPAIGNS, request.user)
    campaigns = (
        campaign_rows(
            Campaign.objects.involving(request.user)
            .filter(archived=False)
            .select_related("owner")
            .order_by("name", "pk"),
            request.user,
        )
        if campaigns_open
        else []
    )
    # An invitation waiting is the one thing on this page worth interrupting
    # for, so the tab wears a mark and the rows sit above the reader's own.
    # The mark is markup rather than a flag because the tab strip is built in
    # the browser from a registered string, and a string is what it can take.
    invitations = list(invitations_for(request.user)) if campaigns_open else []

    return render(
        request,
        "n26/dashboard.html",
        {
            **_record_table_context(request),
            "changelog": changelog_entries()[:5],
            "campaigns_open": campaigns_open,
            "campaigns": campaigns,
            "invitations": invitations,
            "waiting_invitations": len(invitations),
            "campaigns_mark": CAMPAIGNS_WAITING if invitations else "",
        },
    )


@login_required
def gangs(request):
    """Every gang you own, on a page of its own — or everybody's.

    The dashboard's gangs tab shows the same rows in two thirds of a
    column beside the changelog; this is where the bar's Gangs link
    lands, so the list gets the whole width and nothing else competes
    with it. Same context, same component — the two cannot disagree
    about what a gang row looks like.

    ``?everyone=1`` widens it to every gang on the site, which is the
    way to somebody else's roster: a sheet is readable by whoever holds
    its address, and this is where an address is found. Your own is the
    default, because that is what the link in the bar is for.
    """
    return render(
        request,
        "n26/gangs.html",
        _record_table_context(
            request,
            everyone=bool(request.GET.get("everyone")),
            per_page=GANGS_PER_PAGE,
        ),
    )


def _record_table_context(request, everyone=False, per_page=None):
    """The rows and facets <c-n26.record-table> needs: gangs — the
    viewer's own, or everybody's — narrowed by ``?q=`` when there is
    one, and the types present among what survives.

    Name and gang type are searched because they are the two things a row
    shows, and the two the table's own in-page filter reads — a query that
    works in the box works after clicking Search.

    The matching is the platform's ``search_queryset``: full-text plus a
    substring fallback on every field, so "scav" finds "Scavvies". It
    knows nothing about either edition, and writing a second one here is
    how the two come to disagree about what a search means.

    ``per_page`` cuts the answer into pages. Without it the caller gets
    the whole list, which is what a reader's own gangs on the dashboard
    are; the gangs page passes one, because every gang on the site is
    not a page anybody should be sent.
    """
    from gyrinx.querysets import search_queryset
    from n26.core.models import Gang

    query = request.GET.get("q", "").strip()
    listed = Gang.objects.filter(archived=False)
    if not everyone:
        listed = listed.filter(owner=request.user)
    listed = listed.select_related("gang_type", "stash", "owner").order_by("name")
    found = search_queryset(listed, query, ["name", "gang_type__name"])
    total = None
    pages = None
    if per_page is not None:
        page = Paginator(found, per_page).get_page(request.GET.get("page"))
        total = page.paginator.count
        pages = _pages(request, page) if page.paginator.num_pages > 1 else None
        found = page.object_list
    return {
        "gangs": found,
        "query": query,
        # How many rows this page carries, for a reader with no script:
        # the live count is Alpine's, and without it the number beside
        # the noun would be blank.
        "listed": len(found),
        # What the whole answer holds, where this is one page of it, so
        # the count can say "8 of 143" rather than leaving a reader to
        # wonder what the pager is for.
        "total": total,
        "pages": pages,
        # A row says whose it is only where that can differ; a page of
        # your own would print your name down the side of it.
        "show_owners": everyone,
        "everyone": everyone,
        # Deduplicated in order rather than sorted: the filter reads
        # better in the order the reader saw the types down the list.
        "gang_type_options": [
            {"value": name, "label": name}
            for name in dict.fromkeys(str(gang.gang_type) for gang in found)
        ],
    }


def _pages(request, page):
    """The numbered links under a paged list, addresses and all.

    Built here rather than by the kit's own automatic mode, which writes
    ``?page=2`` and nothing else: a reader who has searched, or asked
    for everybody's gangs, would lose the question they asked by turning
    the page. Every other parameter rides along.

    Django picks which numbers to draw and elides the middle of a long
    run, handing back a string where the gap goes; a gap is marked
    rather than linked, because there is no one page it leads to.
    """

    def address(number):
        asked = request.GET.copy()
        asked["page"] = number
        return f"?{asked.urlencode()}"

    numbers = []
    for number in page.paginator.get_elided_page_range(page.number):
        if number == page.paginator.ELLIPSIS:
            numbers.append({"elided": True})
        else:
            numbers.append(
                {
                    "elided": False,
                    "label": number,
                    "href": address(number),
                    "current": number == page.number,
                }
            )
    return {
        "numbers": numbers,
        "previous": address(page.previous_page_number()) if page.has_previous() else "",
        "next": address(page.next_page_number()) if page.has_next() else "",
        "number": page.number,
        "of": page.paginator.num_pages,
    }


def gang_sheet(request, pk):
    """One gang, whole: what it is worth, what it owns, who is in it.

    The design system's gang sheet over real rows. ``render_gang``
    already does the derivation — the gang's own lines, its choices and
    counters, the stash, a card per member — in a fixed number of
    queries however big the roster, so this view is the lookup and
    nothing else, and the page draws the same component the gallery's
    shell does.

    Anyone may read a roster, signed in or not — the address one player
    sends another shows the same gang to whoever opens it. Owning it is
    what adds the controls: the reader who does not gets the sheet with
    every button, dialog and picker left off, and choices nobody has
    made read as words rather than as something to click. An
    archived gang is nobody's to read.

    Every choice slot on the sheet — the gang's own and every member's —
    is pointed at its picker here, in one pass over what has already been
    derived. No queries, so a roster of sixteen costs what a roster of one
    does.

    The way into a fighter's skills is pointed the same way, and costs
    one query for the whole roster: which collections hold what a model
    selects is asked once, and each card already carries the collections
    its own grid reaches. A fighter with no grid gets no control, which
    is a content gap showing rather than a screen being withheld.
    """
    from n26.core.card import build_gang_card
    from n26.core.owned import DIALOGS, EquipHost
    from n26.core.render import render_gang
    from n26.core.views.choose import link_slots
    from n26.core.views.learn import link_skills
    from n26.core.views.owned import link_stash_actions, owned_dialog

    gang = _any_gang_or_404(pk)
    yours = gang.owner_id == getattr(request.user, "id", None)
    at = reverse("n26-gang", args=[gang.pk])
    card = build_gang_card(gang)
    sheet = render_gang(gang, card=card)
    dialog = None
    if yours:
        link_slots(gang, sheet, *sheet.models)
        link_skills(*sheet.models)
        link_stash_actions(sheet, at, refunds=not gang.credits_unlimited)
    # One question at a time: a URL naming two dialogs draws the leaving
    # one, because two open modals is not a state the page can mean.
    leaving = _leaving(request, gang) if yours else None
    renaming = None if leaving or not yours else _renaming(request, gang)
    if (
        yours
        and not leaving
        and not renaming
        and any(request.GET.get(kind) for kind in DIALOGS)
    ):
        host = EquipHost.stash(gang, card, at=at)
        dialog = owned_dialog(request, host)
    return render(
        request,
        "n26/gang_sheet.html",
        {
            "gang": gang,
            "sheet": sheet,
            "yours": yours,
            "trade_points_href": trade_points_href(gang, request.user),
            # Printing follows reading rather than owning, so a reader
            # who does not own the gang is still offered it — but a
            # visitor who has not signed in is not.
            "may_print": request.user.is_authenticated,
            # A reader who does not own this gang reads it and nothing
            # more: the cards drop every control, and a choice still to
            # be made is the words alone.
            "card_mode": "gang" if yours else "view",
            "renaming": renaming,
            "leaving": leaving,
            "dialog": dialog,
            # A gang founded without a budget never spent credits, so
            # there is nothing a refund could give back: its cards offer
            # Delete alone.
            "budgeted": gang.starting_credits is not None,
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

    # A gang founded without a budget never spent credits, so there is
    # nothing to give back: a refund asked of it is a deletion, and the
    # dialog says so rather than offering 0¢.
    if kind == "refund" and gang.starting_credits is None:
        kind = "delete"

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

    A refusal from the operation unwinds the whole departure, so the
    fighter is still there afterwards and the sheet says why.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation, refund_of, subtree
    from n26.core.views.permissions import _own_miniature_or_404

    miniature = _own_miniature_or_404(request, pk)
    membership = miniature.membership
    gang = membership.gang
    # No budget, no refund: the gang never spent credits, so the act
    # behind either address is the same deletion the dialog promised.
    if kind == "refund" and gang.starting_credits is None:
        kind = "delete"
    sheet_url = reverse("n26-gang", args=[gang.pk])
    if request.method != "POST":
        return redirect(f"{sheet_url}?{kind}={miniature.pk}")

    was = miniature.name
    stash_kit = request.POST.get("kit") == "stash"
    try:
        with operation(gang, actor=request.user) as op:
            moved = 0
            if stash_kit:
                for root in _kit_roots(miniature):
                    if refund_of(root)[1] > 0:
                        op.move(root, gang.stash, note=f"{was} left it behind")
                        moved += 1
            # What the whole departure returns, asked before anything is
            # archived: refund_of skips archived assignments, so asking
            # afterwards would answer zero.
            in_hire = {membership.pk, *(row.pk for row in subtree(membership))}
            remaining = [
                root for root in _kit_roots(miniature) if root.pk not in in_hire
            ]
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
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return redirect(sheet_url)

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
    """Rename one model: the act behind the model's own-page dialog.

    No rating moves and nothing is priced, but a rename is part of the
    gang's story, so it goes through an operation and the history keeps
    both names. GET reopens the dialog instead of acting, so the
    address can be followed, sent, or reloaded without renaming anyone.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.forms import RenameFighterForm
    from n26.core.operations import operation
    from n26.core.views.permissions import _own_miniature_or_404

    miniature = _own_miniature_or_404(request, pk)
    # The model's own page carries the rename pencil; the sheet still
    # draws the dialog when ``?rename=`` names a member. The act lands
    # back on whichever asked. ``?back=edit`` is a named place, never a
    # URL, so there is nothing here for an open redirect to ride.
    if request.GET.get("back") == "edit":
        back_url = reverse("n26-edit-fighter", args=[miniature.pk])
    else:
        back_url = reverse("n26-gang", args=[miniature.membership.gang_id])
    if request.method != "POST":
        return redirect(f"{back_url}?rename={miniature.pk}")

    form = RenameFighterForm(request.POST)
    if not form.is_valid():
        messages.error(request, "A model needs a name.")
        return redirect(f"{back_url}?rename={miniature.pk}")

    was = miniature.name
    name = form.cleaned_data["name"]
    if name == was:
        return redirect(back_url)
    with operation(miniature.membership.gang, actor=request.user) as op:
        op.rename(miniature, name)
    record(request, N26Noun.MODEL, EventVerb.UPDATE, miniature, renamed_from=was)
    messages.success(request, f"Renamed {was} to {miniature.name}.")
    return redirect(back_url)


@login_required
def create_gang(request):
    """Found a gang: the design system's create form, wired to write.

    POST founds for real — the Gang itself, then its founding assignment
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


def gang_lore(request, pk):
    """The gang's story, then every model's — the written half of a roster.

    Anyone may read it, as anyone may read the sheet: lore is what a
    player shows people. Owning the gang adds the Edit links and nothing
    else. Models with nothing written and no picture are left off rather
    than listed as empty headings.
    """
    from n26.core.render import roster, summarise_roster

    gang = _any_gang_or_404(pk)
    yours = gang.owner_id == getattr(request.user, "id", None)
    members = roster(gang)
    entries = [
        {
            "name": model.name,
            # The library entry beside the owner's name, as the card
            # header says it — and skipped the same way when nobody has
            # renamed the model, so it is not named twice.
            "profile": (
                str(model.membership.profile)
                if model.membership
                and model.membership.profile
                and str(model.membership.profile) != model.name
                else ""
            ),
            "lore": model.lore,
            "image_url": model.image.url if model.image else "",
            "edit_url": reverse("n26-edit-fighter", args=[model.pk]) if yours else "",
        }
        for model in members
        if model.lore or model.image
    ]
    return render(
        request,
        "n26/gang_lore.html",
        {
            "gang": gang,
            "gang_image_url": gang.image.url if gang.image else "",
            "entries": entries,
            "yours": yours,
            "summary": summarise_roster(members),
            "trade_points_href": trade_points_href(gang, request.user),
        },
    )


@login_required
def edit_gang(request, pk):
    """Edit a standing gang: name, colour, and the credits budget.

    The create form's shape without the one answer that cannot change —
    the type fixed who could be hired and what the founding brought, so
    it is shown as the fact it is.

    The budget edit is the interesting part. Its floor is the gang's
    wealth (see ``EditGangForm``), and the write happens inside an
    operation so ``settle`` recomputes the credits from the ledger —
    the budget less everything actually spent — and refuses a budget
    the spending history cannot fit, unwinding the whole change.

    Notes and lore each have their own form and save. htmx leaves the
    page as drawn so typing in one box survives saving the other; a
    full submit lands back on this tab.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.forms import EditGangForm, GangLoreForm, GangNotesForm, PictureForm
    from n26.core.images import LANDSCAPE, MAX_PX
    from n26.core.operations import NotEnoughCredits, operation
    from n26.core.views.htmx import stay_or_redirect

    gang = _own_gang_or_404(request, pk)
    at = reverse("n26-edit-gang", args=[gang.pk])
    tab = "notes" if request.GET.get("tab") == "notes" else "general"
    if request.method == "POST" and request.POST.get("act") == "picture":
        form = PictureForm(request.POST, request.FILES, ratio=LANDSCAPE)
        if form.is_valid():
            new_picture = bool(form.cleaned_data["image"])
            dropped_picture = (
                form.cleaned_data["remove_image"]
                and bool(gang.image)
                and not new_picture
            )
            with operation(gang, actor=request.user) as op:
                op.set_gang_image(
                    form.cleaned_data["image"],
                    clear=form.cleaned_data["remove_image"],
                )
            record(
                request,
                N26Noun.GANG,
                EventVerb.UPDATE,
                gang,
                image=new_picture or dropped_picture,
            )
            if new_picture:
                messages.success(request, "Picture saved.")
            elif dropped_picture:
                messages.success(request, "Picture removed.")
            else:
                messages.success(request, "Nothing changed.")
        else:
            # The one field that can refuse — a file that is not an
            # image. The reason travels as a message to the page this
            # redirects back to.
            for wrong in form.errors.get("image", []):
                messages.error(request, wrong)
        return redirect(f"{at}?tab=notes")
    elif request.method == "POST" and request.POST.get("act") == "notes":
        form = GangNotesForm(request.POST)
        if form.is_valid():
            with operation(gang, actor=request.user) as op:
                op.edit_gang_notes(form.cleaned_data["notes"])
            record(request, N26Noun.GANG, EventVerb.UPDATE, gang, notes=True)
            messages.success(request, "Notes saved.")
        return stay_or_redirect(request, f"{at}?tab=notes")
    elif request.method == "POST" and request.POST.get("act") == "lore":
        form = GangLoreForm(request.POST)
        if form.is_valid():
            with operation(gang, actor=request.user) as op:
                op.edit_gang_lore(form.cleaned_data["lore"])
            record(request, N26Noun.GANG, EventVerb.UPDATE, gang, lore=True)
            messages.success(request, "Lore saved.")
        return stay_or_redirect(request, f"{at}?tab=notes")
    elif request.method == "POST" and not request.POST.get("act"):
        form = EditGangForm(gang, request.POST)
        if form.is_valid():
            try:
                with operation(gang, actor=request.user) as op:
                    # The name and the budget are the gang's story and
                    # go through their own verbs, which record them. The
                    # colour is how a reader draws it and is nobody's
                    # history, so it is a plain save.
                    op.rename_gang(form.cleaned_data["name"])
                    op.set_budget(form.cleaned_data["starting_credits"])
                    gang.colour = form.cleaned_data["colour"]
                    gang.save(update_fields=["colour", "modified"])
                    op.settle()
            except NotEnoughCredits as refusal:
                # The ledger's own floor: a budget the spending history
                # cannot fit. The wealth floor usually refuses first, but
                # the two figures part company where money was spent on
                # things worth less than was paid.
                #
                # The database rolled back, so this instance is holding
                # figures nothing ever took — a heading and a wealth line
                # drawn from it would state a change that did not happen.
                gang.refresh_from_db()
                form.add_error("starting_credits", str(refusal))
            else:
                record(
                    request,
                    N26Noun.GANG,
                    EventVerb.UPDATE,
                    gang,
                    starting_credits=gang.starting_credits,
                )
                messages.success(request, f"Saved {gang.name}.")
                return redirect("n26-gang", pk=gang.pk)
    elif tab == "notes":
        form = None
    else:
        form = EditGangForm(
            gang,
            initial={
                "name": gang.name,
                "starting_credits": gang.starting_credits,
                "colour": gang.colour,
            },
        )

    # A failed save re-renders on the tab its form lives on, whatever
    # the address said. Notes and lore each redirect (or stay, under
    # htmx) and never reach here.
    if request.method == "POST":
        tab = "general"

    return render(
        request,
        "n26/edit_gang.html",
        {
            "gang": gang,
            "form": form,
            "notes_form": GangNotesForm(initial={"notes": gang.notes}),
            "lore_form": GangLoreForm(initial={"lore": gang.lore}),
            "wealth": gang.wealth,
            "tab": tab,
            # The crop spec the picture box stamps onto the browser's
            # dialog — handed from the same constants the server crops
            # with, so the two cannot disagree.
            "picture_shape": LANDSCAPE,
            "picture_max": MAX_PX,
            "picture_url": gang.image.url if gang.image else "",
            "edit_tabs": _edit_tabs(gang, tab),
        },
    )


#: The most a visit may be worth. No table in the book comes near it;
#: the figure is typed by hand, so a slip on the keyboard is refused
#: rather than stored.
TRADE_POINT_CEILING = 999


def _brought(data, ticked):
    """What the visit is worth: the ticks, or a figure typed over them.

    The box opens empty. Left empty, the ticks decide. A figure typed
    there is the amount, even nought — nought is a number somebody
    meant, not an empty box.

    Raises ValueError on a figure that is not a whole number in range.
    """
    typed = (data.get("brought") or "").strip()
    if not typed:
        return ticked
    if not typed.isdigit() or int(typed) > TRADE_POINT_CEILING:
        raise ValueError(typed)
    return int(typed)


def _the_trading_post():
    """The standard Trading Post, or None where the library has none.

    Pinned to the default pack, as the equipping screens pin it: names
    are unique per pack, so a homebrew pack's own "Trading Post" must
    not shadow the standard one.
    """
    from n26.library.models import Collection, get_default_pack
    from n26.library.standard_content import TRADING_POST_COLLECTION

    return Collection.objects.filter(
        name=TRADING_POST_COLLECTION, pack=get_default_pack()
    ).first()


def _edit_tabs(gang, current):
    """The strip every screen that edits a gang's own facts carries.

    Trade Points sit here rather than on a page of their own because a
    reader looking for what a gang *has* looks in one place. It keeps its
    own address all the same: it is a different act with its own two
    forms, and a strip is a set of links, not a claim that one view
    answers them all.
    """
    at = reverse("n26-edit-gang", args=[gang.pk])
    return [
        {"label": "General", "href": at, "current": current == "general"},
        {
            "label": "Notes and Lore",
            "href": f"{at}?tab=notes",
            "current": current == "notes",
        },
        {
            "label": "Trade Points",
            "href": reverse("n26-gang-trade-points", args=[gang.pk]),
            "current": current == "trade-points",
        },
    ]


@login_required
def gang_trade_points(request, pk):
    """The Visit Trading Post action: the one open, and starting another.

    One act per post. Starting names the fighters who perform it and
    takes what they add between them; finishing shuts the post and
    loses whatever is left, which is the book's own rule rather than
    this screen's idea. Both go through an operation, and the event each
    writes is what the spending is measured against.

    The figures are not a form. A visit adds what its fighters add, and
    the box beneath the ticks is for an owner who would rather say the
    figure outright. Empty, the ticks decide; a number there is the
    amount. The screen stays two plain posts and no query string.

    Two things are refused, and both are refusals a reader cannot reach
    from the page as drawn. An empty visit: with neither a ticked
    fighter nor a typed amount there is nothing to start. And a second
    visit while one is open: the form is shut then, so a start arriving
    anyway is a stale page rather than an intention.

    Spending past what a visit added is not among them — the purchase
    asks whether that was meant, and then does it.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import operation
    from n26.core.render import roster
    from n26.core.trading import as_offer, minted, receipt_for, visitors

    gang = _own_gang_or_404(request, pk)
    at = reverse("n26-gang-trade-points", args=[gang.pk])

    if request.method == "POST" and request.POST.get("act") == "finish":
        if gang.visiting_trading_post:
            left = gang.trade_points_left
            with operation(gang, actor=request.user) as op:
                op.leave_trading_post()
            record(request, N26Noun.GANG, EventVerb.UPDATE, gang, trade_points=None)
            if left == 1:
                lost = " 1 unspent Trade Point was discarded."
            elif left > 0:
                lost = f" {left} unspent Trade Points were discarded."
            else:
                lost = ""
            messages.success(request, f"{gang.name} left the Trading Post.{lost}")
        return redirect(at)

    if request.method == "POST":
        # One action at a time. The form is shut while one is open, so a
        # start arriving here is a stale page — and silently discarding
        # the open action's remaining Trade Points is not what whoever
        # sent it meant.
        if gang.visiting_trading_post:
            messages.error(
                request,
                "Finish the open Visit Trading Post action before starting another.",
            )
            return redirect(at)
        # Ticked boxes name models; anything else names nothing on this
        # roster, so a tampered form simply sends nobody.
        going = visitors(gang, set(request.POST.getlist("visiting")))
        performing = [visitor for visitor in going if visitor.visiting]
        typed = (request.POST.get("brought") or "").strip()
        if not performing and not typed:
            messages.error(
                request,
                "Select at least one model to visit the Trading Post, or "
                "enter a Trade Point amount.",
            )
            return redirect(at)
        try:
            brought = _brought(request.POST, minted(performing))
        except ValueError:
            messages.error(
                request,
                "Trade Points are a whole number, from 0 to 999.",
            )
            return redirect(at)
        with operation(gang, actor=request.user) as op:
            op.visit_trading_post(going, brought=brought)
        record(request, N26Noun.GANG, EventVerb.UPDATE, gang, trade_points=brought)
        if performing:
            who = (
                f"{len(performing)} model{'' if len(performing) == 1 else 's'} "
                f"visited the Trading Post, adding "
            )
        else:
            who = f"{gang.name} visited the Trading Post, adding "
        messages.success(
            request,
            f"{who}{brought} Trade Point{'' if brought == 1 else 's'}.",
        )
        return redirect(at)

    offered = visitors(gang, going=set())
    return render(
        request,
        "n26/trade_points.html",
        {
            "gang": gang,
            "action": at,
            # Each fighter on the receipt gets a way to their own equip
            # screen, opened on the post itself: having sent them there,
            # spending what they added is the next thing an owner
            # wants. Empty where the library has no post, which leaves
            # the buttons off rather than sending anybody nowhere.
            "post": _the_trading_post(),
            # The open visit, or None where the post is shut. The card is
            # drawn from this and the form below it either way, so the
            # page reads the same whichever state it is in.
            "receipt": receipt_for(gang),
            # What each offered fighter adds, keyed by the box value, so
            # the running total can follow the ticks without a second
            # copy of who is on the list.
            "points_json": json.dumps(
                {visitor.key: visitor.trade_points for visitor in offered}
            ),
            # Whether an action is open, as a plain boolean: the start form
            # reads it to shut itself, and a cotton :attribute takes a
            # variable rather than an expression.
            "visit_open": gang.visiting_trading_post,
            "visitors": offered,
            # Every fighter, not only those who performed the action:
            # what a visit added is the gang's, and it is spent on
            # whoever it was for. Who went is the ranks on the receipt.
            "roster": roster(gang),
            "offer": as_offer(offered),
            "edit_tabs": _edit_tabs(gang, "trade-points"),
        },
    )


@login_required
def delete_gang(request, pk):
    """Deleting a gang: the question at its own address, then the act.

    GET asks and changes nothing; the POST from that page archives. Two
    steps rather than one because the click is not reversible by the
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
        # Recorded as a deletion, which is what the player did. That the gang
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
            # not one of the things this click takes away.
            "roster": Miniature.objects.filter(
                membership__gang=gang, membership__archived=False
            ).count(),
        },
    )
