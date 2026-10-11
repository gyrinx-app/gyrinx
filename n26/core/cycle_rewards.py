"""One authoritative preview and recorded resolution of a campaign cycle."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from uuid import uuid4

from n26.core.campaigns import campaign_operation
from n26.core.card import build_gang_card, build_modifier_index, carriers
from n26.core.cycles import _may_manage
from n26.core.effects import compute_gang, counter_readings
from n26.core.income import asset_assignment_income_sources, holding_income_sources
from n26.core.models import CycleResolution, CycleRewardClaim, Gang, LedgerEvent
from n26.core.operations import Refusal, operation
from n26.library.income import is_income_counter


@dataclass(frozen=True)
class RewardLine:
    key: str
    source: str
    name: str
    kind: str
    amount: int = 0
    parts: tuple = ()
    options: tuple = ()
    quantity: int = 0
    thing_id: str = ""
    thing_kind: str = ""
    blocked: str = ""
    claimed: str = ""


@dataclass
class GangRewards:
    gang_id: str
    name: str
    credits: int | None
    lines: list[RewardLine] = field(default_factory=list)
    receipt_id: str = ""


@dataclass
class CyclePlan:
    cycle_id: str
    label: str
    gangs: list[GangRewards]
    token: str = ""

    def props(self):
        return asdict(self)


def pending_gangs(cycle):
    resolved = cycle.resolutions.values_list("gang_id", flat=True)
    return list(
        cycle.campaign.memberships.filter(left__isnull=True)
        .exclude(gang_id__in=resolved)
        .select_related("gang")
        .order_by("gang__name")
    )


def _income_lines(gang, computed):
    lines = []
    held = holding_income_sources(computed)
    owned = asset_assignment_income_sources(computed)
    for (holding_id, _revision), source in held.items():
        if source.parts:
            key = f"holding:{holding_id}"
            lines.append(
                RewardLine(
                    key=key,
                    source=key,
                    name=source.name,
                    kind="income",
                    amount=source.value,
                    parts=tuple(asdict(part) for part in source.parts),
                )
            )
    for node_key, source in owned.items():
        if source.parts:
            key = f"assignment:{node_key}"
            lines.append(
                RewardLine(
                    key=key,
                    source=key,
                    name=source.name,
                    kind="income",
                    amount=source.value,
                    parts=tuple(asdict(part) for part in source.parts),
                )
            )
    total = sum(
        reading.value
        for reading in counter_readings(computed.card, computed)
        if is_income_counter(reading.thing)
    )
    other = total - sum(line.amount for line in lines)
    if other:
        key = f"gang:{gang.pk}:income"
        lines.append(
            RewardLine(
                key=key, source=key, name="Other income", kind="income", amount=other
            )
        )
    return lines


def _additional_lines(gang, computed):
    return []


def preview_cycle(cycle):
    from dataclasses import replace

    resolutions = {str(receipt.gang_id): receipt for receipt in cycle.resolutions.all()}
    claims = {
        claim.source: claim.resolution.gang.name
        for claim in cycle.claims.select_related("resolution__gang")
    }
    gangs = []
    memberships = (
        cycle.campaign.memberships.filter(left__isnull=True)
        .select_related("gang__gang_type")
        .order_by("gang__name", "gang_id")
    )
    for membership in memberships:
        gang = membership.gang
        receipt = resolutions.get(str(gang.pk))
        if receipt:
            gangs.append(
                GangRewards(
                    str(gang.pk), gang.name, gang.credits, receipt_id=str(receipt.pk)
                )
            )
            continue
        card = build_gang_card(gang, with_statlines=False)
        index = build_modifier_index(carriers(card, *card.members.values()))
        computed = compute_gang(card, index)
        lines = [*_income_lines(gang, computed), *_additional_lines(gang, computed)]
        lines = [replace(line, claimed=claims.get(line.source, "")) for line in lines]
        gangs.append(GangRewards(str(gang.pk), gang.name, gang.credits, lines))
    plan = CyclePlan(str(cycle.pk), cycle.label, gangs)
    plan.token = hashlib.sha256(
        json.dumps(plan.props(), sort_keys=True).encode()
    ).hexdigest()
    return plan


def _apply_line(op, line, selection):
    if line.kind != "income":
        raise Refusal("This reward is not supported for automatic application.")
    op.receive_credits(line.amount, f"Cycle boon: {line.name}")
    return []


def apply_cycle(cycle, *, actor, token, selections):
    """Apply a checked preview atomically, including explicit skipped rewards."""
    with campaign_operation(cycle.campaign, actor=actor) as act:
        _may_manage(act.campaign, actor)
        cycle.refresh_from_db()
        if cycle.ended is not None:
            raise Refusal("This cycle has ended. Review the current cycle's boons.")
        ids = list(selections)
        if not ids:
            raise Refusal("Select at least one gang.")
        members = act.campaign.memberships.filter(left__isnull=True, gang_id__in=ids)
        if members.count() != len(ids):
            raise Refusal("Select gangs currently in this campaign.")
        # Campaign operations use a no-key lock; gang operations keep their existing ordering.
        gangs = list(Gang.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
        plan = preview_cycle(cycle)
        if plan.token != token:
            raise Refusal(
                "The rewards changed. Refresh the preview before applying them."
            )
        by_gang = {reward.gang_id: reward for reward in plan.gangs}
        receipts = []
        for gang in gangs:
            reward = by_gang[str(gang.pk)]
            if reward.receipt_id:
                raise Refusal(
                    "This gang's boons have already been resolved for this cycle."
                )
            submitted = selections[str(gang.pk)]
            rows = submitted.get("lines", {})
            keys = {line.key for line in reward.lines}
            if set(rows) != keys:
                raise Refusal("The reward selection changed. Refresh the preview.")
            comment = submitted.get("comment", "")
            if not isinstance(comment, str) or len(comment) > 255:
                raise Refusal("Enter a comment of 255 characters or fewer.")
            batch = uuid4()
            recorded = []
            with operation(gang, actor=actor, batch=batch) as op:
                for line in reward.lines:
                    selection = rows[line.key]
                    if not isinstance(selection, dict) or not isinstance(
                        selection.get("skip"), bool
                    ):
                        raise Refusal("Select which rewards to skip.")
                    skipped = selection["skip"]
                    if line.blocked and not skipped and not line.claimed:
                        raise Refusal(line.blocked)
                    written = (
                        []
                        if skipped or line.claimed
                        else _apply_line(op, line, selection)
                    )
                    recorded.append(
                        {
                            **asdict(line),
                            "status": "claimed"
                            if line.claimed
                            else "skipped"
                            if skipped
                            else "applied",
                            "created": written,
                        }
                    )
                op.event(
                    gang,
                    LedgerEvent.Kind.CYCLE_RESOLVED,
                    note=f"{cycle.label}" + (f": {comment}" if comment else ""),
                )
                receipt = CycleResolution.objects.create(
                    cycle=cycle,
                    gang=gang,
                    actor=actor,
                    comment=comment,
                    batch=batch,
                    snapshot={
                        "label": cycle.label,
                        "gang": gang.name,
                        "credits_before": gang.credits,
                        "lines": recorded,
                    },
                )
                for source in {
                    line.source for line in reward.lines if not line.claimed
                }:
                    CycleRewardClaim.objects.create(
                        cycle=cycle, resolution=receipt, source=source
                    )
            gang.refresh_from_db()
            receipt.snapshot["credits_after"] = gang.credits
            receipt.save(update_fields=["snapshot", "modified"])
            receipts.append(receipt)
        return receipts
