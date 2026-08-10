"""Browsing a collection — one rendered shape, however it was defined.

A curated collection (stored entries: an equipment list, a variant
trading post) and a derived one (no rows: the default Trading
Post) both come out as the same structure — taxonomy groups of priced
lines — so a browsing UI never learns which species it is looking at.
Same move as the model card and the hire view.

Prices resolve through ``n26.library.models.collection.price_of`` in both
cases: that single function is what stops the two species drifting.

Grouping derives from each item's **home category** (fixed per assignable
— see ``n26.library.models.category``), in taxonomy order. Items without a
home gather at the end under no heading.
"""

from dataclasses import dataclass, field

from n26.core.notes import WARNING, Note
from n26.core.taxonomy import group_by_home
from n26.library.models import Optioned, price_of


@dataclass(frozen=True)
class Terms:
    """The terms a collection is shopped on. Usage, never content.

    Charging is not a concern of a collection — a collection declares
    contents and prices, and the code that handles a purchase decides how it
    is charged. The same list can be browsed as a plain list (everything
    visible, nothing spends Trade Points) or as a trading trip (TP
    charged, Exclusive items withheld — "E" means equipment list
    only, in both editions).

    This is also where per-trip mechanics will live: the Nomad post's
    scavenge availability is a fact about *today's visit*, not about the
    collection, so a future field here ("purchasable when availability
    ≥ X") filters the day's listing per session. The TP budget itself — minted or
    granted, pooled or per-fighter, temporary or standing — is the
    session's, not the terms': see design/collections.md.
    """

    charges_trade_points: bool = False
    shows_exclusive: bool = True


#: Browsing a list: everything the author put there, nothing charges TP.
EQUIPMENT_LIST = Terms()
#: A trading trip: purchases spend Trade Points, Exclusive items are off
#: the listing. What makes shopping "at a trading post" is the terms you
#: shop on, not the collection you shop from.
TRADING_POST = Terms(charges_trade_points=True, shows_exclusive=False)


@dataclass(frozen=True)
class OfferedOption:
    """One alternative a line offers the buyer — a mount's plasma guns.

    ``surcharge`` is what taking this adds to the line's own price, which
    is not the same as the set's stored price: the quoted price already
    includes whatever a pick-one set takes unasked, so the number worth
    printing beside an option is the distance from there. Taking the head
    of a pick-one set therefore adds nothing, and a swap adds the
    difference. It may be negative, where the alternative is the cheaper
    one.

    ``default_set`` is what materialises if this is taken — the thing
    ``Operation.buy`` is handed as ``option=``.
    """

    name: str
    surcharge: int
    is_default: bool
    default_set: object


@dataclass(frozen=True)
class OfferedGroup:
    """One set of the alternatives a line offers.

    ``choose`` is "one" (exactly one, the default marked), "any" (take any
    number, none by default) or "one-or-none" (at most one, none by
    default) — the same three the hire view draws.

    The set has no name here, deliberately, exactly as at hire: the one
    the content carries is the author's label for their own page, and a
    player is shown the options rather than the question. What a reader
    needs is that these go together, which is the grouping itself.
    """

    choose: str
    options: tuple = ()


@dataclass(frozen=True)
class PricedLine:
    """One line of a collection's listing: the item, and what buying it *here* costs.

    A line is a complete purchase — ``Operation.buy`` takes one whole, so
    nothing is disassembled and reassembled at the till.
    """

    thing: object
    credits: int
    trade_points: int
    is_exclusive: bool
    #: The entry that priced this line. None on a derived collection:
    #: reference prices, no row anywhere.
    entry: object = None
    #: Whether buying here spends Trade Points. An equipment list never
    #: charges them; a trading post does. Rides the line so the till
    #: needs no idea where the line came from.
    charges_trade_points: bool = False
    #: Whether the surface this line came from deals in Trade Points at
    #: all — a fact about the collection, not about the shopping trip.
    #: A collection whose contents were chosen *by* having a TP price
    #: deals in them; one an author wrote out by hand does not, and a
    #: number drawn there answers a question nobody browsing it can ask.
    #: The line keeps the item's real figures either way; this says
    #: whether a surface should print them, and "E" goes with them,
    #: because "E" is a Trade Point value and not a separate mark.
    shows_trade_points: bool = False
    #: Remarks for the player about this line — "usable by Walkers only",
    #: later "over your weapon slots". One channel, not a flag per rule;
    #: see ``n26.core.notes``. Empty on unexamined views: default open.
    notes: tuple = ()
    #: Nested lines riding this one — a weapon's paid ammo and firing
    #: modes, printed under the gun the way the book's table does. Each
    #: part is itself a PricedLine, so the till buys one the same way:
    #: onto the gun's own assignment, which is what a profile hangs off.
    parts: tuple = ()
    #: The alternatives this line offers at the till — a mount's grenade
    #: launchers or, for a surcharge, its plasma guns. Sets that offer no
    #: real choice are left out, so anything here is worth asking about.
    #: Empty for everything that offers none, which is most of a listing.
    choices: tuple = ()

    @property
    def name(self):
        return str(self.thing)


