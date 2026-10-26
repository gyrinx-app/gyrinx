"""The gang's Gang Tactics page: what it holds, and rolling for more."""

from dataclasses import asdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

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

    The figures are the gang's totals. How each rank adds to the
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

    shown = cards(tactics)
    print_view = request.GET.get("print") == "1"
    selected = set(request.GET.getlist("selected"))
    if print_view and selected:
        shown = [card for card in shown if card.pk in selected]
    island = {
        "cards": _card_props(shown, tactics),
        "yours": yours,
        "toGenerate": room.to_generate,
        "tableChoices": [asdict(choice) for choice in choices],
        "bonusChoices": [
            asdict(choice) for choice in table_choices(gang, tactics, bonus=True)
        ],
        "bonusUrl": reverse("n26-bonus-gang-tactics", args=[gang.pk]),
        "count": str(form["count"].value() or "") if form else "",
        "errors": dict(form.errors) if form else {},
        "csrfToken": get_token(request),
        "rollUrl": at,
        "batchUrl": reverse("n26-batch-gang-tactics", args=[gang.pk]),
        "printView": print_view,
        "initialLayout": request.GET.get("layout", ""),
    }
    return render(
        request,
        "n26/gang_tactics.html",
        {
            "gang": gang,
            "tactics_island": island,
            "print_view": print_view,
            "summary": summarise_roster(members),
            "trade_points_href": trade_points_href(gang, request.user),
            "credits_href": credits_href(gang, request.user),
        },
    )


def _card_props(shown, tactics):
    table_keys = {str(tactic.pk): str(tactic.picklist_id) for tactic in tactics}
    return [{**asdict(card), "tableKey": table_keys[card.pk]} for card in shown]


def _tactics_state(gang):
    """The current collection after an operation, without another page load."""
    from n26.core.render import roster
    from n26.core.tactics import allowance, cards, held, table_choices

    tactics = held(gang)
    room = allowance(gang, tactics, roster(gang))
    return {
        "cards": _card_props(cards(tactics), tactics),
        "toGenerate": room.to_generate,
        "tableChoices": [asdict(choice) for choice in table_choices(gang, tactics)],
        "bonusChoices": [
            asdict(choice) for choice in table_choices(gang, tactics, bonus=True)
        ],
    }


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
        gang,
        held(gang),
        request.POST.get("table", "") or str(tactic.picklist_id),
        bonus=tactic.bonus,
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


@login_required
@require_POST
def batch_gang_tactics(request, pk):
    """Confirm and atomically change selected tactics belonging to this owner."""
    from django.http import HttpResponseBadRequest, JsonResponse

    from n26.core.confirm import CONFIRM_FIELD, Confirmation, carried
    from n26.core.operations import Refusal, operation
    from n26.core.tactics import held, name_of, table_choices

    gang = _own_gang_or_404(request, pk)
    json_request = "application/json" in request.headers.get("Accept", "")

    def invalid(message):
        if json_request:
            return JsonResponse({"error": message}, status=400)
        return HttpResponseBadRequest(message)

    back = reverse("n26-gang-tactics", args=[gang.pk])
    action = request.POST.get("action")
    keys = set(request.POST.getlist("selected"))
    if action not in {"delete", "reroll"} or not keys:
        return invalid("Select at least one gang tactic.")
    chosen = [tactic for tactic in held(gang) if str(tactic.pk) in keys]
    if len(chosen) != len(keys):
        return invalid("Some selected tactics are no longer available.")
    table = request.POST.get("table", "")
    if action == "reroll" and table:
        from n26.core.forms import RerollTacticForm

        # Bonus cards alone may go to any table; with a counted card in
        # the selection, only the gang's own tables are offered.
        form = RerollTacticForm(
            request.POST,
            table_choices=table_choices(
                gang,
                held(gang),
                table,
                bonus=all(tactic.bonus for tactic in chosen),
            ),
        )
        if not form.is_valid():
            return invalid("Choose an available gang tactics set.")
        table = form.cleaned_data["table"]
    if json_request and request.POST.get(CONFIRM_FIELD) != "yes":
        return invalid("Confirm the selected action.")
    verb = "Delete" if action == "delete" else "Re-roll"
    if request.POST.get(CONFIRM_FIELD) == "yes":
        try:
            with operation(gang, actor=request.user) as op:
                # Re-read after acquiring the gang lock: selections can go stale.
                current = [tactic for tactic in held(gang) if str(tactic.pk) in keys]
                if len(current) != len(keys):
                    raise Refusal("Some selected tactics are no longer available.")
                for tactic in current:
                    if action == "delete":
                        op.discard_tactic(tactic, note=name_of(tactic))
                    else:
                        op.reroll_tactic(tactic, table or str(tactic.picklist_id))
        except Refusal as refusal:
            if json_request:
                return invalid(str(refusal))
            messages.error(request, str(refusal))
            return redirect(back)
        past = "Deleted" if action == "delete" else "Re-rolled"
        message = f"{past} {len(chosen)} gang tactic{'s' if len(chosen) != 1 else ''}."
        if json_request:
            return JsonResponse({**_tactics_state(gang), "message": message})
        messages.success(request, message)
        return redirect(back)
    names = ", ".join(name_of(tactic) for tactic in chosen)
    detail = (
        "They can be generated again."
        if action == "delete"
        else "Each tactic is re-rolled on its current gang tactics set."
    )
    confirmation = Confirmation(
        title=f"{verb} gang tactics",
        lead="",
        heading=f"{verb} {len(chosen)} selected gang tactics?",
        body=f"{names}. {detail} The gang's log records the change.",
        confirm_label=f"{verb} selected",
        action=reverse("n26-batch-gang-tactics", args=[gang.pk]),
        cancel_url=back,
        carry=carried(request.POST),
        confirm_value="yes",
    )
    return render(
        request, "n26/confirm.html", {"gang": gang, "confirmation": confirmation}
    )


@login_required
@require_POST
def bonus_gang_tactics(request, pk):
    """Draw bonus tactics from any table, for the owner, as JSON.

    Bonus tactics sit outside the ranks' allowance, so nothing here asks
    how many the gang has left to roll. They still never duplicate a
    tactic the gang holds.
    """
    from django.http import JsonResponse

    from n26.core.forms import BonusTacticsForm
    from n26.core.operations import Refusal, operation
    from n26.core.tactics import held, table_choices

    gang = _own_gang_or_404(request, pk)
    form = BonusTacticsForm(
        request.POST,
        table_choices=table_choices(gang, held(gang), bonus=True),
    )
    if not form.is_valid():
        first = next(iter(form.errors.values()))[0]
        return JsonResponse({"error": first}, status=400)
    try:
        with operation(gang, actor=request.user) as op:
            gained = op.roll_bonus_tactics(
                form.cleaned_data["table"], form.cleaned_data["count"]
            )
    except Refusal as refusal:
        return JsonResponse({"error": str(refusal)}, status=400)
    names = ", ".join(tactic.pickable.name for tactic in gained)
    plural = "" if len(gained) == 1 else "s"
    return JsonResponse(
        {
            **_tactics_state(gang),
            "message": f"Drew {len(gained)} bonus card{plural}: {names}.",
        }
    )
