"""Crew selection and the shared, canonical model-card sheet."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from n26.core import crew_display as display
from n26.core import crew_workflow
from n26.core.crew_forms import CrewForm
from n26.core.crews import build_crew_sheet, crew_roster, may_edit_crew
from n26.core.models import Campaign
from n26.core.models.crew import BattleCrew, CrewCommandReceipt
from n26.core.operations import Refusal
from n26.core.printing import detail_columns
from n26.core.views.battles import battle_or_404
from n26.core.views.permissions import _any_campaign_or_404

CREW_HELP = {
    "label": "More about crew selection",
    "paragraphs": [
        "Select one equipment set for each model.",
        "After the battle, you can say which reinforcements took part.",
        (
            "A pet that belongs to a model is not listed. It joins the crew "
            "with its owner and does not count towards the crew size. "
            "After the battle, use Record results to add its XP and lasting injuries."
        ),
    ],
}

DRAW_HELP = {
    "label": "More about the random draw",
    "paragraphs": [
        (
            "Use this to select models at random. For random selection, enter "
            "the size of the starting crew. For hybrid selection, first select "
            "the models you want below (the X), then draw the rest (the Y) "
            "here. The crew selection rules are in the Core Rulebook, page 141."
        ),
        (
            "Only available models you have not selected are in the draw. Each "
            "drawn model gets a random equipment set. Drawn models are ticked "
            "below and saved in your draft, so reloading this page does not "
            "draw again."
        ),
    ],
}


def _context(request, pk, battle_pk, gang_pk, *, recovery=False):
    if recovery:
        try:
            campaign = get_object_or_404(Campaign, pk=pk)
        except ValidationError:
            raise Http404("No such campaign") from None
    else:
        campaign = _any_campaign_or_404(request, pk, with_owner_badge=False)
    battle = battle_or_404(campaign, battle_pk)
    try:
        gang = get_object_or_404(battle.gangs.select_related("gang_type"), pk=gang_pk)
    except ValidationError:
        raise Http404("No such gang") from None
    editable = not battle.archived and may_edit_crew(
        campaign=campaign, gang=gang, actor=request.user
    )
    crew = BattleCrew.objects.filter(battle=battle, gang=gang).first()
    return campaign, battle, gang, editable, crew


def _allowed(campaign, gang, actor):
    return may_edit_crew(
        campaign=campaign, gang=gang, actor=actor, include_archived=True
    )


def _props(
    request, campaign, battle, gang, crew, form, *, conflict=False, acknowledgement=None
):
    return display.editor(
        campaign=campaign,
        battle=battle,
        gang=gang,
        actor=request.user,
        form=form,
        crew=crew,
        csrf_token=get_token(request),
        crew_help=CREW_HELP,
        draw_help=DRAW_HELP,
        conflict=conflict,
        read_only=battle.archived or campaign.archived or gang.archived,
        acknowledgement=acknowledgement,
    )


def _next(campaign, battle, gang, result):
    if result.read_only:
        return (
            reverse("n26-battle-crew", args=[campaign.pk, battle.pk, gang.pk])
            + f"?recover=1&saved={result.receipt.request_key}"
        )
    return reverse(
        "n26-battle-crew-sheet"
        if result.receipt.result["action"] == "save"
        else "n26-battle-crew",
        args=[campaign.pk, battle.pk, gang.pk],
    )


def _feedback(request, result):
    tag = f"crew-{result.receipt.request_key}"
    storage = messages.get_messages(request)
    queued = any(tag in (message.extra_tags or "").split() for message in storage)
    storage.used = False
    if not queued:
        messages.success(
            request,
            result.message
            if not result.replayed
            else "This crew change was already saved.",
            extra_tags=tag,
        )


def _acknowledgement(request, battle, gang):
    key = request.GET.get("saved")
    if not key:
        return None
    try:
        receipt = CrewCommandReceipt.objects.filter(
            gang=gang, battle=battle, actor=request.user, request_key=key
        ).first()
    except ValidationError:
        return None
    return receipt.result if receipt else None


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def edit_crew(request, pk, battle_pk, gang_pk):
    recovery = request.method == "POST" or request.GET.get("recover") == "1"
    campaign, battle, gang, editable, crew = _context(
        request, pk, battle_pk, gang_pk, recovery=recovery
    )
    if not _allowed(campaign, gang, request.user) or (not editable and not recovery):
        raise Http404("No such crew")
    conflict = False
    if request.method == "POST":
        try:
            result = crew_workflow.perform(
                battle=battle, gang=gang, actor=request.user, data=request.POST
            )
        except Refusal:
            raise Http404("No such crew") from None
        else:
            if result.saved:
                _feedback(request, result)
                if result.newer:
                    return redirect(
                        reverse(
                            "n26-battle-crew", args=[campaign.pk, battle.pk, gang.pk]
                        )
                        + f"?recover=1&saved={result.receipt.request_key}"
                    )
                return redirect(_next(campaign, battle, gang, result))
            if result.read_only:
                raise Http404("No such crew")
            form = result.form
            crew = result.crew
            conflict = result.conflict
    else:
        form = CrewForm(roster=crew_roster(gang, crew), crew=crew)
    props = _props(
        request,
        campaign,
        battle,
        gang,
        crew,
        form,
        conflict=conflict,
        acknowledgement=_acknowledgement(request, battle, gang),
    )
    return render(
        request,
        "n26/crew.html",
        {
            "campaign": campaign,
            "battle": battle,
            "gang": gang,
            "crew": crew,
            "form": form,
            "crew_workflow": props,
            "crew_picker": {
                "models": props["models"],
                "battleUrl": props["battleUrl"],
                "revision": props["revision"],
            },
        },
    )


@require_POST
@never_cache
def crew_command(request, pk, battle_pk, gang_pk):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in again to save this crew."}, status=401)
    campaign, battle, gang, editable, crew = _context(
        request, pk, battle_pk, gang_pk, recovery=True
    )
    if not _allowed(campaign, gang, request.user):
        raise Http404("No such crew")
    try:
        result = crew_workflow.perform(
            battle=battle,
            gang=gang,
            actor=request.user,
            data=request.POST,
            require_key=True,
        )
    except Refusal as exc:
        return JsonResponse({"errors": {"__all__": [exc.public_message]}}, status=409)
    if result.saved:
        _feedback(request, result)
        return JsonResponse(
            {
                "nextUrl": _next(campaign, battle, gang, result),
                "acknowledged": result.receipt.result,
                "newer": result.newer,
                "currentUrl": reverse(
                    "n26-battle-crew", args=[campaign.pk, battle.pk, gang.pk]
                )
                + "?recover=1",
            }
        )
    return JsonResponse(
        {
            "errors": dict(result.form.errors),
            "code": "revision_conflict"
            if result.conflict
            else "key_conflict"
            if result.key_conflict
            else "invalid",
            "current": _props(
                request, campaign, battle, gang, result.crew, result.form
            )["current"],
        },
        status=result.status,
    )


@never_cache
@require_http_methods(["GET"])
def crew_display(request, pk, battle_pk, gang_pk):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in again to view this crew."}, status=401)
    campaign, battle, gang, editable, crew = _context(
        request, pk, battle_pk, gang_pk, recovery=request.GET.get("recover") == "1"
    )
    if not _allowed(campaign, gang, request.user) or (
        not editable and request.GET.get("recover") != "1"
    ):
        raise Http404("No such crew")
    form = CrewForm(roster=crew_roster(gang, crew), crew=crew)
    return JsonResponse(_props(request, campaign, battle, gang, crew, form))


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
            for pet in line.pets:
                rows.append(
                    {
                        "card": pet,
                        "subtitle": " · ".join(
                            part
                            for part in ("Pet", pet.profile_name, pet.owner_line)
                            if part
                        ),
                        "columns": detail_columns(pet),
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
