"""Possessions as catalogue rows, read from an already-built card.

The index built here issues no queries. It keeps root gear separate from
parts such as ammunition and accessories, and gives every allowed act a URL
on the page that supplied the card.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from n26.library.models.assignable import Family


@dataclass(frozen=True)
class EquipHost:
    """The assignment roots and return address behind an equip screen."""

    gang: object
    at: str
    roots: tuple
    miniature: object | None = None

    @property
    def is_stash(self):
        return self.miniature is None

    @property
    def held_label(self):
        return "in stash" if self.is_stash else "equipped"

    @classmethod
    def fighter(cls, gang, card, miniature, at):
        return cls(
            gang=gang,
            at=at,
            roots=tuple(card.roots),
            miniature=miniature,
        )

    @classmethod
    def stash(cls, gang, gang_card, at):
        return cls(
            gang=gang,
            at=at,
            roots=tuple(gang_card.stash_roots),
        )


#: URL parameters that can open one assignment dialog. Their order is the
#: precedence when an address names more than one.
DIALOGS = (
    "sell",
    "reassign",
    "fit",
    "detach",
    "refund",
    "remove",
    "accessorise",
    "rechoose",
)


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


def can_unbolt(assignment):
    """Can this copy come off what it hangs from and stay with the gang?

    :func:`is_detachable` is about the *kind* of thing: a sight can, a
    firing line cannot. This is about *this copy*. A sight the gun came
    with belongs to the package — what caused it goes, so it goes — and
    offering to take one off would be offering something the sale of the
    gun takes straight back.
    """
    return (
        assignment.parent_id is not None
        and assignment.caused_by_id is None
        and is_detachable(assignment.assignable)
    )


def thing_key(thing):
    """One string naming a piece of content — what a form submits to name it.

    Model label plus primary key, because a bare key is ambiguous across
    the assignable tables: a weapon and a wargear may share one.
    """
    return f"{thing._meta.label_lower}:{thing.pk}"


@dataclass(frozen=True)
class OwnedPart:
    """Something hanging off a thing the model owns: ammo, an accessory.

    A firing line stays put: it *is* the weapon's line. An accessory the
    gang bought can come off — kept held, or fitted to another gun —
    which is why those two addresses are here and empty for everything
    that cannot.
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
    #: Where to go to take this off and leave the fighter holding it.
    #: Empty for a firing line, and for a sight the gun came with.
    detach_href: str = ""
    #: Where to go to bolt this onto a different gun this fighter is
    #: carrying. Empty unless there is another gun to name.
    fit_href: str = ""


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
    #: Where to go to bolt this onto one of the guns the fighter is
    #: carrying — the other end of the same act. Only a loose accessory
    #: has one, and only where there is a gun to put it on.
    fit_href: str = ""
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


def _parts_of(node, at, *, can_refit=False):
    """The children drawn beneath a thing, each with an address of its own.

    A weapon's *unnamed* profile is the weapon — the book prints an
    Autogun's first line as "Autogun" — so it draws no row here either,
    the same rule ``n26.render.WeaponLine.own_line`` keeps for the card.
    It also cannot be sold apart from its gun, which is the same fact
    said about money.

    ``can_refit`` is whether this host carries another gun this part
    could move onto. A screen must not ask a question its answer
    refuses, so an accessory on the only gun is offered Detach and not
    Fit.
    """
    parts = []
    for child in node.children:
        if child.is_weapon_profile and not child.assignable.name:
            continue
        pk = str(child.assignment.pk)
        unbolt = can_unbolt(child.assignment)
        parts.append(
            OwnedPart(
                id=pk,
                key=thing_key(child.assignable),
                name=_part_name(child),
                rating=child.rating,
                sell_href=with_query(at, sell=pk),
                refund_href=with_query(at, refund=pk),
                remove_href=with_query(at, remove=pk),
                detach_href=with_query(at, detach=pk) if unbolt else "",
                fit_href=(with_query(at, fit=pk) if unbolt and can_refit else ""),
            )
        )
    return tuple(parts)


def weapons_on(host: EquipHost):
    """The guns this host is carrying — everywhere an accessory could go.

    A root the host holds in its own right, rather than anything nested
    under one: a weapon's own firing line is the weapon, and a gun bolted
    to a mount belongs to whatever is holding it. The accessory question
    is asked of exactly this set, so the two directions agree about what
    counts as a gun on this card.

    No queries — the card is already built.
    """
    from n26.library.models import Weapon

    return tuple(
        node
        for node in host.roots
        if node.assignment is not None
        and not node.suppressed
        and not node.broadcast
        and isinstance(node.assignable, Weapon)
    )


def possessions(host: EquipHost):
    """Everything this host carries, keyed the way a catalogue keys its rows.

    Keyed by :func:`thing_key`, so a row looks its own key up and finds
    the copies held — one dictionary read per row, however much is carried.

    ``host.at`` is the page the reader is on, query string and all: the
    confirmations open over it and Cancel returns to it, so the list they
    were reading is still the list underneath.
    """
    from n26.library.models import Weapon, WeaponAccessory

    # Whether this card has anywhere to fit an accessory, asked once for
    # the whole of it. A fighter carrying no gun is offered no fitting:
    # a screen must not ask a question its answer refuses. The stash is
    # never asked — its accessories are fitted from the gang sheet,
    # where the guns of the whole roster are in reach.
    guns = weapons_on(host)
    fittable = not host.is_stash and bool(guns)

    index = {}
    for node in host.roots:
        if node.assignment is None:
            continue
        if node.broadcast or node.suppressed:
            # Suppressed assignments remain stored but are not possessions on
            # this card; broadcast roots belong to the gang, not the fighter.
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
                parts=_parts_of(
                    node,
                    at,
                    can_refit=any(
                        gun.assignment.pk != node.assignment.pk for gun in guns
                    ),
                ),
                sell_href=with_query(at, sell=pk),
                reassign_href=with_query(at, reassign=pk),
                refund_href=with_query(at, refund=pk),
                remove_href=with_query(at, remove=pk),
                accessorise_href=(
                    with_query(at, accessorise=pk)
                    if isinstance(node.assignable, Weapon)
                    else ""
                ),
                fit_href=(
                    with_query(at, fit=pk)
                    if fittable and isinstance(node.assignable, WeaponAccessory)
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