@dataclass
class CategoryGroup:
    """One category heading and its lines."""

    name: str
    lines: list[PricedLine] = field(default_factory=list)


@dataclass
class SectionGroup:
    """One section heading and its categories."""

    name: str
    categories: list[CategoryGroup] = field(default_factory=list)


@dataclass
class CollectionView:
    """A whole browsable surface, ready to draw."""

    name: str
    sections: list[SectionGroup] = field(default_factory=list)

    def all_lines(self):
        for section in self.sections:
            for category in section.categories:
                yield from category.lines


def browse(collection, terms=EQUIPMENT_LIST):
    """A collection, browsed: its selector sweeps plus its entries.

    Entries win over selectors for the same item — that is where per-item
    customisation lives (the Nomad post pricing Imperial equipment above
    the usual). Swept-in items sell at reference. The ``terms``
    are the caller's — how this browse charges is the shopping flow's
    business, not the collection's — and they ride every line so the till
    never needs to know where a line came from.

    Sweeps respect the terms (a trading trip has no Exclusive items on
    the listing); curated entries always show — they are the author's
    explicit word.

    **A collection shows only what it lists.** For a sweep that is what
    the criteria caught, ammo included: membership at a Trading Post is
    having a Trade Point price, and that is asked of a gun's rounds as
    much as of the gun. For a curated list it is the entries and nothing
    else — including the ammo, which is the list's own row for that ammo
    at the list's own price. A gun's other profiles are not on the list
    and do not appear under it.

    Whether the listing talks in Trade Points follows from the same
    fact. A collection whose contents were chosen *by* having a TP price
    deals in them; one written out by hand prices in credits, and a TP
    figure or an "E" there answers a question nobody browsing it can
    ask. Each line says which, and the lines keep the item's real
    numbers regardless — see ``shows_trade_points``.

    A fixed number of queries: the entries with their prefetches, plus
    one per selector row — the count follows the collection's
    *definition*, never its size.
    """
    from n26.library.models import CollectionEntry
    from n26.library.models.assignable import (
        OPTION_OFFER_PATHS,
        USABLE_BY_LISTS,
        UsableBy,
    )
    from n26.library.models.collection import ENTRY_ASSIGNABLE_FIELDS

    lines = {}
    selectors = list(collection.selectors.select_related("of_kind"))
    # Read off the definition rather than the name: a pack's own
    # TP-swept collection is a trading post whatever it was called, and
    # a list called one is not.
    in_trade_points = any(selector.with_trade_point_price for selector in selectors)

    for selector in selectors:
        for thing in selector.contents(include_exclusive=terms.shows_exclusive):
            price = price_of(thing)
            lines[_key(thing)] = (
                thing.category,
                PricedLine(
                    thing=thing,
                    credits=price.credits,
                    trade_points=price.trade_points,
                    is_exclusive=price.is_exclusive,
                    charges_trade_points=terms.charges_trade_points,
                    shows_trade_points=in_trade_points,
                    parts=_swept_parts(thing, terms, in_trade_points),
                    choices=_offered_choices(thing),
                ),
            )

    # Prefetch paths rather than joins: joined, the kinds and their
    # category chains make a select wide enough that planning it costs
    # more than running it, and a kind no entry names never queries.
    entries = list(
        collection.entries.prefetch_related(
            *ENTRY_ASSIGNABLE_FIELDS,
            *(f"{name}__category__section" for name in ENTRY_ASSIGNABLE_FIELDS),
            # Use-restriction lists, derived for every kind carrying the
            # mixin — so noting a whole listing costs no extra queries,
            # whichever kind an author narrowed and however they narrowed it.
            *(
                f"{name}__{listed}"
                for name in ENTRY_ASSIGNABLE_FIELDS
                if issubclass(
                    CollectionEntry._meta.get_field(name).related_model, UsableBy
                )
                for listed in USABLE_BY_LISTS
            ),
            # The alternatives a line offers at the till, derived for every
            # kind that can carry them — so a list of a hundred mounts puts
            # their swaps on screen for the same queries as a list of one.
            *(
                f"{name}__{path}"
                for name in ENTRY_ASSIGNABLE_FIELDS
                if issubclass(
                    CollectionEntry._meta.get_field(name).related_model, Optioned
                )
                for path in OPTION_OFFER_PATHS
            ),
        )
    )
    ammo = _ammo_by_weapon(entries)
    housed = {entry.pk for rows in ammo.values() for entry in rows}

    for entry in entries:
        if entry.pk in housed:
            continue
        thing = entry.assignable
        price = price_of(thing, entry)
        lines[_key(thing)] = (
            thing.category,
            PricedLine(
                thing=thing,
                credits=price.credits,
                trade_points=price.trade_points,
                is_exclusive=price.is_exclusive,
                entry=entry,
                charges_trade_points=terms.charges_trade_points,
                shows_trade_points=in_trade_points,
                parts=_entry_parts(
                    ammo.get(entry.weapon_id, ()), terms, in_trade_points
                ),
                choices=_offered_choices(thing),
            ),
        )

    return _sectioned(str(collection), lines.values())


