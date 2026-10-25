"""Battle records: shared reading and arbitrator-owned metadata."""

from dataclasses import dataclass
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from n26.core import matchmaking
from n26.core.battle_permissions import may_record_gang
from n26.core.campaigns import battle_stake, campaign_operation
from n26.core.forms import BattleForm, MatchmakerForm
from n26.core.models import (
    Battle,
    BattleCrew,
    CampaignEvent,
    Gang,
    PostBattleReport,
)
from n26.core.operations import Refusal
from n26.core.views.campaigns import _badge_a_redrawn_page
from n26.core.views.permissions import _any_campaign_or_404, _own_campaign_or_404


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
    gang: object
    may_record: bool
    crew: object = None
    report: object = None

    @property
    def report_label(self):
        if self.report is None:
            return "Record results"
        if self.report.state == PostBattleReport.State.DRAFT:
            return "Continue draft"
        return "View results"


@login_required
def battle(request, pk, battle_pk):
    campaign = _any_campaign_or_404(request, pk)
    found = battle_or_404(campaign, battle_pk)
    winners = {gang.pk for gang in found.winners.all()}
    active_gang_ids = set(
        campaign.memberships.filter(left__isnull=True).values_list("gang_id", flat=True)
    )
    # A pet saved as a crew member goes with its owner and is not counted.
    counted = Q(members__miniature__membership__caused_by__miniature_root__isnull=True)
    starting = counted & Q(members__role="starting")
    reserve = counted & Q(members__role="reserve")
    crews = {
        crew.gang_id: crew
        for crew in BattleCrew.objects.filter(battle=found).annotate(
            starting_count=Count("members", filter=starting),
            reserve_count=Count("members", filter=reserve),
            starting_rating=Sum("members__rating", filter=starting, default=0),
            reserve_rating=Sum("members__rating", filter=reserve, default=0),
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
            gang=gang,
            may_record=not found.archived
            and may_record_gang(
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
            "request_key": uuid4(),
            "recorded": recorded,
            "stake": battle_stake(found, request.user),
            "yours": campaign.owner_id == request.user.pk,
        },
    )


@login_required
def edit_battle(request, pk, battle_pk):
    campaign = _own_campaign_or_404(
        request, pk, with_owner_badge=request.method == "GET"
    )
    found = battle_or_404(campaign, battle_pk)
    if found.archived:
        raise Http404("This battle is archived")
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


@login_required
def archived_battles(request, pk):
    campaign = _own_campaign_or_404(request, pk)
    page = Paginator(
        campaign.battles.filter(archived=True).prefetch_related("gangs", "winners"),
        30,
    ).get_page(request.GET.get("page"))
    return render(
        request, "n26/archived_battles.html", {"campaign": campaign, "page": page}
    )


@login_required
def matchmaker(request, pk):
    """Draw random matchups, then pre-record or redraw the ones ticked.

    The settings live in the address, so a POST keeps them. Drawing writes
    nothing: only Pre-record battles does.
    """
    campaign = _own_campaign_or_404(request, pk)
    today = timezone.localdate()
    entrants = matchmaking.campaign_entrants(campaign, today)
    if "mode" in request.GET:
        form = MatchmakerForm(request.GET, entrants=entrants)
    else:
        form = MatchmakerForm(entrants=entrants)
    draw, selected, results_error = None, set(), ""
    if request.method == "POST":
        values = request.POST.getlist("selected")
        try:
            draw = matchmaking.Draw.read(
                campaign, request.POST.get("draw", ""), entrants
            )
            chosen = draw.chosen(values)
            selected = {str(index + 1) for index in chosen}
            if request.POST.get("action") == "rematch":
                draw = draw.redraw(chosen)
                selected = set()
            elif not chosen:
                raise Refusal("Select at least one matchup to pre-record.")
            else:
                picked = [
                    (title, matchup)
                    for number, title, matchup in draw.titled()
                    if number - 1 in chosen
                ]
                gangs = {
                    str(gang.pk): gang
                    for gang in Gang.objects.filter(
                        pk__in=[g.id for _, m in picked for g in m.gangs]
                    )
                }
                with campaign_operation(campaign, actor=request.user) as act:
                    battles = act.pre_record_matchups(
                        [
                            (title, [gangs[gang.id] for gang in matchup.gangs])
                            for title, matchup in picked
                        ],
                        today=today,
                    )
                count = len(battles)
                messages.success(
                    request,
                    f"Pre-recorded {count} battle{'s' if count != 1 else ''}.",
                )
                return redirect("n26-campaign", pk=campaign.pk)
        except (matchmaking.NoMatchup, Refusal) as exc:
            results_error = str(exc)
    elif form.is_bound and form.is_valid():
        data = form.cleaned_data
        try:
            draw = matchmaking.Draw(
                mode=data["mode"],
                ways=data["ways"],
                allow_uneven=data["allow_uneven"],
                allow_rematches=data["allow_rematches"],
                matchups=tuple(
                    matchmaking.make_matchups(
                        form.selected(),
                        ways=data["ways"],
                        matchups=data["matchups"],
                        allow_uneven=data["allow_uneven"],
                        allow_rematches=data["allow_rematches"],
                    )
                ),
            )
        except matchmaking.NoMatchup as exc:
            form.add_error(None, str(exc))
    mode = request.GET.get("mode", matchmaking.Mode.PAIRS)
    results_url = reverse("n26-campaign-matchmaker", args=[campaign.pk])
    if request.GET:
        results_url += "?" + request.GET.urlencode()
    return render(
        request,
        "n26/matchmaker.html",
        {
            "campaign": campaign,
            "form": form,
            "mode_pairs": mode != matchmaking.Mode.MORE,
            "mode_more": mode == matchmaking.Mode.MORE,
            "entrants": entrants,
            "chosen": set(form["gangs"].value() or ()),
            "draw_token": draw.sign(campaign) if draw else "",
            "proposals": draw.titled() if draw else [],
            "selected": selected,
            "results_url": results_url,
            "results_error": results_error,
        },
    )


@login_required
@require_POST
def restore_battle(request, pk, battle_pk):
    campaign = _own_campaign_or_404(request, pk, with_owner_badge=False)
    found = battle_or_404(campaign, battle_pk)
    try:
        revision = int(request.POST.get("revision", ""))
    except TypeError, ValueError:
        messages.error(
            request,
            "The battle version is missing or invalid. Reload it before restoring it.",
        )
    else:
        try:
            with campaign_operation(campaign, actor=request.user) as act:
                act.restore_battle(found, revision=revision)
        except Refusal as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Battle restored.")
    return redirect("n26-battle", pk=campaign.pk, battle_pk=found.pk)
