"""Read one campaign holding and its recorded ownership and battles."""

from dataclasses import replace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from n26.core.history import asset_ownership_history
from n26.core.income import holding_income_sources, unclaimed_income_source
from n26.core.models import Battle
from n26.core.render import (
    CampaignAssetAction,
    CampaignAssetBattle,
    CampaignAssetDetails,
)
from n26.core.views.campaigns import _campaign_asset_or_404, _holding_owner
from n26.core.views.gangs import _pages
from n26.core.views.permissions import _any_campaign_or_404
from n26.flags import CAMPAIGNS, requires_flag


@requires_flag(CAMPAIGNS)
@login_required
@require_GET
def asset_detail(request, pk, asset_pk):
    return render(
        request, "n26/campaign_asset.html", _asset_context(request, pk, asset_pk)
    )


def _asset_detail_update(request, pk, asset_pk):
    from n26.core.views.htmx import with_toasts

    context = _asset_context(
        request, pk, asset_pk, back=reverse("n26-campaign-asset", args=[pk, asset_pk])
    )
    context["redrawn"] = True
    response = with_toasts(
        request, render(request, "n26/includes/campaign_asset_update.html", context)
    )
    response["HX-Replace-Url"] = reverse("n26-campaign-asset", args=[pk, asset_pk])
    return response


def _asset_context(request, pk, asset_pk, *, back=None):
    campaign = _any_campaign_or_404(request, pk)
    holding = _campaign_asset_or_404(campaign, asset_pk)
    held = holding.held
    arbitrating = campaign.owner_id == request.user.pk
    may_release = held and (arbitrating or _holding_owner(holding, request.user))
    actions = []

    def action(label, route, danger=False):
        href = reverse(route, args=[campaign.pk, holding.pk])
        attrs = {}
        if not danger:
            href += "?from=detail"
            attrs = {"hx-get": href, "hx-swap": "none"}
        actions.append(
            CampaignAssetAction(
                label=label,
                href=href,
                attrs=attrs,
                variant="danger" if danger else "default",
            )
        )

    if may_release:
        action(
            "Transfer" if arbitrating else "Hand over", "n26-campaign-asset-transfer"
        )
        action("Unassign", "n26-campaign-asset-unassign")
    elif not held and arbitrating:
        action("Assign", "n26-campaign-asset-assign")
        action("Remove", "n26-campaign-asset-remove", danger=True)

    battles = []
    for battle in holding.staked_in.select_related("stake_awarded_to").prefetch_related(
        "gangs", "winners"
    ):
        if battle.result == Battle.Result.NOT_RECORDED:
            outcome = "Result not recorded"
        elif battle.result == Battle.Result.DRAW:
            outcome = "Draw"
        else:
            outcome = "Winners: " + ", ".join(
                gang.name for gang in battle.winners.all()
            )
        battles.append(
            CampaignAssetBattle(
                title=battle.title,
                date=battle.date,
                href=reverse("n26-battle", args=[campaign.pk, battle.pk]),
                gangs=", ".join(gang.name for gang in battle.gangs.all()),
                outcome=outcome,
                transferred_to=battle.stake_awarded_to.name
                if battle.stake_transfer_mark and battle.stake_awarded_to_id
                else "",
            )
        )
    history = list(reversed(asset_ownership_history(holding)))
    page = Paginator(history, 50).get_page(request.GET.get("page"))
    choices = []
    boons = []
    income_modifiers = None
    boon_editor = None
    static_boons = []
    if held:
        from n26.core.card import build_gang_card, build_modifier_index, carriers
        from n26.core.effects import compute_gang
        from n26.core.models import DismissedOffer
        from n26.core.render import (
            hide_dismissed_choices,
            holding_boons,
            holding_choices,
        )
        from n26.core.views.choose import link_slots

        gang = holding.holder.gang
        card = build_gang_card(gang)
        index = build_modifier_index(carriers(card))
        computed = compute_gang(card, index)
        income_source = holding_income_sources(computed).get(
            (holding.pk, holding.ownership_revision)
        )
        income = income_source.value if income_source is not None else 0
        offered = holding_choices(computed, holding)
        owning = _holding_owner(holding, request.user)
        hide_dismissed_choices(
            DismissedOffer.keys_for(gang), offered.questions, reveal=owning
        )
        if owning:
            link_slots(gang, offered, back=back or request.get_full_path())
        choices = offered.questions
        boon = holding_boons(computed, holding, choices)
        if boon is not None and (boon.effects or boon.choices):
            boons = [boon]
            if owning:
                groups = _boon_groups(computed, choices, request.user)
                if groups:
                    boon_editor = {
                        "groups": [group["props"] for group in groups],
                        "showLabels": len(choices) > 1,
                        "effects": [
                            dict(name=effect.name, text=effect.text)
                            for effect in boon.effects
                        ],
                        "saveUrl": reverse(
                            "n26-campaign-asset-boons", args=[campaign.pk, holding.pk]
                        ),
                        "csrfToken": get_token(request),
                        "snapshot": signing.dumps(
                            _boon_snapshot(holding, groups),
                            salt="territory-boon-choices",
                        ),
                    }
                    inline_keys = {group["props"]["key"] for group in groups}
                    remaining = tuple(
                        choice for choice in choices if choice.key not in inline_keys
                    )
                    if remaining:
                        static_boons = [replace(boon, choices=remaining, effects=())]
    else:
        income_modifiers = list(
            holding.asset.modifiers.select_related(
                "contributes_to_counter__counter", "targets_gang"
            ).prefetch_related("targets_gang__has_gang_pickable__pickables")
        )
    if not held:
        income_source = unclaimed_income_source(holding, income_modifiers)
        income = income_source.value
    return {
        "campaign": campaign,
        "details": CampaignAssetDetails(
            name=str(holding),
            library_name=holding.asset.name if holding.name else "",
            kind=holding.asset.asset_type.label_singular,
            created=holding.created,
            income=income,
            income_source=income_source,
            holder=holding.holder.gang.name if held else "",
            holder_href=reverse("n26-gang", args=[holding.holder.gang_id])
            if held
            else "",
        ),
        "actions": actions,
        "choices": choices,
        "boons": boons,
        "boon_editor": boon_editor,
        "static_boons": static_boons,
        "battles": battles,
        "history": page.object_list,
        "pages": _pages(request, page) if page.paginator.num_pages > 1 else None,
        "total": page.paginator.count,
    }