def _offered_choices(thing):
    """The sets of alternatives this thing puts to a buyer.

    Read off the same offer a hire reads (``Optioned.grouped_offers``), so
    a mount's swaps are one description of the content however it is
    acquired. Prefetched by the browse, so a listing pays no query per
    line; a thing that offers nothing has nothing here.

    Sets that are not a choice are left out: a pick-one set with a single
    option is taken unasked, and drawing it would ask a reader to consider
    something they cannot change. What comes back is what a surface draws
    *and* what the till reads a submitted answer against, so a set missing
    here is one nothing can name.
    """
    if not isinstance(thing, Optioned):
        return ()
    groups = []
    for group, offered in thing.grouped_offers():
        choose = group.choose if group is not None else "one"
        one_of = choose == "one"
        if one_of and len(offered) < 2:
            continue
        # A pick-one set's head is already in the price the line quotes, so
        # what an option adds is measured from there: taking the head adds
        # nothing and a swap adds the difference.
        included = offered[0].price if one_of else 0
        groups.append(
            OfferedGroup(
                choose=choose,
                options=tuple(
                    OfferedOption(
                        name=option.name,
                        surcharge=option.price - included,
                        is_default=one_of and position == 0,
                        default_set=option.default_set,
                    )
                    for position, option in enumerate(offered)
                ),
            )
        )
    return tuple(groups)


def _ammo_by_weapon(entries):
    """The list's own profile entries, filed under the gun they belong to.

    A profile a list names is that list's row for that ammo, and it
    belongs under the gun rather than beside it — otherwise a reader
    cannot buy the two on one press, and the same thing can be priced
    twice on one page by two different routes.

    A profile whose gun the list does not name keeps a row of its own:
    there is nothing to file it under, and dropping it would hide
    something the author wrote down. A blank profile is never filed —
    it *is* the weapon's own line, so it is bought with the gun.
    """
    weapons = {entry.weapon_id for entry in entries if entry.weapon_id is not None}
    filed = {}
    for entry in entries:
        profile = entry.weapon_profile
        if profile is None or not profile.name:
            continue
        if profile.weapon_id in weapons:
            filed.setdefault(profile.weapon_id, []).append(entry)
    return filed


