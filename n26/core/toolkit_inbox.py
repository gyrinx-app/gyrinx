"""Batch the recipient's own intervention offers for the shared inbox."""

from uuid import uuid4

from django.db.models import Q
from django.urls import reverse

from n26.core.fields import to_ulid
from n26.core.models.toolkit import InterventionReceipt


def offers_for(deliveries, viewer):
    offer_ids = {}
    for delivery in deliveries:
        if delivery.identity.startswith("offer:"):
            try:
                offer_ids[to_ulid(delivery.identity.removeprefix("offer:"))] = (
                    delivery.pk.to_uuid()
                )
            except ValueError, TypeError:
                continue
    if not offer_ids:
        return {}
    receipts = InterventionReceipt.objects.filter(
        Q(gang__owner=viewer, gang__archived=False) | Q(player=viewer),
        pk__in=offer_ids,
        intervention__mode="choice",
        intervention__campaign__archived=False,
    ).select_related("intervention", "gang", "player")
    return {
        offer_ids[r.pk]: {
            "id": str(r.pk),
            "gang": r.gang.name if r.gang_id else r.player.username,
            "choices": r.intervention.choices,
            "rewards": [
                {"label": reward["label"]} for reward in r.intervention.rewards
            ],
            "resolved": r.resolved_at is not None,
            "selected": r.selected,
            "values": {"request_key": str(uuid4()), "payload": ""},
            "commandHref": reverse(
                "n26-toolkit-command", args=[r.intervention.campaign_id, "choose"]
            ),
            "recoveryKey": f"toolkit:{viewer.pk}:{r.intervention.campaign_id}:choose:{r.pk}",
        }
        for r in receipts
    }
