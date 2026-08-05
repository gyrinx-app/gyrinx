"""Roll-flow views: spend a counter, roll on a table, confirm the result.

The flow is URL-driven, mirroring the advancement wizard: the roll step
records the dice (as a CampaignAction in campaign mode, or a ``dice=`` query
parameter otherwise) and the confirm step derives the matched row from that
state, so refreshing or sharing the URL re-renders the same result.
"""

import random
import uuid

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from n23.content.models import ContentRollFlow
from n23.core.forms.list import RollFlowDiceForm
from n23.core.handlers.fighter import (
    handle_roll_flow,
    handle_roll_result_deletion,
)
from n23.core.models.campaign import CampaignAction
from gyrinx.analytics.models import EventNoun, EventVerb, log_event
from n23.core.models.list import ListFighterRollResult
from n23.core.views.fighter.permissions import get_list_and_fighter


def _get_flow_for_fighter(fighter, flow_id):
    """Fetch a roll flow, ensuring it applies to this fighter's counter set."""
    return get_object_or_404(
        ContentRollFlow.objects.select_related("counter", "roll_table"),
        id=flow_id,
        counter__restricted_to_fighters=fighter.content_fighter,
    )


def _counter_value(fighter, counter):
    """Current value of a counter for a fighter (0 when never edited)."""
    existing = fighter.counters.filter(counter=counter).first()
    return existing.value if existing else 0


@login_required
def roll_flow_roll(request, id, fighter_id, flow_id):
    """
    Roll step of a roll flow: show the table and roll (or enter) the dice.

    **Template**

    :template:`core/list_fighter_roll_flow.html`
    """
    lst, fighter, _perms = get_list_and_fighter(request, id, fighter_id)
    flow = _get_flow_for_fighter(fighter, flow_id)
    table = flow.roll_table

    counter_value = _counter_value(fighter, flow.counter)
    affordable = counter_value >= flow.cost

    counter_url = reverse(
        "core:list-fighter-counter-edit", args=(lst.id, fighter.id, flow.counter.id)
    )

    if request.method == "POST":
        if not affordable:
            messages.error(
                request,
                f"{fighter.name} needs {flow.cost} {flow.counter.name} to use "
                f"{flow.name} (currently {counter_value}).",
            )
            return HttpResponseRedirect(counter_url)

        form = RollFlowDiceForm(request.POST, dice_count=table.dice_count)
        if form.is_valid():
            roll_action = form.cleaned_data["roll_action"]

            if roll_action == "roll_auto":
                dice = [
                    random.randint(1, 6)  # nosec B311 - game dice, not crypto
                    for _ in range(table.dice_count)
                ]
                description = f"Rolling on {table.name} for {fighter.name}"
            elif roll_action == "roll_manual":
                dice = [form.cleaned_data["d6_1"], form.cleaned_data["d6_2"]][
                    : table.dice_count
                ]
                description = f"Rolled on tabletop on {table.name} for {fighter.name}"
            else:
                dice = None

            if dice:
                confirm_url = reverse(
                    "core:list-fighter-roll-flow-confirm",
                    args=(lst.id, fighter.id, flow.id),
                )
                campaign_action = None
                if lst.campaign:
                    with transaction.atomic():
                        campaign_action = CampaignAction.objects.create(
                            user=request.user,
                            owner=request.user,
                            campaign=lst.campaign,
                            list=lst,
                            description=description,
                            dice_count=len(dice),
                            dice_results=dice,
                            # Use the table's semantics (D66 reads tens+units)
                            # so the logged total matches the resolved value
                            dice_total=table.roll_value_from_dice(dice),
                        )
                if campaign_action:
                    return HttpResponseRedirect(
                        f"{confirm_url}?campaign_action_id={campaign_action.id}"
                    )
                # No campaign action to key idempotency on: mint a roll token
                # so double-submitting the confirm form applies the roll once.
                dice_param = ",".join(str(d) for d in dice)
                return HttpResponseRedirect(
                    f"{confirm_url}?dice={dice_param}&token={uuid.uuid4()}"
                )
    else:
        form = RollFlowDiceForm(dice_count=table.dice_count)

    return render(
        request,
        "core/list_fighter_roll_flow.html",
        {
            "list": lst,
            "fighter": fighter,
            "flow": flow,
            "table": table,
            "rows": table.rows.all(),
            "form": form,
            "counter_value": counter_value,
            "affordable": affordable,
            "counter_url": counter_url,
            "in_campaign": bool(lst.campaign),
        },
    )


