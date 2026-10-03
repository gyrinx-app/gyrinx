"""Saved post-battle forms, per-gang application, and immutable receipts."""

from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Prefetch, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from n26.core.campaigns import battle_stake, stake_came_from
from n26.core.models import (
    Battle,
    BattleCrew,
    Miniature,
    PostBattleReport,
    PostBattleRevision,
)
from n26.core.operations import Refusal
from n26.core.post_battle_forms import (
    ReportVersionForm,
    StartReportForm,
    change_draft,
    editor_models,
    keep_recorded_xp,
    mission_results,
    posted_payload,
    preview_display,
    receipt_mission,
    receipt_models,
    refreshed_model,
    refreshes_mission,
    toolbar_display,
    xp_toolbar,
)
from n26.core.views.battles import battle_or_404
from n26.core.views.htmx import is_htmx, redirect_page
from n26.core.views.permissions import (
    _any_campaign_or_404,
    _any_gang_or_404,
    _own_gang_or_404,
)
from n26.flags import CAMPAIGNS, requires_flag


def _report_or_404(pk):
    try:
        return get_object_or_404(
            PostBattleReport.objects.select_related(
                "gang",
                "gang__owner",
                "gang__gang_type",
                "battle__campaign",
                "last_editor",
            ),
            pk=pk,
            gang__archived=False,
        )
    except ValidationError:
        raise Http404("No such report") from None


def _editable_or_404(report, user):
    from n26.core.post_battle import can_edit_report

    if not can_edit_report(report, user):
        raise Http404("No such report")


def _initial_payload(gang, battle=None):
    starting = set()
    if battle:
        crew = BattleCrew.objects.filter(battle=battle, gang=gang).first()
        if crew:
            starting = set(
                crew.members.filter(
                    role="starting", miniature__isnull=False
                ).values_list("miniature_id", flat=True)
            )
    # A pet takes part when its owner starts; any other model when it starts.
    return {
        "schema": 2,
        "credit_lines": [{"id": str(uuid4()), "amount": "", "reason": ""}],
        "gang_counters": {},
        "participation_confirmed": False,
        "models": [
            {
                "id": str(model.pk),
                "participated": (
                    getattr(model.membership.caused_by, "miniature_root_id", None)
                    or model.pk
                )
                in starting,
                "xp": "",
                "status": "",
                "equipment": "keep",
                "effects": [],
                "counters": {},
                "note": "",
            }
            for model in Miniature.objects.filter(
                membership__gang=gang, membership__archived=False
            ).select_related("membership__caused_by")
        ],
    }


def _report_destination(report, request=None):
    name = (
        "n26-post-battle-receipt"
        if report.state == PostBattleReport.State.APPLIED
        else "n26-post-battle-editor"
    )
    if request is not None:
        return redirect_page(request, name, pk=report.pk)
    return redirect(name, pk=report.pk)


def _campaign_report_entry(battle, gang):
    report = next(iter(battle.gang_reports), None)
    entry = {"battle": battle, "report": report}
    if battle.campaign.archived:
        entry["unavailable"] = "This campaign is archived."
    elif report and (
        report.state == PostBattleReport.State.APPLIED
        or (not battle.is_participant and report.latest_sequence)
    ):
        entry.update(
            href=reverse("n26-post-battle-receipt", args=[report.pk]),
            label="View results",
        )
    elif not battle.is_participant:
        entry["unavailable"] = "This gang is no longer a participant in this battle."
    elif report:
        entry.update(
            href=reverse("n26-post-battle-editor", args=[report.pk]),
            label="Continue draft",
        )
    else:
        entry.update(
            start_url=reverse(
                "n26-battle-report", args=[battle.campaign_id, battle.pk, gang.pk]
            ),
            request_key=uuid4(),
        )
    return entry


@requires_flag(CAMPAIGNS)
@login_required
def gang_post_battle(request, pk):
    from n26.core.post_battle import start_report

    gang = _own_gang_or_404(request, pk)
    form = StartReportForm(
        request.POST if request.method == "POST" else None,
        initial={"request_key": uuid4(), "date": timezone.localdate()},
    )
    if request.method == "POST" and form.is_valid():
        try:
            report = start_report(
                gang,
                actor=request.user,
                payload=_initial_payload(gang),
                **form.cleaned_data,
            )
        except Refusal as exc:
            form.add_error(None, str(exc))
        else:
            return _report_destination(report)

    reports = gang.post_battle_reports.defer("draft")
    battles = (
        Battle.objects.annotate(
            is_participant=Exists(
                Battle.gangs.through.objects.filter(battle_id=OuterRef("pk"), gang=gang)
            )
        )
        .filter(
            Q(is_participant=True, campaign__archived=False)
            | Exists(reports.filter(battle_id=OuterRef("pk")))
        )
        .select_related("campaign")
        .prefetch_related(Prefetch("reports", queryset=reports, to_attr="gang_reports"))
        .order_by("-date", "-pk")
    )
    campaign_page = Paginator(battles, 30).get_page(request.GET.get("campaign_page"))
    standalone_page = Paginator(reports.filter(battle__isnull=True), 50).get_page(
        request.GET.get("standalone_page")
    )
    return render(
        request,
        "n26/post_battle_list.html",
        {
            "gang": gang,
            "form": form,
            "campaign_entries": [
                _campaign_report_entry(battle, gang) for battle in campaign_page
            ],
            "campaign_page": campaign_page,
            "standalone_page": standalone_page,
        },
    )


