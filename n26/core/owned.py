"""Possessions as catalogue rows, read from an already-built card.

The index built here issues no queries. It keeps root gear separate from
parts such as ammunition and accessories, and gives every allowed act a URL
on the page that supplied the card.
"""

from dataclasses import dataclass
from urllib.parse import urlencode

from n26.library.models.assignable import Family, Weapon, slots_of


@dataclass(frozen=True)
class EquipHost:
    """The assignment roots and return address behind an equip screen."""

    gang: object
    at: str
    roots: tuple
    miniature: object | None = None
    bound_items: frozenset = frozenset()

    @property
    def is_stash(self):
        return self.miniature is None

    @property
    def held_label(self):
        return "in stash" if self.is_stash else "equipped"

    @classmethod
    def fighter(cls, gang, card, miniature, at):
        from n26.core.tier_choices import augmentation_bound_items

        return cls(
            gang=gang,
            at=at,
            roots=tuple(card.roots),
            miniature=miniature,
            bound_items=augmentation_bound_items(
                node.assignment
                for node in card.all_nodes()
                if node.assignment is not None and not node.broadcast
            ),
        )

    @classmethod
    def stash(cls, gang, gang_card, at):
        from n26.core.tier_choices import augmentation_bound_items

        return cls(
            gang=gang,
            at=at,
            roots=tuple(gang_card.stash_roots),
            bound_items=augmentation_bound_items(
                node.assignment
                for root in gang_card.stash_roots
                for node in root.walk()
                if node.assignment is not None and not node.broadcast
            ),
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
    """Whether the library family represents equipment that can be moved or sold.

    Discover possession kinds from the library's families, matching catalogue
    purchase discovery. Exclude identity, abilities, collections and counters.
    """
    return getattr(type(thing), "family", None) == Family.GEAR


def is_detachable(thing):
    """Can this be taken off whatever it hangs from and fitted elsewhere?

    A weapon's profile cannot. It names one particular weapon and
    *is* that weapon's own profile — unbolt it and there is nothing left
    to put anywhere, which is why a gun's ammo offers no move. A sight
    is the other case: it is gear in its own right that happens to be bolted
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
    weapon profile cannot. This is about *this copy*. A sight the gun came
    with belongs to the package — what caused it goes, so it goes — and
    offering to take one off would be offering something the sale of the
    gun takes straight back. ``Operation.move`` refuses only the kind;
    the copy's rule is held by whoever asks it, so a view refuses a
    built-in itself before reaching the operation.
    """
    return (
        assignment.parent_id is not None
        and assignment.caused_by_id is None
        and is_detachable(assignment.assignable)
    )


def is_built_in_profile(assignment):
    """Is this one of a weapon's own profiles, granted with the gun?

    Free profiles ride with the weapon: they *are* how it shoots, and
    selling one leaves no way to put it back. Bought ammunition is the
    other case — assigned with no cause, paid for on its own, and
    handed back the same way.

    ``caused_by`` is the signal. ``_grant_free_profiles`` writes it;
    ``buy_weapon_profile`` does not.
    """
    from n26.library.models import WeaponProfile

    return (
        isinstance(assignment.assignable, WeaponProfile)
        and assignment.caused_by_id is not None
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

    A weapon profile stays put: it *is* the weapon's own profile. An
    accessory the gang bought can come off — kept held, or fitted to
    another gun — which is why those two addresses are here and empty
    for everything that cannot.
    """

    id: str
    #: Content key shared with catalogue lines, available without a parent lookup.
    key: str
    name: str
    rating: int
    #: Included weapon profiles have no independent removal controls.
    #: Paid ammunition retains its own command URLs.
    sell_href: str
    refund_href: str
    remove_href: str
    #: Whether this subtree used Trade Points. This determines refund
    #: availability when the gang has no credit budget.
    paid_trade_points: bool = False
    #: Option-selection URL, available only when content offers a choice.
    detach_href: str = ""
    #: Fitting URL for a loose accessory when the bearer carries a weapon.
    fit_href: str = ""


@dataclass(frozen=True)
class OwnedThing:
    """One copy of something the model already holds."""

    id: str
    #: The content this is a copy of, as :func:`thing_key` writes it.
    key: str
    name: str
    #: Rating for this copy alone; parts retain their contributions. Sales
    #: recalculate from stored assignments.
    rating: int
    parts: tuple[OwnedPart, ...]
    sell_href: str
    reassign_href: str
    refund_href: str
    remove_href: str
    #: Whether this subtree used Trade Points. This determines refund
    #: availability when the gang has no credit budget.
    paid_trade_points: bool = False
    #: Accessory-fitting URL, available only on weapons.
    accessorise_href: str = ""
    #: Fitting URL for a loose accessory when the bearer carries a weapon.
    fit_href: str = ""
    #: Option-selection URL, available only when content offers a choice.
    rechoose_href: str = ""
    #: Loaded weapon slot count, or one for other kinds. Reading it cannot query.
    slots: int = 1
    #: Option labels for this specific copy, which may differ from another
    #: copy of the same content.
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
    A named free profile still draws a row, because the card needs the
    extra weapon profile, but it cannot be sold apart from its gun: it
    came with the weapon and there is no way to put it back.

    ``can_refit`` is whether this host carries another gun this part
    could move onto. A screen must not ask a question its answer
    refuses, so an accessory on the only gun is offered Detach and not
    Fit. The stash is never asked — its accessories are fitted from
    the gang sheet, where the guns of the whole roster are in reach.
    """
    parts = []
    for child in node.children:
        if child.is_weapon_profile and not child.assignable.name:
            continue
        pk = str(child.assignment.pk)
        unbolt = can_unbolt(child.assignment)
        bundled = is_built_in_profile(child.assignment)
        parts.append(
            OwnedPart(
                id=pk,
                key=thing_key(child.assignable),
                name=_part_name(child),
                rating=child.rating,
                sell_href="" if bundled else with_query(at, sell=pk),
                refund_href="" if bundled else with_query(at, refund=pk),
                remove_href="" if bundled else with_query(at, remove=pk),
                paid_trade_points=child.paid_trade_points,
                detach_href=with_query(at, detach=pk) if unbolt else "",
                fit_href=(with_query(at, fit=pk) if unbolt and can_refit else ""),
            )
        )
    return tuple(parts)


def weapons_on(host: EquipHost):
    """The guns this host is carrying — everywhere an accessory could go.

    A root the host holds in its own right, rather than anything nested
    under one: a weapon's own profile is the weapon, and a gun bolted
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
    """Index held copies by the catalogue's ``thing_key`` without querying.

    ``host.at`` retains the current page and query string for confirmation
    and cancellation links.
    """
    from n26.library.models import WeaponAccessory

    # Compute fitting availability once per bearer. Stash accessories are
    # fitted from the gang sheet, which can reach weapons across the roster.
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
                    can_refit=(
                        not host.is_stash
                        and any(gun.assignment.pk != node.assignment.pk for gun in guns)
                    ),
                ),
                sell_href=with_query(at, sell=pk),
                reassign_href=(
                    ""
                    if node.assignment.pk in host.bound_items
                    else with_query(at, reassign=pk)
                ),
                refund_href=with_query(at, refund=pk),
                remove_href=with_query(at, remove=pk),
                paid_trade_points=node.paid_trade_points,
                slots=slots_of(node.assignable),
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
