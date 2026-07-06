"""Fighter counter editing views."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.content.models import ContentCounter
from gyrinx.core.forms.list import EditCounterForm, SpendCounterForm
from gyrinx.core.handlers.fighter import (
    handle_counter_spend,
    handle_counter_spend_removal,
)
from gyrinx.core.models.list import ListFighterCounter, ListFighterCounterSpend
from gyrinx.core.views.fighter.permissions import get_list_and_fighter


@login_required
def edit_list_fighter_counter(request, id, fighter_id, counter_id):
    """
    Edit a single counter for a :model:`core.ListFighter`.

    Handles three POST intents on one page:

    - ``intent=save`` — set the counter value directly (no audit trail).
    - ``intent=spend`` — record a free-form spend (amount + why + outcome),
      decrementing the counter and leaving a durable, refundable record.
    - ``remove_spend_id=<uuid>`` — remove a recorded spend, refunding it.

    **Template**

    :template:`core/list_fighter_counters_edit.html`
    """
    lst, fighter, _perms = get_list_and_fighter(request, id, fighter_id)

    # Look up the specific counter, ensuring it applies to this fighter
    counter = get_object_or_404(
        ContentCounter,
        id=counter_id,
        restricted_to_fighters=fighter.content_fighter,
    )

    # Get existing value if any
    existing = (
        fighter.counters.filter(counter=counter).select_related("counter").first()
    )
    current_value = existing.value if existing else 0

    redirect_to_counter = HttpResponseRedirect(
        reverse(
            "core:list-fighter-counter-edit",
            args=(lst.id, fighter.id, counter.id),
        )
    )

    form = EditCounterForm(counter=counter, current_value=current_value)
    spend_form = SpendCounterForm(counter=counter, current_value=current_value)

    if request.method == "POST":
        # Remove (refund) a recorded spend
        remove_spend_id = request.POST.get("remove_spend_id")
        if remove_spend_id:
            spend = get_object_or_404(
                ListFighterCounterSpend,
                id=remove_spend_id,
                fighter=fighter,
                archived=False,
            )
            try:
                handle_counter_spend_removal(
                    user=request.user, fighter=fighter, spend=spend
                )
            except ValidationError as e:
                messages.error(request, e.messages[0])
            else:
                messages.success(
                    request,
                    f"Refunded {spend.amount} {counter.name} to {fighter.name}",
                )
            return redirect_to_counter

        intent = request.POST.get("intent")

        if intent == "spend":
            spend_form = SpendCounterForm(
                request.POST,
                counter=counter,
                current_value=current_value,
            )
            if spend_form.is_valid():
                try:
                    handle_counter_spend(
                        user=request.user,
                        fighter=fighter,
                        counter=counter,
                        amount=spend_form.cleaned_data["amount"],
                        reason=spend_form.cleaned_data["reason"],
                        outcome=spend_form.cleaned_data["outcome"],
                    )
                except ValidationError as e:
                    messages.error(request, e.messages[0])
                else:
                    messages.success(
                        request,
                        f"{fighter.name} spent {spend_form.cleaned_data['amount']} "
                        f"{counter.name}",
                    )
                    return redirect_to_counter
            # invalid or handler error: fall through to re-render with errors

        else:
            form = EditCounterForm(
                request.POST,
                counter=counter,
                current_value=current_value,
            )
            if form.is_valid():
                new_value = form.cleaned_data["value"]

                if new_value != current_value:
                    with transaction.atomic():
                        if existing:
                            existing.value = new_value
                            existing.save_with_user(user=request.user)
                        else:
                            ListFighterCounter.objects.create_with_user(
                                user=request.user,
                                fighter=fighter,
                                counter=counter,
                                value=new_value,
                                owner=lst.owner,
                            )
                    messages.success(
                        request, f"{counter.name} updated for {fighter.name}"
                    )
                else:
                    messages.info(
                        request, f"{counter.name} was unchanged for {fighter.name}"
                    )
                return HttpResponseRedirect(
                    reverse("core:list", args=(lst.id,)) + f"#{fighter.id}"
                )

    # Roll flows that spend this counter (e.g. Suit Evolution for Kill Count)
    flows = [
        {
            "flow": flow,
            "affordable": current_value >= flow.cost,
        }
        for flow in counter.flows.select_related("roll_table").all()
    ]

    # Recorded free-form spends for this counter
    spends = fighter.counter_spends.filter(
        counter=counter, archived=False
    ).select_related("campaign_action")

    return render(
        request,
        "core/list_fighter_counters_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "counter": counter,
            "form": form,
            "spend_form": spend_form,
            "flows": flows,
            "spends": spends,
            "can_spend": current_value > 0,
        },
    )
