"""List hireable profiles and submit named acquisitions through operations.

A listing POST identifies one offer and redirects to ``?hire=`` with that
row's selected options. GET opens its naming and price dialog. The dialog's
POST supplies ``profile``, validates the selection and performs the hire.

Preserve scope and section in every destination. The intermediate redirect
keeps unrelated listing controls out of the URL. After hiring, show any
introduced interstitials before returning to the list.
"""

from urllib.parse import urlencode
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from n26.core import hire_workflow
from n26.core.hire_workflow import HireSubmissionForm, UnavailableHire
from n26.core.prices import PRICE_CEILING
from n26.core.views.permissions import (
    _own_gang_or_404,
    credits_href,
    trade_points_href,
)
from n26.library.staged import sees_staged

#: Build only the URL-selected scope; All profiles is substantially larger than the gang list.
HIRE_SCOPES = {
    "gang": "Gang list",
    "supplementary": "Supplementary",
    "all": "All profiles",
}


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


def _here(request, scope, section):
    """Build this hire page's URL while preserving scope and section."""
    params = [
        *([("list", scope)] if scope != "gang" else []),
        *([("section", section)] if section else []),
    ]
    return f"{request.path}?{urlencode(params)}" if params else request.path


def _scope_tabs(request, scope):
    return [
        {
            "label": label,
            "href": request.path if key == "gang" else f"{request.path}?list={key}",
            "current": key == scope,
        }
        for key, label in HIRE_SCOPES.items()
    ]


def _offered(gang, raw, offers, *, include_staged=False):
    try:
        return hire_workflow.resolve_offer(raw, offers, include_staged=include_staged)
    except UnavailableHire as error:
        raise Http404(str(error)) from None


def _picks(data, profile, entry, key=None):
    try:
        return hire_workflow.resolve_picks(data, profile, entry, key=key)
    except UnavailableHire as error:
        raise Http404(str(error)) from None


def _dialog(
    request,
    profile,
    picks,
    scope="gang",
    section="",
    entry=None,
    key=None,
    rate_at_paid=True,
):
    """Build a hire confirmation using shared option pricing and preserved hidden fields.

    ``rate_at_paid`` defaults on for the initial dialog. Reuse the submitted value
    after validation errors so an unchecked rating option stays unchecked.
    """
    try:
        price = hire_workflow.quote(profile, picks, entry)
    except UnavailableHire:
        raise Http404("No such option") from None
    return {
        "profile": profile.name,
        "price": price,
        "paid": request.POST.get("paid", str(price))
        if request.method == "POST"
        else None,
        "scope": scope,
        "choices": [pick.option.name for pick in picks if pick.option.default_set],
        "fields": [
            {"name": "profile", "value": key or str(profile.pk)},
            *([{"name": "list", "value": scope}] if scope != "gang" else []),
            *([{"name": "section", "value": section}] if section else []),
            *({"name": pick.field, "value": pick.value} for pick in picks),
        ],
        "cancel_url": _here(request, scope, section),
        "rate_at_paid": rate_at_paid,
    }


def _link_cards(gang, hire_list):
    """Add preview URLs for each hire offer and its individual options.

    Preserve entry identifiers so preview cards use the same collection price.
    The row URL accepts its whole selection; option URLs preview that option
    with otherwise default groups.
    """
    from django.urls import reverse

    for section in hire_list:
        for entry in section.all_entries():
            address = reverse("n26-hire-card", args=[gang.pk, entry.profile.pk])
            offered = [("entry", entry.entry.pk)] if entry.entry is not None else []
            entry.card_url = f"{address}?{urlencode(offered)}" if offered else address
            for group in entry.groups:
                for option in group.options:
                    params = [
                        *(
                            [("option", option.default_set.pk)]
                            if option.default_set is not None
                            else []
                        ),
                        *offered,
                    ]
                    option.card_url = (
                        f"{address}?{urlencode(params)}" if params else address
                    )


