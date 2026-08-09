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
"""

from dataclasses import dataclass, field


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


def owned_things(card):
    """Everything on this card, keyed the way a listing keys its rows.

    Keyed by :func:`thing_key`, so a row looks its own key up and finds
    the copies of itself the fighter is carrying — one dictionary read per
    row, whatever the fighter owns.

    The gang's own rows are skipped. They ride every member's card so
    gang-wide rules reach them, but they are the gang's property and not
    this fighter's to sell.
    """
    index = {}
    for node in card.roots:
        if node.broadcast or node.assignment is None:
            continue
        index.setdefault(thing_key(node.assignable), []).append(
            OwnedThing(
                id=str(node.assignment.pk),
                name=node.name,
                rating=node.rating,
                parts=_parts_of(node),
            )
        )
    return index
