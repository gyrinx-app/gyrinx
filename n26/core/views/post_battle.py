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
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from n26.core.campaigns import battle_stake
from n26.core.models import (
    Battle,
    BattleCrew,
    Miniature,
    PostBattleReport,
)
from n26.core.operations import Refusal
from n26.core.post_battle_forms import (
    StartReportForm,
    editor_models,
    preview_display,
    receipt_mission,
    receipt_models,
)
from n26.core.views.battles import battle_or_404
from n26.core.views.htmx import is_htmx, redirect_page
from n26.core.views.permissions import (
    _any_campaign_or_404,
    _any_gang_or_404,
    _own_gang_or_404,
)


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
            form.add_error(None, exc.public_message)
        else:
            return _report_destination(report)

    reports = gang.post_battle_reports.defer("draft")
    battles = (
        Battle.objects.filter(archived=False)
        .annotate(
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
        messages.error(request, exc.public_message)
        return redirect("n26-battle", pk=campaign.pk, battle_pk=battle.pk)
    return _report_destination(report)


def _editor_props(request, report, payload, plan, *, errors=(), show_errors=False):
    from django.middleware.csrf import get_token

    from n26.core.post_battle_display import editor_display

    return {
        **editor_display(
            report, request.user, payload, plan, errors=errors, show_errors=show_errors
        ),
        "action": reverse("n26-post-battle-editor", args=[report.pk]),
        "commandHref": reverse("n26-post-battle-command", args=[report.pk]),
        "csrfToken": get_token(request),
        "recoveryKey": f"post-battle:{request.user.pk}:{report.pk}",
        "submissionKey": request.POST.get("submission_key", str(uuid4())),
        "messages": [
            {"text": str(message), "level": message.level}
            for message in messages.get_messages(request)
        ],
    }


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def post_battle_editor(request, pk):
    from n26.core.post_battle_workflow import command, prepared

    report = _report_or_404(pk)
    _editable_or_404(report, request.user)
    if report.state == PostBattleReport.State.APPLIED:
        return _report_destination(report, request)
    errors = []
    status = 200
    show_errors = request.GET.get("show_errors") == "1"
    payload = report.draft
    result = None
    if request.method == "POST":
        result = command(report, request.user, request.POST)
        _editable_or_404(result.report, request.user)
        report, payload, errors, status = (
            result.report,
            result.payload,
            result.errors,
            result.status,
        )
        if result.sequence:
            if not result.replayed:
                messages.success(request, "Post-battle results applied.")
            return redirect_page(
                request,
                "n26-post-battle-revision",
                pk=report.pk,
                sequence=result.sequence,
            )
        if result.acknowledged and request.POST.get("intent", "save") == "save":
            if not result.replayed:
                messages.success(request, "Draft saved. The gang has not changed.")
            return redirect_page(request, "n26-post-battle-editor", pk=report.pk)
        show_errors = (
            bool(errors)
            or request.POST.get("intent") == "check"
            or bool(request.POST.get("showing_errors"))
        )
    payload, plan = prepared(report, request.user, payload)
    if request.method == "POST" and request.POST.get("intent") == "autosave":
        return JsonResponse(
            {"error": " ".join(errors)}
            if errors
            else {
                "revision": report.draft_revision,
                "generation": str(report.generation),
                "review": plan.review,
                "saved": timezone.localtime(report.modified).strftime("%H:%M:%S"),
                "preview": preview_display(plan, editor_models(plan, payload)),
                "corrections": {
                    f"model-{model['id']}-xp": str(model.get("xp") or "")
                    for model in payload["models"]
                    if str(model.get("xp") or "")
                    != request.POST.get(f"model-{model['id']}-xp", "")
                },
            },
            status=status,
        )
    if is_htmx(request):
        if errors:
            return HttpResponse(
                " ".join(errors), status=status, content_type="text/plain"
            )
        response = redirect_page(request, "n26-post-battle-editor", pk=report.pk)
        if show_errors:
            response["HX-Redirect"] += "?show_errors=1"
        return response
    props = _editor_props(
        request, report, payload, plan, errors=errors, show_errors=show_errors
    )
    if result is not None and (result.conflict or result.newer):
        from n26.core.post_battle_display import editor_display

        current_payload, current_plan = prepared(report, request.user, report.draft)
        props["currentDisplay"] = editor_display(
            report, request.user, current_payload, current_plan
        )
        props["initialConflict"] = True
        props["generation"] = request.POST.get("generation", props["generation"])
        props["revision"] = int(request.POST.get("revision", props["revision"]))
    return render(
        request,
        "n26/post_battle.html",
        {
            "report": report,
            "gang": report.gang,
            "battle": report.battle,
            "editor_props": props,
        },
        status=400 if status == 422 else status,
    )


@never_cache
@require_POST
def post_battle_command(request, pk):
    from n26.core.post_battle_display import editor_display
    from n26.core.post_battle_workflow import command, prepared

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in again to save this change."}, status=401)
    report = _report_or_404(pk)
    _editable_or_404(report, request.user)
    result = command(report, request.user, request.POST)
    _editable_or_404(result.report, request.user)
    if result.sequence:
        return JsonResponse(
            {
                "acknowledged": result.acknowledged,
                "nextUrl": reverse(
                    "n26-post-battle-revision", args=[report.pk, result.sequence]
                ),
            }
        )
    payload, plan = prepared(result.report, request.user, result.payload)
    display = editor_display(
        result.report,
        request.user,
        payload,
        plan,
        errors=result.errors,
        show_errors=bool(request.POST.get("showing_errors"))
        or request.POST.get("intent") in {"check", "apply"},
    )
    response = {
        "display": display,
        "acknowledged": result.acknowledged,
        "errors": result.errors,
        "conflict": result.conflict,
        "newer": result.newer,
    }
    if result.newer or result.conflict:
        current_payload, current_plan = prepared(
            result.report, request.user, result.report.draft
        )
        response["currentDisplay"] = editor_display(
            result.report, request.user, current_payload, current_plan
        )
    return JsonResponse(response, status=result.status)


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


@login_required
@require_POST
def correct_post_battle(request, pk):
    from n26.core.post_battle import start_correction

    report = _report_or_404(pk)
    _editable_or_404(report, request.user)
    try:
        report = start_correction(report, actor=request.user)
    except Refusal as exc:
        messages.error(request, exc.public_message)
        return redirect("n26-post-battle-receipt", pk=report.pk)
    return redirect("n26-post-battle-editor", pk=report.pk)
