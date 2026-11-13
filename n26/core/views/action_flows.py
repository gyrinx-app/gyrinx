"""Native and JSON adapters for the complete model action workflow."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from n26.core.action_display import page_data
from n26.core.action_stages import (
    StageNavigation,
    _review_payments,
    _review_token,
    _steps,
    _submitted_review,
    flow_url,
    flow_url_for,
    link_action_panels,
    split_action_panels,
)
from n26.core.action_workflow import ActionTarget, change, read, target_from

__all__ = [
    "action_start",
    "action_by_hand",
    "action_flow",
    "action_command",
    "action_display",
    "flow_url",
    "flow_url_for",
    "link_action_panels",
    "split_action_panels",
    "_steps",
    "_review_token",
    "_submitted_review",
    "_review_payments",
]


def _target(kind, key, request, step=""):
    return ActionTarget(
        kind,
        str(key),
        step,
        request.GET.get("allowance"),
        request.GET.get("pick"),
    )


def _notices(request, notices):
    for notice in notices:
        getattr(messages, notice["tone"])(request, notice["text"])


def _native(request, pk, target):
    result = (
        change(request.user, pk, target, request.POST)
        if request.method == "POST"
        else None
    )
    if result and result.saved:
        _notices(request, result.notices)
        return redirect(result.next_url)
    if result and result.errors and target.step in {"cancel", "reopen"}:
        from django.urls import reverse

        for texts in result.errors.values():
            for text in texts:
                messages.error(request, text)
        return redirect(reverse("n26-edit-fighter", args=[pk]))
    page = (
        result.page
        if result and result.page
        else read(
            request.user,
            pk,
            target,
            recover=request.GET.get("recover") == "1",
            gang_id=request.GET.get("gang_id", ""),
        )
    )
    if isinstance(page, StageNavigation):
        _notices(request, page.notices)
        if result and result.errors:
            for texts in result.errors.values():
                for text in texts:
                    messages.error(request, text)
        return redirect(page.href)
    if result and result.errors and page.context.get("form") is not None:
        from copy import copy

        form = copy(page.context["form"])
        form.data = request.POST
        form.is_bound = True
        form._errors = None
        form.full_clean()
        for name, texts in result.errors.items():
            for text in texts:
                field = None if name == "__all__" or name not in form.fields else name
                if text not in form.errors.get(name, []):
                    form.add_error(field, text)
        page.context["form"] = form
    props = page_data(
        request,
        page,
        target,
        errors=result.errors if result else None,
        conflict=result.code in {"revision_conflict", "unavailable"}
        if result
        else False,
    )
    return render(
        request, "n26/action_flow.html", {**page.context, "action_props": props}
    )


@never_cache
@login_required
def action_start(request, pk, action_id):
    return _native(request, pk, _target("start", action_id, request))


@never_cache
@login_required
def action_by_hand(request, pk, action_id):
    return _native(request, pk, _target("by-hand", action_id, request))


@never_cache
@login_required
def action_flow(request, pk, record_id, step):
    return _native(request, pk, _target("flow", record_id, request, step))


@never_cache
@require_POST
def action_command(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Sign in again before retrying this save."}, status=401
        )
    result = change(request.user, pk, target_from(request.POST), request.POST)
    if not result.saved:
        return JsonResponse(
            {
                "errors": result.errors,
                "conflict": result.conflict,
                "code": result.code,
                "terminal": result.terminal,
                "reviewUrl": result.review_url,
            },
            status=409 if result.conflict else 422,
        )
    if not result.replayed:
        _notices(request, result.notices)
    return JsonResponse(
        {
            "saved": True,
            "replayed": result.replayed,
            "nextUrl": result.next_url,
            "reviewUrl": result.review_url,
            "facts": result.facts,
            "notices": result.notices,
        }
    )


@never_cache
@require_GET
def action_display(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Sign in again to continue this flow."}, status=401
        )
    target = target_from(request.GET)
    page = read(
        request.user,
        pk,
        target,
        recover=request.GET.get("recover") == "1",
        gang_id=request.GET.get("gang_id", ""),
    )
    if isinstance(page, StageNavigation):
        _notices(request, page.notices)
        return JsonResponse({"nextUrl": page.href})
    # Native form destinations stay canonical; a display URL is never a form target.
    from django.urls import reverse

    here = (
        flow_url_for(page.context["miniature"], target.key, target.step)
        if target.kind == "flow"
        else reverse(
            "n26-action-start" if target.kind == "start" else "n26-action-by-hand",
            args=[pk, target.key],
        )
    )
    props = page_data(request, page, target)
    from urllib.parse import urlencode

    props["action"] = here + ("?" + urlencode(target.query) if target.query else "")
    props["recoveryHref"] = (
        here
        + "?"
        + urlencode(
            {**target.query, "recover": "1", "gang_id": str(page.context["gang"].pk)}
        )
    )
    props["signInHref"] = (
        reverse("account_login") + "?" + urlencode({"next": props["recoveryHref"]})
    )
    return JsonResponse({"props": props})