def _entry_parts(entries, terms, shows_trade_points):
    """A curated gun's ammo: the list's own entries, at the list's prices.

    Priced through the entry like every other line the list carries, so
    an author who reprices a round reprices the one the reader presses.
    Whether the profile costs anything of its own is beside the point —
    a list naming a free profile at 15 credits is the list selling it at
    15 credits.
    """
    parts = []
    for entry in entries:
        price = price_of(entry.weapon_profile, entry)
        parts.append(
            PricedLine(
                thing=entry.weapon_profile,
                credits=price.credits,
                trade_points=price.trade_points,
                is_exclusive=price.is_exclusive,
                entry=entry,
                charges_trade_points=terms.charges_trade_points,
                shows_trade_points=shows_trade_points,
            )
        )
    return tuple(parts)


def _swept_parts(thing, terms, shows_trade_points):
    """The nested lines a swept thing carries — a weapon's paid ammo and
    firing modes, prefetched to ``tradeable_profiles`` by the sweep that
    found it, so a whole listing's parts cost one query. Things without
    the prefetch simply have no parts.

    A sweep's rule applies to ammo as it does to guns: what the criteria
    caught is what is on the listing.
    """
    parts = []
    for part in getattr(thing, "tradeable_profiles", ()):
        price = price_of(part)
        parts.append(
            PricedLine(
                thing=part,
                credits=price.credits,
                trade_points=price.trade_points,
                is_exclusive=price.is_exclusive,
                charges_trade_points=terms.charges_trade_points,
                shows_trade_points=shows_trade_points,
            )
        )
    return tuple(parts)


def _key(thing):
    return (thing._meta.label_lower, thing.pk)


def placements_for(computed, collection):
    """Where each category sits for this fighter, on this collection's
    listing, folded from their card.

    ``{category: CategoryPlacement}`` — placements are **scoped**: a
    placement aims at a section row, and section rows belong to a
    collection, so a placement into some other collection's schema simply
    does not apply here. When two carriers place the same category, the
    **lowest section position wins** (a Psy-Gheist profile placing powers
    under Primary at 0 beats the Wyrd subtype's Secondary at 1) —
    ordering, the same conflict rule as everywhere else, with the numbers
    agreed once in the collection's schema. There is no access table:
    this is read off the card like everything else.
    """
    placements = {}
    for placement in computed.placements:
        if placement.section.collection_id != collection.pk:
            continue
        held = placements.get(placement.category)
        if held is None or placement.section.position < held.section.position:
            placements[placement.category] = placement
    return placements


def usability_for(computed):
    """The fighter as selector food, for use-restrictions.

    **Computed facts, as adapter policy** — the card's printed subtypes
    *plus* what modifiers granted, so a wargear that grants Walker makes
    walker-only skills usable, the same transitivity as everything else
    read off the card. This runs after ``compute``, so it can afford to;
    the scope adapter (``Card.model_matchable``) runs during it and
    deliberately cannot. One engine, two documented fact policies.
    """
    granted = [contribution.thing for contribution in computed.subtypes]
    return computed.card.model_matchable().also(*granted)


def with_use_notes(view, fighter):
    """The same view, with a note on every line this fighter can't use.

    "(Fighter Or Walker Only)" is the item's own data (``UsableBy``);
    this asks the question for one fighter and writes the answer as a
    :class:`n26.notes.Note` pointing at the item itself — identity, so
    nothing downstream ever matches on text. Nothing is removed — an
    unusable skill stays in the listing, noted, because we inform, never
    police. Unrestricted things get no note.

    View in, view out: composes with ``regrouped_by_placement`` and
    ``narrow`` — the roll-12 pick ("any set, if your Type/Subtype may
    use it") is ``narrow(noted, without_warnings=True)``.
    """
    import dataclasses

    noted = CollectionView(name=view.name)
    for section in view.sections:
        regrouped = SectionGroup(name=section.name)
        for category in section.categories:
            lines = []
            for line in category.lines:
                check = getattr(line.thing, "is_usable_by", None)
                if check is None or check(fighter):
                    lines.append(line)
                    continue
                allowed = [
                    *line.thing.usable_by_profiles.all(),
                    *line.thing.usable_by_profile_types.all(),
                    *line.thing.usable_by_subtypes.all(),
                    *line.thing.usable_by_specialisations.all(),
                ]
                note = Note(
                    text="usable by " + " or ".join(str(a) for a in allowed) + " only",
                    about=line.thing,
                    level=WARNING,
                )
                lines.append(dataclasses.replace(line, notes=(*line.notes, note)))
            regrouped.categories.append(CategoryGroup(name=category.name, lines=lines))
        noted.sections.append(regrouped)
    return noted


