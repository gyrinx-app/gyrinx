"""Crew selection and the shared, canonical model-card sheet."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from n26.core.crew_forms import CrewForm
from n26.core.crews import build_crew_sheet, crew_roster, may_edit_crew, save_crew
from n26.core.models.crew import BattleCrew
from n26.core.operations import Refusal
from n26.core.printing import detail_columns
from n26.core.views.battles import battle_or_404
from n26.core.views.permissions import _any_campaign_or_404
from n26.flags import CAMPAIGNS, requires_flag


def _context(request, pk, battle_pk, gang_pk):
    campaign = _any_campaign_or_404(request, pk, with_owner_badge=False)
    battle = battle_or_404(campaign, battle_pk)
    try:
        gang = get_object_or_404(battle.gangs.select_related("gang_type"), pk=gang_pk)
    except ValidationError:
        raise Http404("No such gang") from None
    editable = may_edit_crew(campaign=campaign, gang=gang, actor=request.user)
    crew = BattleCrew.objects.filter(battle=battle, gang=gang).first()
    return campaign, battle, gang, editable, crew


@requires_flag(CAMPAIGNS)
@login_required
@require_http_methods(["GET", "POST"])
def edit_crew(request, pk, battle_pk, gang_pk):
    campaign, battle, gang, editable, crew = _context(request, pk, battle_pk, gang_pk)
    if not editable:
        raise Http404("No such crew")
    roster = crew_roster(gang, crew)
    form = CrewForm(
        request.POST if request.method == "POST" else None, roster=roster, crew=crew
    )
    if request.method == "POST" and form.is_valid():
        action = request.POST.get("action", "save")
        if action not in {"save", "draft", "draw"}:
            form.add_error(None, "Select Save crew, Save draft or Draw.")
        elif action == "draw" and not form.cleaned_data["random_count"]:
            form.add_error("random_count", "Enter the number of models to draw.")
        else:
            try:
                save_crew(
                    battle=battle,
                    gang=gang,
                    actor=request.user,
                    revision=form.cleaned_data["revision"],
                    selections=form.cleaned_data["selections"],
                    confirm=action == "save",
                    random_count=form.cleaned_data["random_count"]
                    if action == "draw"
                    else 0,
                    random_role=form.cleaned_data["random_role"],
                )
            except Refusal as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(
                    request,
                    "Draw saved."
                    if action == "draw"
                    else "Crew saved."
                    if action == "save"
                    else "Crew draft saved.",
                )
                return redirect(
                    "n26-battle-crew-sheet" if action == "save" else "n26-battle-crew",
                    pk=campaign.pk,
                    battle_pk=battle.pk,
                    gang_pk=gang.pk,
                )
    selected = [m for m in form.models if m.role.value() in {"starting", "reserve"}]
    return render(
        request,
        "n26/crew.html",
        {
            "campaign": campaign,
            "battle": battle,
            "gang": gang,
            "crew": crew,
            "form": form,
            "selected_count": len(selected),
            "selected_rating": sum(m.miniature.rating for m in selected),
            "starting_count": sum(m.role.value() == "starting" for m in selected),
            "reserve_count": sum(m.role.value() == "reserve" for m in selected),
        },
    )


@requires_flag(CAMPAIGNS)
@login_required
@require_http_methods(["GET"])
def crew_sheet(request, pk, battle_pk, gang_pk):
    campaign, battle, gang, editable, crew = _context(request, pk, battle_pk, gang_pk)
    if crew is None or (not crew.confirmed and not editable):
        raise Http404("No saved crew")
    # The fetched gang is reused so drawing the crew needs no lazy FK query.
    crew.gang = gang
    sheet = build_crew_sheet(crew)
    if request.GET.get("print") == "1":
        # These cards already use the saved equipment snapshot. The general
        # print picker keeps all wargear, so rebuilding through it would change
        # the crew's chosen cards.
        rows = []
        for line in [*sheet.starting, *sheet.reserves]:
            card = line.card
            rows.append(
                {
                    "card": card,
                    "member": line.member,
                    "missing_equipment": line.missing_equipment,
                    "subtitle": " · ".join(
                        part
                        for part in (
                            line.member.get_role_display(),
                            line.member.card_name,
                            card.status_label if card else "",
                            card.profile_name if card else "",
                            card.owner_line if card else "",
                        )
                        if part
                    ),
                    "columns": detail_columns(card) if card else [],
                }
            )
        return render(
            request,
            "n26/print_gang.html",
            {
                "gang": gang,
                "battle": battle,
                "crew_sheet": sheet,
                "crew_url": reverse(
                    "n26-battle-crew-sheet",
                    kwargs={
                        "pk": campaign.pk,
                        "battle_pk": battle.pk,
                        "gang_pk": gang.pk,
                    },
                ),
                "rows": rows,
                "include_notes": True,
            },
        )
    return render(
        request,
        "n26/crew_sheet.html",
        {
            "campaign": campaign,
            "battle": battle,
            "gang": gang,
            "crew": crew,
            "sheet": sheet,
            "editable": editable,
            "groups": [
                ("Starting crew", sheet.starting),
                ("Reinforcements", sheet.reserves),
            ],
        },
    )
