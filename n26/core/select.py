"""Selectors — saying "these things" once, for both worlds.

The content library keeps needing to express a selection: a *kind* of thing
(any Specialisation), a *subset* of a kind (weapons with the Melee trait,
later "a Psychoteric Whispers power"), or a *specific* thing. Each place
that needs one used to grow its own filter code. This module is the one
vocabulary, usable in two contexts:

``selector.matches(target)``
    In memory, against a wrapped thing — a card node, a content row.

``selector.as_q(for_model)``
    Compiled to a database filter, for discovery surfaces: pickers, shop
    pages. Relative to the model being queried, because "has trait X" is
    ``traits=x`` when filtering weapon profiles and ``profiles__traits=x``
    when filtering weapons.

**The two contexts may legitimately disagree.** A database query sees the
library as printed; in-memory matching can see computed reality (a trait a
skill added). That is the ownership-vs-card distinction, not a bug.

The matrix that is not here, by design: quantifiers are combinators
(``HasAnyTrait(a, b)`` is spelled ``Any(Has(a), Has(b))``), and ``Has``
takes any assignable because the instance already carries its kind — so
there is one ``Has``, not one per model, and per-kind knowledge lives in
the target adapters and one lookup table instead of a family of classes.

References are not selections: ``AddsAssignable.skill`` and friends stay
plain foreign keys. ``Exactly`` exists for contexts that need "this one"
*as a selection*, not to replace them.
"""

from dataclasses import dataclass

from django.db.models import Q


def key(thing):
    """A hashable identity for a content row: (model label, pk)."""
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
    """A thing plus what it possesses, as selector food.

    ``assignables`` is a frozenset of :func:`key` results. What counts as
    possessed is the *adapter's* decision — a card builds targets whose
    assignables are computed traits; ``matchable`` on a bare content row uses
    what is printed.
    """

    thing: object
    assignables: frozenset = frozenset()
    #: Counter values the thing holds, keyed by :func:`key` of the
    #: counter — what threshold conditions read.
    counts: tuple = ()

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
        )


def matchable(thing, assignables=()):
    """The default adapter: a content row and, if relevant, its printed traits.

    ``assignables`` are content rows the thing possesses beyond what the
    adapter can see for itself — a fighter's subtypes, say. Callers pass
    rows; :func:`key` is internal.
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
class Has:
    """The target possesses this thing — a trait, a skill, a subtype.

    One leaf for every kind: the instance carries its own kind.
    """

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
    """The target is one of these at all — any Specialisation."""

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
    """This one specific thing, as a selection.

    First real use: "(Wyld Runner only)" — an item usable by one fighter
    *entry*. The fighter matchable's thing is their profile, so being that
    entry is an ``Exactly``, where having a subtype is a ``Has``.
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
    """The target's home category is this one.

    Its own leaf rather than a ``Has``, because a home is not a
    possession: every assignable sorts into exactly one category, fixed
    per item, whatever list shows it (see ``n26.library.models.category``).
    This is the sweep's "every Weapon in Auto/Stub Weapons", and the leaf
    family narrowing will reuse — "a Psychoteric Whispers power" is
    ``All(OfKind(Power), HomedIn(whispers))``.
    """

    category: object

    def matches(self, target):
        return getattr(target.thing, "category_id", None) == self.category.pk

    def as_q(self, for_model):
        return Q(category=self.category)

    def __str__(self):
        return f"homed in {self.category.name}"


@dataclass(frozen=True)
class TakesSlots:
    """The target is a weapon taking this many slots.

    The book's asterisk: heavy weapons "marked with *" take two slots,
    and Suspensors fit those alone. A numeric fact, not a possession.
    """

    slots: int

    def matches(self, target):
        return getattr(target.thing, "slots", None) == self.slots

    def as_q(self, for_model):
        return Q(slots=self.slots)

    def __str__(self):
        return f"takes {self.slots} slots"


@dataclass(frozen=True)
class HasTradePointPrice:
    """The target is offered at the Trading Post — a TP price is set.

    Blank means not offered there at all; 0 is a real (free) price, so
    the test is null-ness, never magnitude. Exclusive items carry no TP
    price by constraint, so they fall outside this leaf for free.
    """

    def matches(self, target):
        return getattr(target.thing, "trade_point_price", None) is not None

    def as_q(self, for_model):
        return Q(trade_point_price__isnull=False)

    def __str__(self):
        return "with a TP price"


@dataclass(frozen=True)
class CounterAtLeast:
    """The target's counter has reached this value.

    What lets effects hang off XP: a scope conditioned on
    ``CounterAtLeast(xp, 5)`` reveals a promotion offer the moment the
    tally crosses five, and withdraws it if the value drops. In-memory
    only — thresholds are asked of cards, not of the library.
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
    """How conditional a selector is — what evaluation round it belongs to.

    0 is unconditional (``Anything``): its answer can never depend on
    another modifier's output, so it is safe to evaluate first. Each leaf
    condition scores 1. ``Any`` is alternatives on one axis (max);
    ``All`` stacks conditions (sum). CSS's idea, one integer.
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
