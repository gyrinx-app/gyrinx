"""Convert baseline territory Income into an ordinary per-asset choice.

The Income option carries the existing modifier, with its identity and effect
unchanged. Alternatives record a persistent policy with manual cycle rewards;
no recruitment, equipment, credit or post-cycle executor runs here. Existing
owners receive explicit Income picks through ordinary operations. New content
inherits its asset's staging, and authored or shared graphs are reported intact.
"""

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.db import transaction

from n26.library.core_campaign import CAMPAIGN_TYPE, SETTLEMENT
from n26.library.gang_supertypes import Outcome
from n26.library.income import INCOME, income_modifiers, is_income_contribution
from n26.library.territory_boons import _archived, _conditions, _same_contribution
from n26.library.territory_table import TERRITORY
from n26.write_pause import SCOPE, exclusive_write_scope, write_guard


@dataclass(frozen=True)
class Alternative:
    """The numeric baseline and original display copy for one manual policy."""

    asset: str
    income: int
    name: str
    summary: str
    asset_type: str = TERRITORY

    @property
    def slot_type_name(self):
        return f"{self.asset} boon"

    @property
    def picklist_name(self):
        return f"{self.asset} boons"

    @property
    def grant_name(self):
        return f"{self.asset}: boon choice"


ALTERNATIVES = (
    Alternative(
        SETTLEMENT,
        15,
        "Ganger recruitment",
        "At cycle end, resolve a 25-credit ganger recruitment discount manually. "
        "The minimum recruitment price is 0 credits.",
        SETTLEMENT,
    ),
    Alternative(
        "Bullet Den",
        15,
        "Ammo-Jack recruitment",
        "At cycle end, resolve a 30-credit Ammo-Jack recruitment discount manually "
        "if your gang has no Ammo-Jack.",
    ),
    Alternative(
        "Rogue Doc Shop",
        15,
        "Rogue Doc recruitment",
        "At cycle end, resolve a 30-credit Rogue Doc recruitment discount manually "
        "if your gang has no Rogue Doc.",
    ),
    Alternative(
        "Mess Shack",
        15,
        "Slopper recruitment",
        "At cycle end, resolve a 30-credit Slopper recruitment discount manually "
        "if your gang has no Slopper.",
    ),
    Alternative(
        "Drinking Hole",
        15,
        "Hive Watcher recruitment",
        "At cycle end, resolve a 30-credit Hive Watcher recruitment discount manually "
        "if your gang has no Hive Watcher.",
    ),
    Alternative(
        "Fence Hangout",
        15,
        "Dome Runner recruitment",
        "At cycle end, resolve a 30-credit Dome Runner recruitment discount manually "
        "if your gang has no Dome Runner.",
    ),
    Alternative(
        "Promethium Cache",
        15,
        "Hazard suits",
        "At cycle end, add 3 hazard suits manually.",
    ),
    Alternative(
        "Mine Workings",
        20,
        "Respirators",
        "At cycle end, add 2 respirators manually.",
    ),
    Alternative(
        "Flesh-makers Theatre",
        15,
        "Forge Patcher recruitment",
        "At cycle end, resolve a 25-credit Forge Patcher recruitment discount manually "
        "if your gang is Goliath and has fewer than 3 Forge Patchers.",
    ),
    Alternative(
        "Wyld Den",
        15,
        "Wyld Runner recruitment",
        "At cycle end, resolve a 20-credit Wyld Runner recruitment discount manually "
        "if your gang is Escher.",
    ),
    Alternative(
        "Rogue Las Factoria",
        20,
        "Lasguns",
        "At cycle end, add 2 lasguns manually if your gang is Escher.",
    ),
    Alternative(
        "Chem Arena",
        15,
        "Chem-alchemy Elixir",
        "At cycle end, add 1 Chem-alchemy Elixir manually if your gang is Escher.",
    ),
)

NOTHING_TO_DO = "Nothing to do: territory boon choices are unchanged."


def _one(queryset, label, outcome):
    try:
        found = queryset.get()
    except ObjectDoesNotExist:
        outcome.skipped.append(f"skipped territory boon choices: missing {label}")
        return None
    except MultipleObjectsReturned:
        outcome.skipped.append(f"skipped territory boon choices: ambiguous {label}")
        return None
    if _archived(found):
        outcome.skipped.append(f"skipped territory boon choices: {label} is archived")
        return None
    return found


