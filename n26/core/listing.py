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
from n26.library.models import slot_mark, slots_of

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
    """A listing control's submission or navigation target and semantic tone.

    ``kind`` is SUBMIT or LINK. ``target`` is the submitted value or URL.
    ``tone`` is PRIMARY for the main action, DANGER for removal, or SECONDARY.
    Templates map these meanings to visual styles.
    ``separator_before`` groups links when the action appears in a menu.
    """

    label: str
    kind: str
    target: str
    tone: str
    separator_before: bool = False


@dataclass(frozen=True)
class OptionRow:
    """A component selected as part of its parent purchase, such as ammunition.

    It shares the parent's Buy control. ``index`` identifies its position in
    the server-derived list, preventing submission of an unoffered component.
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
    #: Informational restrictions displayed beneath this part without hiding it.
    notes: tuple = ()


@dataclass(frozen=True)
class GroupOption:
    """An offered option and its surcharge within one listing's group.

    ``value`` is its index in the server-derived alternatives. The server
    validates against that list. ``surcharge_label`` is the displayed adjustment.
    """

    name: str
    value: str
    surcharge: int
    #: Whether this is the one its set takes unasked. A fact about the
    #: offer, true wherever the offer is drawn.
    is_default: bool
    #: Initial selection for this display: acquisition defaults or held options.
    checked: bool = False
    #: Change previews compare full set prices, including a priced default.
    price: int = 0
    set_key: str = ""

    @property
    def surcharge_label(self):
        if self.surcharge == 0:
            return ""
        sign = "+" if self.surcharge > 0 else "−"
        return f"{sign}{abs(self.surcharge)}¢"


@dataclass(frozen=True)
class PickGroup:
    """An option group requiring one, any, or at most one selection.

    ``choose`` records that rule; templates choose the controls. Internal
    set names are not exposed as player-facing group labels.
    """

    choose: str
    #: The input every option in this group shares.
    field: str
    options: tuple[GroupOption, ...]
    #: Initial None selection for one-or-none radio groups.
    nothing_taken: bool = True


class SlotMarked:
    """A row that draws the book's asterisk after a two-slot weapon's name.

    The rows carry ``slots`` — the library's number, 1 for anything that
    is not a weapon — and a template draws ``marked_name``, the name with
    the mark after it, so the mark is never written into a name and never
    lost from one. ``name`` stays the bare name a catalogue is keyed by.
    """

    @property
    def slot_mark(self):
        return slot_mark(self.slots)

    @property
    def marked_name(self):
        return f"{self.name}{self.slot_mark}"


@dataclass(frozen=True)
class Listing(SlotMarked):
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
    #: Weapon slots this takes on a card; see :class:`SlotMarked`.
    slots: int = 1


@dataclass(frozen=True)
class OwnedPartRow:
    """Something hanging off a copy the fighter holds: ammo, an accessory.

    A weapon profile has no move among its actions: it *is* the weapon's
    own profile, and ``Operation.move`` refuses it. An accessory the gang
    bought can come off, so Detach and Fit sit with Refund and Remove
    when there is somewhere for them to go.
    """

    id: str
    key: str
    name: str
    #: What this part contributed to the fighter's rating on its own.
    rating: int
    #: Empty when this part came with the gun — a named free profile
    #: draws a row for its statline, and nothing to click.
    sell: Action | None
    more: tuple[Action, ...]


@dataclass(frozen=True)
class OwnedCopyRow(SlotMarked):
    """One copy the fighter holds, with whatever hangs off it."""

    id: str
    key: str
    name: str
    #: This copy's rating excluding parts. Settlement calculates current sale
    #: proceeds from stored assignments.
    rating: int
    parts: tuple[OwnedPartRow, ...]
    sell: Action
    more: tuple[Action, ...]
    #: Accessory-fitting URL for weapons, separate from removal actions.
    accessorise: Action | None = None
    #: Selected option labels in offer order. Their surcharges already count
    #: in the copy's rating.
    chosen: tuple[str, ...] = ()
    #: Weapon slots this takes on a card; see :class:`SlotMarked`.
    slots: int = 1


@dataclass(frozen=True)
class OwnedRow(SlotMarked):
    """A row for something the fighter is already carrying.

    ``count`` is copies, not pieces: two Autoguns with a paid round on
    one of them is two. A round is not a thing you own an Autogun's worth
    of, and counting it would say the fighter had three guns.
    """

    key: str
    name: str
    count: int
    copies: tuple[OwnedCopyRow, ...]
    #: Listing for buying another copy, absent when the catalogue does not
    #: sell this held item.
    buy: Listing | None = None
    expanded: bool = False
    #: Weapon slots this takes on a card; see :class:`SlotMarked`. The
    #: listing's where there is one, else the held copies'.
    slots: int = 1


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
    """Return displayed Trade Points only when the browse uses that currency.

    Keep the original amount on the browsed line even when hidden here.
    """
    return line.trade_points if line.shows_trade_points else None


def _shown_exclusive(line):
    """Whether to display E for an exclusive item in a Trade Point browse."""
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
            notes=tuple(part.notes),
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
                    price=option.default_set.price
                    if option.default_set is not None
                    else 0,
                    set_key=str(option.default_set.pk)
                    if option.default_set is not None
                    else "",
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


def pick_group_props(groups):
    """JSON-safe option controls, with prices for purchase and change previews."""
    return [
        {
            "choose": group.choose,
            "field": group.field,
            "nothingTaken": group.nothing_taken,
            "options": [
                {
                    "name": option.name,
                    "value": option.value,
                    "surcharge": option.surcharge,
                    "surchargeLabel": option.surcharge_label,
                    "price": option.price,
                    "setKey": option.set_key,
                    "checked": option.checked,
                }
                for option in group.options
            ],
        }
        for group in groups
    ]


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
        # Submit identity only. The server rebuilds the listing and validates
        # that this line is offered.
        buy=Action(label="Buy", kind=SUBMIT, target=key, tone=PRIMARY),
        choices=pick_groups(line.choices, key),
        slots=slots_of(line.thing),
    )


def copy_row(copy, refunds=True):
    """Describe one held copy's permitted controls and semantic tones.

    ``OwnedThing`` supplies their targets. Offer Refund when credits are
    refundable or this copy was bought with refundable Trade Points.
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
                sell=(
                    Action("Sell", LINK, part.sell_href, DANGER)
                    if part.sell_href
                    else None
                ),
                # Paid ammunition can be refunded or removed independently. Included
                # weapon profiles cannot, since they have no separate acquisition.
                more=(
                    # List detach and fit controls before removal controls.
                    *(
                        (Action("Detach", LINK, part.detach_href, SECONDARY),)
                        if part.detach_href
                        else ()
                    ),
                    *(
                        (Action("Fit to a weapon", LINK, part.fit_href, SECONDARY),)
                        if part.fit_href
                        else ()
                    ),
                    *(
                        (Action("Refund", LINK, part.refund_href, SECONDARY),)
                        if (refunds or part.paid_trade_points) and part.refund_href
                        else ()
                    ),
                    *(
                        (Action("Remove", LINK, part.remove_href, DANGER),)
                        if part.remove_href
                        else ()
                    ),
                ),
            )
            for part in copy.parts
        ),
        sell=Action("Sell", LINK, copy.sell_href, DANGER),
        chosen=copy.chosen,
        slots=copy.slots,
        accessorise=(
            Action("Add accessory", LINK, copy.accessorise_href, SECONDARY)
            if copy.accessorise_href
            else None
        ),
        more=(
            # List option and fitting controls before removal. Offer them only when
            # the content has options or the fighter has a fitting destination.
            *(
                (Action("Change options", LINK, copy.rechoose_href, SECONDARY),)
                if copy.rechoose_href
                else ()
            ),
            *(
                (Action("Fit to a weapon", LINK, copy.fit_href, SECONDARY),)
                if copy.fit_href
                else ()
            ),
            *(
                (Action("Reassign", LINK, copy.reassign_href, SECONDARY),)
                if copy.reassign_href
                else ()
            ),
            *(
                (Action("Refund", LINK, copy.refund_href, SECONDARY),)
                if refunds or copy.paid_trade_points
                else ()
            ),
            Action("Delete", LINK, copy.remove_href, DANGER),
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
        slots=row.slots,
    )


def owned_row_manage_only(key, copies, refunds=True, expanded=False):
    return OwnedRow(
        key=key,
        name=copies[0].name,
        count=len(copies),
        copies=tuple(copy_row(copy, refunds=refunds) for copy in copies),
        buy=None,
        expanded=expanded,
        slots=copies[0].slots,
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
    """Combine browsed sections with possessions using content-key lookups.

    ``owned`` is the index from ``n26.core.owned.possessions``. ``refunds`` controls
    credit-refund availability on each copy; Trade Point refunds remain
    available where recorded. Preserve browse order and label otherwise
    unnamed sections Uncategorised so tabs have visible text.
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
