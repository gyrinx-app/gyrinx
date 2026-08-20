"""A browsed collection joined to possessions.

A category contains either :class:`Listing` or :class:`OwnedRow` for a
piece of content. An owned row keeps its listing when another copy can be
bought; stash-only rows have no listing. Actions state their meaning and
target while templates decide how to draw them.

Input names live on the rows because the server must derive the same names
when it validates a purchase.
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

#: A click within the catalogue's own form, carrying
#: :attr:`Action.target` as its value.
SUBMIT = "submit"
#: A navigation to :attr:`Action.target`.
LINK = "link"


def parts_field(key):
    """The input name the tickable parts of one line share.

    Scoped by the line, because one form holds the whole catalogue:
    without it, ticking warp rounds on the autogun row would arrive with
    the stub gun's click. Slugified, because that is what the template
    renders — read the raw key back and every box ticked in a real
    browser is silently ignored while a test posting the raw key still
    passes.
    """
    return f"{slugify(key)}:parts"


def choice_field(key, group):
    """The input name one set of a line's alternatives shares.

    Scoped by the line and then by the set, because one form holds the
    whole catalogue and a line may put more than one group: without the
    line's scope a mount's swap would arrive with another listing's
    click, and without the set's the two groups would be one radio group
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
    holds the whole catalogue, so a price typed on the autogun row must
    not arrive with the stub gun's click.
    """
    scope = slugify(key)
    return f"{scope}:price" if index is None else f"{scope}:parts:{index}:price"


@dataclass(frozen=True)
class Action:
    """One thing a row offers, said in the row's own words.

    ``kind`` is how the click happens — :data:`SUBMIT` inside the
    catalogue's form, or :data:`LINK` to an address. ``target`` is the
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
    tampered form ask for something the catalogue never offered.
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
class GroupOption:
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
    #: Whether this is the one its set takes unasked. A fact about the
    #: offer, true wherever the offer is drawn.
    is_default: bool
    #: Whether this control arrives already picked. A question about
    #: *this* drawing rather than about the offer: buying starts on the
    #: standard one, and changing what something already holds starts on
    #: what it holds.
    checked: bool = False

    @property
    def surcharge_label(self):
        if self.surcharge == 0:
            return ""
        sign = "+" if self.surcharge > 0 else "−"
        return f"{sign}{abs(self.surcharge)}¢"


@dataclass(frozen=True)
class PickGroup:
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
    options: tuple[GroupOption, ...]
    #: Whether the control for taking nothing from this set is the one
    #: picked. Radios cannot be unclicked, so a one-or-none set draws a
    #: "None" beside its options, and this says whether that is where it
    #: starts.
    nothing_taken: bool = True


@dataclass(frozen=True)
class Listing:
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
    #: everything that asks none, which is most of a catalogue.
    choices: tuple[PickGroup, ...] = ()