def _sole_carrier(modifier, carrier):
    from n26.library.conversion.base import carriers_of

    carried = carriers_of(modifier)
    return len(carried) == 1 and carried[0] == (type(carrier).__name__, carrier)


def _plain_gang_effect(modifier, effect_field):
    from n26.library.models.modifier import EFFECT_FIELDS, SCOPE_FIELDS

    return (
        modifier.targets_gang_id is not None
        and getattr(modifier, f"{effect_field}_id") is not None
        and not modifier.targets_gang.echoes
        and not _conditions(modifier.targets_gang)
        and all(
            getattr(modifier, f"{field}_id") is None
            for field in SCOPE_FIELDS
            if field != "targets_gang"
        )
        and all(
            getattr(modifier, f"{field}_id") is None
            for field in EFFECT_FIELDS
            if field != effect_field
        )
    )


def _names(entry, pack):
    from n26.library.models import Modifier, Pickable, Picklist, Slot, SlotType

    return (
        SlotType.objects.filter(pack=pack, name__iexact=entry.slot_type_name),
        Picklist.objects.filter(pack=pack, name__iexact=entry.picklist_name),
        Slot.objects.filter(
            pack=pack, name__iexact="Boon", qualifier__iexact=entry.asset
        ),
        Pickable.objects.filter(
            pack=pack, name__iexact=INCOME, qualifier__iexact=entry.asset
        ),
        Pickable.objects.filter(
            pack=pack, name__iexact=entry.name, qualifier__iexact=entry.asset
        ),
        Modifier.objects.filter(pack=pack, name__iexact=entry.grant_name),
    )


def _authored_edges(asset, except_modifier=None):
    if asset.built_ins_id is not None:
        return True
    return any(
        modifier.pk != except_modifier
        and (
            modifier.adds_assignable_id is not None
            or modifier.removes_assignable_id is not None
            or modifier.offers_choice_id is not None
        )
        for modifier in asset.modifiers.all()
    )


def _ordinary_pick(pick, kind, summary):
    return (
        pick.slot_type_id == kind.pk
        and not pick.record_only
        and pick.summary == summary
        and pick.built_ins_id is None
        and pick.category_id is None
        and pick.rating_contribution == 0
        and pick.price == 0
        and pick.trade_point_price is None
        and not pick.is_exclusive
        and not pick.annotation
        and not pick.library_author_help
    )


def _converted(asset, entry, counter):
    """Recognise only the complete graph; partial or edited content is retained."""
    from n26.library.models import AddsAssignable, DefaultAssignment, Slot
    from n26.library.models.modifier import GRANTABLE_FIELDS

    try:
        kind, picklist, slot, income, alternative, grant = (
            candidates.get() for candidates in _names(entry, asset.pack)
        )
    except ObjectDoesNotExist, MultipleObjectsReturned:
        return None
    rows = (kind, picklist, slot, income, alternative, grant)
    if any(_archived(row) for row in rows):
        return None
    baseline = asset.base_income_modifier
    if (
        _archived(baseline)
        or not _same_contribution(baseline, counter, entry.income)
        or not _sole_carrier(baseline, income)
        or list(baseline.income_assets.values_list("pk", flat=True)) != [asset.pk]
        or asset.modifiers.filter(pk=baseline.pk).exists()
        or any(is_income_contribution(row) for row in asset.modifiers.all())
        or _authored_edges(asset, except_modifier=grant.pk)
        or not kind.allows_repeats
        or kind.is_lasting_effect
        or kind.plural_name != entry.picklist_name
        or set(kind.pickables.values_list("pk", flat=True))
        != {income.pk, alternative.pk}
        or list(kind.slots.values_list("pk", flat=True)) != [slot.pk]
        or picklist.slot_type_id != kind.pk
        or picklist.dice
        or picklist.roll_selects
        or list(picklist.slots.values_list("pk", flat=True)) != [slot.pk]
        or slot.slot_type_id != kind.pk
        or slot.picklist_id != picklist.pk
        or slot.mode != Slot.Mode.STANDARD
        or slot.min_picks != 1
        or slot.max_picks != 1
        or slot.assigned_to != Slot.WillBeAssignedTo.GANG
        or slot.hidden
        or slot.follows_status
        or slot.built_ins_id is not None
        or slot.modifiers.exists()
        or slot.interstitial_attachments.exists()
        or not _ordinary_pick(income, kind, "Use this territory's Income contribution.")
        or not _ordinary_pick(alternative, kind, entry.summary)
        or list(income.modifiers.values_list("pk", flat=True)) != [baseline.pk]
        or alternative.modifiers.exists()
        or income.listed_on.exclude(picklist=picklist).exists()
        or alternative.listed_on.exclude(picklist=picklist).exists()
        or not _plain_gang_effect(grant, "adds_assignable")
        or grant.adds_assignable.slot_id != slot.pk
        or grant.adds_assignable.with_pick_id is not None
        or any(
            getattr(grant.adds_assignable, f"{field}_id") is not None
            for field in GRANTABLE_FIELDS
            if field != "slot"
        )
        or not _sole_carrier(grant, asset)
        or AddsAssignable.objects.filter(slot=slot)
        .exclude(pk=grant.adds_assignable_id)
        .exists()
        or DefaultAssignment.objects.filter(slot=slot).exists()
    ):
        return None
    members = list(picklist.members.order_by("position", "pk"))
    if len(members) != 2 or any(_archived(member) for member in members):
        return None
    for position, member, pick in zip(
        (0, 1), members, (income, alternative), strict=True
    ):
        if (
            member.pickable_id != pick.pk
            or member.position != position
            or member.label_override
            or member.roll_low is not None
            or member.roll_high is not None
            or member.level is not None
        ):
            return None
    return slot, income


