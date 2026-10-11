"""Baseline Income and supported standing territory benefits.

This seed adds numeric contributions while an asset is held. Recruitment,
equipment rewards, cycle actions and battlefield effects have no executor here.
Existing authored content is preserved: only absent assets and contributions
are created, and every conflict is reported. All additions are staged, which
controls discovery but does not delay effects on gangs already holding an asset.
"""

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.db import transaction

from n26.library.core_campaign import CAMPAIGN_TYPE, REPUTATION, SETTLEMENT
from n26.library.gang_supertypes import SLOT_TYPE, Outcome
from n26.library.income import INCOME, income_modifiers
from n26.library.territory_table import TERRITORY
from n26.write_pause import SCOPE, exclusive_write_scope, write_guard


@dataclass(frozen=True)
class Territory:
    """An asset's source name, baseline Income and expected asset type."""

    name: str
    income: int
    asset_type: str = TERRITORY


TERRITORIES = (
    Territory(SETTLEMENT, 15, SETTLEMENT),
    Territory("Bullet Den", 15),
    Territory("Rogue Doc Shop", 15),
    Territory("Mess Shack", 15),
    Territory("Drinking Hole", 15),
    Territory("Fence Hangout", 15),
    Territory("Bounty Den", 25),
    Territory("Generatorium", 15),
    Territory("Corpse Farm", 25),
    Territory("Tunnels", 20),
    Territory("Tech Bazaar", 15),
    Territory("Promethium Cache", 15),
    Territory("Collapsed Dome", 20),
    Territory("Bone Shrine", 25),
    Territory("Mine Workings", 20),
    Territory("Gambling Den", 15),
    Territory("Synth Still", 20),
    Territory("Old Ruins", 20),
    Territory("Fighting Pit", 25),
    Territory("Slug House", 20),
    Territory("Flesh-makers Theatre", 15),
    Territory("Fight Arena", 15),
    Territory("Amneo-vats", 15),
    Territory("Feasting Hall", 20),
    Territory("Badzone Smelter", 20),
    Territory("Phelynx Pen", 20),
    Territory("Bio-lab", 15),
    Territory("Wyld Den", 15),
    Territory("Rogue Las Factoria", 20),
    Territory("Chem Arena", 15),
    Territory("Shivver Den", 15),
)


@dataclass(frozen=True)
class StandingBoon:
    """A counter contribution, optionally restricted to a Gang supertype."""

    asset: str
    counter: str
    amount: int
    house: str = ""

    @property
    def modifier_name(self):
        condition = f"{self.house} " if self.house else ""
        return f"{self.asset}: {condition}standing {self.counter}"


STANDING_BOONS = (
    StandingBoon("Generatorium", REPUTATION, 1),
    StandingBoon("Gambling Den", REPUTATION, 1),
    StandingBoon("Amneo-vats", INCOME, 10, "Goliath"),
    StandingBoon("Shivver Den", REPUTATION, 1, "Escher"),
)

NOTHING_TO_DO = "Nothing to do: territory Income and standing boons are unchanged."


def _archived(row):
    return row.archived or row.archived_at is not None


def _prerequisite(queryset, label, outcome):
    try:
        row = queryset.get()
    except ObjectDoesNotExist:
        row = None
    except MultipleObjectsReturned:
        outcome.skipped.append(f"skipped territory boons: ambiguous {label}")
        return None
    if row is None:
        outcome.skipped.append(f"skipped territory boons: missing {label}")
    elif _archived(row):
        outcome.skipped.append(f"skipped territory boons: {label} is archived")
        row = None
    return row


def _conditions(scope):
    return [
        condition
        for relation in scope.CONDITIONS
        for condition in getattr(scope, relation).all()
    ]


def _same_contribution(row, counter, amount, pick=None):
    """Check every scope, effect and condition before treating an effect as present."""
    from n26.library.models import GangHasPickable
    from n26.library.models.modifier import EFFECT_FIELDS, SCOPE_FIELDS

    if (
        row.pack_id != counter.pack_id
        or row.targets_gang_id is None
        or row.contributes_to_counter_id is None
        or any(
            getattr(row, f"{field}_id") is not None
            for field in SCOPE_FIELDS
            if field != "targets_gang"
        )
        or any(
            getattr(row, f"{field}_id") is not None
            for field in EFFECT_FIELDS
            if field != "contributes_to_counter"
        )
    ):
        return False
    scope, effect = row.targets_gang, row.contributes_to_counter
    if scope.echoes or effect.counter_id != counter.pk or effect.amount != amount:
        return False
    conditions = _conditions(scope)
    if pick is None:
        return not conditions
    return (
        len(conditions) == 1
        and isinstance(conditions[0], GangHasPickable)
        and not conditions[0].negate
        and list(conditions[0].pickables.values_list("pk", flat=True)) == [pick.pk]
    )


