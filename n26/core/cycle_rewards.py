"""One authoritative preview and recorded resolution of a campaign cycle."""

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from uuid import uuid4

from n26.core.campaigns import campaign_operation
from n26.core.card import build_gang_card, build_modifier_index, carriers
from n26.core.cycles import _may_manage
from n26.core.effects import asset_origins, compute_gang, counter_readings
from n26.core.income import asset_assignment_income_sources, holding_income_sources
from n26.core.models import (
    CycleResolution,
    CycleRewardClaim,
    Gang,
    LedgerEvent,
    Miniature,
)
from n26.core.models.ledger import Reason
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
    maximum: int | None = None
    eligible_profiles: tuple = ()


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
        if any(part.amount or part.label != "Base income" for part in source.parts):
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
        if any(part.amount or part.label != "Base income" for part in source.parts):
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


def _recruitment_entries(gang, computed):
    from n26.core.access import gang_collections
    from n26.core.hire import (
        build_entries,
        collection_offers,
        gang_scope_sections,
        supplementary_profiles,
    )

    carried = [
        access.collection
        for access in gang_collections(gang, card=computed.card, computed=computed)
    ]
    sections = gang_scope_sections(
        collection_offers(carried), gang.gang_type, carried, with_cards=False
    )
    entries = [entry for section in sections for entry in section.all_entries()]
    present = {entry.profile.pk for entry in entries}
    entries.extend(
        build_entries(
            [
                profile
                for profile in supplementary_profiles()
                if profile.pk not in present
            ],
            with_cards=False,
        )
    )
    return entries


def _existing_recruits(gang, profiles):
    return Miniature.objects.filter(
        membership__gang=gang,
        membership__archived=False,
        membership__profile_id__in=profiles,
    ).count()


def _additional_lines(gang, computed):
    from n26.core.models import CampaignAsset
    from n26.library.models import OffersCycleRecruitment

    origins = asset_origins(computed.card)
    entries = (
        _recruitment_entries(gang, computed)
        if any(
            isinstance(offer.effect, OffersCycleRecruitment)
            for offer in computed.cycle_rewards
        )
        else []
    )
    existing = (
        Counter(
            str(profile_id)
            for profile_id in Miniature.objects.filter(
                membership__gang=gang, membership__archived=False
            ).values_list("membership__profile_id", flat=True)
        )
        if entries
        else Counter()
    )
    lines = []
    for offer in computed.cycle_rewards:
        effect = offer.effect
        origin = offer.holding or origins.get(offer.root_key)
        if isinstance(origin, CampaignAsset):
            source, name = f"holding:{origin.pk}", str(origin)
        elif origin is not None:
            source, name = f"assignment:{origin.key}", origin.name
        else:
            source, name = f"gang:{gang.pk}:reward:{offer.modifier.pk}", offer.source
        key = f"{source}:reward:{offer.modifier.pk}"
        if isinstance(effect, OffersCycleRecruitment):
            authored = {str(profile.pk) for profile in effect.profiles.all()}
            eligible = [
                entry
                for entry in entries
                if (not authored or str(entry.profile.pk) in authored)
                and (
                    not effect.profile_type_id
                    or entry.profile.profile_type_id == effect.profile_type_id
                )
            ]
            profiles = tuple(
                sorted(authored or {str(entry.profile.pk) for entry in eligible})
            )
            limit = (
                effect.maximum is not None
                and sum(existing.get(profile, 0) for profile in profiles)
                >= effect.maximum
            )
            options = tuple(
                {
                    "key": entry.key,
                    "profile_id": str(entry.profile.pk),
                    "name": entry.name,
                    "list_price": entry.base_price,
                    "discount": min(effect.discount, entry.base_price),
                    "payment": max(0, entry.base_price - effect.discount),
                }
                for entry in eligible
            )
            blocked = (
                "This gang already has the maximum number of these fighters."
                if limit
                else "No eligible fighters are available. Skip this reward or update its content."
                if not options
                else ""
            )
            lines.append(
                RewardLine(
                    key=key,
                    source=source,
                    name=name,
                    kind="recruitment",
                    options=options,
                    blocked=blocked,
                    maximum=effect.maximum,
                    eligible_profiles=profiles,
                )
            )
        else:
            thing = effect.thing
            lines.append(
                RewardLine(
                    key=key,
                    source=source,
                    name=name,
                    kind="equipment",
                    quantity=effect.quantity,
                    thing_id=str(thing.pk),
                    thing_kind="weapon" if effect.weapon_id else "wargear",
                    parts=({"label": str(thing), "amount": effect.quantity},),
                )
            )
    return list({line.key: line for line in lines}.values())


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
                    str(gang.pk),
                    gang.name,
                    None if gang.credits_unlimited else gang.credits,
                    receipt_id=str(receipt.pk),
                )
            )
            continue
        card = build_gang_card(gang, with_statlines=False)
        index = build_modifier_index(carriers(card, *card.members.values()))
        computed = compute_gang(card, index)
        lines = [*_income_lines(gang, computed), *_additional_lines(gang, computed)]
        lines = [replace(line, claimed=claims.get(line.source, "")) for line in lines]
        gangs.append(
            GangRewards(
                str(gang.pk),
                gang.name,
                None if gang.credits_unlimited else gang.credits,
                lines,
            )
        )
    plan = CyclePlan(str(cycle.pk), cycle.label, gangs)
    plan.token = hashlib.sha256(
        json.dumps(plan.props(), sort_keys=True).encode()
    ).hexdigest()
    return plan


