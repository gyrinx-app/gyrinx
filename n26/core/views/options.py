"""HTML and JSON adapters for a model's retained acquisition choices."""

import json
from urllib.parse import urlencode
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from n26.core import options_workflow
from n26.core.views.permissions import (
    _own_gang_or_404,
    _own_miniature_or_404,
    credits_href,
    may_mark_status,
    status_href,
    trade_points_href,
)


def data_selection_label(data):
    return str(data.get("selection_label", ""))[:2000]


def _display(request, miniature, form, groups, *, conflict=None):
    from n26.core.card import build_card, build_modifier_index, carriers
    from n26.core.effects import compute
    from n26.core.hire_display import figures_data
    from n26.core.model_card_display import model_card_props
    from n26.core.navigation import fighter_switcher, model_screen_tabs, switcher_props
    from n26.core.owned import EquipHost
    from n26.core.people import person_link
    from n26.core.render import roster, summarise_roster
    from n26.core.views.edit import link_model_card

    gang = miniature.gang
    here = reverse("n26-fighter-options", args=[miniature.pk])
    edit = reverse("n26-edit-fighter", args=[miniature.pk])
    own = build_card(miniature, with_statlines=True, with_options=True)
    computed = compute(own, build_modifier_index(carriers(own)))
    host = EquipHost.fighter(gang, own, miniature, edit)
    card = link_model_card(
        gang,
        miniature,
        own,
        computed,
        host,
        back=edit,
        dismissal_at=request.get_full_path(),
    )
    status = (
        status_href(gang, miniature, back="edit")
        if may_mark_status(gang, request.user)
        else ""
    )
    summary = summarise_roster(roster(gang))
    badges = {}
    owner = person_link(gang.owner, badges)
    owner["badge"] = badges.get(owner.get("badge"))
    raw_selection = form["selection"].value()
    selection = (
        raw_selection
        if isinstance(raw_selection, str)
        else json.dumps(raw_selection or [])
    )
    props = {
        "name": miniature.name,
        "role": miniature.membership.profile.category.name
        if miniature.membership.profile.category
        else "",
        "owner": owner,
        "gangName": gang.name,
        "gangHref": reverse("n26-gang", args=[gang.pk]),
        "figures": figures_data(
            gang,
            summary,
            trade_points_href=trade_points_href(gang, request.user),
            credits_href=credits_href(gang, request.user),
        ),
        "card": model_card_props(
            card, rename_href=edit + f"?rename={miniature.pk}", status_href=status
        ),
        "tabs": model_screen_tabs(miniature, "options"),
        "switcher": switcher_props(
            fighter_switcher(gang, miniature, route="n26-fighter-options"), hotkey="r"
        ),
        "groups": groups,
        "values": {
            "gang": str(gang.pk),
            "selection": selection,
            "selection_label": ", ".join(
                option["name"]
                for group in groups
                for option in group["options"]
                if option["key"] in (json.loads(selection) if selection else [])
            )
            if not form.is_bound
            else data_selection_label(form.data),
            "snapshot": form["snapshot"].value() or "",
            "request_key": str(form["request_key"].value() or ""),
        },
        "errors": dict(form.errors),
        "conflict": conflict,
        "action": here,
        "recoveryHref": here + "?recover=1",
        "back": edit,
        "commandHref": reverse("n26-fighter-options-command", args=[miniature.pk]),
        "signInHref": reverse("account_login")
        + "?"
        + urlencode({"next": here + "?recover=1"}),
        "csrfToken": get_token(request),
        "recoveryKey": f"model-options:{request.user.pk}:{gang.pk}:{miniature.pk}",
        "messages": [
            {
                "text": str(message),
                "tone": message.level_tag
                if message.level_tag in {"success", "error", "warning"}
                else "info",
            }
            for message in messages.get_messages(request)
        ],
    }
    return {"gang": gang, "miniature": miniature, "card": card, "options_props": props}


def _feedback(request, result):
    if result.saved and not result.replayed:
        from n26.analytics import EventVerb, N26Noun, record

        record(request, N26Noun.MODEL, EventVerb.UPDATE, result.subject, **result.facts)
    tag = f"model-options-{result.form.cleaned_data['request_key']}"
    storage = messages.get_messages(request)
    queued = any(tag in (message.extra_tags or "").split() for message in storage)
    storage.used = False
    if not queued:
        message = (
            result.message.replace("Options saved.", "Options already saved.", 1)
            if result.replayed
            else result.message
        )
        messages.success(request, message, extra_tags=tag)


