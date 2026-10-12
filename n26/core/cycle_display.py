"""Compact current-cycle data for campaign and gang metadata boxes."""

from dataclasses import dataclass
from datetime import datetime

from django.urls import reverse

from n26.core.cycles import current_cycle


def cycle_summary(campaign, *, actor=None, gang=None, gangs=()):
    cycle = current_cycle(campaign)
    yours = (
        actor is not None and actor.pk == campaign.owner_id and not campaign.archived
    )
    props = {
        "label": cycle.label if cycle else "Not started",
        "edit_href": reverse("n26-edit-cycle", args=[campaign.pk]) if yours else "",
    }
    if cycle:
        props["rename_href"] = props["edit_href"] + "?action=rename" if yours else ""
        props["view_href"] = reverse("n26-cycle-rewards", args=[campaign.pk, cycle.pk])
        props["apply_href"] = props["view_href"] if yours else ""
        if gang:
            receipt = cycle.resolutions.filter(gang=gang).first()
            props["state"] = "Boons applied" if receipt else "Boons pending"
            props["receipt_href"] = (
                reverse("n26-cycle-receipt", args=[campaign.pk, receipt.pk])
                if receipt
                else ""
            )
            props["view_href"] += f"?gang={gang.pk}"
            if props["apply_href"]:
                props["apply_href"] += f"?gang={gang.pk}"
        if gangs:
            receipts = {
                str(receipt.gang_id): receipt for receipt in cycle.resolutions.all()
            }
            for line in gangs:
                receipt = receipts.get(line.gang_id)
                line.cycle = {
                    "state": "Applied" if receipt else "Pending",
                    "receipt_href": reverse(
                        "n26-cycle-receipt", args=[campaign.pk, receipt.pk]
                    )
                    if receipt
                    else "",
                    "view_href": f"{props['view_href']}?gang={line.gang_id}"
                    if not receipt
                    else "",
                    "apply_href": f"{props['apply_href']}?gang={line.gang_id}"
                    if props["apply_href"] and not receipt
                    else "",
                }
    return props


@dataclass(frozen=True)
class CycleHistoryGang:
    name: str
    state: str
    receipt_href: str = ""
    review_href: str = ""
    view_href: str = ""


@dataclass(frozen=True)
class CycleHistoryEntry:
    label: str
    started: datetime
    ended: datetime | None
    gangs: list[CycleHistoryGang]


def cycle_history_entries(cycles, memberships, *, actor, campaign):
    """Historical memberships and frozen receipts preserve each cycle's context."""
    entries = []
    active = {str(member.gang_id) for member in memberships if member.left is None}
    arbitrating = actor.pk == campaign.owner_id and not campaign.archived
    for cycle in cycles:
        receipts = {
            str(receipt.gang_id): receipt for receipt in cycle.resolutions.all()
        }
        present = {
            str(member.gang_id): member.gang.name
            for member in memberships
            if (cycle.ended is None or member.created <= cycle.ended)
            and (member.left is None or member.left > cycle.started)
        }
        present.update(
            {key: receipt.snapshot["gang"] for key, receipt in receipts.items()}
        )
        gangs = []
        for key, name in sorted(present.items(), key=lambda item: (item[1], item[0])):
            receipt = receipts.get(key)
            if receipt:
                state = "Applied"
            elif cycle.ended:
                state = "Not applied before the cycle ended"
            elif key in active:
                state = "Pending"
            else:
                state = "Not applied before leaving the campaign"
            gangs.append(
                CycleHistoryGang(
                    name=name,
                    state=state,
                    receipt_href=reverse(
                        "n26-cycle-receipt", args=[campaign.pk, receipt.pk]
                    )
                    if receipt
                    else "",
                    review_href=f"{reverse('n26-cycle-rewards', args=[campaign.pk, cycle.pk])}?gang={key}"
                    if arbitrating and not cycle.ended and not receipt and key in active
                    else "",
                    view_href=f"{reverse('n26-cycle-rewards', args=[campaign.pk, cycle.pk])}?gang={key}"
                    if not cycle.ended and not receipt and key in active
                    else "",
                )
            )
        entries.append(
            CycleHistoryEntry(cycle.label, cycle.started, cycle.ended, gangs)
        )
    return entries