def _boon_groups(computed, choices, viewer):
    """The territory's single-choice offers, from the already-loaded card."""
    from n26.core.render import (
        GANG_SLOT_HOST,
        build_choice_offers,
        option_key,
        slot_key,
    )
    from n26.core.views.choose import _Found
    from n26.library.staged import sees_staged

    by_key = {
        slot_key(slot, GANG_SLOT_HOST): slot
        for slot in computed.choices
        if not slot.is_history_only
    }
    inline = [
        (line, by_key[line.key])
        for line in choices
        if not line.dismissed
        and line.key
        and line.key in by_key
        and by_key[line.key].slot is not None
        and by_key[line.key].max_picks == 1
        and not by_key[line.key].slot.picklist.dice
        and not by_key[line.key].slot.follows_status
    ]
    offers = build_choice_offers(
        [slot for _, slot in inline], computed, include_staged=sees_staged(viewer)
    )
    groups = []
    for (line, slot), offer in zip(inline, offers, strict=True):
        options = [option for group in offer.groups for option in group.options]
        if not options:
            continue
        current = next((option.key for option in options if option.is_current), "")
        if not current and slot.picks:
            current = option_key(slot.picks[0].assignable)
        props = {
            "key": line.key,
            "label": offer.label,
            "selected": current,
            "options": [
                dict(
                    value=option.key,
                    label=option.name,
                    description=" · ".join(
                        filter(None, [option.summary, option.remark])
                    ),
                    disabled=False,
                )
                for option in options
            ],
        }
        if current and current not in {option.key for option in options}:
            props["options"].insert(
                0,
                dict(
                    value=current,
                    label=line.chosen,
                    description="Current choice",
                    disabled=False,
                ),
            )
        groups.append(
            {
                "props": props,
                "found": _Found(
                    slot=slot,
                    computed=computed,
                    anchor=slot.holding or slot.anchor.assignment,
                ),
                "offer": offer,
                "assignments": [
                    str(pick.assignment.pk)
                    for pick in slot.picks
                    if pick.assignment is not None
                ],
            }
        )
    return groups