def _same_counter(row, counter):
    if row.contributes_to_counter_id is None:
        return False
    other = row.contributes_to_counter.counter
    return not other.qualifier and other.name.casefold() == counter.name.casefold()


def _occupied_name(pack, name, outcome):
    from n26.library.models import Modifier

    if Modifier.objects.filter(pack=pack, name__iexact=name).exists():
        outcome.skipped.append(
            f"skipped modifier {name}: its name is already used by existing content"
        )
        return True
    return False


def _has_authored_graph(asset, modifiers=None):
    """Preserve indirect authored effects without evaluating their graph.

    Any first edge is enough to refuse a new contribution. We never descend
    through grants or choices, so authored cycles also stay unchanged.
    """
    if asset.built_ins_id is not None:
        return True
    carried = asset.modifiers.all() if modifiers is None else modifiers
    return any(
        row.adds_assignable_id is not None
        or row.removes_assignable_id is not None
        or row.offers_choice_id is not None
        for row in carried
    )


def _baseline(asset, entry, counter, outcome):
    from n26.library.authoring import revise, set_income

    standing = income_modifiers(asset)
    if standing:
        if (
            len(standing) != 1
            or _archived(standing[0])
            or not _same_contribution(standing[0], counter, entry.income)
        ):
            outcome.skipped.append(
                f"skipped baseline Income for {entry.name}: its existing "
                "contributions or archive state differ"
            )
        else:
            from n26.library.models import Modifier

            expected_name = f"{asset.name}: income"
            if (
                Modifier.objects.filter(pack=asset.pack, name__iexact=expected_name)
                .exclude(pk=standing[0].pk)
                .exists()
            ):
                _occupied_name(asset.pack, expected_name, outcome)
        return
    if _has_authored_graph(asset):
        outcome.skipped.append(
            f"skipped baseline Income for {entry.name}: its existing grants, "
            "choices or built-ins are authored"
        )
        return
    name = f"{asset.name}: income"
    if _occupied_name(asset.pack, name, outcome):
        return
    row = set_income(asset, entry.income)
    revise(row, staged=True)
    outcome.created.append(
        f"added baseline Income {entry.income} to {entry.name}, staged"
    )


def _house_pick(pack, house, outcome):
    from n26.library.models import Pickable

    pick = Pickable.objects.filter(
        pack=pack,
        name__iexact=house,
        qualifier__iexact=SLOT_TYPE,
        slot_type__pack=pack,
        slot_type__name__iexact=SLOT_TYPE,
    ).first()
    if pick is None or _archived(pick) or _archived(pick.slot_type):
        outcome.skipped.append(
            f"skipped {house} standing boon: missing or archived Gang supertype pick"
        )
        return None
    return pick


def _standing(asset, entry, counter, pack, outcome):
    from n26.library.authoring import (
        ef_contributes_to_counter,
        has_gang_pickable,
        modifier,
        targets_gang_alone,
    )

    pick = _house_pick(pack, entry.house, outcome) if entry.house else None
    if entry.house and pick is None:
        return
    carried = list(asset.modifiers.all())
    baseline = income_modifiers(asset, carried) if entry.counter == INCOME else []
    candidates = [
        row for row in carried if _same_counter(row, counter) and row not in baseline
    ]
    if candidates:
        if (
            len(candidates) != 1
            or _archived(candidates[0])
            or not _same_contribution(candidates[0], counter, entry.amount, pick)
        ):
            outcome.skipped.append(
                f"skipped modifier {entry.modifier_name}: its existing "
                "contributions or archive state differ"
            )
        else:
            from n26.library.models import Modifier

            if (
                Modifier.objects.filter(pack=pack, name__iexact=entry.modifier_name)
                .exclude(pk=candidates[0].pk)
                .exists()
            ):
                _occupied_name(pack, entry.modifier_name, outcome)
        return
    if _has_authored_graph(asset, carried):
        outcome.skipped.append(
            f"skipped modifier {entry.modifier_name}: its existing grants, "
            "choices or built-ins are authored"
        )
        return
    if _occupied_name(pack, entry.modifier_name, outcome):
        return
    conditions = [has_gang_pickable(pick)] if pick is not None else []
    modifier(
        entry.modifier_name,
        targets_gang_alone(*conditions),
        ef_contributes_to_counter(counter, entry.amount),
        attach_to=asset,
        pack=pack,
        staged=True,
    )
    condition = f" for {entry.house} gangs" if entry.house else ""
    outcome.created.append(
        f"added standing {entry.counter} {entry.amount} to {entry.asset}{condition}, staged"
    )


