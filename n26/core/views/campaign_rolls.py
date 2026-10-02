"""Record dice and describe their outcome on dedicated campaign pages."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from n26.core.campaign_permissions import may_record_campaign
from n26.core.campaigns import campaign_operation
from n26.core.forms import CampaignRollForm, CampaignRollOutcomeForm
from n26.core.models import CampaignRoll
from n26.core.operations import Refusal
from n26.core.views.permissions import _any_campaign_or_404, _recording_campaign_or_404
from n26.flags import CAMPAIGNS, requires_flag


@requires_flag(CAMPAIGNS)
@login_required
def record_campaign_roll(request, pk):
    campaign = _recording_campaign_or_404(request, pk)
    form = CampaignRollForm(
        request.POST if request.method == "POST" else None, campaign=campaign
    )
    if request.method == "POST" and form.is_valid():
        try:
            with campaign_operation(campaign, actor=request.user) as act:
                roll = act.record_roll(**form.cleaned_data)
        except Refusal as exc:
            form.add_error(None, str(exc))
        else:
            return redirect("n26-campaign-roll", pk=campaign.pk, roll_pk=roll.pk)
    return render(
        request, "n26/record_campaign_roll.html", {"campaign": campaign, "form": form}
    )


@requires_flag(CAMPAIGNS)
@login_required
def campaign_roll(request, pk, roll_pk):
    campaign = _any_campaign_or_404(request, pk)
    try:
        roll = get_object_or_404(
            CampaignRoll.objects.select_related("gang", "battle"),
            campaign=campaign,
            pk=roll_pk,
        )
    except ValidationError:
        raise Http404("No such dice roll") from None
    may_note = roll.actor_id == request.user.pk and may_record_campaign(
        campaign, request.user
    )
    if request.method == "POST" and not may_note:
        raise Http404("No such dice roll")
    form = CampaignRollOutcomeForm(
        request.POST if request.method == "POST" else None,
        initial={"outcome": roll.outcome},
    )
    if request.method == "POST" and form.is_valid():
        try:
            with campaign_operation(campaign, actor=request.user) as act:
                act.note_roll(roll, form.cleaned_data["outcome"])
        except Refusal as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Outcome note saved.")
            return redirect("n26-campaign", pk=campaign.pk)
    return render(
        request,
        "n26/campaign_roll.html",
        {"campaign": campaign, "roll": roll, "form": form, "may_note": may_note},
    )
