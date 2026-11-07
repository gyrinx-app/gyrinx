"""HTML and JSON adapters for editing a campaign's own asset type."""

import json
from hashlib import sha256

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from n26.core import asset_type_edit
from n26.core.campaigns import ownership_fixed_because
from n26.core.people import person_link
from n26.core.views.permissions import _own_campaign_or_404
from n26.library.models import AssetType


def _context(request, pk, asset_type_pk):
    campaign = _own_campaign_or_404(
        request, pk, with_owner_badge=request.method == "GET"
    )
    try:
        asset_type = get_object_or_404(
            AssetType, pk=asset_type_pk, campaign_type_id=campaign.additions_id
        )
    except ValidationError:
        raise Http404("No such asset type") from None
    return campaign, asset_type


def _feedback(request, result):
    tag = (
        "asset-type-"
        + sha256(
            json.dumps(result.form.cleaned_data, sort_keys=True).encode()
        ).hexdigest()
    )
    storage = messages.get_messages(request)
    queued = any(tag in (message.extra_tags or "").split() for message in storage)
    storage.used = False
    if not queued:
        text = result.message
        if not result.applied and text != "Nothing changed.":
            text = "These asset type details were already saved."
        messages.success(request, text, extra_tags=tag)


def _props(request, campaign, asset_type, form, result):
    from n26.core.views.campaigns import _ownership_cards

    badges = {}
    owner = person_link(campaign.owner, badges)
    owner["badge"] = badges.get(owner["badge"])
    fixed = ownership_fixed_because(campaign, asset_type)
    return {
        "heading": f"Edit {asset_type.label_singular}",
        "campaignName": campaign.name,
        "campaignHref": reverse("n26-campaign", args=[campaign.pk]),
        "campaignsHref": reverse("n26-campaigns"),
        "owner": owner,
        "back": reverse("n26-edit-campaign", args=[campaign.pk]) + "?tab=asset-types",
        "action": reverse(
            "n26-campaign-edit-asset-type", args=[campaign.pk, asset_type.pk]
        ),
        "commandHref": reverse(
            "n26-campaign-edit-asset-type-command", args=[campaign.pk, asset_type.pk]
        ),
        "csrfToken": get_token(request),
        "recoveryKey": f"asset-type:{request.user.pk}:{asset_type.pk}",
        "values": {
            name: str(form[name].value() or "")
            for name in (*asset_type_edit.FIELDS, "snapshot")
        },
        "fields": {
            name: {
                "label": form.fields[name].label,
                "help": form.fields[name].help_text,
            }
            for name in asset_type_edit.FIELDS
        },
        "ownershipNote": f"{asset_type.get_ownership_display()}. You cannot change ownership. {fixed}"
        if fixed
        else "",
        "ownerships": _ownership_cards(str(form["ownership"].value() or ""))
        if not fixed
        else [],
        "errors": dict(form.errors),
        "conflict": result.current if result and result.conflict else None,
    }


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def edit_asset_type(request, pk, asset_type_pk):
    campaign, asset_type = _context(request, pk, asset_type_pk)
    result = None
    if request.method == "POST":
        result = asset_type_edit.change(
            campaign, asset_type, request.user, request.POST
        )
        form = result.form
        if result.saved:
            _feedback(request, result)
            return redirect(
                reverse("n26-edit-campaign", args=[campaign.pk]) + "?tab=asset-types"
            )
    else:
        form = asset_type_edit.initial_form(campaign, asset_type, request.user)
    props = _props(request, campaign, asset_type, form, result)
    return render(
        request,
        "n26/edit_asset_type.html",
        {
            "campaign": campaign,
            "asset_type": asset_type,
            "form": form,
            "heading": props["heading"],
            "back": props["back"],
            "edit_props": props,
        },
    )


@require_POST
def edit_asset_type_command(request, pk, asset_type_pk):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in again to save this change."}, status=401)
    campaign, asset_type = _context(request, pk, asset_type_pk)
    result = asset_type_edit.change(campaign, asset_type, request.user, request.POST)
    if result.saved:
        _feedback(request, result)
        return JsonResponse(
            {
                "nextUrl": reverse("n26-edit-campaign", args=[campaign.pk])
                + "?tab=asset-types"
            }
        )
    return JsonResponse(
        {
            "errors": dict(result.form.errors),
            "code": "revision_conflict" if result.conflict else "invalid",
            "current": result.current,
        },
        status=409 if result.conflict else 422,
    )