def _create(asset, entry, baseline):
    from n26.library.authoring import (
        attach_modifiers_to,
        create_pickable,
        create_picklist,
        create_slot,
        create_slot_type,
        detach_modifier,
        ef_adds,
        modifier,
        set_base_income_modifier,
        targets_gang_alone,
    )

    in_pack = {"pack": asset.pack, "staged": asset.staged}
    kind = create_slot_type(
        entry.slot_type_name, plural_name=entry.picklist_name, **in_pack
    )
    income = create_pickable(
        INCOME,
        kind,
        qualifier=entry.asset,
        summary="Use this territory's Income contribution.",
        **in_pack,
    )
    alternative = create_pickable(
        entry.name, kind, qualifier=entry.asset, summary=entry.summary, **in_pack
    )
    picklist = create_picklist(
        entry.picklist_name, kind, members=(income, alternative), **in_pack
    )
    slot = create_slot(
        "Boon", kind, picklist, assigned_to="gang", qualifier=entry.asset, **in_pack
    )
    modifier(
        entry.grant_name,
        targets_gang_alone(),
        ef_adds(slot),
        attach_to=asset,
        **in_pack,
    )
    detach_modifier(asset, baseline)
    attach_modifiers_to(income, [baseline])
    set_base_income_modifier(asset, baseline)
    return slot, income


def _defaults(asset, slot, income, actor, outcome):
    from n26.core.campaigns import campaign_operation
    from n26.core.models import Assignment, CampaignAsset, DismissedOffer
    from n26.core.models.dismissed_offer import (
        GANG_SLOT_HOST,
        holding_slot_key,
        slot_key,
    )
    from n26.core.operations import operation
    from n26.core.reconcile import assert_reconciled

    if asset.is_possession:
        anchors = Assignment.objects.filter(
            asset=asset,
            archived=False,
            removes=False,
            gang__isnull=False,
            gang_root__archived=False,
            miniature_root__isnull=True,
            stash_root__isnull=True,
        ).select_related("gang_root", "gang_root__owner")
    else:
        anchors = CampaignAsset.objects.filter(
            asset=asset,
            holder__left__isnull=True,
            holder__gang__archived=False,
            campaign__archived=False,
        ).select_related("holder__gang__owner", "campaign")
    for anchor in anchors.order_by("pk"):
        if isinstance(anchor, Assignment):
            gang = anchor.gang_root
            recorded = Assignment.objects.filter(
                chosen_for=anchor, chosen_for_slot=slot
            )
            key = slot_key(GANG_SLOT_HOST, anchor.pk, slot.pk)
        else:
            gang = anchor.holder.gang
            recorded = Assignment.objects.filter(
                chosen_for_holding=anchor,
                chosen_for_holding_revision=anchor.ownership_revision,
                chosen_for_slot=slot,
            )
            key = holding_slot_key(anchor, slot.pk)
        # Archived selections and dismissals record the owner's decision too.
        if (
            recorded.exists()
            or DismissedOffer.objects.filter(gang=gang, slot_key=key).exists()
        ):
            assert_reconciled(gang)
            continue
        if isinstance(anchor, Assignment):
            with operation(gang, actor=actor) as op:
                op.choose(anchor, income, slot=slot)
        else:
            with (
                campaign_operation(anchor.campaign, actor=actor),
                operation(gang, actor=actor) as op,
            ):
                op.choose(anchor, income, slot=slot)
        assert_reconciled(gang)
        outcome.created.append(f"selected Income for {asset.name} held by {gang.name}")


