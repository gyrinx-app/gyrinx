"""Adding credits to a gang, or removing them, by hand.

For whatever the app does not record itself: credits a scenario paid
out, a purchase made away from the app, a correction. The gang's owner
may do it, and so may the arbitrator of the campaign it is playing. A
gang with unlimited credits has no figure to change, so the page is not
there for it; its budget is set on the Edit page.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from n26.core.forms import CreditsForm
from n26.core.views.permissions import _any_gang_or_404, credits_campaign

DIRECTION_HELP = {
    CreditsForm.ADD: "Credits the gang gained outside the app, such as a scenario reward.",
    CreditsForm.REMOVE: (
        "Credits the gang spent or lost outside the app. "
        "To buy equipment, use Equip instead."
    ),
}


@login_required
def gang_credits(request, pk):
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import NotEnoughCredits, Refusal, operation

    gang = _any_gang_or_404(request, pk)
    if gang.credits_unlimited:
        raise Http404("No such gang")
    yours = gang.owner_id == request.user.pk
    if yours:
        back = reverse("n26-gang", args=[gang.pk])
    else:
        # The arbitrator came from the campaign's gangs table and goes
        # back to it.
        campaign = credits_campaign(gang, request.user)
        if campaign is None:
            raise Http404("No such gang")
        back = reverse("n26-campaign", args=[campaign.pk]) + "#gangs"

    form = CreditsForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        amount = form.signed_amount()
        had = gang.credits
        try:
            with operation(gang, actor=request.user) as op:
                op.adjust_credits(amount, form.cleaned_data["note"])
        except NotEnoughCredits:
            form.add_error(
                "amount", f"You cannot remove more than {gang.name} has ({had}¢)."
            )
        except Refusal as refusal:
            form.add_error("amount", str(refusal))
        else:
            record(request, N26Noun.GANG, EventVerb.UPDATE, gang, credits=amount)
            if amount > 0:
                messages.success(request, f"Added {amount}¢ to {gang.name}.")
            else:
                messages.success(request, f"Removed {-amount}¢ from {gang.name}.")
            return redirect(back)

    direction = form["direction"].value() or CreditsForm.ADD
    return render(
        request,
        "n26/gang_credits.html",
        {
            "gang": gang,
            "form": form,
            "back": back,
            "directions": [
                {
                    "value": value,
                    "label": label,
                    "description": DIRECTION_HELP[value],
                    "checked": value == direction,
                }
                for value, label in form.fields["direction"].choices
            ],
            # The history page is the owner's alone.
            "history_href": (
                reverse("n26-gang-history", args=[gang.pk]) + "?kind=credits"
                if yours
                else ""
            ),
        },
    )
