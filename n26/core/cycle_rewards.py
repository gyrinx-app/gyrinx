"""One authoritative preview and recorded resolution of a campaign cycle."""

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from uuid import uuid4

from n26.core.campaigns import campaign_operation
from n26.core.card import build_gang_cards, build_modifier_index, carriers
from n26.core.cycles import _may_manage
from n26.core.effects import asset_origins, compute_gang, counter_readings
from n26.core.income import asset_assignment_income_sources, holding_income_sources
from n26.core.models import (
    CampaignAsset,
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
    eligible_profile_type: str = ""


@dataclass
class GangRewards:
    gang_id: str
    name: str
    credits: int | None
    lines: list[RewardLine] = field(default_factory=list)
    receipt_id: str = ""
    sources: tuple = ()


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


def _recruitment_entries(gang, computed, cache):
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
    key = (gang.gang_type_id, tuple(collection.pk for collection in carried))
    if key in cache:
        return cache[key]
    sections = gang_scope_sections(
        collection_offers(carried), gang.gang_type, carried, with_cards=False
    )
    entries = [entry for section in sections for entry in section.all_entries()]
    present = {entry.profile.pk for entry in entries}
    if "supplementary" not in cache:
        cache["supplementary"] = build_entries(
            supplementary_profiles(), with_cards=False
        )
    entries.extend(
        entry for entry in cache["supplementary"] if entry.profile.pk not in present
    )
    cache[key] = entries
    return entries


def _existing_recruits(gang, line):
    models = Miniature.objects.filter(membership__gang=gang, membership__archived=False)
    if line.eligible_profiles:
        models = models.filter(membership__profile_id__in=line.eligible_profiles)
    if line.eligible_profile_type:
        models = models.filter(
            membership__profile__profile_type_id=line.eligible_profile_type
        )
    return models.count()


def _additional_lines(gang, computed, existing, entry_cache):
    from n26.core.models import CampaignAsset
    from n26.library.models import OffersCycleRecruitment

    origins = asset_origins(computed.card)
    entries = (
        _recruitment_entries(gang, computed, entry_cache)
        if any(
            isinstance(offer.effect, OffersCycleRecruitment)
            for offer in computed.cycle_rewards
        )
        else []
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
            profiles = tuple(sorted(authored))
            profile_type = str(effect.profile_type_id) if effect.profile_type_id else ""
            matching = sum(
                count
                for (profile_id, type_id), count in existing.items()
                if (not profiles or profile_id in profiles)
                and (not profile_type or type_id == profile_type)
            )
            limit = effect.maximum is not None and matching >= effect.maximum
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
                    eligible_profile_type=profile_type,
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
    memberships = list(
        cycle.campaign.memberships.filter(left__isnull=True)
        .select_related("gang__gang_type")
        .order_by("gang__name", "gang_id")
    )
    pending = [
        membership.gang
        for membership in memberships
        if str(membership.gang_id) not in resolutions
    ]
    holdings = {}
    for holding in CampaignAsset.objects.filter(
        holder__gang__in=pending, holder__left__isnull=True
    ).select_related(
        "holder", "asset__asset_type", "income_override__contributes_to_counter"
    ):
        holdings.setdefault(holding.holder.gang_id, []).append(holding)
    cards = build_gang_cards(pending, holdings, with_members=True)
    index = build_modifier_index(
        carriers(
            *(
                card
                for gang_card in cards.values()
                for card in (gang_card, *gang_card.members.values())
            )
        )
    )
    existing = {gang.pk: Counter() for gang in pending}
    for gang_id, profile_id, profile_type_id in Miniature.objects.filter(
        membership__gang__in=pending, membership__archived=False
    ).values_list(
        "membership__gang_id",
        "membership__profile_id",
        "membership__profile__profile_type_id",
    ):
        existing[gang_id][(str(profile_id), str(profile_type_id))] += 1
    entry_cache = {}
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
        card = cards[gang.pk]
        computed = compute_gang(card, index)
        lines = [
            *_income_lines(gang, computed),
            *_additional_lines(gang, computed, existing[gang.pk], entry_cache),
        ]
        lines = [replace(line, claimed=claims.get(line.source, "")) for line in lines]
        sources = (
            {f"holding:{holding.pk}" for holding in card.holdings}
            | {f"assignment:{key}" for key in asset_assignment_income_sources(computed)}
            | {line.source for line in lines}
        )
        gangs.append(
            GangRewards(
                str(gang.pk),
                gang.name,
                None if gang.credits_unlimited else gang.credits,
                lines,
                sources=tuple(sorted(sources - claims.keys())),
            )
        )
    plan = CyclePlan(str(cycle.pk), cycle.label, gangs)
    plan.token = json.dumps(
        {
            gang.gang_id: hashlib.sha256(
                json.dumps(
                    {
                        "cycle_id": plan.cycle_id,
                        "label": plan.label,
                        "gang": asdict(gang),
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            for gang in plan.gangs
        },
        sort_keys=True,
    )
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
            raise Refusal("Enter a model name of 200 characters or fewer.")
        if (
            line.maximum is not None
            and _existing_recruits(op.gang, line) >= line.maximum
        ):
            raise Refusal("This gang already has the maximum number of these fighters.")
        profile = Profile.objects.get(pk=chosen["profile_id"])
        miniature = op.hire(
            profile,
            name,
            paid=chosen["payment"],
            list_price=chosen["list_price"],
            discount=chosen["discount"],
            rating=chosen["list_price"],
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
        try:
            reviewed = json.loads(token)
        except ValueError, TypeError:
            reviewed = None
        current = json.loads(plan.token)
        if not isinstance(reviewed, dict) or any(
            key not in current or reviewed.get(key) != current[key] for key in ids
        ):
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
            credits_before = None if gang.credits_unlimited else gang.credits
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
            gang.refresh_from_db()
            receipt = CycleResolution.objects.create(
                cycle=cycle,
                gang=gang,
                actor=actor,
                comment=comment,
                batch=batch,
                snapshot={
                    "label": cycle.label,
                    "gang": gang.name,
                    "credits_before": credits_before,
                    "credits_after": None if gang.credits_unlimited else gang.credits,
                    "lines": recorded,
                },
            )
            for source in reward.sources:
                CycleRewardClaim.objects.create(
                    cycle=cycle, resolution=receipt, source=source
                )
            receipts.append(receipt)
        return receipts
