"""Attach typed cycle rewards to unchanged seeded territory choices."""

from django.conf import settings
from django.db import transaction

from n26.library.gang_supertypes import Outcome, supertype_pick
from n26.library.income import INCOME
from n26.library.territory_boon_choices import ALTERNATIVES, _converted
from n26.write_pause import SCOPE, exclusive_write_scope, write_guard

NOTHING_TO_DO = "Nothing to do: territory cycle rewards are unchanged."
RECRUITS = {
    "Settlement": (None, 25, None, ""),
    "Bullet Den": ("Ammo-jack", 30, 1, ""),
    "Rogue Doc Shop": ("Rogue Doc", 30, 1, ""),
    "Mess Shack": ("Slopper", 30, 1, ""),
    "Drinking Hole": ("Hive Watcher", 30, 1, ""),
    "Fence Hangout": ("Dome Runner", 30, 1, ""),
    "Flesh-makers Theatre": ("Forge Patcher", 25, 3, "Goliath"),
    "Wyld Den": ("Wyld Runner", 20, None, "Escher"),
}
EQUIPMENT = {
    "Promethium Cache": ("Hazard suit", 3, ""),
    "Mine Workings": ("Respirator", 2, ""),
    "Rogue Las Factoria": ("Lasgun", 2, "Escher"),
    "Chem Arena": ("Chem-alchemy Elixir", 1, "Escher"),
}


def seed_all(actor=None):
    from n26.library.authoring import (
        ef_offers_cycle_equipment,
        ef_offers_cycle_recruitment,
        has_gang_pickable,
        modifier,
        targets_gang_alone,
    )
    from n26.library.models import (
        Asset,
        Counter,
        Modifier,
        Pickable,
        Profile,
        Wargear,
        Weapon,
    )

    outcome = Outcome()
    with transaction.atomic(), exclusive_write_scope(SCOPE), write_guard():
        pack = {"pack__slug": settings.DEFAULT_CONTENT_PACK_SLUG}
        counter = Counter.objects.filter(**pack, name__iexact=INCOME).first()
        for entry in ALTERNATIVES:
            assets = Asset.objects.filter(
                **pack,
                name__iexact=entry.asset,
                asset_type__label_singular__iexact=entry.asset_type,
            ).unarchived()
            if assets.count() != 1 or counter is None:
                outcome.skipped.append(
                    f"skipped {entry.asset}: missing or ambiguous territory or Income counter"
                )
                continue
            asset = assets.get()
            name = f"{entry.asset}: cycle reward"
            pick = Pickable.objects.filter(
                pack=asset.pack, name__iexact=entry.name, qualifier__iexact=entry.asset
            ).first()
            existing = Modifier.objects.filter(pack=asset.pack, name__iexact=name)
            if existing.exists():
                outcome.skipped.append(
                    f"left {entry.asset}: cycle reward already exists; preserve authored content"
                )
                continue
            if not _converted(asset, entry, counter) or pick is None:
                outcome.skipped.append(
                    f"skipped {entry.asset}: boon choice differs from the seed"
                )
                continue
            if entry.asset in RECRUITS:
                profile_name, discount, maximum, house = RECRUITS[entry.asset]
                profiles = Profile.objects.filter(**pack, hireable=True).unarchived()
                if profile_name:
                    profiles = profiles.filter(name__iexact=profile_name)
                    if profiles.count() != 1:
                        outcome.skipped.append(
                            f"skipped {entry.asset}: missing or ambiguous {profile_name} profile"
                        )
                        continue
                else:
                    profiles = profiles.filter(
                        built_ins__members__subtype__name__iexact="Ganger",
                        built_ins__members__archived=False,
                    ).distinct()
                profiles = list(profiles)
                if not profiles:
                    outcome.skipped.append(f"skipped {entry.asset}: no Ganger profiles")
                    continue
                effect_args = (profiles, discount, maximum)
                summary = f"At cycle end, recruit one eligible fighter with a {discount}-credit discount, to a minimum price of 0 credits."
            else:
                thing_name, quantity, house = EQUIPMENT[entry.asset]
                things = list(
                    Wargear.objects.filter(**pack, name__iexact=thing_name).unarchived()
                ) + list(
                    Weapon.objects.filter(**pack, name__iexact=thing_name).unarchived()
                )
                if len(things) != 1:
                    outcome.skipped.append(
                        f"skipped {entry.asset}: missing or ambiguous {thing_name}"
                    )
                    continue
                effect_args = (things[0], quantity)
                summary = f"At cycle end, add {quantity} {thing_name} to the stash."
            house_pick = supertype_pick(house) if house else None
            if house and house_pick is None:
                outcome.skipped.append(
                    f"skipped {entry.asset}: missing {house} Gang supertype"
                )
                continue
            scope = targets_gang_alone(
                *([has_gang_pickable(house_pick)] if house else [])
            )
            if entry.asset in RECRUITS:
                profiles, discount, maximum = effect_args
                effect = ef_offers_cycle_recruitment(
                    profiles=profiles, discount=discount, maximum=maximum
                )
            else:
                thing, quantity = effect_args
                effect = ef_offers_cycle_equipment(thing, quantity=quantity)
            modifier(
                name,
                scope,
                effect,
                attach_to=pick,
                pack=asset.pack,
                staged=asset.staged,
            )
            pick.summary = summary
            pick.save(update_fields=["summary", "modified"])
            outcome.created.append(f"added {entry.asset}: {entry.name} cycle reward")
    return outcome.lines if outcome.created else [NOTHING_TO_DO, *outcome.skipped]


class _RolledBack(Exception):
    pass


def preview():
    try:
        with transaction.atomic():
            raise _RolledBack(seed_all())
    except _RolledBack as rolled_back:
        return rolled_back.args[0]
