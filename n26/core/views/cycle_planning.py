"""Flagged schedule reading and arbitrator-owned planning workflows."""

from dataclasses import asdict
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from n26 import flags
from n26.core import cycle_workflow as workflow
from n26.core.cycle_display import build, schedule_url
from n26.core.models import CampaignCycle, CampaignCycleCommand
from n26.core.views.permissions import _any_campaign_or_404, _own_campaign_or_404


def _respond(request, campaign, display):
    notices = [
        {
            "message": str(message),
            "tone": message.level_tag
            if message.level_tag in {"success", "warning", "error"}
            else "info",
        }
        for message in messages.get_messages(request)
    ]
    if request.method == "GET" and "application/json" in request.headers.get(
        "Accept", ""
    ):
        return JsonResponse(
            {
                "schedule": display,
                "notices": notices,
            }
        )
    return render(
        request,
        "n26/campaign_cycles.html",
        {"campaign": campaign, "schedule_props": {**display, "notices": notices}},
    )


def _display(request, campaign, *, focus=None):
    try:
        preview = max(1, min(int(request.GET.get("preview", 12)), 100))
    except ValueError:
        preview = 12
    return asdict(
        build(
            campaign,
            request.user,
            page=request.GET.get("page"),
            preview=preview,
            focus=focus,
        )
    )


def _require_action(request, campaign, action):
    if action in workflow.FIELDS:
        return
    if action not in workflow.RETIRED_FIELDS:
        raise Http404("No such schedule action")
    receipts = CampaignCycleCommand.objects.filter(
        campaign=campaign,
        actor=request.user,
        kind="save_template" if action == "save-template" else "apply_template",
    )
    if request.method == "POST":
        try:
            key = UUID(request.POST.get("request_key", ""))
        except ValueError, AttributeError, TypeError:
            raise Http404("No earlier template save") from None
        receipts = receipts.filter(request_key=key)
    if not receipts.exists():
        raise Http404("No earlier template save")


@flags.requires_flag(flags.CYCLE_TRACKING)
@login_required
@never_cache
@require_http_methods(["GET"])
def cycle_schedule(request, pk, cycle_pk=None):
    """Signed-in feature readers may read; only the arbitrator receives actions."""
    campaign = _any_campaign_or_404(request, pk)
    focus = None
    if cycle_pk is not None:
        try:
            focus = get_object_or_404(CampaignCycle, campaign=campaign, pk=cycle_pk)
        except ValidationError:
            raise Http404("No such campaign cycle") from None
    return _respond(
        request, campaign, {**_display(request, campaign, focus=focus), "editor": None}
    )


def _feedback(request, campaign, action, submitted):
    if not submitted.result.replayed:
        from n26.analytics import EventVerb, N26Noun, record

        record(
            request, N26Noun.CAMPAIGN, EventVerb.UPDATE, campaign, cycle_command=action
        )
    tag = f"cycle-command-{submitted.form.cleaned_data['request_key']}"
    storage = messages.get_messages(request)
    present = any(tag in (message.extra_tags or "").split() for message in storage)
    storage.used = False
    if not present:
        messages.success(request, "Campaign schedule saved.", extra_tags=tag)


@flags.requires_flag(flags.CYCLE_TRACKING)
@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def cycle_editor(request, pk, action):
    campaign = _own_campaign_or_404(request, pk)
    _require_action(request, campaign, action)
    submitted = None
    if request.method == "POST":
        submitted = workflow.perform(
            campaign, request.user, action, request.POST, request.GET
        )
        if submitted.result:
            _feedback(request, campaign, action, submitted)
            return redirect(workflow.next_url(campaign, action, submitted))
    try:
        prepared = workflow.prepare(campaign, action, request.GET)
    except Http404:
        prepared = workflow.recovery_editor(campaign, action, request.GET)
    form = (
        submitted.form
        if submitted
        else workflow.CycleEditorForm(action, initial=prepared.initial)
    )
    editor = workflow.editor_props(
        campaign,
        request.user,
        prepared,
        form,
        csrf_token=get_token(request),
        conflict=bool(submitted and submitted.conflict),
        current=submitted.current if submitted else None,
    )
    if action == "setup":
        stage = request.GET.get("step", "1")
        editor["context"]["setupStage"] = int(stage) if stage in {"1", "2", "3"} else 1
    return _respond(
        request, campaign, {**_display(request, campaign), "editor": editor}
    )


@never_cache
@require_POST
def cycle_command(request, pk, action):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in again to save this change."}, status=401)
    if not flags.enabled(flags.CYCLE_TRACKING, request.user):
        return JsonResponse(
            {"error": "Cycle tracking is not available to this account."}, status=404
        )
    campaign = _own_campaign_or_404(request, pk, with_owner_badge=False)
    _require_action(request, campaign, action)
    submitted = workflow.perform(
        campaign, request.user, action, request.POST, request.GET
    )
    if submitted.result:
        _feedback(request, campaign, action, submitted)
        return JsonResponse({"nextUrl": workflow.next_url(campaign, action, submitted)})
    errors = {name: list(items) for name, items in submitted.form.errors.items()}
    if submitted.conflict:
        return JsonResponse(
            {
                "code": "revision_conflict",
                "errors": errors,
                "current": submitted.current,
                "reviewUrl": schedule_url(campaign),
            },
            status=409,
        )
    if submitted.key_conflict:
        return JsonResponse(
            {"code": "request_key_conflict", "errors": errors}, status=409
        )
    return JsonResponse({"errors": errors}, status=422)
