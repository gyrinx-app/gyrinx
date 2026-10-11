"""Campaign cycle controls, reward review and immutable receipts."""

import json

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from n26.core.confirm import Checkbox
from n26.core.cycle_display import cycle_history_entries
from n26.core.cycle_rewards import apply_cycle, pending_gangs, preview_cycle
from n26.core.cycles import current_cycle, rename_cycle, start_cycle
from n26.core.models import CampaignCycle, CycleResolution
from n26.core.operations import Refusal
from n26.core.views.permissions import _any_campaign_or_404, _own_campaign_or_404
from n26.flags import CAMPAIGNS, requires_flag


class CycleForm(forms.Form):
    name = forms.CharField(required=False, max_length=200, label="Cycle name")
    previous = forms.CharField(required=False, widget=forms.HiddenInput)
    leave_pending = forms.BooleanField(
        required=False, label="Leave pending boons unapplied"
    )


@requires_flag(CAMPAIGNS)
@login_required
def edit_cycle(request, pk):
    campaign = _own_campaign_or_404(request, pk)
    cycle = current_cycle(campaign)
    renaming = request.GET.get("action") == "rename"
    if renaming and cycle is None:
        raise Http404("No current cycle")
    pending = pending_gangs(cycle) if cycle and not renaming else []
    form = CycleForm(
        request.POST or None,
        initial={
            "previous": str(cycle.pk) if cycle else "",
            "name": cycle.name if renaming else "",
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            if renaming:
                if form.cleaned_data["previous"] != str(cycle.pk):
                    raise Refusal("The current cycle changed. Refresh this page.")
                rename_cycle(cycle, actor=request.user, name=form.cleaned_data["name"])
            else:
                start_cycle(
                    campaign,
                    actor=request.user,
                    name=form.cleaned_data["name"],
                    previous=form.cleaned_data["previous"] or None,
                    leave_pending=form.cleaned_data["leave_pending"],
                )
        except Refusal as refused:
            form.add_error(None, str(refused))
        else:
            messages.success(
                request,
                "Cycle name updated." if renaming else "Campaign cycle started.",
            )
            return redirect("n26-campaign", pk=pk)
    return render(
        request,
        "n26/cycle_form.html",
        {
            "campaign": campaign,
            "cycle": cycle,
            "form": form,
            "pending": pending,
            "renaming": renaming,
            "pending_checkbox": Checkbox(
                name="leave_pending",
                value="on",
                label="Leave pending boons unapplied",
                checked=bool(form["leave_pending"].value()),
            ),
            "title": "Rename cycle"
            if renaming
            else f"Start cycle {cycle.number + 1}"
            if cycle
            else "Start first cycle",
            "next_number": cycle.number + 1 if cycle else 1,
            "submit_label": "Save"
            if renaming
            else f"Start cycle {cycle.number + 1 if cycle else 1}",
        },
    )


def _cycle(campaign, pk):
    try:
        return get_object_or_404(CampaignCycle, campaign=campaign, pk=pk)
    except ValidationError:
        raise Http404("No such campaign cycle") from None


@requires_flag(CAMPAIGNS)
@login_required
def cycle_rewards(request, pk, cycle_pk):
    campaign = (
        _own_campaign_or_404(request, pk)
        if request.method == "POST"
        else _any_campaign_or_404(request, pk)
    )
    read_only = request.user.pk != campaign.owner_id or campaign.archived
    cycle = _cycle(campaign, cycle_pk)
    if cycle.ended:
        return redirect("n26-cycle-history", pk=pk)
    problem = ""
    submitted = None
    if request.method == "POST":
        try:
            submitted = json.loads(request.POST.get("selections", ""))
            if not isinstance(submitted, dict) or any(
                not isinstance(item, dict) for item in submitted.values()
            ):
                raise Refusal("Review the rewards and select gangs to apply.")
            apply_cycle(
                cycle,
                actor=request.user,
                token=request.POST.get("token", ""),
                selections=submitted,
            )
        except ValueError, ValidationError:
            problem = "Review the rewards and select gangs to apply."
        except Refusal as refused:
            problem = str(refused)
        else:
            messages.success(
                request,
                "Selected gangs' cycle boons applied. View their receipts below.",
            )
            return redirect("n26-cycle-rewards", pk=pk, cycle_pk=cycle.pk)
    props = preview_cycle(cycle).props()
    if problem and isinstance(submitted, dict):
        props["submitted"] = _reward_draft(submitted, props["gangs"])
    props.update(
        csrf=get_token(request),
        problem=problem,
        readOnly=read_only,
        focusGang=request.GET.get("gang", ""),
        receipts={
            str(receipt.gang_id): reverse("n26-cycle-receipt", args=[pk, receipt.pk])
            for receipt in cycle.resolutions.all()
        },
    )
    return render(
        request,
        "n26/cycle_rewards.html",
        {
            "campaign": campaign,
            "cycle": cycle,
            "props": props,
            "read_only": read_only,
            "title": "Cycle boons" if read_only else "Apply boons",
        },
    )


def _reward_draft(submitted, gangs):
    """Keep known controls on refusal; fresh server props still own the preview."""
    draft = {}
    for gang in gangs:
        value = submitted.get(gang["gang_id"])
        if gang["receipt_id"] or not isinstance(value, dict):
            continue
        comment = value.get("comment", "")
        lines = value.get("lines", {})
        kept = {}
        for line in gang["lines"]:
            choice = lines.get(line["key"]) if isinstance(lines, dict) else None
            if not isinstance(choice, dict):
                continue
            kept[line["key"]] = {
                "skip": choice.get("skip") is True,
                **{
                    key: choice[key][:200]
                    for key in ("option", "name")
                    if isinstance(choice.get(key), str)
                },
            }
        draft[gang["gang_id"]] = {
            "comment": comment[:255] if isinstance(comment, str) else "",
            "lines": kept,
        }
    return draft


@requires_flag(CAMPAIGNS)
@login_required
def cycle_history(request, pk):
    campaign = _any_campaign_or_404(request, pk)
    cycles = campaign.cycles.prefetch_related("resolutions")
    page = Paginator(cycles, 20).get_page(request.GET.get("page"))
    memberships = list(campaign.memberships.select_related("gang"))
    page.object_list = cycle_history_entries(
        page.object_list, memberships, actor=request.user, campaign=campaign
    )
    return render(
        request, "n26/cycle_history.html", {"campaign": campaign, "page": page}
    )


@requires_flag(CAMPAIGNS)
@login_required
def cycle_receipt(request, pk, receipt_pk):
    campaign = _any_campaign_or_404(request, pk)
    try:
        receipt = get_object_or_404(
            CycleResolution.objects.select_related("cycle", "gang", "actor"),
            pk=receipt_pk,
            cycle__campaign=campaign,
        )
    except ValidationError:
        raise Http404("No such cycle receipt") from None
    return render(
        request, "n26/cycle_receipt.html", {"campaign": campaign, "receipt": receipt}
    )
