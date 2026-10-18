"""Record dice and describe their outcome on dedicated campaign pages."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from n26.core.campaign_permissions import may_record_campaign
from n26.core.campaigns import campaign_operation
from n26.core.forms import CampaignRollForm, CampaignRollOutcomeForm
from n26.core.models import CampaignRoll
from n26.core.operations import Refusal
from n26.core.views.permissions import (
    _any_campaign_or_404,
    _own_campaign_or_404,
    _recording_campaign_or_404,
)


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
    rolled = form["rolled"].value()
    attribution = {
        "gang": str(form["gang"].value() or ""),
        "miniature": str(form["miniature"].value() or ""),
        "gangErrors": list(form["gang"].errors),
        "miniatureErrors": list(form["miniature"].errors),
        "gangs": [
            {"value": str(gang.pk), "label": gang.name}
            for gang in form.fields["gang"].queryset
        ],
        "models": [
            {"value": str(pk), "label": name, "gang": str(gang_id)}
            for pk, name, gang_id in form.fields["miniature"].queryset.values_list(
                "pk", "name", "membership__gang_id"
            )
        ],
    }
    return render(
        request,
        "n26/record_campaign_roll.html",
        {
            "campaign": campaign,
            "form": form,
            "roll_attribution": attribution,
            "dice_choices": [
                {
                    "value": value,
                    "label": label,
                    "checked": value == form["dice"].value(),
                }
                for value, label in form.fields["dice"].choices
            ],
            "roll_source": {
                "requestKey": str(form["request_key"].value()),
                "source": form["source"].value() or "",
                "rolled": "" if rolled is None else str(rolled),
                "choices": [
                    {"value": value, "label": label}
                    for value, label in form.fields["source"].choices
                ],
                "sourceErrors": list(form["source"].errors),
                "rolledErrors": list(form["rolled"].errors),
                "count": str(form["count"].value() or 1),
                "countErrors": list(form["count"].errors),
                "maxDice": CampaignRoll.MAX_DICE,
                "modifier": str(form["modifier"].value() or ""),
                "modifierErrors": list(form["modifier"].errors),
                "modifierApplication": form["modifier_application"].value() or "total",
                "modifierApplicationErrors": list(form["modifier_application"].errors),
                "modifierChoices": [
                    {"value": value, "label": label}
                    for value, label in CampaignRoll.ModifierApplication.choices
                ],
            },
        },
    )


@login_required
def campaign_roll(request, pk, roll_pk):
    campaign = _any_campaign_or_404(request, pk)
    try:
        roll = get_object_or_404(
            CampaignRoll.objects.select_related("gang", "miniature", "battle"),
            campaign=campaign,
            pk=roll_pk,
        )
    except ValidationError:
        raise Http404("No such dice roll") from None
    may_note = (
        (not roll.battle_id or not roll.battle.archived)
        and roll.actor_id == request.user.pk
        and may_record_campaign(campaign, request.user)
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
    results = roll.results or ([roll.rolled] if roll.count == 1 else [])
    dice_groups = [
        {
            "value": result,
            "faces": [str(result // 10), str(result % 10)]
            if roll.dice == CampaignRoll.Dice.D66
            else [str(result)],
        }
        for result in results
    ]
    return render(
        request,
        "n26/campaign_roll.html",
        {
            "campaign": campaign,
            "roll": roll,
            "form": form,
            "may_note": may_note,
            "faces": [face for group in dice_groups for face in group["faces"]],
            "dice_groups": dice_groups,
        },
    )


@login_required
@require_GET
def preview_pool_roll(request, pk):
    """Read the same table and visible entries used when adding to the pool."""
    from n26.core.campaigns import roll_table_entries, tables_in_play
    from n26.core.views.campaigns import _asset_type_asked_for
    from n26.library.models import Dice
    from n26.library.staged import sees_staged

    campaign = _own_campaign_or_404(request, pk, with_owner_badge=False)
    asset_type = _asset_type_asked_for(campaign, request.GET.get("type", ""))
    if asset_type is None:
        raise Http404("No such asset type")
    tables = (
        tables_in_play(campaign, include_staged=sees_staged(request.user))
        .filter(asset_type=asset_type)
        .exclude(dice="")
    )
    try:
        table = get_object_or_404(tables, pk=request.GET.get("table", ""))
    except ValidationError:
        raise Http404("No such table") from None
    try:
        rolled = int(request.GET.get("rolled", ""))
    except ValueError:
        return JsonResponse(
            {"status": "invalid", "message": "Enter a whole-number roll."}
        )
    dice = Dice(table.dice)
    if rolled not in Dice.rolls(dice):
        return JsonResponse(
            {
                "status": "invalid",
                "message": f"You cannot roll {rolled} on a {dice.label}.",
            }
        )
    entry = table.landing(rolled, roll_table_entries(table, request.user))
    if entry is None:
        return JsonResponse(
            {
                "status": "invalid",
                "message": f"No result on this table covers a roll of {rolled}.",
            }
        )
    return JsonResponse({"status": "valid", "message": str(entry.asset)})
