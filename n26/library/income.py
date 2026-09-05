"""Income — the system counter a campaign's assets contribute to.

An asset's income is not a figure written on the asset. It is a
modifier the asset carries: a ``TargetsGang`` scope with a
``ContributesToCounter`` effect aimed at the system pack's **Income**
counter, so a gang's Income *reading* is the sum of what it holds —
its Settlement, every Territory it has this cycle — read the way any
counter is read, and drawn wherever counters are drawn. Nothing
collects the reading yet; a later flow will pay it out.

The authoring forms keep a plain Income box. ``authoring.set_income``
writes the modifier behind it; the readers here take the figure back
off the modifiers, so a page prints the same number the author typed.
The Income counter is known by its natural key — a counter called
Income, however cased, with no qualifier — which is how the library
states a counter's identity and how the seed finds one already there.
"""

from django.conf import settings

INCOME = "Income"

#: What the Income box says on every form that asks it: the asset's
#: authoring page, the campaign type's page, the arbitrator's own.
INCOME_HELP = (
    "Credits this asset brings its holder each cycle. Added to the gang's "
    "Income counter. Nothing collects it yet."
)


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
    """The Income counter, created in the system pack where it is missing.

    A test database built from the models has no seed rows, and an author
    writing an asset's income there still needs the counter to aim at.
    Matched without regard to case, as the library's own uniqueness is.
    """
    from n26.library.models import Counter
    from n26.library.models.pack import get_default_pack

    found = income_counter()
    if found is None:
        found = Counter.objects.create(pack=get_default_pack(), name=INCOME)
    return found


def is_income_contribution(modifier):
    """Whether a modifier is an asset's income: gang-scoped, and adding to
    the Income counter. Reads the effect and its counter off the row, so a
    caller loading many should ``select_related`` both."""
    if modifier.targets_gang_id is None or modifier.contributes_to_counter_id is None:
        return False
    return is_income_counter(modifier.contributes_to_counter.counter)


def _modifiers(asset, modifiers):
    return asset.modifiers.all() if modifiers is None else modifiers


def income_modifiers(asset, modifiers=None):
    """The asset's income contributions — one, once ``set_income`` has
    been through, but an author can attach more by hand."""
    return [row for row in _modifiers(asset, modifiers) if is_income_contribution(row)]


def income_of(asset, modifiers=None):
    """What the asset brings its holder each cycle: the sum of its Income
    contributions, 0 where it carries none.

    ``modifiers`` are the asset's modifiers where the caller already holds
    them — the modifier index a card was computed against. Otherwise they
    are read off the asset, which is a query unless prefetched
    (``with_income``).
    """
    return sum(
        row.contributes_to_counter.amount for row in income_modifiers(asset, modifiers)
    )


def boons_of(asset, modifiers=None):
    """The asset's modifiers other than its income: what holding it does
    beyond the figure, for a column that prints the figure separately."""
    return [
        row for row in _modifiers(asset, modifiers) if not is_income_contribution(row)
    ]


def with_income(assets):
    """An asset queryset with what ``income_of`` reads loaded, so a page
    listing many assets pays one query for all their figures."""
    from django.db.models import Prefetch

    from n26.library.models import Modifier

    return assets.prefetch_related(
        Prefetch(
            "modifiers",
            queryset=Modifier.objects.select_related("contributes_to_counter__counter"),
        )
    )


def income_modifier_name(asset, Modifier, pack_id):
    """A name for the asset's Income modifier that nothing else in the
    pack has taken: the asset's name and the word, the qualifier where
    the name alone is spoken for, and a number after that.

    Takes the model class rather than importing it, so a migration can
    hand it the historical one.
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