def _seed():
    from n26.library.authoring import create_asset
    from n26.library.models import Asset, AssetType, CampaignType, ContentPack, Counter

    outcome = Outcome()
    pack = _prerequisite(
        ContentPack.objects.filter(slug__iexact=settings.DEFAULT_CONTENT_PACK_SLUG),
        "default content pack",
        outcome,
    )
    if pack is None:
        return outcome
    campaign_type = _prerequisite(
        CampaignType.objects.filter(
            pack=pack, name__iexact=CAMPAIGN_TYPE, qualifier=""
        ),
        CAMPAIGN_TYPE,
        outcome,
    )
    if campaign_type is None:
        return outcome
    types = {}
    for label, ownership in (
        (SETTLEMENT, AssetType.Ownership.POSSESSION),
        (TERRITORY, AssetType.Ownership.HOLDING),
    ):
        asset_type = _prerequisite(
            AssetType.objects.filter(
                campaign_type=campaign_type, label_singular__iexact=label
            ),
            f"{label} asset type",
            outcome,
        )
        if asset_type is not None and (
            asset_type.pack_id != pack.pk or asset_type.ownership != ownership
        ):
            outcome.skipped.append(
                f"skipped territory boons: {label} asset type has a different pack or ownership"
            )
            asset_type = None
        types[label] = asset_type
    counters = {
        name: _prerequisite(
            Counter.objects.filter(pack=pack, name__iexact=name, qualifier=""),
            f"{name} counter",
            outcome,
        )
        for name in (INCOME, REPUTATION)
    }
    if any(row is None for row in (*types.values(), *counters.values())):
        return outcome
    assets = {}
    for entry in TERRITORIES:
        asset = Asset.objects.filter(
            pack=pack, name__iexact=entry.name, qualifier=""
        ).first()
        if asset is not None and (
            _archived(asset) or asset.asset_type_id != types[entry.asset_type].pk
        ):
            outcome.skipped.append(
                f"skipped {entry.name}: its archive state or asset type differs"
            )
            continue
        if asset is None:
            if (
                entry.asset_type == SETTLEMENT
                and campaign_type.built_ins_id is not None
                and _archived(campaign_type.built_ins)
            ):
                outcome.skipped.append(
                    f"skipped {SETTLEMENT}: the campaign built-ins are archived"
                )
                continue
            before_set = campaign_type.built_ins_id
            asset = create_asset(
                entry.name, types[entry.asset_type], pack=pack, staged=True
            )
            outcome.created.append(
                f"created the {entry.name} {entry.asset_type}, staged"
            )
            if entry.asset_type == SETTLEMENT:
                campaign_type.refresh_from_db()
                if before_set is None:
                    outcome.created.append(
                        f"created the {campaign_type.built_ins.name} set"
                    )
                outcome.created.append(f"built the {SETTLEMENT} into {CAMPAIGN_TYPE}")
        assets[entry.name] = asset
        _baseline(asset, entry, counters[INCOME], outcome)
    for entry in STANDING_BOONS:
        if entry.asset in assets:
            _standing(
                assets[entry.asset], entry, counters[entry.counter], pack, outcome
            )
    return outcome


def seed_all():
    """Add absent assets and supported effects in one exclusive transaction."""
    with exclusive_write_scope(SCOPE), write_guard():
        outcome = _seed()
    return outcome.lines if outcome.created else [NOTHING_TO_DO, *outcome.skipped]


class _RolledBack(Exception):
    """Carry the exact seed report out of its rolled-back preview."""


def preview():
    """Run the seed and return its report without retaining any changes."""
    try:
        with transaction.atomic():
            raise _RolledBack(seed_all())
    except _RolledBack as rolled_back:
        return rolled_back.args[0]
