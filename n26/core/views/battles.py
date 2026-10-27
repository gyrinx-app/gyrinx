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
from django.views.decorators.http import require_POST

from n26.core.battle_permissions import may_record_gang
from n26.core.campaign_permissions import may_record_outcome
from n26.core.campaigns import battle_stakes, campaign_operation
from n26.core.forms import BattleForm, BattleOutcomeForm
from n26.core.models import (
    Battle,
    BattleCrew,
    BattleStake,
    CampaignEvent,
    Gang,
    PostBattleReport,
)
from n26.core.operations import Refusal
from n26.core.scenarios import results
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
            "stakes": battle_stakes(found, request.user),
            "yours": campaign.owner_id == request.user.pk,
            "may_record_outcome": may_record_outcome(found, request.user),
            "scenario_results": results(found.scenario_rolls or {}),
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
    # "Add another" redraws the draft with one more stake row and saves
    # nothing, so what was entered is kept and nothing is checked yet.
    adding_stake = request.method == "POST" and "add_stake" in request.POST
    form = BattleForm(
        request.POST if request.method == "POST" and not adding_stake else None,
        playing=playing,
        battle=found,
        draft=request.POST if adding_stake else None,
    )
    if request.method == "POST" and not adding_stake and form.is_valid():
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


@dataclass(frozen=True)
class BattleListGang:
    gang: object
    won: bool
    #: Models saved as this gang's starting crew, or None before a crew is
    #: saved.
    starting: int | None


@dataclass(frozen=True)
class BattleListLine:
    battle: object
    gangs: list
    #: The battle's ``BattleStake`` rows, in the order they were added.
    stakes: list

    @property
    def players(self):
        """The usernames of the gangs' owners, A to Z, for sorting."""
        return sorted(
            line.gang.owner.username.lower() for line in self.gangs if line.gang.owner
        )


def _battle_lines(campaign):
    """Each battle that is not archived, with its gangs, their starting
    crew sizes and its stake, read in a fixed number of queries."""
    # A pet saved as a crew member goes with its owner and is not counted,
    # as on the battle's own page.
    starting = Q(
        members__miniature__membership__caused_by__miniature_root__isnull=True,
        members__role="starting",
    )
    battles = campaign.battles.filter(archived=False).prefetch_related(
        Prefetch(
            "stakes",
            queryset=BattleStake.objects.select_related(
                "asset__asset__asset_type", "awarded_to"
            ),
        ),
        Prefetch(
            "gangs",
            # The owner's profile and badges, so each Player link
            # costs nothing more.
            queryset=Gang.objects.select_related(
                "gang_type", "owner__profile"
            ).prefetch_related("owner__badge_grants"),
        ),
        "winners",
        Prefetch(
            "crews",
            queryset=BattleCrew.objects.annotate(
                starting_count=Count("members", filter=starting)
            ),
        ),
    )
    lines = []
    for found in battles:
        crews = {crew.gang_id: crew.starting_count for crew in found.crews.all()}
        lines.append(
            BattleListLine(
                battle=found,
                gangs=[
                    BattleListGang(gang, won, crews.get(gang.pk))
                    for gang, won in found.gang_outcomes
                ],
                stakes=list(found.stakes.all()),
            )
        )
    return lines


def _sorted_battle_lines(lines, sort):
    """``lines`` in the order ``sort`` names. A battle missing the value
    sorted on, such as one with no stakes, goes last either way; ties keep
    the newest battle first."""
    key = sort.lstrip("-")
    reverse = sort.startswith("-")
    value = {
        "date": lambda line: (line.battle.date, line.battle.created),
        "scenario": lambda line: line.battle.title.lower(),
        "gangs": lambda line: len(line.gangs),
        "player": lambda line: line.players or None,
        "stake": lambda line: (
            ", ".join(str(stake).lower() for stake in line.stakes) or None
        ),
    }[key]
    known = [line for line in lines if value(line) is not None]
    unknown = [line for line in lines if value(line) is None]
    return sorted(known, key=value, reverse=reverse) + unknown


@login_required
def campaign_battles(request, pk):
    """Every battle in the campaign that is not archived, with who took
    part, their players and gang types, and what was staked. Sorted and
    filtered by the address, so a view can be shared."""
    from n26.core.forms import CampaignBattlesForm

    campaign = _any_campaign_or_404(request, pk)
    lines = _battle_lines(campaign)
    gangs = {}
    for line in lines:
        for entry in line.gangs:
            gangs[str(entry.gang.pk)] = entry.gang.name
    filters = CampaignBattlesForm(
        request.GET or None,
        gangs=sorted(gangs.items(), key=lambda item: item[1].lower()),
    )
    sort, gang = "-date", ""
    if filters.is_valid():
        sort = filters.cleaned_data["sort"] or sort
        gang = filters.cleaned_data["gang"]
    total = len(lines)
    if gang:
        lines = [
            line
            for line in lines
            if any(str(entry.gang.pk) == gang for entry in line.gangs)
        ]
    # Each heading sorts by its column in its usual first order; a second
    # click reverses it. The gang filter is kept.
    headings = []
    for first, label in (
        ("scenario", "Battle"),
        ("-gangs", "Gangs"),
        ("player", "Player"),
        ("stake", "Stake"),
        ("-date", "Date"),
    ):
        token = first.lstrip("-")
        reverse = token if first.startswith("-") else f"-{token}"
        query = request.GET.copy()
        query["sort"] = reverse if sort == first else first
        state = ""
        if sort.lstrip("-") == token:
            state = "descending" if sort.startswith("-") else "ascending"
        headings.append(
            {"label": label, "href": f"?{query.urlencode()}", "state": state}
        )
    return render(
        request,
        "n26/campaign_battles.html",
        {
            "campaign": campaign,
            "filters": filters,
            "headings": headings,
            "sort": sort,
            "lines": _sorted_battle_lines(lines, sort),
            "matched": len(lines),
            "total": total,
            "narrowed": bool(gang) or sort != "-date",
        },
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


@login_required
def record_battle_outcome(request, pk, battle_pk):
    """The outcome of a battle with none, recorded by a player who fought
    it or by the arbitrator.

    Only the outcome and winners are offered. A reader who may not record
    it, or a battle whose outcome is already in, gets a 404.
    """
    campaign = _any_campaign_or_404(
        request, pk, with_owner_badge=request.method == "GET"
    )
    found = battle_or_404(campaign, battle_pk)
    if not may_record_outcome(found, request.user):
        raise Http404("No such battle")

    if request.method == "POST":
        form = BattleOutcomeForm(request.POST, battle=found)
        if form.is_valid():
            try:
                with campaign_operation(campaign, actor=request.user) as act:
                    act.record_outcome(
                        found,
                        result=form.cleaned_data["result"],
                        winners=form.cleaned_data["winners"],
                        revision=form.cleaned_data["revision"],
                    )
            except Refusal as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, "Outcome recorded.")
                return redirect("n26-battle", pk=campaign.pk, battle_pk=found.pk)
    else:
        form = BattleOutcomeForm(battle=found)

    _badge_a_redrawn_page(request, campaign)
    return render(
        request,
        "n26/battle_outcome.html",
        {"campaign": campaign, "battle": found, "form": form},
    )
