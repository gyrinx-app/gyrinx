"""Remove a frozen prelaunch cycle scope while retaining player facts and receipts.

Snapshots use stored fields directly: invalid legacy schedules must not prevent
resetting the prelaunch data. The maintenance boundary supplies the strict flag
check, and the shared write barrier drains both campaign and gang writers.
"""

import hashlib
import json
from dataclasses import dataclass, field

from n26.core.fields import to_ulid
from n26.core.models import (
    ActionRecord,
    Battle,
    Campaign,
    CampaignCycle,
    CampaignCycleCommand,
    CampaignCycleDelivery,
    CampaignCycleTransition,
    CampaignPhase,
    CampaignPlan,
    CampaignSchedule,
    LedgerEvent,
)
from n26.write_pause import SCOPE, exclusive_write_scope

TOMBSTONE = "prelaunch_reset"
MODELS = {
    "campaigns": Campaign,
    "headers": CampaignSchedule,
    "cycles": CampaignCycle,
    "plans": CampaignPlan,
    "phases": CampaignPhase,
    "commands": CampaignCycleCommand,
    "transitions": CampaignCycleTransition,
    "deliveries": CampaignCycleDelivery,
    "battles": Battle,
    "actions": ActionRecord,
    "ledger_events": LedgerEvent,
}
CATALOG = ("transitions", "deliveries", "headers", "cycles", "plans", "phases")


class ResetRefused(Exception):
    """The approved prelaunch scope is unavailable or has changed."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _rows(queryset):
    return json.loads(_json(list(queryset.order_by("pk").values())))


def _ids(rows):
    return [row["id"] for row in rows]


@dataclass(frozen=True)
class ResetPlan:
    rows: dict
    problems: tuple[str, ...] = field(default=())

    @property
    def ok(self):
        return not self.problems

    @property
    def nothing_here(self):
        return not any(self.rows[key] for key in (*CATALOG, "commands"))

    @property
    def fingerprint(self):
        return hashlib.sha256(_json(self.rows).encode()).hexdigest()

    @property
    def counts(self):
        counts = {key: len(rows) for key, rows in self.rows.items()}
        counts["deliveries_pending"] = sum(
            row["delivered_at"] is None for row in self.rows["deliveries"]
        )
        counts["deliveries_delivered"] = (
            counts["deliveries"] - counts["deliveries_pending"]
        )
        return counts

    def preview(self):
        counts = self.counts
        lines = [
            f"Reset cycle data for {counts['campaigns']} campaigns: {counts['plans']} plans, "
            f"{counts['headers']} schedule headers, {counts['cycles']} cycles and {counts['phases']} phases.",
            f"Remove {counts['transitions']} transitions and {counts['deliveries']} deliveries "
            f"({counts['deliveries_pending']} pending, {counts['deliveries_delivered']} delivered).",
            f"Clear cycle attribution from {counts['battles']} battles, {counts['actions']} actions "
            f"and {counts['ledger_events']} ledger events. Keep their other fields and financial totals.",
            f"Retain {counts['commands']} cycle command receipts with kind {TOMBSTONE}.",
            "Keep schedule templates, battle and action receipts, notifications and campaign events.",
        ]
        lines.extend(
            f"Campaign {row['id']}: {row['name']}" for row in self.rows["campaigns"]
        )
        lines.extend(
            f"Plan {row['id']} in campaign {row['campaign_id']}"
            for row in self.rows["plans"]
        )
        return tuple(lines)

    def recorded(self):
        return {"plan": json.loads(_json({"version": 1, "rows": self.rows}))}


def empty_plan():
    return ResetPlan({key: [] for key in MODELS})


def find():
    rows = {
        key: _rows(MODELS[key].objects.all())
        for key in ("headers", "cycles", "plans", "phases", "transitions")
    }
    rows["commands"] = _rows(CampaignCycleCommand.objects.exclude(kind=TOMBSTONE))
    campaign_ids = {row["campaign_id"] for records in rows.values() for row in records}
    rows["campaigns"] = _rows(Campaign.objects.filter(pk__in=campaign_ids))
    rows["deliveries"] = _rows(
        CampaignCycleDelivery.objects.filter(
            transition_id__in=_ids(rows["transitions"])
        )
    )
    cycle_ids = _ids(rows["cycles"])
    for key in ("battles", "actions", "ledger_events"):
        rows[key] = _rows(MODELS[key].objects.filter(cycle_id__in=cycle_ids))
    return ResetPlan(rows)


def _approved(data):
    try:
        if (
            not isinstance(data, dict)
            or set(data) != {"version", "rows"}
            or type(data["version"]) is not int
            or data["version"] != 1
        ):
            raise ValueError
        rows = data["rows"]
        if not isinstance(rows, dict) or rows.keys() != MODELS.keys():
            raise ValueError
        for records in rows.values():
            if not isinstance(records, list):
                raise ValueError
            for row in records:
                if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                    raise ValueError
                to_ulid(row["id"])
            if len(set(_ids(records))) != len(records):
                raise ValueError
    except ValueError, TypeError, KeyError:
        raise ResetRefused(
            "Prepare and review a new prelaunch cycle reset preview."
        ) from None
    return ResetPlan(json.loads(_json(rows)))


def _already_reset(plan):
    if any(
        MODELS[key].objects.filter(pk__in=_ids(plan.rows[key])).exists()
        for key in CATALOG
    ):
        return False
    commands = _ids(plan.rows["commands"])
    return CampaignCycleCommand.objects.filter(
        pk__in=commands, kind=TOMBSTONE
    ).count() == len(commands)


def apply(approved, *, require_disabled):
    """Apply only the approved raw scope, atomically and behind the edition barrier."""
    plan = _approved(approved)
    with exclusive_write_scope(SCOPE):
        require_disabled()
        if _already_reset(plan):
            return ("The captured prelaunch cycle data was already reset.",)
        list(
            Campaign.objects.select_for_update()
            .filter(pk__in=_ids(plan.rows["campaigns"]))
            .order_by("pk")
        )
        if find().rows != plan.rows:
            raise ResetRefused(
                "Campaign cycle data changed after the preview. Prepare and review a new preview."
            )
        cycle_ids = _ids(plan.rows["cycles"])
        for key in ("battles", "actions", "ledger_events"):
            changed = (
                MODELS[key]
                .objects.filter(pk__in=_ids(plan.rows[key]), cycle_id__in=cycle_ids)
                .update(cycle=None)
            )
            if changed != len(plan.rows[key]):
                raise ResetRefused(
                    "Cycle attribution changed during the reset. Nothing was reset."
                )
        changed = CampaignCycleCommand.objects.filter(
            pk__in=_ids(plan.rows["commands"])
        ).update(kind=TOMBSTONE)
        if changed != len(plan.rows["commands"]):
            raise ResetRefused(
                "Cycle command receipts changed during the reset. Nothing was reset."
            )
        for key in ("transitions", "headers", "cycles", "plans", "phases"):
            MODELS[key].objects.filter(pk__in=_ids(plan.rows[key])).delete()
    return plan.preview()