def _destination(gang, model_key):
    from n26.core.models import Miniature

    live = Miniature.objects.filter(
        pk=model_key, membership__gang=gang, membership__archived=False
    ).exists()
    return (
        reverse("n26-fighter-options", args=[model_key])
        if live
        else reverse("n26-gang", args=[gang.pk])
    )


def _recovery_display(request, pk, result=None):
    from n26.core.model_choice_recovery import target_for
    from n26.core.people import person_link

    target = target_for(pk, request.user, action="options")
    if target is None:
        raise Http404("No such model")
    gang = target.gang
    here = reverse("n26-fighter-options", args=[pk])
    recovery = here + "?recover=1"
    badges = {}
    owner = person_link(gang.owner, badges)
    owner["badge"] = badges.get(owner.get("badge"))
    values = {
        "gang": str(gang.pk),
        "selection": "[]",
        "selection_label": "",
        "snapshot": "",
        "request_key": str(uuid4()),
    }
    if result is not None:
        values.update({name: str(result.form.data.get(name, "")) for name in values})
    props = {
        "recoveryOnly": True,
        "removed": bool(result and result.removed),
        "name": target.name,
        "role": "",
        "gangName": gang.name,
        "gangHref": reverse("n26-gang", args=[gang.pk]),
        "owner": owner,
        "figures": None,
        "card": None,
        "tabs": [],
        "switcher": None,
        "groups": [],
        "values": values,
        "errors": dict(result.form.errors) if result else {},
        "conflict": None,
        "action": recovery,
        "recoveryHref": recovery,
        "back": reverse("n26-gang", args=[gang.pk]),
        "commandHref": reverse("n26-fighter-options-command", args=[pk]),
        "signInHref": reverse("account_login") + "?" + urlencode({"next": recovery}),
        "csrfToken": get_token(request),
        "recoveryKey": f"model-options:{request.user.pk}:{gang.pk}:{pk}",
        "messages": [
            {
                "text": str(message),
                "tone": message.level_tag
                if message.level_tag in {"success", "error", "warning"}
                else "info",
            }
            for message in messages.get_messages(request)
        ],
    }
    return {"gang": gang, "recovery_name": target.name, "options_props": props}


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def fighter_options(request, pk):
    """Only the signed-in gang owner may inspect or replace a model's options."""
    result = None
    if request.method == "POST":
        gang = _own_gang_or_404(request, request.POST.get("gang", ""))
        result = options_workflow.change(gang, request.user, pk, request.POST)
        if result.saved:
            _feedback(request, result)
            return redirect(_destination(gang, pk))
    if result and result.removed:
        return render(
            request,
            "n26/fighter_options.html",
            _recovery_display(request, pk, result),
            status=409,
        )
    try:
        miniature = _own_miniature_or_404(request, pk)
    except Http404:
        if request.GET.get("recover") != "1":
            raise
        return render(
            request,
            "n26/fighter_options.html",
            _recovery_display(request, pk, result),
            status=409 if result else 200,
        )
    form, groups = options_workflow.initial(miniature, request.user)
    if result is not None:
        form = result.form
    context = _display(
        request, miniature, form, groups, conflict=result.current if result else None
    )
    return render(
        request,
        "n26/fighter_options.html",
        context,
        status=409 if result and result.conflict else 422 if result else 200,
    )


@require_POST
@never_cache
def options_command(request, pk):
    """The JSON command shares native validation, locks, writes and replay."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Sign in again to save these options."}, status=401
        )
    gang = _own_gang_or_404(request, request.POST.get("gang", ""))
    result = options_workflow.change(gang, request.user, pk, request.POST)
    if result.saved:
        _feedback(request, result)
        return JsonResponse({"nextUrl": _destination(gang, pk)})
    if result.removed:
        return JsonResponse(
            {"code": "model_removed", "errors": dict(result.form.errors)}, status=409
        )
    return JsonResponse(
        {
            "errors": dict(result.form.errors),
            **(
                {"code": "revision_conflict", "current": result.current}
                if result.conflict
                else {}
            ),
        },
        status=409 if result.conflict else 422,
    )
