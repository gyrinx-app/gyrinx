"""The gang's Gang Tactics page: what it holds, and rolling for more."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from n26.core.views.permissions import (
    _any_gang_or_404,
    _own_gang_or_404,
    credits_href,
    trade_points_href,
)


def gang_tactics(request, pk):
    """The gang's Gang Tactics, and the form to roll for more.

    Anyone may read it, as anyone may read the sheet. Only the owner
    rolls: a post from anyone else finds no form and is sent back.

    The three figures are the gang's totals. How each rank adds to the
    first is the library's counter, and the page never shows it per
    model.
    """
    from n26.core.forms import RollTacticsForm
    from n26.core.operations import Refusal, operation
    from n26.core.render import roster, summarise_roster
    from n26.core.tactics import allowance, cards, held, table_choices

    gang = _any_gang_or_404(request, pk)
    yours = gang.owner_id == getattr(request.user, "id", None)
    at = reverse("n26-gang-tactics", args=[gang.pk])
    members = roster(gang)
    tactics = held(gang)
    room = allowance(gang, tactics, members)
    choices = table_choices(gang, tactics, request.POST.get("table", ""))

    form = None
    if yours:
        form = RollTacticsForm(
            request.POST if request.method == "POST" else None,
            table_choices=choices,
            to_generate=room.to_generate,
            initial={"count": room.to_generate or 1},
        )
        if request.method == "POST" and form.is_valid():
            try:
                with operation(gang, actor=request.user) as op:
                    gained = op.roll_tactics(
                        form.cleaned_data["table"], form.cleaned_data["count"]
                    )
            except Refusal as refusal:
                messages.error(request, str(refusal))
                return redirect(at)
            names = [card.name for card in cards(gained)]
            messages.success(
                request,
                f"Rolled {len(names)} Gang Tactic{'' if len(names) == 1 else 's'}: "
                f"{', '.join(names)}.",
            )
            return redirect(at)
    elif request.method == "POST":
        return redirect(at)

    return render(
        request,
        "n26/gang_tactics.html",
        {
            "gang": gang,
            "yours": yours,
            "room": room,
            "cards": cards(tactics),
            "form": form,
            "table_choices": choices,
            "summary": summarise_roster(members),
            "trade_points_href": trade_points_href(gang, request.user),
            "credits_href": credits_href(gang, request.user),
        },
    )


def _own_tactic_or_404(request, pk, tactic_pk):
    """The gang, if it is the viewer's, and one tactic it holds."""
    from django.core.exceptions import ValidationError
    from django.http import Http404

    from n26.core.models import GangTactic

    gang = _own_gang_or_404(request, pk)
    try:
        tactic = (
            GangTactic.objects.filter(gang=gang, pk=tactic_pk, archived=False)
            .select_related("picklist", "pickable")
            .first()
        )
    except ValidationError:
        tactic = None
    if tactic is None:
        raise Http404
    return gang, tactic


@login_required
def delete_gang_tactic(request, pk, tactic_pk):
    """Discard one Gang Tactic, behind a page that asks first.

    The gang's log keeps the act, which is what keeps play honest: the
    tactic goes from the page and its share is free to roll again.
    """
    from n26.core.confirm import CONFIRM_FIELD, Confirmation
    from n26.core.operations import Refusal, operation
    from n26.core.tactics import name_of

    gang, tactic = _own_tactic_or_404(request, pk, tactic_pk)
    back = reverse("n26-gang-tactics", args=[gang.pk])
    name = name_of(tactic)
    if request.method == "POST" and request.POST.get(CONFIRM_FIELD) == "yes":
        try:
            with operation(gang, actor=request.user) as op:
                op.discard_tactic(tactic, note=name)
        except Refusal as refusal:
            messages.error(request, str(refusal))
            return redirect(back)
        messages.success(request, f"Deleted the Gang Tactic {name}.")
        return redirect(back)
    confirmation = Confirmation(
        title=f"Delete {name}",
        lead="",
        heading=f"Delete the Gang Tactic {name}?",
        body=(
            "It goes from the gang's tactics and can be rolled for again. "
            "The gang's log records that it was deleted."
        ),
        confirm_label="Delete tactic",
        action=reverse("n26-delete-gang-tactic", args=[gang.pk, tactic.pk]),
        cancel_url=back,
        confirm_value="yes",
    )
    return render(
        request, "n26/confirm.html", {"gang": gang, "confirmation": confirmation}
    )


@login_required
def reroll_gang_tactic(request, pk, tactic_pk):
    """Swap one Gang Tactic for a new roll on a table the owner picks.

    The page is the question: which table, and Re-roll to mean it. A bad
    pick re-draws the page with the choice kept.
    """
    from n26.core.forms import RerollTacticForm
    from n26.core.operations import Refusal, operation
    from n26.core.tactics import held, name_of, table_choices

    gang, tactic = _own_tactic_or_404(request, pk, tactic_pk)
    back = reverse("n26-gang-tactics", args=[gang.pk])
    name = name_of(tactic)
    choices = table_choices(
        gang, held(gang), request.POST.get("table", "") or str(tactic.picklist_id)
    )
    form = RerollTacticForm(
        request.POST if request.method == "POST" else None, table_choices=choices
    )
    if request.method == "POST" and form.is_valid():
        try:
            with operation(gang, actor=request.user) as op:
                new = op.reroll_tactic(tactic, form.cleaned_data["table"])
        except Refusal as refusal:
            messages.error(request, str(refusal))
            return redirect(back)
        messages.success(request, f"Re-rolled {name}. The gang now has {name_of(new)}.")
        return redirect(back)
    return render(
        request,
        "n26/gang_tactic_reroll.html",
        {
            "gang": gang,
            "name": name,
            "form": form,
            "table_choices": choices,
            "action": reverse("n26-reroll-gang-tactic", args=[gang.pk, tactic.pk]),
            "cancel_url": back,
        },
    )
