"""Battle form workflows share native and JSON validation and commands."""

import json

from django.contrib import messages
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from n26 import flags
from n26.core import battle_workflow as workflow
from n26.core.models import Gang
from n26.core.operations import Refusal
from n26.core.views.permissions import _own_campaign_or_404, _recording_campaign_or_404
from n26.library.scenario_tables import request_catalogue


def resources(request, pk, battle_pk=None):
    from django.db.models import Q

    from n26.core.views.battles import battle_or_404
    from n26.core.views.campaigns import _playing

    campaign = (_own_campaign_or_404 if battle_pk else _recording_campaign_or_404)(
        request, pk, with_owner_badge=request.method == "GET"
    )
    battle = battle_or_404(campaign, battle_pk) if battle_pk else None
    playing = (
        Gang.objects.filter(
            Q(
                campaign_memberships__campaign=campaign,
                campaign_memberships__left__isnull=True,
            )
            | Q(battles=battle)
        )
        .distinct()
        .order_by("name")
        if battle
        else _playing(campaign)
    )
    return campaign, battle, playing


def _submit(request, campaign, battle, playing):
    try:
        return workflow.perform(
            campaign,
            request.user,
            playing,
            request.POST,
            battle=battle,
            catalogue=request_catalogue(request) if battle is None else None,
        )
    except Refusal as exc:
        form = workflow.form_for(
            campaign, request.user, playing, data=request.POST, battle=battle
        )
        form.is_valid()
        form.add_error(None, exc.public_message)
        return workflow.Submission(form)


def _feedback(request, submitted):
    tag = f"battle-command-{request.POST.get('request_key', '')}"
    storage = messages.get_messages(request)
    exists = any(tag in (message.extra_tags or "").split() for message in storage)
    storage.used = False
    if not exists:
        messages.success(request, "Battle saved.", extra_tags=tag)


@never_cache
@require_http_methods(["GET", "POST"])
def editor(request, pk, battle_pk=None):
    campaign, battle, playing = resources(request, pk, battle_pk)
    submitted = (
        _submit(request, campaign, battle, playing)
        if request.method == "POST"
        else None
    )
    if submitted and submitted.battle:
        _feedback(request, submitted)
        return redirect(workflow.next_url(campaign, submitted.battle))
    form = (
        submitted.form
        if submitted
        else workflow.form_for(
            campaign,
            request.user,
            playing,
            battle=battle,
            catalogue=request_catalogue(request) if battle is None else None,
        )
    )
    if not submitted and battle is None:
        form.initial.update(
            {key: request.GET[key] for key in form.scenario_keys if key in request.GET}
        )
    props = workflow.editor_props(
        campaign,
        request.user,
        form,
        battle=battle,
        catalogue=request_catalogue(request) if battle is None else None,
        csrf_token=get_token(request),
        conflict=bool(submitted and submitted.conflict),
        current=submitted.current if submitted else None,
    )
    return render(
        request,
        "n26/add_battle.html",
        {"campaign": campaign, "battle": battle, "form": form, "battle_editor": props},
    )


@never_cache
@require_POST
def command(request, pk, battle_pk=None):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in again to save this battle."}, status=401)
    campaign, battle, playing = resources(request, pk, battle_pk)
    if not request.POST.get("request_key"):
        return JsonResponse(
            {"errors": {"request_key": ["Reload the battle form before saving."]}},
            status=422,
        )
    submitted = _submit(request, campaign, battle, playing)
    if submitted.battle:
        _feedback(request, submitted)
        return JsonResponse({"nextUrl": workflow.next_url(campaign, submitted.battle)})
    errors = {name: list(items) for name, items in submitted.form.errors.items()}
    if submitted.conflict:
        from django.urls import reverse

        return JsonResponse(
            {
                "code": "revision_conflict",
                "errors": errors,
                "current": submitted.current,
                "reviewUrl": reverse(
                    "n26-campaign-edit-battle", args=[campaign.pk, battle.pk]
                ),
            },
            status=409,
        )
    return JsonResponse({"errors": errors}, status=422)


@flags.requires_flag(flags.CYCLE_TRACKING)
@require_GET
def cycle_options(request, pk):
    from n26.core.cycle_selection import options

    campaign = _recording_campaign_or_404(request, pk, with_owner_badge=False)
    try:
        selected = json.loads(request.GET.get("selected", "null"))
    except ValueError:
        selected = None
    return JsonResponse(
        options(campaign, page=request.GET.get("page"), selected=selected)
    )