def regrouped_by_placement(view, placements, fallback=None, name=None):
    """The same view, resectioned by where this fighter's placements
    put each category.

    A category is fundamental — Agility is Agility for everyone — but its
    *section* is dynamic: whatever the fighter's placements say
    ("Primary", "Secondary", or any section content invents), falling
    back for anything unplaced. ``fallback`` is the collection's own
    default section row (``collection.default_section()``) — part of its
    schema, so its name and position are content too; a code-level
    "Other", last, is only the safety net for collections that never
    declared one. Section names live in content, not here, and this
    regrouping is computed per fighter and never stored.

    Sections order by their placements' positions, fallback last;
    categories keep taxonomy order within them. Same shape in, same shape
    out: anything that draws a collection draws this, and
    ``narrow(view, sections=["Primary"])`` is literally the advancement
    table's "select a Primary skill".

    The fallback keeps everything unplaced — Inherent, unrevealed power
    families, other gangs' sets. We inform, not police: a surface may
    collapse it, but the data never hides it.
    """
    if fallback is not None:
        unplaced_name, unplaced_order = fallback.name, fallback.position
    else:
        unplaced_name, unplaced_order = "Other", float("inf")

    sections = {}  # section name -> (order, {home category -> lines})
    for section in view.sections:
        for category in section.categories:
            for line in category.lines:
                home = getattr(line.thing, "category", None)
                placement = placements.get(home)
                if placement is None:
                    section_name, order = unplaced_name, unplaced_order
                else:
                    section_name, order = (
                        placement.section.name,
                        placement.section.position,
                    )
                held_order, homes = sections.setdefault(section_name, (order, {}))
                if order < held_order:
                    sections[section_name] = (order, homes)
                homes.setdefault(home, []).append(line)

    def taxonomy_order(home):
        if home is None:
            return (1, 0, "")
        return (0, home.position, home.name.lower())

    regrouped = CollectionView(name=name or view.name)
    for section_name, (_, homes) in sorted(
        sections.items(), key=lambda item: (item[1][0], item[0])
    ):
        group = SectionGroup(name=section_name)
        for home in sorted(homes, key=taxonomy_order):
            group.categories.append(
                CategoryGroup(name=home.name if home else "", lines=homes[home])
            )
        regrouped.sections.append(group)
    return regrouped


def offered_by(slot, computed, terms=EQUIPMENT_LIST):
    """What *this* fighter may pick to answer a choice slot.

    A slot narrowed to a tier ("a Skill from a set that is Primary for
    them") is answered by the view they already browse: take the
    section's collection, resection it by their placements, and keep that
    tier. So a Leader's pickable skills and the skills they browse
    are the same list built the same way — the pick is a shop with one
    section showing, not a second mechanism.

    An unnarrowed slot has no collection to browse, so it answers with the
    whole kind. Either way this is a **list to offer**, never a rule:
    ``Operation.choose`` checks the kind and nothing else, so an
    owner may still hand over something off-list.
    """
    offer = slot.offer
    section = getattr(offer, "from_section", None) if offer is not None else None
    if section is None:
        return None if offer is None else offer.choosables()

    collection = section.collection
    view = browse(collection, terms)
    placed = regrouped_by_placement(
        view,
        placements_for(computed, collection),
        fallback=collection.default_section(),
        name=slot.kind_label,
    )
    return narrow(placed, sections=[section.name], name=slot.kind_label)


def with_fit_notes(view, weapon):
    """The same view, noted for fitting one particular weapon.

    Browsing accessories *for* a lasgun marks what will not fit it —
    "(Las Weapons Only)" as a note pointing at the item, same channel
    and same default-open rule as the fighter restrictions. Nothing is
    removed; the owner may bolt anything to anything.
    """
    import dataclasses

    noted = CollectionView(name=view.name)
    for section in view.sections:
        regrouped = SectionGroup(name=section.name)
        for category in section.categories:
            lines = []
            for line in category.lines:
                check = getattr(line.thing, "fits", None)
                if check is None or check(weapon):
                    lines.append(line)
                    continue
                note = Note(
                    text=f"does not fit {weapon.name}: "
                    f"{line.thing.fits_selector()} only",
                    about=line.thing,
                    level=WARNING,
                )
                lines.append(dataclasses.replace(line, notes=(*line.notes, note)))
            regrouped.categories.append(CategoryGroup(name=category.name, lines=lines))
        noted.sections.append(regrouped)
    return noted


