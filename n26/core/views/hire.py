"""HTML and JSON adapters for the complete Hire workflow."""

from json import dumps
from urllib.parse import urlencode
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from n26.core import hire_workflow
from n26.core.hire_display import (
    HIRE_SCOPES,
    HireCatalogue,
    catalogue_data,
    confirmation_data,
    figures_data,
    listing_url,
)
from n26.core.hire_workflow import HireSubmissionForm, UnavailableHire
from n26.core.views.permissions import (
    _own_gang_or_404,
    credits_href,
    trade_points_href,
)
from n26.library.staged import sees_staged


def _scope(request):
    """Resolve a supported scope from POST or GET, defaulting to the gang list."""
    named = request.POST.get("list", request.GET.get("list", ""))
    return named if named in HIRE_SCOPES else "gang"


def _section(request):
    """Carry a bounded section identifier through the form and URL.

    The picker ignores unknown names and starts on its first tab.
    """
    named = request.POST.get("section", request.GET.get("section", ""))
    return named[:100]


def _preview(request, pk, profile):
    """Render a privately cached preview for an authorised gang owner.

    Validate profile visibility and selected option sets. An optional entry must
    name this profile; previews do not check whether the gang carries its collection.
    Listing POSTs, dialog GETs and hire POSTs validate named collection offers.
    Repeated option parameters compose the preview.
    Cache for five minutes because previews derive only from library content.
    """
    from django.shortcuts import get_object_or_404

    from n26.core.hire import preview_model_card
    from n26.library.models import CollectionEntry, Profile

    _own_gang_or_404(request, pk)
    # Apply the same archive and staged-content visibility as the hiring list.
    profiles = Profile.objects.unarchived()
    if not sees_staged(request.user):
        profiles = profiles.live()
    try:
        found = get_object_or_404(profiles, pk=profile)
    except ValidationError:
        raise Http404("No such profile") from None

    option = None
    if "selection" in request.GET:
        try:
            keys = hire_workflow.SelectionField(required=False).clean(
                request.GET["selection"]
            )
            option = hire_workflow.resolve_sets(found, keys)
        except ValidationError, UnavailableHire:
            raise Http404("No such option") from None
    named = request.GET.getlist("option")
    if named and "selection" not in request.GET:
        offered_sets = {
            str(offer.default_set.pk): offer.default_set
            for offer in found.options.select_related("default_set")
        }
        try:
            option = [offered_sets[each] for each in named]
        except KeyError:
            # Reject option sets absent from this profile's offer.
            raise Http404("No such option") from None

    entry = None
    offered = request.GET.get("entry")
    if offered:
        try:
            entry = CollectionEntry.objects.filter(pk=offered, profile=found).first()
        except ValidationError:
            entry = None
        if entry is None:
            # Validate the entry-profile pair here. Actual hiring separately checks
            # that the gang carries its collection before accepting the entry price.
            raise Http404("No such offer")

    try:
        card = preview_model_card(
            found, option=option, base=hire_workflow.base_price(entry)
        )
    except ValueError:
        # Reject invalid combinations through the same option resolution used by hiring.
        raise Http404("No such option") from None

    return card


def hire_feedback(request, gang, result):
    """Record one analytics event and keep one unread success for a hire."""
    if result.applied:
        from n26.analytics import EventVerb, N26Noun, record

        record(
            request,
            N26Noun.MODEL,
            EventVerb.CREATE,
            result.miniature,
            gang_id=str(gang.pk),
            profile=result.receipt.profile_name,
            paid=result.receipt.paid,
        )
    tag = f"hire-{result.receipt.request_key}"
    storage = messages.get_messages(request)
    already_queued = any(
        tag in (message.extra_tags or "").split() for message in storage
    )
    storage.used = False
    if not already_queued:
        messages.success(request, result.message, extra_tags=tag)


def _figures(gang, user):
    return figures_data(
        gang,
        HireCatalogue(gang, user, "gang").summary,
        trade_points_href=trade_points_href(gang, user),
        credits_href=credits_href(gang, user),
    )


@login_required
@require_GET
def hire_card(request, pk, profile):
    """Serve existing HTML preview links through the shared preview reader."""
    from django.utils.cache import patch_cache_control

    response = render(
        request, "n26/hire_card.html", {"card": _preview(request, pk, profile)}
    )
    patch_cache_control(response, private=True, max_age=300)
    return response


@require_GET
def hire_preview(request, pk, profile):
    """Return one authorised, lazily requested model preview."""
    from django.utils.cache import patch_cache_control

    from n26.core.model_preview import model_preview_props

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in again to view this model."}, status=401)
    response = JsonResponse(
        {"preview": model_preview_props(_preview(request, pk, profile))}
    )
    patch_cache_control(response, private=True, max_age=300)
    return response