@login_required
def hire_card(request, pk, profile):
    """Render a privately cached preview for an authorised gang owner.

    Validate profile visibility and selected option sets. An optional entry must
    name this profile; previews do not check whether the gang carries its collection.
    Listing POSTs, dialog GETs and hire POSTs validate named collection offers.
    Repeated option parameters compose the preview.
    Cache for five minutes because previews derive only from library content.
    """
    from django.shortcuts import get_object_or_404
    from django.utils.cache import patch_cache_control

    from n26.core.hire import preview_model_card
    from n26.library.models import CollectionEntry, Profile

    _own_gang_or_404(request, pk)
    # Apply the same archive and staged-content visibility as the hiring list.
    profiles = Profile.objects.unarchived()
    if not sees_staged(request.user):
        profiles = profiles.live()
    found = get_object_or_404(profiles, pk=profile)

    option = None
    named = request.GET.getlist("option")
    if named:
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

    response = render(request, "n26/hire_card.html", {"card": card})
    patch_cache_control(response, private=True, max_age=300)
    return response


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


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def hire_fighter(request, pk):
    """Build the selected hiring scope and execute confirmed hires through operations.

    Gang-held collections can offer additional profiles at entry-specific prices.
    Validate the offer, options and typed payment server-side, then redirect
    through any arrival screens. Operation refusals roll back the acquisition.
    """
    from functools import cache

    from n26.core.access import gang_collections
    from n26.core.arrivals import onward
    from n26.core.hire import (
        build_entries,
        build_hire_entry,
        collection_offers,
        gang_scope_sections,
        hireable_profiles,
        section_by_gang_type,
        section_hire_list,
        supplementary_profiles,
    )
    from n26.core.render import roster, summarise_roster

    gang = _own_gang_or_404(request, pk)
    # Reuse staged-content access for every displayed and submitted profile.
    shown = sees_staged(request.user)
    scope = _scope(request)
    section = _section(request)
    # Preserve scope and section through confirmation, cancellation and successful hiring.
    back = _here(request, scope, section)
    form = HireSubmissionForm(initial={"request_key": uuid4()})
    dialog = None

    @cache
    def carried():
        """Cache the gang's held collections for offer validation and section building."""
        return [access.collection for access in gang_collections(gang)]

    @cache
    def offers():
        """Lazily cache current collection offers within this request."""
        return collection_offers(carried(), include_staged=shown)

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
        key = request.POST["profile"]
        profile, offer = _offered(gang, key, offers, include_staged=shown)
        if profile is not None:
            picks = _picks(
                request.POST,
                profile,
                build_hire_entry(profile, with_cards=False),
                key=key,
            )
            # Preserve typed name, selected options and rating mode after validation errors.
            dialog = _dialog(
                request,
                profile,
                picks,
                scope=scope,
                section=section,
                entry=offer,
                key=key,
                rate_at_paid=request.POST.get("rate") == "paid",
            )
    elif request.method == "POST":
        # Redirect the selected offer and its options into the dialog URL.
        key = request.POST.get("hire", "")
        profile, offer = _offered(gang, key, offers, include_staged=shown)
        if profile is not None:
            picks = _picks(
                request.POST,
                profile,
                build_hire_entry(profile, with_cards=False),
                key=key,
            )
            # Preserve colons in option field names when encoding the query string.
            query = urlencode(
                [
                    *([("list", scope)] if scope != "gang" else []),
                    *([("section", section)] if section else []),
                    ("hire", key),
                    *((pick.field, pick.value) for pick in picks),
                ],
                safe=":",
            )
            return redirect(f"{request.path}?{query}")
    elif request.GET.get("hire"):
        key = request.GET["hire"]
        profile, offer = _offered(gang, key, offers, include_staged=shown)
        if profile is not None:
            dialog = _dialog(
                request,
                profile,
                _picks(
                    request.GET,
                    profile,
                    build_hire_entry(profile, with_cards=False),
                    key=key,
                ),
                scope=scope,
                section=section,
                entry=offer,
                key=key,
            )

    # Build priced sections without preview cards; fetch cards lazily through hire_card.
    if scope == "supplementary":
        hire_list = section_hire_list(
            build_entries(
                list(supplementary_profiles(include_staged=shown)), with_cards=False
            )
        )
    elif scope == "all":
        hire_list = section_by_gang_type(
            build_entries(
                list(hireable_profiles(include_staged=shown)), with_cards=False
            )
        )
    else:
        # Order the gang list before additional held collections offering profiles.
        hire_list = gang_scope_sections(
            offers(),
            gang.gang_type,
            carried(),
            with_cards=False,
            include_staged=shown,
        )
    _link_cards(gang, hire_list)
    prices = [
        entry.base_price for section in hire_list for entry in section.all_entries()
    ]
    return render(
        request,
        "n26/hire_fighter.html",
        {
            "gang": gang,
            "form": form,
            "dialog": dialog,
            # Use the same typed-price ceiling as equipment purchases.
            "price_cap": PRICE_CEILING,
            # Keep the query string in form actions to preserve the selected tab.
            "back": back,
            "hire_list": hire_list,
            "scope_tabs": _scope_tabs(request, scope),
            "scope": scope,
            "scope_label": HIRE_SCOPES[scope],
            # Include the current roster summary beside the gang's figures.
            "summary": summarise_roster(roster(gang)),
            "trade_points_href": trade_points_href(gang, request.user),
            "credits_href": credits_href(gang, request.user),
            # Include every section exactly once in navigation so none becomes unreachable.
            "sections": [section.name for section in hire_list],
            # Match category registration keys, falling back to the section for unnamed categories.
            # Deduplicate keys because the same category name can occur under several sections.
            "categories": list(
                dict.fromkeys(
                    category.name or section.name
                    for section in hire_list
                    for category in section.categories
                )
            ),
            "category_options": [
                {"value": name, "label": name}
                for name in dict.fromkeys(
                    category.name
                    for section in hire_list
                    for category in section.categories
                    if category.name
                )
            ],
            "price_floor": min(prices, default=0),
            "price_ceiling": max(prices, default=0),
        },
    )
