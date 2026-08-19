"""What a model already holds, as a catalogue needs to see it.

A catalogue asks two questions of a fighter's card. Does this fighter
already own one of these? And if so, what exactly — which copy, worth
what, with what hanging off it — so the reader can sell it, hand it to
somebody else, undo the purchase, or take it off the card.

Both answers come off the card the page has already built. Nothing here
queries, which is the whole point: a catalogue is hundreds of rows, and an
owned-count fetched per row would be hundreds of queries.

What is owned is drawn as a *state of an equip row*: where the fighter holds
one of the thing a row names, the row says so instead of offering another.
Anything they own that the list on screen does not sell has nowhere to be
drawn, which is a known gap and not one to be closed from here.

A **thing** is a root assignment: the fighter owns it and may re-home it.
A **part** is one of its children — a paid ammo type, a sight bolted to a
gun. A part is sold and removed like anything else. Whether it can be
re-homed on its own depends on what sort of part it is, and
:func:`is_detachable` is where that is said.

Neither is *anything* the gang holds. Selling, handing on and dropping
are acts on **possessions**, and :func:`is_possession` is the one place
that says what one is — read by the catalogue that draws the controls and
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
from enum import Enum
from urllib.parse import urlencode

from n26.library.models.assignable import Family


class EquipAnchor(Enum):
    """Which screen's possessions are being read — a fighter's card or the stash."""

    FIGHTER = "fighter"
    STASH = "stash"


@dataclass(frozen=True)
class EquipHost:
    """Where an equip screen reads possessions from and sends the reader back.

    One object carries the gang, the page address, the assignment roots to
    walk, and which anchor this screen is — so the catalogue, the dialogs
    and the POST redirects all agree without each guessing from the other.
    """

    gang: object
    at: str
    roots: tuple
    anchor: EquipAnchor
    miniature: object | None = None

    @property
    def held_label(self):
        """Words for how many copies the reader already holds."""
        return "equipped" if self.anchor is EquipAnchor.FIGHTER else "in stash"

    @classmethod
    def fighter(cls, gang, card, miniature, at):
        return cls(
            gang=gang,
            at=at,
            roots=tuple(card.roots),
            anchor=EquipAnchor.FIGHTER,
            miniature=miniature,
        )

    @classmethod
    def stash(cls, gang, gang_card, at):
        return cls(
            gang=gang,
            at=at,
            roots=tuple(gang_card.stash_roots),
            anchor=EquipAnchor.STASH,
            miniature=None,
        )


#: The dialogs a screen can have open, each a query parameter naming one
#: assignment on the card. Both sides read this tuple: the rows that draw
#: the controls and the view that answers the URL behind them, so neither
#: can invent a question the other does not know.
#:
#: Three of them confirm something about the assignment named. The last
#: two ask a question instead — which accessory to bolt onto the weapon
#: named, and which of its alternatives a thing is taken with — and they
#: sit here because they are the same sort of state: one assignment on
#: this card, open because the address says so, closed by going back to
#: the address without it. A screen draws one at a time, so a URL naming
#: two draws whichever comes first here.
DIALOGS = ("sell", "reassign", "refund", "remove", "accessorise", "rechoose")


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
    the model is and knows; a collection is somewhere to buy from rather
    than something owned; a counter is a running number; a gang type is
    the gang itself.

    Asked of the library's own families rather than a list kept here, so
    a new kind of gear is sellable the day it is authored and nobody has
    to remember this file — and so the set matches what the catalogue
    sells, which is chosen the same way.
    """
    return getattr(type(thing), "family", None) == Family.GEAR


def is_detachable(thing):
    """Can this be taken off whatever it hangs from and fitted elsewhere?

    A weapon's firing line cannot. It names one particular weapon and
    *is* that weapon's line — unbolt it and there is nothing left to put
    anywhere, which is why a gun's ammo offers no move. A sight is the
    other case: it is gear in its own right that happens to be bolted
    on, so it can go into the stash when the gun is sold and come back
    out onto a different gun later.

    Asked by both sides, like :func:`is_possession` — the rows that draw
    the controls and ``Operation.move`` behind them — so a screen never
    offers a move the operation would refuse.
    """
    from n26.library.models import WeaponProfile

    return is_possession(thing) and not isinstance(thing, WeaponProfile)


