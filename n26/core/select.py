"""Selectors for in-memory matching and database discovery.

``selector.matches(target)`` checks an adapted card node or content object.
``selector.as_q(for_model)`` compiles a database filter for the queried model;
a trait lookup therefore differs for weapons and weapon profiles.

Database discovery sees printed library content. In-memory matching may
include computed traits and other effective facts, so results can differ.

Combine predicates through All, Any and other combinators. Has accepts an
assignable of any supported kind; adapters and registered lookups provide
kind-specific behaviour. Exactly represents identity as a selector when a
plain foreign-key reference is insufficient.
"""

from dataclasses import dataclass

from django.db.models import Q


def key(thing):
    """A hashable identity for a piece of content: (model label, pk)."""
    return (thing._meta.label_lower, thing.pk)


#: (model being queried, kind of thing possessed) -> lookup path.
#: Growing this is one line; Has.as_q raises clearly when it is missing.
LOOKUPS = {}


def register_lookup(queried_model, thing_model, path):
    LOOKUPS[(queried_model, thing_model)] = path


class NotExpressibleAsQuery(Exception):
    """This selector cannot be compiled to SQL for that model."""


# --- Targets: what selectors match against -------------------------------


@dataclass(frozen=True)
class Matchable:
    """A target with assignable identities and effective counter values for matching.

    assignables contains key results. Adapters decide whether these represent
    printed library facts or computed card facts.
    """

    thing: object
    assignables: frozenset = frozenset()
    #: Counter values the thing holds, keyed by :func:`key` of the
    #: counter — what threshold conditions read.
    counts: tuple = ()
    status: str | None = None

    @property
    def kind(self):
        return type(self.thing)

    def count_of(self, counter):
        return dict(self.counts).get(key(counter), 0)

    def also(self, *things):
        """This matchable with extra possessions — how an adapter layers
        computed facts over printed ones without rebuilding."""
        return Matchable(
            thing=self.thing,
            assignables=self.assignables | {key(thing) for thing in things},
            counts=self.counts,
            status=self.status,
        )

    def counting(self, extra):
        """Add effective counter contributions keyed by counter identity before threshold checks."""
        if not extra:
            return self
        totals = dict(self.counts)
        for counter_key, amount in extra.items():
            totals[counter_key] = totals.get(counter_key, 0) + amount
        return Matchable(
            thing=self.thing,
            assignables=self.assignables,
            counts=tuple(totals.items()),
            status=self.status,
        )


def matchable(thing, assignables=()):
    """Adapt content and its printed traits for matching.

    Callers can supply additional assignable objects; key conversion stays internal.
    """
    owned = {key(assignable) for assignable in assignables}
    if hasattr(thing, "traits"):
        owned |= {key(trait) for trait in thing.traits.all()}
    return Matchable(thing=thing, assignables=frozenset(owned))


# --- Leaves ---------------------------------------------------------------


@dataclass(frozen=True)
class Anything:
    def matches(self, target):
        return True

    def as_q(self, for_model):
        return Q()

    def __str__(self):
        return "anything"


@dataclass(frozen=True)
class HasStatus:
    status: str

    def matches(self, target):
        return target.status == self.status

    def as_q(self, for_model):
        from n26.core.models import Miniature

        if for_model is not Miniature:
            raise NotExpressibleAsQuery("Status belongs to a model.")
        return Q(status=self.status)

    def __str__(self):
        from n26.core.status import Status

        return f"status is {Status(self.status).label}"


@dataclass(frozen=True)
class Has:
    """Match a target possessing the supplied assignable, regardless of its kind."""

    thing: object

    def matches(self, target):
        return key(self.thing) in target.assignables

    def as_q(self, for_model):
        path = LOOKUPS.get((for_model, type(self.thing)))
        if path is None:
            raise NotExpressibleAsQuery(
                f"No lookup registered from {for_model.__name__} to "
                f"{type(self.thing).__name__}. Add one with register_lookup()."
            )
        return Q(**{path: self.thing})

    def __str__(self):
        return f"has {self.thing}"


@dataclass(frozen=True)
class OfKind:
    """Match any target of the supplied assignable kind."""

    model: type

    def matches(self, target):
        return isinstance(target.thing, self.model)

    def as_q(self, for_model):
        if for_model is not self.model:
            raise NotExpressibleAsQuery(
                f"OfKind({self.model.__name__}) can only filter "
                f"{self.model.__name__} querysets, not {for_model.__name__}."
            )
        return Q()

    def choosables(self):
        """The pickable set, as a queryset — what a choice UI shows."""
        return self.model.objects.filter(self.as_q(self.model))

    def __str__(self):
        return f"any {self.model._meta.verbose_name}"


