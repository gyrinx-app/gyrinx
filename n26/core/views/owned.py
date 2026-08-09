"""What a fighter already owns — selling it, handing it on, taking it off.

Three acts, three addresses, one shape each: a POST names the assignment
in its path, an ``operation`` writes it, and the reader lands back where
they pressed. The three are addressed by *assignment* rather than by
fighter, because that is what they are about — a weapon on a fighter, a
sight on that weapon, a crate in the stash are all one row — and because
the next screen that wants them (a gang sheet, a stash page) then needs
no routes of its own.

Which dialog is open is URL state on the screen that opened it
(``?sell=<assignment>``), so an open confirmation is a link, survives a
reload, and is drawn by the server rather than revealed by a script. The
press behind it is a real form to a real address, so it works with
scripting switched off.

The three acts are deliberately distinct, and the ledger says which
happened:

``sell``
    Half of what the thing is worth, rounded up, into the gang's credits.
    Not a refund: what was paid has nothing to do with it.
``reassign``
    A move to another model or to the stash. No money, and no re-pricing.
``remove``
    Off the card, money stays spent.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from n26.core.owned import CONFIRMATIONS, is_possession, with_query
from n26.core.views.permissions import _own_assignment_or_404


def _possession_or_404(request, pk):
    """One of the viewer's own rows, and one these acts are *about*.

    ``_own_assignment_or_404`` answers who may act; this answers on what.
    Both are needed, because a gang holds a great deal that is not kit and
    every bit of it is an assignment with a primary key: the row naming a
    model's profile **is** the model, and selling it would take the
    fighter off the roster and everything they carry with them, for half
    the price of the profile and nothing for the kit. The row naming the
    gang's type is the gang. Neither has any business arriving at a shop
    row's Sell button.

    A 404 rather than a message: no control anywhere draws these
    addresses, so a press that reaches here is a hand-made URL, and the
    honest answer is that there is no such thing to sell. That is
    different from the refusals below, which answer a control that does
    exist with a reason.
    """
    assignment = _own_assignment_or_404(request, pk)
    if not is_possession(assignment.assignable):
        raise Http404("Not something the gang owns")
    return assignment


def _held(card, pk):
    """The stored possession ``pk`` names, if this card is carrying it.

    The card is the fighter's own, so finding a row on it is the whole of
    the permission check for drawing a dialog about it — and it is free,
    where fetching the row again would be a query per press. The gang's
    broadcast rows are skipped: they ride the card so gang-wide rules
    reach it, and they are not this fighter's to sell.

    The same kind test the routes apply, so a URL naming the fighter's own
    profile draws no dialog rather than a confirmation whose press would
    404 — a screen must not ask a question its answer refuses.
    """
    return next(
        (
            node.assignment
            for node in card.all_nodes()
            if not node.broadcast
            and node.assignment is not None
            and str(node.assignment.pk) == pk
            and is_possession(node.assignable)
        ),
        None,
    )


def _other_models(gang, miniature):
    """Everyone else on the roster — where a thing could go instead."""
    from n26.core.models import Miniature

    return list(
        Miniature.objects.filter(
            membership__gang=gang, membership__archived=False
        ).exclude(pk=miniature.pk)
    )


def owned_dialog(request, card, *, at, miniature, gang):
    """The confirmation the URL says is open, as a template's worth of facts.

    One of ``?sell=``, ``?reassign=`` or ``?remove=``, naming a row of
    this card. A name that is not on the card draws nothing at all: a
    stale link is a page without a dialog, not an error worth a screen.
    """
    from n26.core.operations import MINIMUM_PROCEEDS, sale_of

    for kind in CONFIRMATIONS:
        named = request.GET.get(kind)
        if named:
            break
    else:
        return None

    assignment = _held(card, named)
    if assignment is None:
        return None

    name = str(assignment.assignable)
    # A part is what hangs off something else — ammo in a gun, a sight
    # bolted to it. It is removed rather than deleted, because what is
    # left afterwards is still the fighter's gun.
    is_part = assignment.parent_id is not None
    dialog = {
        "kind": kind,
        "name": name,
        "cancel_url": at,
        "action": reverse(f"n26-{kind}", args=[assignment.pk]),
        "list": request.GET.get("list", ""),
    }

    if kind == "sell":
        _, rating, proceeds = sale_of(assignment)
        # Half of the figure, or the floor — whichever decided it. The
        # arithmetic is stated because the number is money and there is
        # nothing on the page for a reader to check it against.
        halved = proceeds * 2 <= rating + 1
        return dialog | {
            "title": f"Sell {name}?",
            "proceeds": proceeds,
            "rating": rating,
            "sum": (
                f"Half of {rating}¢, rounded up — {proceeds}¢."
                if halved
                else f"{proceeds}¢: half of {rating}¢ is less than the "
                f"{MINIMUM_PROCEEDS}¢ a sale never goes under."
            ),
            "submit_label": "Sell",
            "submit_variant": "danger",
        }

    if kind == "reassign":
        models = _other_models(gang, miniature)
        return dialog | {
            "title": f"Move {name}",
            "models": models,
            # With nobody else on the roster the stash is not one of two
            # places it could go — it is the only one, so it stops being
            # a second control and becomes the act.
            "submit_label": "Move" if models else "To the stash",
            "submit_variant": "primary",
        }

    return dialog | {
        "title": f"{'Remove' if is_part else 'Delete'} {name}?",
        "submit_label": "Remove" if is_part else "Delete",
        "submit_variant": "danger",
    }


def _back_to(request, miniature, gang):
    """Where a press lands: the screen it was pressed on.

    The fighter's own shopping screen, on the list they were reading —
    kitting a fighter out is a run of presses and the way back is the
    breadcrumb. With no fighter to return to, the gang's sheet.
    """
    if miniature is None:
        return reverse("n26-gang", args=[gang.pk])
    url = reverse("n26-equip", args=[miniature.pk])
    chosen = request.POST.get("list", "")
    return with_query(url, list=chosen) if chosen else url


@login_required
@require_POST
def sell_assignment(request, pk):
    """Sell something on: it archives, and half its worth comes back.

    Half of what it *is worth*, not of what was paid — see
    ``Operation.sell``. The confirmation names the figure because with
    the arithmetic done by the server there is nothing on the page for a
    reader to check it against.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import operation

    assignment = _possession_or_404(request, pk)
    gang = assignment.gang_root
    miniature = assignment.miniature_root
    name = str(assignment.assignable)

    with operation(gang, actor=request.user) as op:
        proceeds = op.sell(assignment)

    record(
        request,
        N26Noun.ASSIGNMENT,
        EventVerb.ARCHIVE,
        assignment,
        gang_id=str(gang.pk),
        miniature_id=str(miniature.pk) if miniature else None,
        thing=name,
        action="sell",
        proceeds=proceeds,
    )
    messages.success(request, f"Sold {name} for {proceeds}¢.")
    return redirect(_back_to(request, miniature, gang))