def _dice_from_request(request, lst, table):
    """
    Recover the dice rolled at the roll step from the confirm URL.

    Returns (dice, campaign_action, roll_token), or (None, None, None) when
    the URL state is missing or invalid. Exactly one of campaign_action and
    roll_token is set on success: campaign rolls are anchored to their
    logged CampaignAction, non-campaign rolls to the token minted at the
    roll step (both serve as the apply-once idempotency key).
    """
    campaign_action_id = request.GET.get("campaign_action_id")
    if campaign_action_id:
        try:
            action_id = uuid.UUID(campaign_action_id)
        except ValueError:
            return None, None, None
        campaign_action = CampaignAction.objects.filter(id=action_id, list=lst).first()
        if not campaign_action or not campaign_action.dice_results:
            return None, None, None
        dice = list(campaign_action.dice_results)
        roll_token = None
    else:
        campaign_action = None
        try:
            dice = [int(d) for d in request.GET.get("dice", "").split(",")]
            roll_token = uuid.UUID(request.GET.get("token", ""))
        except ValueError:
            return None, None, None

    if len(dice) != table.dice_count or any(d < 1 or d > 6 for d in dice):
        return None, None, None
    return dice, campaign_action, roll_token


@login_required
def roll_flow_confirm(request, id, fighter_id, flow_id):
    """
    Confirm step of a roll flow: review the rolled result and apply it.

    **Template**

    :template:`core/list_fighter_roll_flow_confirm.html`
    """
    lst, fighter, _perms = get_list_and_fighter(request, id, fighter_id)
    flow = _get_flow_for_fighter(fighter, flow_id)
    table = flow.roll_table

    roll_url = reverse(
        "core:list-fighter-roll-flow", args=(lst.id, fighter.id, flow.id)
    )

    dice, campaign_action, roll_token = _dice_from_request(request, lst, table)
    if dice is None:
        messages.error(request, "That roll could not be found. Please roll again.")
        return HttpResponseRedirect(roll_url)

    rolled_value = table.roll_value_from_dice(dice)
    row = table.row_for_roll(rolled_value)

    if request.method == "POST" and row:
        try:
            result = handle_roll_flow(
                user=request.user,
                fighter=fighter,
                flow=flow,
                row=row,
                rolled_value=rolled_value,
                campaign_action_id=campaign_action.id if campaign_action else None,
                roll_token=roll_token,
            )
        except ValidationError as e:
            messages.error(request, "; ".join(e.messages))
            return HttpResponseRedirect(roll_url)

        if result:
            log_event(
                user=request.user,
                noun=EventNoun.LIST_FIGHTER,
                verb=EventVerb.UPDATE,
                object=fighter,
                request=request,
                fighter_name=fighter.name,
                list_id=str(lst.id),
                list_name=lst.name,
                action="roll_result_added",
                flow_name=flow.name,
                row_name=row.name,
                rolled_value=rolled_value,
            )
            messages.success(request, f"{fighter.name} gained {row.name}")
        else:
            messages.info(request, "This roll has already been applied.")

        return HttpResponseRedirect(
            reverse("core:list", args=(lst.id,)) + f"#{fighter.id}"
        )

    return render(
        request,
        "core/list_fighter_roll_flow_confirm.html",
        {
            "list": lst,
            "fighter": fighter,
            "flow": flow,
            "table": table,
            "dice": dice,
            "rolled_value": rolled_value,
            "row": row,
            "modifiers": row.modifiers.all() if row else [],
            "roll_url": roll_url,
        },
    )


@login_required
def roll_results_edit(request, id, fighter_id):
    """
    List a fighter's roll results with remove links.

    **Template**

    :template:`core/list_fighter_roll_results_edit.html`
    """
    lst, fighter, _perms = get_list_and_fighter(request, id, fighter_id)

    results = fighter.roll_results.filter(archived=False).select_related(
        "row__table", "flow", "counter"
    )

    return render(
        request,
        "core/list_fighter_roll_results_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "results": results,
        },
    )


@login_required
def roll_result_remove(request, id, fighter_id, result_id):
    """
    Confirm and remove a roll result, refunding the counter points spent.

    **Template**

    :template:`core/list_fighter_roll_result_remove.html`
    """
    lst, fighter, _perms = get_list_and_fighter(request, id, fighter_id)

    roll_result = get_object_or_404(
        ListFighterRollResult.objects.select_related("row", "flow", "counter"),
        id=result_id,
        fighter=fighter,
        archived=False,
    )

    if request.method == "POST":
        try:
            result = handle_roll_result_deletion(
                user=request.user,
                fighter=fighter,
                roll_result=roll_result,
            )
        except ValidationError as e:
            messages.error(request, "; ".join(e.messages))
            return HttpResponseRedirect(
                reverse(
                    "core:list-fighter-roll-results-edit", args=(lst.id, fighter.id)
                )
            )

        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.UPDATE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            action="roll_result_removed",
            row_name=roll_result.row.name,
            counter_refund=result.counter_refund,
        )
        refund_text = (
            f" and {result.counter_refund} {roll_result.counter.name} refunded"
            if result.counter_refund and roll_result.counter
            else ""
        )
        messages.success(
            request,
            f"Removed {roll_result.row.name} from {fighter.name}{refund_text}",
        )
        return HttpResponseRedirect(
            reverse("core:list", args=(lst.id,)) + f"#{fighter.id}"
        )

    return render(
        request,
        "core/list_fighter_roll_result_remove.html",
        {
            "list": lst,
            "fighter": fighter,
            "roll_result": roll_result,
        },
    )
