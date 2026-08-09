"""A collection as one fighter sees it: what is for sale, and what they hold.

:mod:`n26.core.browse` renders a collection knowing nothing about who is
reading it — a taxonomy of priced lines, the same shape whether the
collection was written out by hand or swept together by a selector.
:mod:`n26.core.owned` reads the other half off the fighter's card: which
copies of which content rows they are already carrying.

A listing is the two joined. It is what a shopping screen draws, and it
is a structure rather than a bag of dictionaries so that the join has one
definition: a test can build one and ask what a row offers without going
through a request, and a gallery can build one without a database.

  --- owning something replaces its row ---

A category holds :class:`PricedRow` or :class:`OwnedRow`, one or the
other for a given content row, never both and never a flag on one type.
Where the fighter holds one of the thing a row names, the row says so
instead of offering another: the count stands where Buy would be and
opens onto the copies themselves.

The ordinary row is not lost when that happens — it is nested, as
:attr:`OwnedRow.buy`, unconditionally. That is how a reader buys a
second, and it is the same row they would have seen had they owned none,
so there is one definition of what buying this thing looks like.

  --- a row's actions say what they mean, never how to draw it ---

Buy is a submit: the listing is one form, and a purchase names its line
and presses. Sell, Reassign and Delete are links, because each opens a
confirmation that is a server-rendered state of the page it was pressed
on. A template that had to know which of the four was which would decide
that by name, and the first act added would be drawn wrong.

Tones are the row's own vocabulary — what the control *means* — and a
template maps them to whatever the button kit calls those colours. So
nothing here knows that a sale is red.

  --- what a row submits ---

Each input's name is derived from the row's key and carried on the row.
The server derives the same names when it reads the press back, and a
name computed twice from two places is a name that eventually disagrees
with itself.
"""

from dataclasses import dataclass, field

from django.utils.text import slugify

from n26.core.browse import UNCATEGORISED
from n26.core.owned import thing_key

#: The affirmative act on a row: buying the thing it names.
PRIMARY = "primary"
#: Taking a thing away, whatever it puts in the bank.
DANGER = "danger"
#: The rarer acts, the ones that share a chevron.
SECONDARY = "secondary"

#: A press within the listing's own form, carrying :attr:`Action.target`
#: as its value.
SUBMIT = "submit"
#: A navigation to :attr:`Action.target`.
LINK = "link"


def parts_field(key):
    """The input name the tickable parts of one line share.

    Scoped by the line, because one form holds the whole listing: without
    it, ticking warp rounds on the autogun row would arrive with the stub
    gun's press. Slugified, because that is what the template renders —
    read the raw key back and every box ticked in a real browser is
    silently ignored while a test posting the raw key still passes.
    """
    return f"{slugify(key)}:parts"


def price_field(key, index=None):
    """The input name a line's price is typed into — the row's own, or
    one of its parts'.

    Scoped by the line for the same reason the tick boxes are: one form
    holds the whole listing, so a price typed on the autogun row must not
    arrive with the stub gun's press.
    """
    scope = slugify(key)
    return f"{scope}:price" if index is None else f"{scope}:parts:{index}:price"


@dataclass(frozen=True)
class Action:
    """One thing a row offers, said in the row's own words.

    ``kind`` is how the press happens — :data:`SUBMIT` inside the
    listing's form, or :data:`LINK` to an address. ``target`` is the
    value a submit carries or the address a link goes to.

    ``tone`` is what the act means: :data:`PRIMARY` for the one the
    reader came to do, :data:`DANGER` for one that takes a thing away,
    :data:`SECONDARY` for the rest. Colours are the drawing's business.
    """

    label: str
    kind: str
    target: str
    tone: str


@dataclass(frozen=True)
class OptionRow:
    """A part bought with the line above it: a gun's paid ammo, a firing mode.

    Not a purchase of its own — a profile belongs to one particular
    weapon, so buying one is a way of buying that weapon. It offers no
    action for that reason: it rides the row's Buy.

    ``index`` is its place in the line the server re-derives, which is
    what the tick box submits. Naming the part any other way would let a
    tampered form ask for something the listing never offered.
    """

    name: str
    index: int
    price: int
    trade_points: int | None
    is_exclusive: bool
    #: The tick box's name, shared with every other option on this row.
    field: str
    #: Where this part's own price is typed. A discount on the gun is not
    #: a discount on the rounds, so each is charged at its own figure.
    price_field: str


@dataclass(frozen=True)
class PricedRow:
    """Something for sale, and what buying it here asks for."""

    key: str
    name: str
    price: int
    trade_points: int | None
    is_exclusive: bool
    #: Remarks about this line for this reader — "usable by Walkers
    #: only". One channel, never a flag per rule; see ``n26.core.notes``.
    notes: tuple
    price_field: str
    parts_field: str
    options: tuple[OptionRow, ...]
    buy: Action


@dataclass(frozen=True)
class OwnedPartRow:
    """Something hanging off a copy the fighter holds: ammo, an accessory.

    No move among its actions. A part belongs to the thing it hangs off
    and ``Operation.move`` refuses an assignment with a parent, so
    offering one would be offering a press that cannot work.
    """

    id: str
    key: str
    name: str
    #: What this part contributed to the fighter's rating on its own.
    rating: int
    sell: Action
    more: tuple[Action, ...]