def _apply_line(op, line, selection):
    from n26.library.models import Profile, Wargear, Weapon

    if line.kind == "income":
        op.receive_credits(line.amount, f"Cycle boon: {line.name}"[:255])
        return []
    if line.kind == "recruitment":
        chosen = next(
            (
                option
                for option in line.options
                if option["key"] == selection.get("option")
            ),
            None,
        )
        if chosen is None:
            raise Refusal("Choose an eligible fighter for this reward.")
        name = (
            selection.get("name", "").strip()
            if isinstance(selection.get("name", ""), str)
            else ""
        )
        if not name or len(name) > 200:
            raise Refusal("Enter a fighter name of 200 characters or fewer.")
        if (
            line.maximum is not None
            and _existing_recruits(op.gang, line.eligible_profiles) >= line.maximum
        ):
            raise Refusal("This gang already has the maximum number of these fighters.")
        profile = Profile.objects.get(pk=chosen["profile_id"])
        miniature = op.hire(
            profile,
            name,
            paid=chosen["payment"],
            list_price=chosen["list_price"],
            discount=chosen["discount"],
            rating=profile.reference_price(),
            reason=Reason.REWARD,
            note=f"Cycle boon: {line.name}"[:255],
        )
        return [str(miniature.pk)]
    if line.kind == "equipment":
        thing = (Weapon if line.thing_kind == "weapon" else Wargear).objects.get(
            pk=line.thing_id
        )
        return [
            str(
                op.buy(
                    op.gang.stash,
                    thing=thing,
                    paid=0,
                    list_price=thing.reference_price(),
                    discount=thing.reference_price(),
                    rating=thing.reference_price(),
                    reason=Reason.REWARD,
                    note=f"Cycle boon: {line.name}"[:255],
                ).pk
            )
            for _ in range(line.quantity)
        ]
    raise Refusal("This reward is not supported for automatic application.")


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
            if not isinstance(rows, dict):
                raise Refusal("Review the reward selection before applying it.")
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
                    chosen = next(
                        (
                            option
                            for option in line.options
                            if option["key"] == selection.get("option")
                        ),
                        None,
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
                            "selection": selection,
                            "selected_option": chosen,
                        }
                    )
                op.event(
                    gang,
                    LedgerEvent.Kind.CYCLE_RESOLVED,
                    note=(f"{cycle.label}" + (f": {comment}" if comment else ""))[:255],
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
                        "credits_before": None
                        if gang.credits_unlimited
                        else gang.credits,
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
            receipt.snapshot["credits_after"] = (
                None if gang.credits_unlimited else gang.credits
            )
            receipt.save(update_fields=["snapshot", "modified"])
            receipts.append(receipt)
        return receipts
