"""HTML and JSON adapters for Manage credits."""

from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from n26.core import credits
from n26.core.forms import CreditsForm
from n26.core.views.permissions import _any_gang_or_404, _safe_redirect


def _prepare(request, pk):
    gang = _any_gang_or_404(request, pk)
    default = credits.destination(gang, request.user)
    if default is None:
        raise Http404("No such gang")
    back = _safe_redirect(
        request, request.POST.get("back") or request.GET.get("back"), default
    ).url
    return gang, back


def _feedback(request, gang, result):
    if result.applied:
        from n26.analytics import EventVerb, N26Noun, record

        record(request, N26Noun.GANG, EventVerb.UPDATE, gang, credits=result.amount)
    tag = f"credits-{result.form.cleaned_data['request_key']}"
    storage = messages.get_messages(request)
    already_queued = any(
        tag in (message.extra_tags or "").split() for message in storage
    )
    storage.used = False
    if not already_queued:
        message = (
            result.message(gang)
            if result.applied
            else "This credit adjustment was already saved."
        )
        messages.success(request, message, extra_tags=tag)


def _props(request, gang, form, back):
    return {
        **credits.display(gang, request.user, form),
        "back": back,
        "action": reverse("n26-gang-credits", args=[gang.pk]),
        "commandHref": reverse("n26-gang-credits-command", args=[gang.pk]),
        "csrfToken": get_token(request),
        "recoveryKey": f"credits:{request.user.pk}:{gang.pk}",
    }


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def gang_credits(request, pk):
    gang, back = _prepare(request, pk)
    if request.method == "POST":
        result = credits.change(gang, request.user, request.POST)
        form = result.form
        if result.saved:
            _feedback(request, gang, result)
            return redirect(back)
    else:
        form = CreditsForm(initial={"request_key": uuid4()})
    return render(
        request,
        "n26/gang_credits.html",
        {
            "gang": gang,
            "form": form,
            "back": back,
            "credits_props": _props(request, gang, form, back),
        },
    )


@require_POST
def gang_credits_command(request, pk):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in again to save this change."}, status=401)
    gang, back = _prepare(request, pk)
    result = credits.change(gang, request.user, request.POST)
    if result.saved:
        _feedback(request, gang, result)
        return JsonResponse({"nextUrl": back})
    return JsonResponse(
        {"errors": dict(result.form.errors), "balance": gang.credits},
        status=409 if result.conflict else 422,
    )
