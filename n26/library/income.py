"""Read asset Income from ordinary gang-scoped counter contributions.

A direct modifier or declared Income option contributes to the system Income
counter. Gang readings include these and other applicable modifiers.
Credit collection remains manual.

Authoring's Income field uses ``set_income``; these readers recover the amount
from the same modifiers. Resolve the counter by case-insensitive name and an
empty qualifier in the system pack.
"""

from django.conf import settings

INCOME = "Income"

#: What the Income box says on every form that asks it: the asset's
#: authoring page, the campaign type's page, the arbitrator's own.
INCOME_HELP = "Contributes to the gang's Income counter. Collect credits manually."


def is_income_counter(counter):
    """Whether this counter is the Income counter, by its natural key."""
    return counter.qualifier == "" and counter.name.casefold() == INCOME.casefold()


def income_counter():
    """The system pack's Income counter, or None where no seed has run."""
    from n26.library.models import Counter

    return Counter.objects.filter(
        pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG,
        name__iexact=INCOME,
        qualifier="",
    ).first()


def ensure_income_counter():
    """Create the system Income counter if missing, matching its name case-insensitively."""
    from n26.library.models import Counter
    from n26.library.models.pack import get_default_pack

    found = income_counter()
    if found is None:
        found = Counter.objects.create(pack=get_default_pack(), name=INCOME)
    return found


def is_income_contribution(modifier):
    """Identify an unconditional gang-scoped contribution to the system Income counter.

    Load the effect, counter and scope conditions together for bulk reads;
    ``with_income`` supplies those relations. Conditional contributions apply
    through the effects engine but do not count as the asset's base income.
    """
    if modifier.targets_gang_id is None or modifier.contributes_to_counter_id is None:
        return False
    if modifier.targets_gang.is_conditional:
        return False
    return getattr(
        modifier.contributes_to_counter, "per_counter_id", None
    ) is None and is_income_counter(modifier.contributes_to_counter.counter)


def _modifiers(asset, modifiers):
    return asset.modifiers.all() if modifiers is None else modifiers


def income_modifiers(asset, modifiers=None):
    """The declared base contribution, or the asset's direct base modifiers."""
    if getattr(asset, "base_income_modifier_id", None):
        return [asset.base_income_modifier]
    return [row for row in _modifiers(asset, modifiers) if is_income_contribution(row)]


def income_of(asset, modifiers=None):
    """Sum an asset's Income contributions, defaulting to zero.

    Pass preloaded ``modifiers`` or use ``with_income`` to avoid an extra query.
    """
    return sum(
        row.contributes_to_counter.amount for row in income_modifiers(asset, modifiers)
    )


def boons_of(asset, modifiers=None):
    """The asset's modifiers other than its income: what holding it does
    beyond the base figure."""
    rows = list(_modifiers(asset, modifiers))
    baseline = {row.pk for row in income_modifiers(asset, rows)}
    return [row for row in rows if row.pk not in baseline]


def with_income(assets):
    """An asset queryset with what ``income_of`` reads loaded, so a page
    listing many assets pays one query for all their figures."""
    from django.db.models import Prefetch

    from n26.library.models import Modifier

    return assets.select_related(
        "base_income_modifier__contributes_to_counter__counter",
        "base_income_modifier__targets_gang",
    ).prefetch_related(
        "base_income_modifier__targets_gang__has_gang_pickable__pickables",
        Prefetch(
            "modifiers",
            queryset=Modifier.objects.select_related(
                "contributes_to_counter__counter", "targets_gang"
            ).prefetch_related("targets_gang__has_gang_pickable__pickables"),
        ),
    )


def income_modifier_name(asset, Modifier, pack_id):
    """Choose an unused modifier name from the asset name, qualifier and numeric suffix.

    Accept the model class to support historical migration registries.
    """
    from itertools import chain, count

    taken = Modifier.objects.filter(pack=pack_id)
    plain = f"{asset.name}: income"
    qualified = (
        f"{asset.name} ({asset.qualifier}): income" if asset.qualifier else plain
    )
    tries = chain(
        (plain, qualified),
        (f"{qualified} {number}" for number in count(2)),
    )
    return next(name for name in tries if not taken.filter(name__iexact=name).exists())