@requires_flag(CAMPAIGNS)
@login_required
def battle_report(request, pk, battle_pk, gang_pk):
    """Start a campaign battle's report on POST; a GET only redirects."""
    from n26.core.post_battle import start_report

    campaign = _any_campaign_or_404(request, pk)
    battle = battle_or_404(campaign, battle_pk)
    gang = _any_gang_or_404(request, gang_pk)
    if not battle.gangs.filter(pk=gang.pk).exists():
        raise Http404("No such participant")
    found = PostBattleReport.objects.filter(battle=battle, gang=gang).first()
    candidate = found or PostBattleReport(gang=gang, battle=battle)
    _editable_or_404(candidate, request.user)
    if found:
        return _report_destination(found)
    if request.method != "POST":
        return redirect("n26-battle", pk=campaign.pk, battle_pk=battle.pk)
    try:
        report = start_report(
            gang,
            actor=request.user,
            battle=battle,
            request_key=request.POST.get("request_key", ""),
            date=battle.date,
            reference=battle.title,
            payload=_initial_payload(gang, battle),
        )
    except Refusal as exc:
        messages.error(request, str(exc))
        return redirect("n26-battle", pk=campaign.pk, battle_pk=battle.pk)
    return _report_destination(report)


@requires_flag(CAMPAIGNS)
@login_required
def post_battle_editor(request, pk):
    from n26.core.post_battle import (
        apply_report,
        normalise,
        preview_report,
        save_draft,
        xp_eligible_models,
    )

    report = _report_or_404(pk)
    _editable_or_404(report, request.user)
    if report.state == PostBattleReport.State.APPLIED:
        return _report_destination(report, request)
    payload = normalise(report.draft)
    errors = []
    show_errors = False
    status = 200
    posted = request.method == "POST"
    version = ReportVersionForm(request.POST if posted else None)
    refresh = None
    mission = False
    if posted:
        payload = posted_payload(request.POST)
        intent = request.POST.get("intent", "save")
        if is_htmx(request):
            refresh = refreshed_model(payload, intent)
            mission = refreshes_mission(intent)
        if version.is_valid():
            version_data = version.cleaned_data
            prior = PostBattleRevision.objects.filter(
                report=report, submission_key=version_data["submission_key"]
            ).first()
            if prior and intent == "apply":
                return redirect(
                    "n26-post-battle-revision", pk=report.pk, sequence=prior.sequence
                )
            try:
                payload = change_draft(
                    payload,
                    intent,
                    xp_eligible=xp_eligible_models(
                        report, actor=request.user, payload=payload
                    )
                    if intent.startswith("xp-step:")
                    else frozenset(),
                )
                report = save_draft(
                    report,
                    actor=request.user,
                    generation=version_data["generation"],
                    revision=version_data["revision"],
                    payload=payload,
                )
                if intent == "apply":
                    applied = apply_report(
                        report,
                        actor=request.user,
                        generation=report.generation,
                        revision=report.draft_revision,
                        submission_key=version_data["submission_key"],
                        review=version_data["review"],
                    )
                    messages.success(request, "Post-battle results applied.")
                    return redirect(
                        "n26-post-battle-revision",
                        pk=report.pk,
                        sequence=applied.sequence,
                    )
                if intent == "save":
                    messages.success(request, "Draft saved. The gang has not changed.")
                    return redirect("n26-post-battle-editor", pk=report.pk)
                # An in-place update keeps the errors the page is showing,
                # so a fixed one disappears and the rest stay put.
                show_errors = intent == "check" or bool(
                    (refresh or mission) and request.POST.get("showing_errors")
                )
            except (Refusal, ValidationError) as exc:
                errors = (
                    exc.messages if isinstance(exc, ValidationError) else [str(exc)]
                )
                show_errors = True
                status = 409
        else:
            errors = [
                "This form's version is missing or invalid. Reload the saved draft before continuing."
            ]
            show_errors = True
            status = 400
        if intent == "autosave" and errors:
            return JsonResponse({"error": " ".join(errors)}, status=status)
        if (refresh or mission) and errors:
            # htmx leaves the page as it is on an error, so every entry
            # stays; the page script shows this text by the save status.
            return HttpResponse(
                " ".join(errors), status=status, content_type="text/plain"
            )
    plan = preview_report(report, actor=request.user, payload=payload)
    payload, changed = keep_recorded_xp(payload, plan)
    if changed:
        plan = preview_report(report, actor=request.user, payload=payload)
    if show_errors:
        errors = list(dict.fromkeys([*errors, *plan.errors]))
    # A refused stale save keeps the submitted generation/revision. Replacing
    # it with the latest would let a second click overwrite somebody's work.
    stale = bool(errors) and status == 409 and report.draft != payload
    values = {
        "generation": request.POST.get("generation") if stale else report.generation,
        "revision": request.POST.get("revision") if stale else report.draft_revision,
        "submission_key": request.POST.get("submission_key", str(uuid4())),
        "review": plan.review,
    }
    version = ReportVersionForm(initial=values)
    models = editor_models(plan, payload, refresh_url=request.path)
    stake = battle_stake(report.battle, request.user)
    territory = None
    if stake:
        if report.battle.stake_transfer_mark:
            source = stake_came_from(report.battle)
            outcome = (
                f"Moved from {source.name} to {stake.awarded_to}."
                if source
                else f"Moved to {stake.awarded_to}."
            )
        elif report.battle.result == report.battle.Result.NOT_RECORDED:
            outcome = "Outcome not recorded."
        else:
            outcome = stake.outcome
        territory = {
            "name": stake.name,
            "heading": stake.label,
            "outcome": outcome,
            "currentHolder": stake.held_by,
            "note": (
                "The campaign’s arbitrator records this outcome on Edit battle."
                if report.battle.result == report.battle.Result.NOT_RECORDED
                else "Already applied."
            ),
        }
    preview = preview_display(plan, models)
    if posted and intent == "autosave":
        return JsonResponse(
            {
                "revision": report.draft_revision,
                "generation": str(report.generation),
                "review": plan.review,
                "saved": timezone.localtime(report.modified).strftime("%H:%M:%S"),
                "preview": preview,
            }
        )
    context = {
        "report": report,
        "gang": report.gang,
        "battle": report.battle,
        "payload": payload,
        "plan": plan,
        "models": models,
        "mission": mission_results(
            plan, payload, refresh_url=request.path, show_errors=show_errors
        ),
        "territory": territory,
        "preview": preview,
        "toolbar_props": toolbar_display(models),
        "xp_toolbar": xp_toolbar(models),
        "version_form": version,
        "errors": errors,
        "show_errors": show_errors,
        "stale": stale,
    }
    if mission:
        return render(
            request,
            "n26/includes/post_battle_refresh.html",
            context | {"section": "n26/includes/post_battle_mission.html"},
        )
    if refresh:
        refreshed = next((model for model in models if model.id == refresh), None)
        if refreshed is None:
            # The model has left the roster since the page was drawn:
            # there is no module to swap, so draw the page again.
            return redirect_page(request, "n26-post-battle-editor", pk=report.pk)
        return render(
            request,
            "n26/includes/post_battle_refresh.html",
            context
            | {"model": refreshed, "section": "n26/includes/post_battle_model.html"},
        )
    return render(request, "n26/post_battle.html", context, status=status)


