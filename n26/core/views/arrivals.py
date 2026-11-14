"""Owner-only arrival choices with shared native and JSON settlement."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from gyrinx.http import safe_redirect
from n26.core import choice_display, choice_workflow
from n26.core.arrivals import MAX_ASKS
from n26.core.views.choose import _choice_feedback
from n26.core.views.permissions import _own_gang_or_404, own_address


def _asks(query):
    seen = []
    for key in query.getlist("ask"):
        if key and key not in seen:
            seen.append(key)
    return seen[:MAX_ASKS]


def _back(request, gang):
    return own_address(
        request,
        request.POST.get("next", request.GET.get("next", ""))
        if request.method == "POST"
        else request.GET.get("next", ""),
    ) or reverse("n26-gang", args=[gang.pk])


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def gang_next(request, pk):
    """Show authored follow-up questions to the current gang owner."""
    gang = _own_gang_or_404(request, pk)
    back = _back(request, gang)
    keys = _asks(request.GET)
    result = None
    if request.method == "POST":
        result = choice_workflow.change_arrivals(
            gang, request.user, keys, request.POST, back=back
        )
        if result.saved:
            _choice_feedback(request, gang, result)
            return redirect(result.next_url)
        if not result.terminal and "request_key" not in result.form.errors:
            from django.contrib import messages

            for errors in result.form.errors.values():
                for message in errors:
                    messages.error(request, message)
            return safe_redirect(
                request, request.get_full_path(), reverse("n26-next", args=[gang.pk])
            )
    read = choice_workflow.prepare_arrivals(gang, request.user, keys, back)
    if not read.screen.blocks and not result and request.GET.get("recover") != "1":
        return redirect(back)
    form = result.form if result else choice_workflow.arrival_initial(keys, back)
    props = choice_display.arrivals(
        request,
        gang,
        read,
        form,
        keys=keys,
        back=back,
        terminal=bool(result and result.terminal),
    )
    return render(
        request,
        "n26/next.html",
        {"gang": gang, "screen": read.screen, "here": read.here, "choice_props": props},
        status=409 if result and result.terminal else 422 if result else 200,
    )


@require_POST
@never_cache
def arrivals_command(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Sign in again to save these choices."}, status=401
        )
    gang = _own_gang_or_404(request, pk)
    result = choice_workflow.change_arrivals(
        gang, request.user, _asks(request.GET), request.POST, back=_back(request, gang)
    )
    if result.saved:
        _choice_feedback(request, gang, result)
        return JsonResponse({"nextUrl": result.next_url})
    if result.terminal:
        return JsonResponse(
            {"code": "choice_unavailable", "errors": dict(result.form.errors)},
            status=409,
        )
    return JsonResponse({"errors": dict(result.form.errors)}, status=422)
