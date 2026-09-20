"""Saved post-battle forms, per-gang application, and immutable receipts."""

from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

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
    posted_payload,
)
from n26.core.views.battles import battle_or_404
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
                crew.members.filter(role="starting").values_list(
                    "miniature_id", flat=True
                )
            )
    return {
        "schema": 1,
        "credits": "",
        "reason": "",
        "participation_confirmed": False,
        "models": [
            {
                "id": str(model.pk),
                "participated": model.pk in starting,
                "xp": "",
                "status": "",
                "equipment": "keep",
                "effects": [],
            }
            for model in Miniature.objects.filter(
                membership__gang=gang, membership__archived=False
            )
        ],
    }


def _report_destination(report):
    name = (
        "n26-post-battle-receipt"
        if report.state == PostBattleReport.State.APPLIED
        else "n26-post-battle-editor"
    )
    return redirect(name, pk=report.pk)


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
    return render(
        request,
        "n26/post_battle_list.html",
        {
            "gang": gang,
            "form": form,
            "reports": gang.post_battle_reports.select_related("battle", "last_editor")[
                :50
            ],
            "battles": Battle.objects.filter(gangs=gang, campaign__archived=False)
            .select_related("campaign")
            .order_by("-date", "-pk")[:30],
        },
    )


@requires_flag(CAMPAIGNS)
@login_required
def battle_report(request, pk, battle_pk, gang_pk):
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
    form = StartReportForm(
        request.POST if request.method == "POST" else None,
        initial={
            "request_key": uuid4(),
            "date": battle.date,
            "reference": battle.title,
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            report = start_report(
                gang,
                actor=request.user,
                battle=battle,
                payload=_initial_payload(gang, battle),
                **form.cleaned_data,
            )
        except Refusal as exc:
            form.add_error(None, str(exc))
        else:
            return _report_destination(report)
    return render(
        request,
        "n26/start_post_battle.html",
        {"gang": gang, "battle": battle, "campaign": campaign, "form": form},
    )


@requires_flag(CAMPAIGNS)
@login_required
def post_battle_editor(request, pk):
    from n26.core.post_battle import apply_report, preview_report, save_draft

    report = _report_or_404(pk)
    _editable_or_404(report, request.user)
    if report.state == PostBattleReport.State.APPLIED:
        return _report_destination(report)
    payload = report.draft
    errors = []
    show_errors = False
    status = 200
    posted = request.method == "POST"
    version = ReportVersionForm(request.POST if posted else None)
    if posted:
        payload = posted_payload(request.POST)
        intent = request.POST.get("intent", "save")
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
                payload = change_draft(payload, intent, previous=report.draft)
                report = save_draft(
                    report,
                    actor=request.user,
                    generation=version_data["generation"],
                    revision=version_data["revision"],
                    payload=payload,
                )
                if intent == "autosave":
                    return JsonResponse(
                        {
                            "revision": report.draft_revision,
                            "generation": str(report.generation),
                            "saved": timezone.localtime(report.modified).strftime(
                                "%H:%M:%S"
                            ),
                        }
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
                show_errors = intent == "check"
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
        if intent == "autosave":
            return JsonResponse({"error": " ".join(errors)}, status=status)
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
    return render(
        request,
        "n26/post_battle.html",
        {
            "report": report,
            "gang": report.gang,
            "battle": report.battle,
            "payload": payload,
            "plan": plan,
            "models": editor_models(plan, payload),
            "version_form": version,
            "errors": errors,
            "show_errors": show_errors,
            "stale": stale,
            "participant_count": sum(
                bool(model.get("participated")) for model in payload.get("models", [])
            ),
        },
        status=status,
    )


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