@dataclass(frozen=True)
class Exactly:
    """Match the target's identity to one specific content object.

    Fighter targets use their profile as identity; subtypes use Has instead.
    """

    thing: object

    def matches(self, target):
        if target.thing is None:
            return False
        return key(target.thing) == key(self.thing)

    def as_q(self, for_model):
        if for_model is not type(self.thing):
            raise NotExpressibleAsQuery(
                f"Exactly({self.thing}) can only filter "
                f"{type(self.thing).__name__} querysets."
            )
        return Q(pk=self.thing.pk)

    def __str__(self):
        return f"exactly {self.thing}"


@dataclass(frozen=True)
class HomedIn:
    """Match the target's authored category, using a weapon's category for its profiles.

    Memory and database implementations follow the same relation. Category is
    identity metadata rather than a possession, so this is separate from Has.
    """

    category: object

    def matches(self, target):
        home = getattr(target.thing, "category_id", None)
        if home is None:
            weapon = getattr(target.thing, "weapon", None)
            home = getattr(weapon, "category_id", None)
        return home == self.category.pk

    def as_q(self, for_model):
        from n26.library.models import WeaponProfile

        if issubclass(for_model, WeaponProfile):
            return Q(weapon__category=self.category)
        return Q(category=self.category)

    def __str__(self):
        return f"homed in {self.category.name}"


@dataclass(frozen=True)
class LineOf:
    """Match weapon-profile targets belonging to one specific weapon.

    Exactly would compare profile identity and cannot identify the parent weapon.
    """

    weapon: object

    def matches(self, target):
        return getattr(target.thing, "weapon_id", None) == self.weapon.pk

    def as_q(self, for_model):
        from n26.library.models import WeaponProfile

        if not issubclass(for_model, WeaponProfile):
            raise NotExpressibleAsQuery(
                f"LineOf({self.weapon}) filters weapon profiles, not "
                f"{for_model.__name__} — a line belongs to a weapon."
            )
        return Q(weapon=self.weapon)

    def __str__(self):
        return f"a line of {self.weapon}"


@dataclass(frozen=True)
class TakesSlots:
    """Match weapons by their numeric slot requirement."""

    slots: int

    def matches(self, target):
        return getattr(target.thing, "slots", None) == self.slots

    def as_q(self, for_model):
        return Q(slots=self.slots)

    def __str__(self):
        return f"takes {self.slots} slots"


@dataclass(frozen=True)
class HasTradePointPrice:
    """Match content with a non-null Trading Post price, including zero.

    Exclusive content has no Trade Point price by constraint.
    """

    def matches(self, target):
        return getattr(target.thing, "trade_point_price", None) is not None

    def as_q(self, for_model):
        return Q(trade_point_price__isnull=False)

    def __str__(self):
        return "with a TP price"


@dataclass(frozen=True)
class CounterAtLeast:
    """Match a card's effective counter value against an in-memory threshold.

    Computed contributions count alongside stored balances. This selector has no
    library-query equivalent.
    """

    counter: object
    at_least: int

    def matches(self, target):
        return target.count_of(self.counter) >= self.at_least

    def as_q(self, for_model):
        raise NotExpressibleAsQuery("Counter thresholds are card facts.")

    def __str__(self):
        return f"{self.counter} at {self.at_least}+"


def specificity(selector):
    """Return the selector's evaluation round score.

    Anything scores zero; each leaf condition scores one. Any takes its maximum
    child score and All sums child scores.
    """
    if isinstance(selector, Anything):
        return 0
    if isinstance(selector, Any):
        return max((specificity(child) for child in selector.children), default=0)
    if isinstance(selector, All):
        return sum(specificity(child) for child in selector.children)
    if isinstance(selector, Not):
        return specificity(selector.child)
    return 1


# --- Combinators ----------------------------------------------------------


class _Combinator:
    def __init__(self, *children):
        self.children = children


class Any(_Combinator):
    def matches(self, target):
        return any(child.matches(target) for child in self.children)

    def as_q(self, for_model):
        combined = Q(pk__in=[])  # matches nothing, the OR identity
        for child in self.children:
            combined |= child.as_q(for_model)
        return combined

    def __str__(self):
        return " or ".join(str(child) for child in self.children)


class All(_Combinator):
    def matches(self, target):
        return all(child.matches(target) for child in self.children)

    def as_q(self, for_model):
        combined = Q()
        for child in self.children:
            combined &= child.as_q(for_model)
        return combined

    def __str__(self):
        return " and ".join(str(child) for child in self.children)


class Not:
    def __init__(self, child):
        self.child = child

    def matches(self, target):
        return not self.child.matches(target)

    def as_q(self, for_model):
        return ~self.child.as_q(for_model)

    def __str__(self):
        return f"not ({self.child})"