@requires_flag(CAMPAIGNS)
@login_required
def post_battle_receipt(request, pk, sequence=None):
    from n26.core.post_battle import can_edit_report

    report = _report_or_404(pk)
    _any_gang_or_404(request, report.gang_id)
    if report.battle_id:
        _any_campaign_or_404(request, report.battle.campaign_id)
    if not report.latest_sequence:
        _editable_or_404(report, request.user)
        return _report_destination(report)
    revision = get_object_or_404(
        report.revisions.select_related("actor"),
        sequence=sequence or report.latest_sequence,
    )
    return render(
        request,
        "n26/post_battle_receipt.html",
        {
            "report": report,
            "gang": report.gang,
            "battle": report.battle,
            "revision": revision,
            "receipt": revision.receipt,
            "receipt_models": receipt_models(revision.receipt),
            "mission": receipt_mission(revision.receipt, revision),
            "stake": battle_stake(report.battle, request.user),
            "revisions": report.revisions.only("sequence", "created"),
            "may_edit": can_edit_report(report, request.user),
        },
    )


@requires_flag(CAMPAIGNS)
@login_required
@require_POST
def correct_post_battle(request, pk):
    from n26.core.post_battle import start_correction

    report = _report_or_404(pk)
    _editable_or_404(report, request.user)
    try:
        report = start_correction(report, actor=request.user)
    except Refusal as exc:
        messages.error(request, str(exc))
        return redirect("n26-post-battle-receipt", pk=report.pk)
    return redirect("n26-post-battle-editor", pk=report.pk)