def _boon_snapshot(holding, groups):
    return {
        "holding": str(holding.pk),
        "revision": holding.ownership_revision,
        "holder": str(holding.holder_id),
        "groups": [
            dict(
                key=group["props"]["key"],
                selected=group["props"]["selected"],
                options=[option["value"] for option in group["props"]["options"]],
                assignments=group["assignments"],
            )
            for group in groups
        ],
    }


@requires_flag(CAMPAIGNS)
@login_required
@require_POST
def save_asset_boons(request, pk, asset_pk):
    """Save changed territory choices together under campaign and gang locks."""
    from n26.core.campaigns import campaign_operation
    from n26.core.card import build_gang_card, build_modifier_index, carriers
    from n26.core.effects import compute_gang
    from n26.core.models import DismissedOffer
    from n26.core.operations import Refusal, operation
    from n26.core.render import hide_dismissed_choices, holding_choices
    from n26.core.views.choose import NotOnTheList, _record_pick, _write_pick

    campaign = _any_campaign_or_404(request, pk)
    written = []
    try:
        with campaign_operation(campaign, actor=request.user):
            holding = _campaign_asset_or_404(campaign, asset_pk)
            if not _holding_owner(holding, request.user):
                raise Http404("No such territory choice")
            gang = holding.holder.gang
            with operation(gang, actor=request.user) as op:
                gang.refresh_from_db(fields=["owner"])
                if gang.owner_id != request.user.pk:
                    raise Http404("No such territory choice")
                card = build_gang_card(gang)
                computed = compute_gang(card, build_modifier_index(carriers(card)))
                choices = holding_choices(computed, holding).questions
                hide_dismissed_choices(
                    DismissedOffer.keys_for(gang), choices, reveal=True
                )
                groups = _boon_groups(computed, choices, request.user)
                try:
                    snapshot = signing.loads(
                        request.POST.get("snapshot", ""),
                        salt="territory-boon-choices",
                        max_age=1800,
                    )
                except signing.BadSignature:
                    snapshot = None
                if snapshot != _boon_snapshot(holding, groups):
                    raise Refusal(
                        "The boon choices changed. Reload this page before saving."
                    )
                fields = {"choice_" + group["props"]["key"] for group in groups}
                if any(
                    key.startswith("choice_") and key not in fields
                    for key in request.POST
                ):
                    raise NotOnTheList
                changes = []
                for group in groups:
                    field = "choice_" + group["props"]["key"]
                    values = request.POST.getlist(field)
                    if len(values) > 1:
                        raise NotOnTheList
                    if not values:
                        continue
                    wanted = values[0]
                    if wanted == group["props"]["selected"]:
                        continue
                    if wanted not in {
                        option.key
                        for part in group["offer"].groups
                        for option in part.options
                    }:
                        raise NotOnTheList
                    changes.append((group, wanted))
                for group, wanted in changes:
                    try:
                        picked = _write_pick(
                            op,
                            request,
                            gang,
                            group["props"]["key"],
                            group["found"],
                            group["offer"],
                            wanted,
                        )
                    except Http404:
                        raise Refusal(
                            "The boon choices changed. Reload this page before saving."
                        ) from None
                    written.append((group["offer"], picked))
    except NotOnTheList:
        return JsonResponse(
            {"error": "That boon is not one of the available options."}, status=400
        )
    except Refusal as error:
        return JsonResponse({"error": str(error)}, status=409)
    for offer, picked in written:
        _record_pick(request, gang, offer, picked, "")
    if written:
        messages.success(request, "Boons saved.")
    return JsonResponse(
        {
            "redirectUrl": reverse("n26-campaign-asset", args=[campaign.pk, holding.pk])
            + "#n26-territory-boons"
        }
    )
