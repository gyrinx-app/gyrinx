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

from n26.core.owned import thing_key
from n26.core.taxonomy import UNCATEGORISED

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


def choice_field(key, group):
    """The input name one set of a line's alternatives shares.

    Scoped by the line and then by the set, because one form holds the
    whole listing and a line may put more than one group: without the
    line's scope a mount's swap would arrive with another listing's
    press, and without the set's the two groups would be one radio group
    where picking in the second clears the pick in the first. Slugified
    for the same reason the rest are — the template renders the slug, and
    reading the raw key back would ignore every pick made in a real
    browser.
    """
    return f"{slugify(key)}:option:{group}"


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
class ChoiceOption:
    """One option a reader may pick, from a group of options on a specific listing.

    ``value`` is its place in the set the server re-derives, which is what
    the control submits — naming it any other way would let a tampered
    form ask for something the listing never offered.

    ``surcharge`` is what taking it adds to the figure in the listing's
    price box, and ``surcharge_label`` is that as a reader sees it.
    Nothing is drawn where taking it changes nothing.
    """

    name: str
    value: str
    surcharge: int
    is_default: bool

    @property
    def surcharge_label(self):
        if self.surcharge == 0:
            return ""
        sign = "+" if self.surcharge > 0 else "−"
        return f"{sign}{abs(self.surcharge)}¢"


@dataclass(frozen=True)
class ChoiceGroup:
    """A group of options on one listing, and how many to pick — one,
    any, or one-or-none.

    ``choose`` is the listing's own word for how the group works, and
    drawing it as radios or tick boxes is the template's business, the
    same division as a tone and a colour.

    The set is never named to a reader; see ``n26.core.browse``.
    """

    choose: str
    #: The input every option in this group shares.
    field: str
    options: tuple[ChoiceOption, ...]


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
    #: The questions buying this asks — a mount's weapon swap. Empty for
    #: everything that asks none, which is most of a listing.
    choices: tuple[ChoiceGroup, ...] = ()


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
    #: The way to bolt something onto this copy. Only a weapon has one:
    #: an accessory changes the gun it hangs off, so there is nowhere
    #: else on a card to fit one. It stays out of ``more`` because it is
    #: the one act here that adds something rather than taking it away,
    #: and a chevron full of ways to lose a thing is no place for it.
    accessorise: Action | None = None


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
    #: been a reason the equip page stops selling it.
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


def _shown_trade_points(line):
    """A line's Trade Point figure where the surface deals in them.

    A collection prices in what it deals in. An equipment list prices in
    credits, so the TP number the item happens to carry answers no
    question a reader of that list is asking, and drawing it invites
    them to compare two lists by a figure only one of them charges.
    The browsed line keeps the truth; this is what a row prints.
    """
    return line.trade_points if line.shows_trade_points else None


def _shown_exclusive(line):
    """Whether to print "E".

    "E" is a Trade Point value — it is what the catalogue's TP column
    says for a thing the Trading Post never stocks. On a list that deals
    in Trade Points it is worth saying; on an equipment list it is
    tautological, because being on the list is the whole of what it
    means.
    """
    return line.is_exclusive and line.shows_trade_points


def _options_of(line, key):
    return tuple(
        OptionRow(
            name=part.thing.name,
            index=index,
            price=part.credits,
            trade_points=_shown_trade_points(part),
            is_exclusive=_shown_exclusive(part),
            field=parts_field(key),
            price_field=price_field(key, index),
        )
        for index, part in enumerate(line.parts)
    )


def _choices_of(line, key):
    """The line's offered alternatives as controls, in the line's own order.

    The order is load-bearing: a control submits its place in the set and
    the purchase reads that place against the line it re-derives, so this
    walks the browsed line and never a second derivation of it.
    """
    return tuple(
        ChoiceGroup(
            choose=group.choose,
            field=choice_field(key, index),
            options=tuple(
                ChoiceOption(
                    name=option.name,
                    value=str(position),
                    surcharge=option.surcharge,
                    is_default=option.is_default,
                )
                for position, option in enumerate(group.options)
            ),
        )
        for index, group in enumerate(line.choices)
    )


def priced_row(line):
    """One line of a browsed collection as a row that offers to sell it."""
    key = thing_key(line.thing)
    return PricedRow(
        key=key,
        name=line.name,
        price=line.credits,
        trade_points=_shown_trade_points(line),
        is_exclusive=_shown_exclusive(line),
        notes=tuple(line.notes),
        price_field=price_field(key),
        parts_field=parts_field(key),
        options=_options_of(line, key),
        # The identity, never the price: the server re-browses the
        # collection and finds the line itself, so a tampered form can
        # name nothing that is not on the list.
        buy=Action(label="Buy", kind=SUBMIT, target=key, tone=PRIMARY),
        choices=_choices_of(line, key),
    )


def copy_row(copy, refunds=True):
    """One copy a fighter holds, with the acts it offers named and toned.

    Takes an :class:`n26.core.owned.OwnedThing`, which already knows where
    each of its controls leads; this says what each of them means.

    ``refunds`` is whether Refund is offered at all. A gang founded
    without a budget never paid credits, so there is nothing a refund
    could give back — its rows offer Remove alone, exactly as its
    fighter cards offer Delete without Refund.
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
                    *(
                        (Action("Refund", LINK, part.refund_href, SECONDARY),)
                        if refunds
                        else ()
                    ),
                    Action("Remove", LINK, part.remove_href, SECONDARY),
                ),
            )
            for part in copy.parts
        ),
        sell=Action("Sell", LINK, copy.sell_href, DANGER),
        accessorise=(
            Action("Add accessory", LINK, copy.accessorise_href, SECONDARY)
            if copy.accessorise_href
            else None
        ),
        more=(
            Action("Reassign", LINK, copy.reassign_href, SECONDARY),
            *(
                (Action("Refund", LINK, copy.refund_href, SECONDARY),)
                if refunds
                else ()
            ),
            Action("Delete", LINK, copy.remove_href, SECONDARY),
        ),
    )


def owned_row(row, copies, refunds=True):
    """The same row, for a fighter who is carrying some of these."""
    return OwnedRow(
        key=row.key,
        name=row.name,
        count=len(copies),
        copies=tuple(copy_row(copy, refunds=refunds) for copy in copies),
        buy=row,
    )


def build_listing(view, owned, name=None, refunds=True):
    """A browsed collection joined to what one fighter already holds.

    ``owned`` is the index :func:`n26.core.owned.owned_things` returns,
    keyed the way rows are keyed — so the join is one dictionary read per
    row, however much the fighter is carrying and however long the list.

    ``refunds`` rides down to every owned copy: a gang with no budget is
    offered no Refund anywhere on the listing.

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
                rows.append(owned_row(row, copies, refunds=refunds) if copies else row)
            drawn.categories.append(ListingCategory(name=category.name, rows=rows))
        listing.sections.append(drawn)
    return listing