@dataclass(frozen=True)
class OwnedPartRow:
    """Something hanging off a copy the fighter holds: ammo, an accessory.

    No move among its actions. A part belongs to the thing it hangs off
    and ``Operation.move`` refuses an assignment with a parent, so
    offering one would be offering a click that cannot work.
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
    #: the stored assignments at the moment of selling.
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
    #: The options this copy was taken with, in the order the offer put
    #: them — "Cutter plasma guns", "Smoke dispenser". What each added is
    #: already inside the copy's rating, so no figure is said again
    #: beside them. Empty where nothing was ever asked.
    chosen: tuple[str, ...] = ()


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
    #: buy another. Absent on a manage-only row — gear held but not sold
    #: by the list being read.
    buy: Listing | None = None
    expanded: bool = False


@dataclass
class CatalogueCategory:
    """One category heading and its rows. An empty name means the content
    filed nothing here, and the rows sit straight inside the section."""

    name: str
    rows: list = field(default_factory=list)


@dataclass
class CatalogueSection:
    """One section heading and its categories."""

    name: str
    categories: list[CatalogueCategory] = field(default_factory=list)


@dataclass
class Catalogue:
    """A whole equip surface for one fighter, ready to draw."""

    name: str
    sections: list[CatalogueSection] = field(default_factory=list)

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


def pick_groups(offered, key, taken=None):
    """Offered alternatives as controls, in the offer's own order.

    The order is load-bearing: a control submits its place in the set and
    whatever answers the form reads that place against the offer it
    re-derives, so this walks one derivation of the offer and never a
    second.

    ``taken`` is the sets something already holds, where it holds any: the
    same controls, starting on what it took rather than on what a buyer
    would be handed. Left out — which is what a row for sale means — each
    set starts on the one taken unasked.
    """
    return tuple(
        PickGroup(
            choose=group.choose,
            field=choice_field(key, index),
            options=tuple(
                GroupOption(
                    name=option.name,
                    value=str(position),
                    surcharge=option.surcharge,
                    is_default=option.is_default,
                    checked=(
                        option.is_default
                        if taken is None
                        else option.default_set is not None
                        and option.default_set.pk in taken
                    ),
                )
                for position, option in enumerate(group.options)
            ),
            nothing_taken=(
                taken is None
                or not any(
                    option.default_set is not None and option.default_set.pk in taken
                    for option in group.options
                )
            ),
        )
        for index, group in enumerate(offered)
    )


def listing_row(line):
    """One line of a browsed collection as a row that offers to sell it."""
    key = thing_key(line.thing)
    return Listing(
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
        choices=pick_groups(line.choices, key),
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
        chosen=copy.chosen,
        accessorise=(
            Action("Add accessory", LINK, copy.accessorise_href, SECONDARY)
            if copy.accessorise_href
            else None
        ),
        more=(
            # First, and only where the content asks anything: the one act
            # here that leaves the fighter holding what they held, so it
            # reads before the ways of parting with it.
            *(
                (Action("Change options", LINK, copy.rechoose_href, SECONDARY),)
                if copy.rechoose_href
                else ()
            ),
            Action("Reassign", LINK, copy.reassign_href, SECONDARY),
            *(
                (Action("Refund", LINK, copy.refund_href, SECONDARY),)
                if refunds
                else ()
            ),
            Action("Delete", LINK, copy.remove_href, SECONDARY),
        ),
    )


def owned_row(row, copies, refunds=True, expanded=False):
    return OwnedRow(
        key=row.key,
        name=row.name,
        count=len(copies),
        copies=tuple(copy_row(copy, refunds=refunds) for copy in copies),
        buy=row,
        expanded=expanded,
    )


def owned_row_manage_only(key, copies, refunds=True, expanded=False):
    return OwnedRow(
        key=key,
        name=copies[0].name,
        count=len(copies),
        copies=tuple(copy_row(copy, refunds=refunds) for copy in copies),
        buy=None,
        expanded=expanded,
    )


def build_stash_catalogue(owned, name, refunds=True, expanded_key=""):
    catalogue = Catalogue(name=name)
    section = CatalogueSection(name=name)
    rows = [
        owned_row_manage_only(
            key,
            copies,
            refunds=refunds,
            expanded=key == expanded_key,
        )
        for key, copies in sorted(
            owned.items(), key=lambda item: item[1][0].name.casefold()
        )
    ]
    section.categories.append(CatalogueCategory(name="", rows=rows))
    catalogue.sections.append(section)
    return catalogue


def build_catalogue(view, owned, name=None, refunds=True, expanded_key=""):
    """A browsed collection joined to what one fighter already holds.

    ``owned`` is the index :func:`n26.core.owned.possessions` returns,
    keyed the way rows are keyed — so the join is one dictionary read per
    row, however much the fighter is carrying and however long the list.

    ``refunds`` rides down to every owned copy: a gang with no budget is
    offered no Refund anywhere in the catalogue.

    Sections keep the order and the shape the browse gave them, with one
    substitution: a section the content left unnamed is called
    "Uncategorised" here. A catalogue is drawn as a strip of tabs, and a
    tab with no word on it is one nobody can click.
    """
    catalogue = Catalogue(name=name or view.name)
    for section in view.sections:
        drawn = CatalogueSection(name=section.name or UNCATEGORISED)
        for category in section.categories:
            rows = []
            for line in category.lines:
                row = listing_row(line)
                copies = owned.get(row.key)
                rows.append(
                    owned_row(
                        row,
                        copies,
                        refunds=refunds,
                        expanded=row.key == expanded_key,
                    )
                    if copies
                    else row
                )
            drawn.categories.append(CatalogueCategory(name=category.name, rows=rows))
        catalogue.sections.append(drawn)
    return catalogue