def narrow(
    view,
    *,
    credits=None,
    trade_points=None,
    categories=None,
    sections=None,
    include_exclusive=True,
    without_warnings=False,
    name=None,
):
    """A custom view of a collection: the same sections, fewer things in them.

    Narrowing takes a ``CollectionView`` and returns one, so anything that
    draws a collection draws a filtered collection with no extra work —
    a search box and a whole equipment list are the same screen.

    ``credits`` and ``trade_points`` are inclusive ``(low, high)`` bounds;
    ``None`` at either end leaves it open, and either argument may be
    omitted entirely. ``categories`` and ``sections`` name what to keep.

    Categories are matched as **objects, not names**: a category name is
    only unique within its section (the rulebook has Primitive Weapons
    under both Ranged and Close Combat), so matching by name would
    silently pick up both.

    Filtering by ``trade_points`` drops Exclusive items — "E" is not a
    number and sits in no numeric range. Ask for them with
    ``include_exclusive`` where the range is not the point.

    ``without_warnings`` drops lines carrying warning-or-louder notes —
    the roll-12 pick over a use-noted view. The notes must have been
    written first (``with_use_notes``); an unexamined view has none.

    The sectioning that came in is the sectioning that goes out. That matters
    for a view already resectioned by a fighter's placements: narrowing
    it to ``sections=["Primary"]`` must keep *their* Primary, and
    re-deriving headings from the taxonomy would quietly hand back
    "Skills" instead. Empty categories and sections fall away.
    """
    wanted_categories = _as_set(categories)
    wanted_sections = _as_set(sections)

    def keeps(line):
        home = getattr(line.thing, "category", None)
        if wanted_categories is not None and home not in wanted_categories:
            return False
        if line.is_exclusive:
            if not include_exclusive or trade_points is not None:
                return False
        elif line.trade_points is None:
            # Not offered at the Trading Post: no number, so it sits in
            # no numeric range — same rule as Exclusive.
            if trade_points is not None:
                return False
        elif not _within(line.trade_points, trade_points):
            return False
        if not _within(line.credits, credits):
            return False
        if without_warnings and any(note.at_least(WARNING) for note in line.notes):
            return False
        return True

    narrowed = CollectionView(name=name or view.name)
    for section in view.sections:
        if wanted_sections is not None and section.name not in wanted_sections:
            continue
        categories_kept = [
            CategoryGroup(name=category.name, lines=lines)
            for category in section.categories
            if (lines := [line for line in category.lines if keeps(line)])
        ]
        if categories_kept:
            narrowed.sections.append(
                SectionGroup(name=section.name, categories=categories_kept)
            )
    return narrowed


def _as_set(value):
    """None means "no filter"; a single thing means a set of one."""
    if value is None:
        return None
    if isinstance(value, str) or not hasattr(value, "__iter__"):
        return {value}
    return set(value)


def _within(value, bounds):
    if bounds is None:
        return True
    low, high = bounds
    if low is not None and value < low:
        return False
    return not (high is not None and value > high)


def _sectioned(name, categorised_lines):
    """A collection's ``(category, line)`` pairs as a browsable surface.

    The grouping itself is the taxonomy's, shared with every other
    surface that files rows under headings; only the containers and the
    order lines take within a category are this one's own. A section the
    content left homeless keeps an empty heading here — a browse says
    what the content says, and naming it belongs to whatever draws it.
    """

    def item_order(line):
        # Within a category, the item's own position rules — a skill's D6
        # number in its set — with name as the tiebreak.
        return (getattr(line.thing, "position", 0), line.name)

    return CollectionView(
        name=name,
        sections=group_by_home(
            categorised_lines,
            section=lambda heading, categories: SectionGroup(
                name=heading, categories=categories
            ),
            category=lambda heading, lines: CategoryGroup(name=heading, lines=lines),
            order=item_order,
        ),
    )