def thing_key(thing):
    """One string naming a piece of content — what a form submits to name it.

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
    #: The content this is one of, as :func:`thing_key` writes it —
    #: so a part can say what it is without being looked up in whatever
    #: is holding it.
    key: str
    name: str
    rating: int
    sell_href: str
    refund_href: str
    remove_href: str


@dataclass(frozen=True)
class OwnedThing:
    """One copy of something the model already holds."""

    id: str
    #: The content this is a copy of, as :func:`thing_key` writes it.
    key: str
    name: str
    #: What this copy contributes to the model's rating on its own. Its
    #: parts state theirs; what a sale returns is worked out from the
    #: assignments themselves at the moment of selling, never from here.
    rating: int
    parts: tuple[OwnedPart, ...]
    sell_href: str
    reassign_href: str
    refund_href: str
    remove_href: str
    #: Where to go to bolt something onto this. Only a weapon has one:
    #: an accessory hangs off the gun it changes, so nothing else on a
    #: card is somewhere to fit one.
    accessorise_href: str = ""
    #: Where to go to take this with different options. Only something
    #: whose content offers a choice has one: everything else would be a
    #: click onto a panel with nothing to pick.
    rechoose_href: str = ""
    #: What this copy was taken with, named as the buyer was offered it.
    #: Per copy and not per content: two of the same mount may carry
    #: different guns. Empty for anything that offered no choice, which
    #: is most of what a model owns.
    chosen: tuple[str, ...] = ()


def _offers_a_choice(thing):
    """Whether this content puts alternatives in front of anyone.

    The same test the buying screen makes of a line, asked here of a copy
    already held: a set with nothing to pick was taken unasked, and a way
    to change it would open onto a panel offering one thing.
    """
    from n26.library.models.assignable import Optioned

    return isinstance(thing, Optioned) and thing.offers_a_choice


def _chosen_of(node):
    """The options this copy was taken with, as the buyer was offered them.

    The recorded sets say what was picked and the offer says what each
    was called, and both are already in hand — describing a copy costs
    no query. The set an option brings is what gets recorded, so two
    options bringing the same set cannot be told apart afterwards; the
    first is named.

    The author's own label for a group is never read here. A reader is
    shown the options themselves, in the order the offer puts them, and
    a heading naming the group would be a second vocabulary they never
    agreed to.
    """
    from n26.library.models.assignable import Optioned

    thing = node.assignable
    if not isinstance(thing, Optioned):
        return ()
    recorded = {row.default_set_id for row in node.assignment.chosen_options.all()}
    return tuple(option.name for option in thing.options_taken(recorded))


def _part_name(node):
    """What a part is called when it is drawn under its parent.

    A weapon profile prints the gun it belongs to in brackets — "warp
    round (Autogun)" — which is what a card wants, where nothing above
    the line says which gun. Beneath the gun's own row the bracket only
    repeats it, so the bare name stands, exactly as the equip row for the
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
                refund_href=with_query(at, refund=pk),
                remove_href=with_query(at, remove=pk),
            )
        )
    return tuple(parts)


def possessions(host: EquipHost):
    """Everything this host carries, keyed the way a catalogue keys its rows.

    Keyed by :func:`thing_key`, so a row looks its own key up and finds
    the copies held — one dictionary read per row, however much is carried.

    ``host.at`` is the page the reader is on, query string and all: the
    confirmations open over it and Cancel returns to it, so the list they
    were reading is still the list underneath.
    """
    from n26.library.models import Weapon

    index = {}
    for node in host.roots:
        if node.assignment is None:
            continue
        if host.anchor is EquipAnchor.FIGHTER:
            if node.broadcast:
                continue
            if node.suppressed:
                # A modifier has taken this away, so the card says the fighter
                # does not have it — and a screen must not offer to sell
                # something the card denies. The assignment is untouched
                # underneath: drop whatever cancelled it and the controls come back.
                continue
        if not is_possession(node.assignable):
            continue
        key = thing_key(node.assignable)
        pk = str(node.assignment.pk)
        at = host.at
        index.setdefault(key, []).append(
            OwnedThing(
                id=pk,
                key=key,
                name=node.name,
                rating=node.rating,
                parts=_parts_of(node, at),
                sell_href=with_query(at, sell=pk),
                reassign_href=with_query(at, reassign=pk),
                refund_href=with_query(at, refund=pk),
                remove_href=with_query(at, remove=pk),
                accessorise_href=(
                    with_query(at, accessorise=pk)
                    if isinstance(node.assignable, Weapon)
                    else ""
                ),
                rechoose_href=(
                    with_query(at, rechoose=pk)
                    if _offers_a_choice(node.assignable)
                    else ""
                ),
                chosen=_chosen_of(node),
            )
        )
    return index


def owned_things(card, at):
    """Everything on this fighter's card — see :func:`possessions`."""
    return possessions(EquipHost.fighter(card.miniature.gang, card, card.miniature, at))
