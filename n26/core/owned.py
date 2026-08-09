"""What a model already holds, as a shop listing needs to see it.

A listing asks two questions of a fighter's card. Does this fighter
already own one of these? And if so, what exactly — which copy, worth
what, with what hanging off it — so the reader can sell it, hand it to
somebody else, or take it off the card.

Both answers come off the card the page has already built. Nothing here
queries, which is the whole point: a listing is hundreds of rows, and an
owned-count fetched per row would be hundreds of queries.

A **thing** is a root assignment: the fighter owns it and may re-home it.
A **part** is one of its children — a paid ammo type, a sight bolted to a
gun. A part is sold and removed like anything else, but it cannot be
re-homed on its own: it belongs to the thing it hangs off, and
``Operation.move`` refuses an assignment with a parent for exactly that
reason.

Neither is *anything* the gang holds. Selling, handing on and dropping
are acts on **possessions**, and :func:`is_possession` is the one place
that says what one is — read by the listing that draws the controls and
by the routes behind them, so a screen can never offer what a route
would refuse, nor the other way round.
"""

from dataclasses import dataclass, field

from n26.library.models.assignable import Family


def is_possession(thing):
    """Is this the sort of thing a gang *owns*, rather than something it is?

    Gear is what a model carries, and carrying is what makes a thing
    sellable, movable and droppable. Everything else it holds fails this:
    a profile **is** the model, and parting with one is leaving the
    roster rather than clearing out a kitbag; a skill or a subtype is what
    the model is and knows; a collection is somewhere to shop rather than
    something owned; a counter is a running number; a gang type is the
    gang itself.

    Asked of the library's own families rather than a list kept here, so
    a new kind of gear is sellable the day it is authored and nobody has
    to remember this file — and so the set matches what the shop sells,
    which is chosen the same way.
    """
    return getattr(type(thing), "family", None) == Family.GEAR


def thing_key(thing):
    """One string naming a content row — what a form submits to name it.

    Model label plus primary key, because a bare key is ambiguous across
    the assignable tables: a weapon and a wargear may share one.
    """
    return f"{thing._meta.label_lower}:{thing.pk}"


@dataclass
class OwnedPart:
    """Something hanging off a thing the model owns: ammo, an accessory.

    No re-homing: a part belongs to its parent and moves only with it.
    """

    id: str
    name: str
    rating: int
    #: Where the controls lead. Filled in by whoever knows the URL space —
    #: this module knows what a part *is*, not where its dialogs live.
    sell_href: str = ""
    remove_href: str = ""


@dataclass
class OwnedThing:
    """One copy of something the model already holds."""

    id: str
    name: str
    #: What this copy contributes to the model's rating on its own. Its
    #: parts state theirs; what a sale returns is worked out from the
    #: rows themselves at the moment of selling, never from here.
    rating: int
    #: What *sort* of thing this is a copy of — :func:`thing_key`, the
    #: identity a shop row submits. Two of one weapon share it; that is
    #: how a listing finds both from the row offering a third.
    key: str = ""
    parts: list[OwnedPart] = field(default_factory=list)
    sell_href: str = ""
    reassign_href: str = ""
    remove_href: str = ""


def _parts_of(node):
    """The children drawn beneath a thing, each with an address of its own.

    A weapon's *unnamed* profile is the weapon — the book prints an
    Autogun's first line as "Autogun" — so it draws no row here either,
    the same rule ``n26.render.WeaponLine.own_line`` keeps for the card.
    It also cannot be sold apart from its gun, which is the same fact
    said about money.
    """
    parts = []
    for child in node.children:
        if child.is_weapon_profile and not child.assignable.name:
            continue
        parts.append(
            OwnedPart(
                id=str(child.assignment.pk),
                name=child.name,
                rating=child.rating,
            )
        )
    return parts


def carried(card):
    """Everything the model is carrying, one line per copy.

    The whole of what they hold, in one list, owing nothing to what any
    shop happens to be selling — which is the point. A fighter's gear is
    exactly the gear least likely to still be on the list they are
    browsing, so a screen that can only annotate rows for sale can say
    nothing at all about most of what they own.

    Only what the model **owns** — see :func:`is_possession`. A card
    carries a good deal more than kit, and none of the rest is something
    to put a Sell button beside: the fighter's own profile is the
    fighter, their skills are what they know, their equipment lists are
    where they shop.

    The gang's own rows are left out for a second reason. They ride every
    member's card so gang-wide rules reach them, but they are the gang's
    property and not this fighter's to sell.

    Two of the same weapon are two lines, never one line counted twice:
    each is its own row in the ledger, each may carry different ammo, and
    each is sold, moved and dropped on its own. Sorted by name, the way a
    card sorts every list it draws, so the order does not change under a
    reader who has just bought something.
    """
    things = []
    for node in card.roots:
        if node.broadcast or node.assignment is None:
            continue
        if not is_possession(node.assignable):
            continue
        things.append(
            OwnedThing(
                id=str(node.assignment.pk),
                name=node.name,
                rating=node.rating,
                key=thing_key(node.assignable),
                parts=_parts_of(node),
            )
        )
    return sorted(things, key=lambda thing: thing.name)


def by_thing(things):
    """The same lines, keyed the way a shop listing keys its rows.

    So a row looks its own key up and finds the copies of itself the
    fighter is carrying — one dictionary read per row, whatever they own.
    The lines are the *same objects* the carried list holds, so whatever
    fills in their links fills in both at once and the two can never
    offer different addresses for one thing.
    """
    index = {}
    for thing in things:
        index.setdefault(thing.key, []).append(thing)
    return index


def owned_things(card):
    """What this card is carrying, keyed for a shop listing to look up."""
    return by_thing(carried(card))