def _props(request, gang, catalogue, form, back, confirmation, notice=""):
    from n26.core.people import person_link

    badges = {}
    owner = person_link(gang.owner, badges)
    owner["badge"] = badges.get(owner.get("badge"))
    data = request.POST if request.method == "POST" else request.GET
    confirmed = confirmation or {}
    values = {
        "list": catalogue.scope,
        "section": _section(request),
        "profile": confirmed.get("key", data.get("profile", data.get("hire", ""))),
        "selection": dumps(confirmed.get("selection", [])),
        "name": str(form["name"].value() or ""),
        "paid": data.get("paid", "")
        if request.method == "POST"
        else str(confirmed["quote"])
        if confirmation
        else "",
        "rate": data.get("rate", "") if request.method == "POST" else "paid",
        "request_key": str(form["request_key"].value() or uuid4()),
        "profile_name": confirmed.get("profileName", ""),
        "choice_names": dumps(confirmed.get("choices", [])),
        "quoted": str(confirmed.get("quote", 0)),
    }
    return {
        **catalogue_data(catalogue, _section(request)),
        "gangName": gang.name,
        "gangHref": reverse("n26-gang", args=[gang.pk]),
        "owner": owner,
        "figures": figures_data(
            gang,
            catalogue.summary,
            trade_points_href=trade_points_href(gang, request.user),
            credits_href=credits_href(gang, request.user),
        ),
        "values": values,
        "errors": dict(form.errors),
        "confirmation": confirmation is not None,
        "notice": notice,
        "messages": [
            {
                "text": str(message),
                "tone": message.level_tag
                if message.level_tag in {"success", "error", "warning"}
                else "info",
            }
            for message in messages.get_messages(request)
        ],
        "csrfToken": get_token(request),
        "action": back,
        "commandHref": reverse("n26-hire-command", args=[gang.pk]),
        "recoveryKey": f"hire:{request.user.pk}:{gang.pk}",
        "back": back,
        "signInHref": reverse("account_login")
        + "?"
        + urlencode(
            {"next": request.get_full_path() if request.method == "GET" else back}
        ),
    }


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def hire_fighter(request, pk):
    """Render the complete Hire owner, retaining the native command adapter."""
    from n26.core.arrivals import onward

    gang = _own_gang_or_404(request, pk)
    scope, section = _scope(request), _section(request)
    back = listing_url(gang, scope, section)
    form = HireSubmissionForm(initial={"request_key": uuid4()})
    if request.method == "POST" and "profile" in request.POST:
        try:
            result = hire_workflow.change(gang, request.user, request.POST)
        except UnavailableHire as error:
            raise Http404(str(error)) from None
        form = result.form
        if result.saved:
            hire_feedback(request, gang, result)
            return redirect(onward(request, gang, result, back))
        if result.refused:
            messages.error(request, result.refused)
            return redirect(back)
        # A rolled-back operation can leave the in-memory gang with attempted totals.
        gang = _own_gang_or_404(request, pk)
    catalogue = HireCatalogue(gang, request.user, scope)
    data = request.POST if request.method == "POST" else request.GET
    key = data.get("profile", data.get("hire", ""))
    confirmation, notice = None, ""
    if key:
        try:
            profile, offer = hire_workflow.resolve_offer(
                key, lambda: catalogue.offers, include_staged=catalogue.shown
            )
            if profile is not None:
                confirmation = confirmation_data(profile, offer, key, data)
            else:
                notice = "This profile is no longer available. Choose another."
        except ValidationError, UnavailableHire:
            if "selection" not in data:
                raise Http404("No such option") from None
            notice = "These model options are no longer available. Choose them again."
    if request.method == "POST" and "profile" not in data and confirmation:
        query = [("hire", key)]
        if "selection" in data:
            query.append(("selection", dumps(confirmation["selection"])))
        else:
            # Cached native forms keep their indexed confirmation URLs.
            prefix = f"{slugify(key)}:"
            query.extend(
                (name, value)
                for name in data
                if name.startswith(prefix)
                for value in data.getlist(name)
                if value
            )
        return redirect(
            back + ("&" if "?" in back else "?") + urlencode(query, safe=":")
        )
    return render(
        request,
        "n26/hire_fighter.html",
        {
            "gang": gang,
            "form": form,
            "back": back,
            "hire_props": _props(
                request, gang, catalogue, form, back, confirmation, notice
            ),
        },
    )


@never_cache
@require_POST
def hire_command(request, pk):
    """Apply the same validated, retry-safe hire as the native POST adapter."""
    from n26.core.arrivals import onward

    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in again to save this change."}, status=401)
    gang = _own_gang_or_404(request, pk)
    try:
        result = hire_workflow.change(gang, request.user, request.POST)
    except UnavailableHire:
        gang = _own_gang_or_404(request, pk)
        return JsonResponse(
            {
                "errors": {
                    "selection": [
                        "These model options are no longer available. Choose them again."
                    ]
                },
                "figures": _figures(gang, request.user),
            },
            status=422,
        )
    if result.saved:
        hire_feedback(request, gang, result)
        return JsonResponse(
            {
                "nextUrl": onward(
                    request,
                    gang,
                    result,
                    listing_url(gang, _scope(request), _section(request)),
                )
            }
        )
    gang = _own_gang_or_404(request, pk)
    return JsonResponse(
        {"errors": dict(result.form.errors), "figures": _figures(gang, request.user)},
        status=409 if result.conflict else 422,
    )
