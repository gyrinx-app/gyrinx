"""Battle records: shared reading and arbitrator-owned metadata."""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from n26.core.battle_permissions import may_record_gang
from n26.core.campaigns import campaign_operation
from n26.core.forms import BattleForm
from n26.core.models import Battle, BattleCrew, CampaignEvent, Gang, PostBattleReport
from n26.core.operations import Refusal
from n26.core.views.campaigns import _badge_a_redrawn_page
from n26.core.views.permissions import _any_campaign_or_404, _own_campaign_or_404
from n26.flags import CAMPAIGNS, requires_flag


def battle_or_404(campaign, pk):
    try:
        return get_object_or_404(
            Battle.objects.prefetch_related(
                Prefetch("gangs", queryset=Gang.objects.select_related("gang_type")),
                "winners",
            ),
            campaign=campaign,
            pk=pk,
        )
    except ValidationError:
        raise Http404("No such battle") from None


@dataclass(frozen=True)
class BattleParticipant:
    id: str
    name: str
    winner: bool
    may_read_history: bool
    gang: object
    may_record: bool
    crew: object = None
    report: object = None


@requires_flag(CAMPAIGNS)
@login_required
def battle(request, pk, battle_pk):
    campaign = _any_campaign_or_404(request, pk)
    found = battle_or_404(campaign, battle_pk)
    winners = {gang.pk for gang in found.winners.all()}
    active_gang_ids = set(
        campaign.memberships.filter(left__isnull=True).values_list("gang_id", flat=True)
    )
    crews = {
        crew.gang_id: crew
        for crew in BattleCrew.objects.filter(battle=found).annotate(
            starting_count=Count("members", filter=Q(members__role="starting")),
            reserve_count=Count("members", filter=Q(members__role="reserve")),
        )
    }
    reports = {
        report.gang_id: report
        for report in PostBattleReport.objects.filter(battle=found).only(
            "id", "gang_id", "state", "latest_sequence", "modified"
        )
    }
    participants = [
        BattleParticipant(
            id=str(gang.pk),
            name=gang.name,
            winner=gang.pk in winners,
            may_read_history=gang.owner_id == request.user.pk,
            gang=gang,
            may_record=may_record_gang(
                gang=gang,
                actor=request.user,
                campaign=campaign,
                active_gang_ids=active_gang_ids,
            ),
            crew=crews.get(gang.pk),
            report=reports.get(gang.pk),
        )
        for gang in found.gangs.all()
    ]
    participants.sort(
        key=lambda participant: (
            participant.gang.owner_id != request.user.pk,
            participant.name.casefold(),
            participant.id,
        )
    )
    recorded = (
        campaign.events.filter(battle=found, kind=CampaignEvent.Kind.BATTLE_RECORDED)
        .select_related("actor", "actor__profile")
        .prefetch_related("actor__badge_grants")
        .first()
    )
    return render(
        request,
        "n26/battle.html",
        {
            "campaign": campaign,
            "battle": found,
            "participants": participants,
            "recorded": recorded,
            "yours": campaign.owner_id == request.user.pk,
            "has_history": bool(crews or reports) or found.gang_events.exists(),
        },
    )


@requires_flag(CAMPAIGNS)
@login_required
def edit_battle(request, pk, battle_pk):
    campaign = _own_campaign_or_404(
        request, pk, with_owner_badge=request.method == "GET"
    )
    found = battle_or_404(campaign, battle_pk)
    # Existing participants remain available after leaving the campaign.
    playing = (
        Gang.objects.filter(
            Q(
                campaign_memberships__campaign=campaign,
                campaign_memberships__left__isnull=True,
            )
            | Q(battles=found)
        )
        .distinct()
        .order_by("name")
    )
    form = BattleForm(
        request.POST if request.method == "POST" else None,
        playing=playing,
        battle=found,
    )
    if request.method == "POST" and form.is_valid():
        try:
            with campaign_operation(campaign, actor=request.user) as act:
                act.edit_battle(found, **form.cleaned_data)
        except Refusal as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Battle updated.")
            return redirect("n26-battle", pk=campaign.pk, battle_pk=found.pk)
    _badge_a_redrawn_page(request, campaign)
    return render(
        request,
        "n26/add_battle.html",
        {"campaign": campaign, "battle": found, "form": form},
    )
