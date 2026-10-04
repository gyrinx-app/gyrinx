"""Read one campaign holding and its recorded ownership and battles."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Prefetch, prefetch_related_objects
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from n26.core.history import asset_ownership_history
from n26.core.models import Battle
from n26.core.render import (
    CampaignAssetAction,
    CampaignAssetBattle,
    CampaignAssetDetails,
    boon_said,
)
from n26.core.views.campaigns import _campaign_asset_or_404, _holding_owner
from n26.core.views.gangs import _pages
from n26.core.views.permissions import _any_campaign_or_404
from n26.flags import CAMPAIGNS, requires_flag
from n26.library.income import boons_of, income_of
from n26.library.models import Modifier
from n26.library.references import reading_sentences


@requires_flag(CAMPAIGNS)
@login_required
@require_GET
def asset_detail(request, pk, asset_pk):
    return render(
        request, "n26/campaign_asset.html", _asset_context(request, pk, asset_pk)
    )


def _asset_detail_update(request, pk, asset_pk):
    from n26.core.views.htmx import with_toasts

    context = _asset_context(request, pk, asset_pk)
    context["redrawn"] = True
    response = with_toasts(
        request, render(request, "n26/includes/campaign_asset_update.html", context)
    )
    response["HX-Replace-Url"] = reverse("n26-campaign-asset", args=[pk, asset_pk])
    return response


def _asset_context(request, pk, asset_pk):
    campaign = _any_campaign_or_404(request, pk)
    holding = _campaign_asset_or_404(campaign, asset_pk)
    prefetch_related_objects(
        [holding.asset],
        Prefetch("modifiers", queryset=reading_sentences(Modifier.objects.all())),
    )
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
    return {
        "campaign": campaign,
        "details": CampaignAssetDetails(
            name=str(holding),
            library_name=holding.asset.name if holding.name else "",
            kind=holding.asset.asset_type.label_singular,
            created=holding.created,
            income=income_of(holding.asset),
            boons=[boon_said(modifier) for modifier in boons_of(holding.asset)],
            holder=holding.holder.gang.name if held else "",
            holder_href=reverse("n26-gang", args=[holding.holder.gang_id])
            if held
            else "",
        ),
        "actions": actions,
        "battles": battles,
        "history": page.object_list,
        "pages": _pages(request, page) if page.paginator.num_pages > 1 else None,
        "total": page.paginator.count,
    }
