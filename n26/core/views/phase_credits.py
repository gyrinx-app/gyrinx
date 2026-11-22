"""Gang owners and the active campaign's arbitrator may resolve phase credits."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from n26.core import phase_credits
from n26.core.models import CampaignCycleTransition, PhaseCreditReceipt
from n26.core.operations import Refusal
from n26.core.views.permissions import _any_campaign_or_404, _any_gang_or_404


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def phase_awards(request, pk, gang_pk):
    campaign = _any_campaign_or_404(request, pk, with_owner_badge=False)
    gang = _any_gang_or_404(request, gang_pk)
    actor = request.user
    if not phase_credits.can_manage(campaign, gang, actor):
        raise Http404
    if request.method == "POST":
        try:
            entry = campaign.cycle_transitions.get(pk=request.POST.get("entry"))
        except CampaignCycleTransition.DoesNotExist, ValidationError:
            raise Http404 from None
        try:
            phase_credits.settle(
                campaign,
                gang,
                actor,
                entry,
                request.POST.get("method"),
                request.POST.get("note", ""),
                request.POST.get("payment", ""),
            )
        except Refusal as exc:
            return JsonResponse({"error": exc.public_message}, status=422)
        return JsonResponse({"saved": True})

    arbitrator = actor.pk == campaign.owner_id
    receipts = {
        receipt.entry_id: receipt
        for receipt in PhaseCreditReceipt.objects.filter(
            gang=gang, entry__campaign=campaign
        ).select_related("actor", "payment")
    }
    awards = []
    for offer in reversed(phase_credits.offers(campaign, gang)):
        receipt = receipts.get(offer.entry.pk)
        if not (arbitrator or offer.eligible or receipt):
            continue
        awards.append(
            {
                "entry": str(offer.entry.pk),
                "name": offer.name,
                "cycle": offer.entry.receipt.get("current_cycle", ""),
                "terms": offer.amount_label,
                "eligible": offer.eligible,
                "receipt": {
                    "amount": -receipt.payment.credits_delta,
                    "method": receipt.method,
                    "actor": receipt.actor.get_username() if receipt.actor else "",
                    "rolls": receipt.rolls,
                    "note": receipt.note,
                    "adjustment": (
                        f"{receipt.payment.created:%Y-%m-%d} · {receipt.payment.note or 'Credit adjustment'}"
                        if receipt.method == "paid"
                        else ""
                    ),
                }
                if receipt
                else None,
            }
        )
    payments = []
    if arbitrator and any(not a["receipt"] for a in awards):
        payments = [
            {
                "id": str(p.pk),
                "label": f"{p.created:%Y-%m-%d} · {-p.credits_delta}¢ · {p.note or 'Credit adjustment'}",
            }
            for p in phase_credits.adjustments(campaign, gang)
        ]
    props = {
        "awards": awards,
        "payments": payments,
        "arbitrator": arbitrator,
        "gang": gang.name,
        "campaign": campaign.name,
        "campaignHref": reverse("n26-campaign", args=[campaign.pk]) + "#gangs",
        "action": request.path,
        "csrfToken": get_token(request),
    }
    return render(request, "n26/phase_credits.html", {"gang": gang, "props": props})
