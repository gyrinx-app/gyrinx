"""What a model already holds, as a shop listing needs to see it.

A listing asks two questions of a fighter's card. Does this fighter
already own one of these? And if so, what exactly — which copy, worth
what, with what hanging off it — so the reader can sell it, hand it to
somebody else, or take it off the card.

Both answers come off the card the page has already built. Nothing here
queries, which is the whole point: a listing is hundreds of rows, and an
owned-count fetched per row would be hundreds of queries.

What is owned is drawn as a *state of a shop row*: where the fighter holds
one of the thing a row names, the row says so instead of offering another.
Anything they own that the list on screen does not sell has nowhere to be
drawn, which is a known gap and not one to be closed from here.

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

Where a control leads is settled here too, in the same pass that finds
the copy. A confirmation is a query parameter on the page the reader is
already on, so what a row needs is that page's address and nothing more;
building the rows half-formed and walking them again to fill the links in
would leave anyone who called this directly holding controls that lead
nowhere.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from n26.library.models.assignable import Family

#: The confirmations a screen can have open, each a query parameter
#: naming one row of the card. Both sides read this tuple: the rows that
#: draw the controls and the view that answers the URL behind them, so
#: neither can invent a question the other does not know.
CONFIRMATIONS = ("sell", "reassign", "remove")


def with_query(url, **params):
    """A URL with more query on the end of it, whatever it had already."""
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}{urlencode(params)}"


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


@dataclass(frozen=True)
class OwnedPart:
    """Something hanging off a thing the model owns: ammo, an accessory.

    No re-homing: a part belongs to its parent and moves only with it.
    """

    id: str
    #: The content row this is one of, as :func:`thing_key` writes it —
    #: so a part can say what it is without being looked up in whatever
    #: is holding it.
    key: str
    name: str
    rating: int
    sell_href: str
    remove_href: str


@dataclass(frozen=True)
class OwnedThing:
    """One copy of something the model already holds."""

    id: str
    #: The content row this is a copy of, as :func:`thing_key` writes it.
    key: str
    name: str
    #: What this copy contributes to the model's rating on its own. Its
    #: parts state theirs; what a sale returns is worked out from the
    #: rows themselves at the moment of selling, never from here.
    rating: int
    parts: tuple[OwnedPart, ...]
    sell_href: str
    reassign_href: str
    remove_href: str


def _part_name(node):
    """What a part is called when it is drawn under its parent.

    A weapon profile prints the gun it belongs to in brackets — "warp
    round (Autogun)" — which is what a card wants, where nothing above
    the line says which gun. Beneath the gun's own row the bracket only
    repeats it, so the bare name stands, exactly as the shop row for the
    same ammo does.
    """
    if node.is_weapon_profile:
        return node.assignable.name
    return node.name


def _parts_of(node, at):
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
        pk = str(child.assignment.pk)
        parts.append(
            OwnedPart(
                id=pk,
                key=thing_key(child.assignable),
                name=_part_name(child),
                rating=child.rating,
                sell_href=with_query(at, sell=pk),
                remove_href=with_query(at, remove=pk),
            )
        )
    return tuple(parts)


def owned_things(card, at):
    """Everything on this card, keyed the way a listing keys its rows.

    Keyed by :func:`thing_key`, so a row looks its own key up and finds
    the copies of itself the fighter is carrying — one dictionary read per
    row, whatever the fighter owns.

    ``at`` is the page the reader is on, query string and all: the
    confirmations open over it and Cancel returns to it, so the list they
    were reading is still the list underneath.

    Two of the same weapon are two entries under one key, never one entry
    counted twice: each is its own row in the ledger, each may carry
    different ammo, and each is sold, moved and dropped on its own.

    Only what the model **owns** — see :func:`is_possession`. A card
    carries a good deal more than kit, and none of the rest is something
    to put a Sell button beside: the fighter's own profile is the
    fighter, their skills are what they know, their equipment lists are
    where they shop.

    The gang's own rows are skipped for a second reason. They ride every
    member's card so gang-wide rules reach them, but they are the gang's
    property and not this fighter's to sell.

    A **granted** weapon is skipped for a third: it is lent, not owned. A
    modifier puts it on the card and nobody bought it, so there is
    nothing to sell, nothing to hand to another fighter, and nothing for
    an accessory to hang off. It is skipped twice over — this reads
    ``card.roots``, which holds what the gang owns, while a grant lives
    on ``card.granted``; and a granted line carries no assignment. The
    consequence a reader should expect on the equipment screen: a row for
    something the fighter owns replaces its Buy button, and a granted
    weapon does not, so a fighter lent a pair of claws is still offered
    claws. That is deliberate — the lent pair goes when its granter does,
    and being unable to buy a pair of your own would be the worse
    surprise.
    """
    index = {}
    for node in card.roots:
        if node.broadcast or node.assignment is None:
            continue
        if not is_possession(node.assignable):
            continue
        key = thing_key(node.assignable)
        pk = str(node.assignment.pk)
        index.setdefault(key, []).append(
            OwnedThing(
                id=pk,
                key=key,
                name=node.name,
                rating=node.rating,
                parts=_parts_of(node, at),
                sell_href=with_query(at, sell=pk),
                reassign_href=with_query(at, reassign=pk),
                remove_href=with_query(at, remove=pk),
            )
        )
    return index