@dataclass(frozen=True)
class OwnedCopyRow:
    """One copy the fighter holds, with whatever hangs off it."""

    id: str
    key: str
    name: str
    #: What this copy contributed on its own — its parts state theirs.
    #: Summing them is the caller's business; a sale prices itself from
    #: the stored rows at the moment of selling.
    rating: int
    parts: tuple[OwnedPartRow, ...]
    sell: Action
    more: tuple[Action, ...]


@dataclass(frozen=True)
class OwnedRow:
    """A row for something the fighter is already carrying.

    ``count`` is copies, not pieces: two Autoguns with a paid round on
    one of them is two. A round is not a thing you own an Autogun's worth
    of, and counting it would say the fighter had three guns.
    """

    key: str
    name: str
    count: int
    copies: tuple[OwnedCopyRow, ...]
    #: The row this would have been had they owned none, so a reader can
    #: buy another. Always present: owning one of something has never
    #: been a reason the shop stops selling it.
    buy: PricedRow


@dataclass
class ListingCategory:
    """One category heading and its rows. An empty name means the content
    filed nothing here, and the rows sit straight inside the section."""

    name: str
    rows: list = field(default_factory=list)


@dataclass
class ListingSection:
    """One section heading and its categories."""

    name: str
    categories: list[ListingCategory] = field(default_factory=list)


@dataclass
class Listing:
    """A whole shopping surface for one fighter, ready to draw."""

    name: str
    sections: list[ListingSection] = field(default_factory=list)

    def all_rows(self):
        for section in self.sections:
            for category in section.categories:
                yield from category.rows


def _options_of(line, key):
    return tuple(
        OptionRow(
            name=part.thing.name,
            index=index,
            price=part.credits,
            trade_points=part.trade_points,
            is_exclusive=part.is_exclusive,
            field=parts_field(key),
            price_field=price_field(key, index),
        )
        for index, part in enumerate(line.parts)
    )


def priced_row(line):
    """One line of a browsed collection as a row that offers to sell it."""
    key = thing_key(line.thing)
    return PricedRow(
        key=key,
        name=line.name,
        price=line.credits,
        trade_points=line.trade_points,
        is_exclusive=line.is_exclusive,
        notes=tuple(line.notes),
        price_field=price_field(key),
        parts_field=parts_field(key),
        options=_options_of(line, key),
        # The identity, never the price: the server re-browses the
        # collection and finds the line itself, so a tampered form can
        # name nothing that is not on the list.
        buy=Action(label="Buy", kind=SUBMIT, target=key, tone=PRIMARY),
    )


def copy_row(copy):
    """One copy a fighter holds, with the acts it offers named and toned.

    Takes an :class:`n26.core.owned.OwnedThing`, which already knows where
    each of its controls leads; this says what each of them means.
    """
    return OwnedCopyRow(
        id=copy.id,
        key=copy.key,
        name=copy.name,
        rating=copy.rating,
        parts=tuple(
            OwnedPartRow(
                id=part.id,
                key=part.key,
                name=part.name,
                rating=part.rating,
                sell=Action("Sell", LINK, part.sell_href, DANGER),
                # A part is refundable for the same reason it is sellable:
                # somebody paid for the wrong ammunition as easily as for
                # the wrong gun. Removed rather than deleted, because what
                # is left afterwards is still the fighter's gun.
                more=(
                    Action("Refund", LINK, part.refund_href, SECONDARY),
                    Action("Remove", LINK, part.remove_href, SECONDARY),
                ),
            )
            for part in copy.parts
        ),
        sell=Action("Sell", LINK, copy.sell_href, DANGER),
        more=(
            Action("Reassign", LINK, copy.reassign_href, SECONDARY),
            Action("Refund", LINK, copy.refund_href, SECONDARY),
            Action("Delete", LINK, copy.remove_href, SECONDARY),
        ),
    )


def owned_row(row, copies):
    """The same row, for a fighter who is carrying some of these."""
    return OwnedRow(
        key=row.key,
        name=row.name,
        count=len(copies),
        copies=tuple(copy_row(copy) for copy in copies),
        buy=row,
    )


def build_listing(view, owned, name=None):
    """A browsed collection joined to what one fighter already holds.

    ``owned`` is the index :func:`n26.core.owned.owned_things` returns,
    keyed the way rows are keyed — so the join is one dictionary read per
    row, however much the fighter is carrying and however long the list.

    Sections keep the order and the shape the browse gave them, with one
    substitution: a section the content left unnamed is called
    "Uncategorised" here. A listing is drawn as a strip of tabs, and a
    tab with no word on it is one nobody can press.
    """
    listing = Listing(name=name or view.name)
    for section in view.sections:
        drawn = ListingSection(name=section.name or UNCATEGORISED)
        for category in section.categories:
            rows = []
            for line in category.lines:
                row = priced_row(line)
                copies = owned.get(row.key)
                rows.append(owned_row(row, copies) if copies else row)
            drawn.categories.append(ListingCategory(name=category.name, rows=rows))
        listing.sections.append(drawn)
    return listing