def _seed(actor):
    from n26.library.models import (
        Asset,
        AssetType,
        CampaignType,
        ContentPack,
        Counter,
        Modifier,
    )

    outcome = Outcome()
    pack = _one(
        ContentPack.objects.filter(slug__iexact=settings.DEFAULT_CONTENT_PACK_SLUG),
        "default content pack",
        outcome,
    )
    if pack is None:
        return outcome
    campaign = _one(
        CampaignType.objects.filter(
            pack=pack, name__iexact=CAMPAIGN_TYPE, qualifier=""
        ),
        CAMPAIGN_TYPE,
        outcome,
    )
    counter = _one(
        Counter.objects.filter(pack=pack, name__iexact=INCOME, qualifier=""),
        "Income counter",
        outcome,
    )
    if campaign is None or counter is None:
        return outcome
    types = {}
    for label, ownership in (
        (SETTLEMENT, AssetType.Ownership.POSSESSION),
        (TERRITORY, AssetType.Ownership.HOLDING),
    ):
        found = _one(
            AssetType.objects.filter(
                campaign_type=campaign, label_singular__iexact=label
            ),
            f"{label} asset type",
            outcome,
        )
        if found is not None and (
            found.pack_id != pack.pk or found.ownership != ownership
        ):
            outcome.skipped.append(
                f"skipped territory boon choices: {label} has a different pack or ownership"
            )
            found = None
        types[label] = found
    for entry in ALTERNATIVES:
        if types[entry.asset_type] is None:
            continue
        asset = _one(
            Asset.objects.filter(pack=pack, name__iexact=entry.asset, qualifier=""),
            entry.asset,
            outcome,
        )
        if asset is None:
            continue
        if asset.asset_type_id != types[entry.asset_type].pk:
            outcome.skipped.append(f"skipped {entry.asset}: its asset type differs")
            continue
        if Modifier.objects.filter(adds_assignable__asset=asset).exists():
            outcome.skipped.append(
                f"skipped {entry.asset}: an existing modifier grants this asset"
            )
            continue
        if asset.base_income_modifier_id is not None:
            converted = _converted(asset, entry, counter)
            if converted is None:
                outcome.skipped.append(
                    f"skipped {entry.asset}: its declared boon graph differs or is shared"
                )
                continue
            slot, income = converted
        else:
            baselines = income_modifiers(asset)
            if (
                len(baselines) != 1
                or _archived(baselines[0])
                or not _same_contribution(baselines[0], counter, entry.income)
                or not _sole_carrier(baselines[0], asset)
                or baselines[0].income_assets.exists()
                or _authored_edges(asset)
            ):
                outcome.skipped.append(
                    f"skipped {entry.asset}: its baseline Income or authored graph differs or is shared"
                )
                continue
            if any(candidates.exists() for candidates in _names(entry, pack)):
                outcome.skipped.append(
                    f"skipped {entry.asset}: a boon graph name is already used by existing content"
                )
                continue
            slot, income = _create(asset, entry, baselines[0])
            outcome.created.append(
                f"converted {entry.asset} to Income or {entry.name}; rewards are resolved manually"
            )
        _defaults(asset, slot, income, actor, outcome)
    return outcome


def seed_all(actor=None):
    """Convert exact baseline content and current defaults in one transaction."""
    with exclusive_write_scope(SCOPE), write_guard():
        outcome = _seed(actor)
    return outcome.lines if outcome.created else [NOTHING_TO_DO, *outcome.skipped]


class _RolledBack(Exception):
    """Carry the exact report out of a rolled-back preview."""


def preview():
    """Perform the same writes and return their report without retaining them."""
    try:
        with transaction.atomic():
            raise _RolledBack(seed_all())
    except _RolledBack as rolled_back:
        return rolled_back.args[0]