@login_required
@require_POST
def reassign_assignment(request, pk):
    """Hand something to another model, or put it in the stash.

    Nothing is charged and nothing is re-priced: the thing keeps the
    rating it was pinned at, and only where it lives changes.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.models import Miniature
    from n26.core.operations import operation

    assignment = _possession_or_404(request, pk)
    gang = assignment.gang_root
    # Read before the move, because afterwards it names the new home and
    # the reader wants the screen they pressed on.
    came_from = assignment.miniature_root
    back = _back_to(request, came_from, gang)
    name = str(assignment.assignable)

    if assignment.parent_id is not None:
        # A part goes where its parent goes. The listing offers no control
        # for this, so only a hand-made press arrives here.
        messages.error(
            request,
            f"{name} is attached to {assignment.parent.assignable} — "
            f"move that instead.",
        )
        return redirect(back)

    wanted = request.POST.get("to")
    if wanted == "stash":
        destination = getattr(gang, "stash", None)
    else:
        try:
            destination = Miniature.objects.filter(
                pk=request.POST.get("miniature", ""),
                membership__gang=gang,
                membership__archived=False,
            ).first()
        except ValidationError:
            destination = None
    if destination is None:
        messages.error(request, f"There is nowhere to move {name} to.")
        return redirect(back)

    with operation(gang, actor=request.user) as op:
        op.move(assignment, destination)

    record(
        request,
        N26Noun.ASSIGNMENT,
        EventVerb.UPDATE,
        assignment,
        gang_id=str(gang.pk),
        miniature_id=str(came_from.pk) if came_from else None,
        thing=name,
        action="reassign",
        to="stash" if wanted == "stash" else "model",
    )
    where = "the stash" if wanted == "stash" else destination.name
    messages.success(request, f"Moved {name} to {where}.")
    return redirect(back)


@login_required
@require_POST
def remove_assignment(request, pk):
    """Take something off the card. The money stays spent.

    ``Operation.remove`` archives rather than deletes, so the ledger goes
    on saying the gang once owned this — it simply stops counting.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import operation

    assignment = _possession_or_404(request, pk)
    gang = assignment.gang_root
    miniature = assignment.miniature_root
    name = str(assignment.assignable)

    with operation(gang, actor=request.user) as op:
        op.remove(assignment)

    record(
        request,
        N26Noun.ASSIGNMENT,
        EventVerb.ARCHIVE,
        assignment,
        gang_id=str(gang.pk),
        miniature_id=str(miniature.pk) if miniature else None,
        thing=name,
        action="remove",
    )
    messages.success(request, f"Removed {name}.")
    return redirect(_back_to(request, miniature, gang))
