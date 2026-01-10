"""Fighter XP editing views."""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.views.list.common import get_clean_list_or_404


@login_required
def edit_list_fighter_xp(request, id, fighter_id):
    """
    Modify XP for a :model:`core.ListFighter` in campaign mode.

    **Context**

    ``form``
        An EditFighterXPForm for modifying fighter XP.
    ``fighter``
        The :model:`core.ListFighter` whose XP is being modified.
    ``list``
        The :model:`core.List` that owns this fighter.

    **Template**

    :template:`core/list_fighter_xp_edit.html`
    """

    from gyrinx.core.forms.list import EditFighterXPForm
    from gyrinx.core.models.campaign import CampaignAction

    lst = get_clean_list_or_404(List, id=id, owner=request.user)
    fighter = get_object_or_404(
        ListFighter, id=fighter_id, list=lst, archived_at__isnull=True
    )

    if request.method == "POST":
        form = EditFighterXPForm(request.POST, fighter=fighter)
        if form.is_valid():
            operation = form.cleaned_data["operation"]
            amount = form.cleaned_data["amount"]
            description = form.cleaned_data.get("description", "")

            # Validate the operation
            if operation == "spend" and amount > fighter.xp_current:
                form.add_error(
                    "amount",
                    f"Cannot spend more XP than available ({fighter.xp_current})",
                )
            elif operation == "reduce" and amount > fighter.xp_current:
                form.add_error(
                    "amount",
                    f"Cannot reduce XP below zero (current: {fighter.xp_current})",
                )
            elif operation == "reduce" and amount > fighter.xp_total:
                form.add_error(
                    "amount",
                    f"Cannot reduce total XP below zero (total: {fighter.xp_total})",
                )
            else:
                with transaction.atomic():
                    # Apply the XP change
                    if operation == "add":
                        fighter.xp_current += amount
                        fighter.xp_total += amount
                        action_desc = f"Added {amount} XP for {fighter.name}"
                    elif operation == "spend":
                        fighter.xp_current -= amount
                        action_desc = f"Spent {amount} XP for {fighter.name}"
                    elif operation == "reduce":
                        fighter.xp_current -= amount
                        fighter.xp_total -= amount
                        action_desc = f"Reduced {amount} XP for {fighter.name}"

                    fighter.save_with_user(user=request.user)

                    # Add description if provided
                    if description:
                        action_desc += f" - {description}"

                    # Log to campaign action
                    if lst.campaign:
                        outcome = f"Current: {fighter.xp_current} XP, Total: {fighter.xp_total} XP"
                        CampaignAction.objects.create(
                            user=request.user,
                            owner=request.user,
                            campaign=lst.campaign,
                            list=lst,
                            description=action_desc,
                            outcome=outcome,
                        )

                messages.success(request, f"XP updated for {fighter.name}")
                return HttpResponseRedirect(reverse("core:list", args=(lst.id,)))
    else:
        form = EditFighterXPForm(fighter=fighter)

    return render(
        request,
        "core/list_fighter_xp_edit.html",
        {
            "form": form,
            "list": lst,
            "fighter": fighter,
        },
    )
