"""Buying equipment — the web face of :mod:`n26.core.browse`.

Two screens, one purchase. A fighter's equip page buys onto that
fighter; the gang's buys into the stash, where the gang's spare kit
waits for whoever needs it. Both re-derive the clicked line from the
list on screen, charge what the box says, and land back where the click
came from, so the two anchors cannot come to disagree about what buying
means — the click is read once, in ``_buy_clicked``.

Both screens also update without a rebuild. A click sent by htmx gets back
only the elements its act changed — the row, the gang's money, the accessory
panels — each carrying the id of the element it replaces; the shared protocol
is documented in :mod:`n26.core.views.htmx`. This module contributes
:func:`_screen`, the one derivation of what a screen shows, used by the pages
and by every update so the two cannot disagree, and :func:`render_update`,
which builds the update itself.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.template.defaultfilters import pluralize

from n26.core.confirm import CONFIRM_FIELD, Confirmation
from n26.core.listing import choice_field as _choice_field
from n26.core.listing import parts_field as _parts_field
from n26.core.listing import price_field as _price_field
from n26.core.owned import thing_key as _thing_key
from n26.core.views.htmx import is_htmx, no_update, with_toasts
from n26.core.views.permissions import (
    _own_gang_or_404,
    _own_miniature_or_404,
    trade_points_href,
)

#: The most a purchase will take for one line. No price in the game comes
#: near it; it is here because the number is typed by hand, and a slip on
#: the keyboard should be refused rather than stored — an unbounded
#: figure does not fit the ledger's integer column, and a gang playing
#: without a budget has nothing else to stop it.
PRICE_CEILING = 100_000

#: A price is a whole number of credits, written in plain digits.
#: Python's own ``int`` would also take "-5", "+5", "1_0" and digits from
#: other scripts, none of which a price field should quietly accept.
_WHOLE_CREDITS = re.compile(r"[0-9]+")


class BadPrice(Exception):
    """A typed price that is not a whole number of credits in range."""


def _parts_picked(data, key, line):
    """The parts a submission ticked on this line, each with the index it
    was drawn at, in the order drawn.

    Values are indices into the line the server has just re-derived, so a
    tampered form can name nothing the listing does not offer. A repeated
    index is refused as well: a checkbox cannot be ticked twice, and one
    click was never an order for two of the same ammo.

    The index comes back out because it names the part's own price field.
    """
    picked, seen = [], set()
    for value in data.getlist(_parts_field(key)):
        # isdigit before int: a negative index is a real index from the
        # far end, so "-1" would quietly resolve to another part rather
        # than being refused like every other index the line lacks.
        if not value.isdigit():
            raise Http404("No such option")
        index = int(value)
        if index >= len(line.parts) or index in seen:
            raise Http404("No such option")
        seen.add(index)
        picked.append((index, line.parts[index]))
    return picked


def _choices_picked(data, key, groups):
    """The alternatives a submission picked, group by group.

    Values are indices into the sets the server has just re-derived, so a
    tampered form can name nothing the offer does not hold — and a group
    that was not drawn has no field to pick from. The offer is passed in
    rather than read off a line, because the same reading answers a row
    being bought and a copy already held being changed.

    An empty value is a one-or-none set's "None": the reader took
    nothing, which is not a pick to pass on. A repeated index is refused
    like a repeated tick box — one click was never an order for two of the
    same swap.
    """
    picked = []
    for index, group in enumerate(groups):
        seen = set()
        for value in data.getlist(_choice_field(key, index)):
            if value == "":
                continue
            # isdigit before int: a negative index is a real index from the
            # far end, so "-1" would quietly resolve to another option in
            # the set rather than being refused like every other index it
            # does not have.
            if not value.isdigit():
                raise Http404("No such option")
            position = int(value)
            if position >= len(group.options) or position in seen:
                raise Http404("No such option")
            seen.add(position)
            picked.append(group.options[position])
    return picked


def price_typed(data, field, quoted, name):
    """What a purchase is charged: the price typed for it, or the price
    it quoted where the form carried none. The same reading for an equip
    page's listing and a hire — the box is the same control on both.

    The number arrives from the browser, so it is read as a whole number
    of credits and nothing else. A negative one would hand the gang
    credits and an enormous one would not fit the ledger; both are
    refused rather than trimmed, because with money, charging a figure
    nobody typed is worse than charging nothing and saying so.

    An empty box is not an override — the quote stands, which is the
    number the reader saw before anyone touched it.
    """
    raw = data.get(field)
    if raw is None or not raw.strip():
        return quoted
    raw = raw.strip()
    if not _WHOLE_CREDITS.fullmatch(raw) or int(raw) > PRICE_CEILING:
        raise BadPrice(
            f"{name}: a price is a whole number of credits, from 0 to {PRICE_CEILING}."
        )
    return int(raw)


def _price_typed(data, field, line):
    return price_typed(data, field, line.credits, line.name)


def _charge(line, paid, surcharge=0):
    """What the ledger is told about a line bought at a set price.

    The price the listing quoted stays the list price and the gap becomes
    the discount, so ``paid = list - discount`` still holds and the entry
    says both what the listing asked and what the gang handed over.

    Rating follows the list price, never the payment. Rating is what the
    gang owns and it is pinned for good: haggling a sword down does not
    make it a lesser sword, and paying over the odds does not make it a
    better one. Only the credits leaving the bank move.

    ``surcharge`` is what the options picked on this line add. It
    lands on both figures, because a mount with plasma guns is a dearer
    mount and not a discounted one: what was agreed at the table is the
    gap between the two, and picking an option never changes it.
    """
    listed = line.credits + surcharge
    paid = paid + surcharge
    return {"paid": paid, "list_price": listed, "discount": listed - paid}


#: What a collection's name says at the end when it says what it is. Every
#: tab in the strip is a list to buy from, so the words they all share are
#: the ones worth dropping.
LIST_SUFFIX = "equipment list"


def _trade_points_asked(line, picked):
    """What one click spends at the post, the ticked parts included.

    A line says whether it charges Trade Points at all — the terms it
    was browsed on ride it — so a list that merely prints TP figures
    adds nothing here. Options add nothing either: a swap changes what
    the thing is built from and is paid for in credits.

    No Trade Point price is nothing to pay, not nothing to sell. A post
    swept together by having such a price holds only things that have
    one, but an author may add an entry to that same collection by hand,
    and that line is browsed on the post's terms with no figure behind
    it. It is a line on a post, so it is bought; it names no Trade
    Points, so it takes none.
    """
    asked = line.trade_points if line.charges_trade_points else 0
    return (asked or 0) + sum(
        part.trade_points or 0 for _, part in picked if part.charges_trade_points
    )


def _overspend(request, gang, line, asked, back):
    """The page that asks whether a Trade Point overspend was meant.

    ``None`` where nothing needs asking: the click spends no points, or
    the allowance covers it, or the reader has already said yes.

    Trade Points are not credits — nothing here refuses, and an owner
    who says they meant it gets what they asked for. What the page owes
    them is the arithmetic, since the allowance is not on the screen
    they clicked from and "you are short" is not a figure.
    """
    from n26.core.confirm import Aside, Fact, carried

    if not asked or request.POST.get(CONFIRM_FIELD):
        return None
    open_visit = gang.visiting_trading_post
    # One reading of the log, not one per figure: the page prints what
    # has gone as well as what is left, and the two must agree. With no
    # action open there is nothing to read — the post is shut, and the
    # purchase has nothing to count against.
    spent = gang.trade_points_spent if open_visit else 0
    brought = gang.starting_trade_points if open_visit else 0
    left = brought - spent
    if asked <= left:
        return None
    return Confirmation(
        title="Not enough Trade Points",
        lead=f"{line.name} — {asked} Trade Point{pluralize(asked)}.",
        heading="You don't have enough TP for this purchase",
        body=(
            f"{line.name} uses {asked} Trade Point{pluralize(asked)}, and "
            f"{gang.name} has {left}."
        ),
        aside=Aside(
            lead="You can buy it anyway.",
            rest=(
                "What the action has left goes below zero, and stays there "
                "until it is finished."
                if open_visit
                else "The purchase records the Trade Points against no action."
            ),
        ),
        # The same tally the Visit Trading Post card draws, with the
        # purchase and what it leaves added under it.
        facts=(
            Fact(
                "Available",
                str(brought),
                sub="" if open_visit else "no action open",
            ),
            Fact("Spent", str(spent)),
            Fact("Remaining", str(left), ruled=True, strong=True),
            Fact("This purchase", str(asked)),
            Fact("Remaining after", str(left - asked), ruled=True, strong=True),
        ),
        confirm_label=f"Buy {line.name} anyway",
        action=request.get_full_path(),
        cancel_url=back,
        carry=carried(request.POST),
        confirm_value="1",
    )


def _tab_label(collection):
    """A collection's name, shortened for a strip of tabs.

    "Ash Waste Nomads Equipment List" reads as "Ash Waste Nomads" with
    nothing lost — the strip is a row of lists, so a name ending by
    saying so spends the width every tab is short of on the one word
    they all have. A name that is nothing but the suffix keeps it.
    """
    name = str(collection)
    if not name.lower().endswith(LIST_SUFFIX):
        return name
    return name[: -len(LIST_SUFFIX)].strip(" -–—:") or name


def buyable_lists(held):
    """The lists among those held that are somewhere to buy kit, in the
    order they were come by, with the standard Trading Post after them.

    Holding a collection and buying from it are different things: a
    set of skills is carried exactly as an equipment list is, and only
    one of the two is somewhere to buy from. So which of them a buying
    screen offers follows from what they contain, never from how they
    were come by. Asked by family, so a new sort of gear puts its lists
    on these screens without anyone editing them — one query, whatever
    is held.

    The Trading Post is pinned to the default pack: collection names are
    only unique per pack, so a homebrew pack's own "Trading Post" must
    not shadow the standard one. A pack's post is reached the way any
    list is — by being assigned or granted, which is what ``held``
    already answers.
    """
    from n26.library.models import Collection, Family, get_default_pack
    from n26.library.standard_content import TRADING_POST_COLLECTION

    held = list(held)
    buyable = set(
        Collection.objects.filter(pk__in=[c.pk for c in held])
        .containing(Family.GEAR)
        .values_list("pk", flat=True)
    )
    collections = [c for c in held if c.pk in buyable]
    post = Collection.objects.filter(
        name=TRADING_POST_COLLECTION, pack=get_default_pack()
    ).first()
    if post is not None and post.pk not in {c.pk for c in collections}:
        collections.append(post)
    return collections


def collection_tabs(collections, chosen):
    """One tab per collection, in the order a fighter reaches them.

    Shortened names, unless two of them shorten to the same word: two
    tabs reading alike is worse than two long ones, and the strip is
    read as a set rather than a tab at a time, so the whole strip falls
    back together.

    ``title`` is the full name for a tab that was shortened, and empty
    where nothing was lost: a tooltip repeating the word already on
    screen tells a reader nothing. It is a plain value rather than
    something the template decides, because a template tag written
    inside a component's attributes is not read as one — it lands in the
    page as text.
    """
    labels = [_tab_label(collection) for collection in collections]
    if len(set(labels)) != len(labels):
        labels = [str(collection) for collection in collections]
    return [
        {
            "label": label,
            "title": "" if label == str(collection) else str(collection),
            "href": f"?list={collection.pk}",
            "current": chosen is not None and collection.pk == chosen.pk,
        }
        for label, collection in zip(labels, collections, strict=True)
    ]


def _panel_response(request, dialog):
    """The confirmation panel alone, for an htmx GET that named one.

    ``None`` for every other request, so a caller reads it as "not that
    kind of click" and carries on rendering the screen.

    ``HX-Replace-Url`` sets the address to the one that renders this
    panel on a plain visit — so a reload draws it again and a link to it
    works. Replaced rather than pushed: an open confirmation is not
    somewhere to go back to, and the panel's own way out already stands
    where the back button would.
    """
    if request.method != "GET" or not is_htmx(request):
        return None
    response = render(request, "n26/includes/equip_panel.html", {"dialog": dialog})
    response["HX-Replace-Url"] = request.get_full_path()
    return response


@dataclass(frozen=True)
class Screen:
    """What an equip screen is showing, derived in one place.

    Pages and partial updates both read the screen through
    :func:`_screen`, so an update cannot be derived against a different
    listing than the page it lands on.
    """

    gang: object
    miniature: object | None
    card: object
    computed: object
    collections: list
    #: The collection being browsed — ``None`` on the gang tabs that are
    #: not collections (the stash, the whole library).
    chosen: object | None
    #: The browsed listing, or ``None`` where the screen shows only what
    #: is held.
    view: object | None

    def host(self, at):
        """The assignment roots behind this screen. ``at`` is the page
        address, query string and all: every owned copy's controls are
        built from it."""
        from n26.core.owned import EquipHost

        if self.miniature is not None:
            return EquipHost.fighter(self.gang, self.card, self.miniature, at=at)
        return EquipHost.stash(self.gang, self.card, at=at)


def _screen(gang, miniature=None, list_param=""):
    """What an equip screen shows: card, collections, chosen list, view.

    ``miniature`` names whose screen this is; without one it is the
    gang's. On either, ``list_param`` may be :data:`ALL_SCOPE`, the
    library tab that is not a collection; on the gang's it may also be
    :data:`STASH_SCOPE`.

    One derivation for the pages and for every partial update — an update
    re-derives here because the act it follows changed the state it
    reports on, and a second implementation of "which list is the reader
    on" would let the two quietly disagree.
    """
    from n26.core.access import collections_for, gang_collections
    from n26.core.browse import all_gear, browse, usability_for, with_use_notes
    from n26.core.card import build_card, build_gang_card, build_modifier_index
    from n26.core.effects import compute, compute_gang

    def chosen_from(collections):
        """The list the address names, or the one a plain visit opens on."""
        named = next((c for c in collections if str(c.pk) == list_param), None)
        return named or (collections[0] if collections else None)

    if miniature is not None:
        # The options ride along because these screens name what each copy
        # was bought with, which no other surface built from a card does.
        card = build_card(miniature, with_options=True)
        index = build_modifier_index([node.assignable for node in card.all_nodes()])
        computed = compute(card, index)
        collections = buyable_lists(
            access.collection
            for access in collections_for(miniature, card=card, computed=computed)
        )
        if list_param == ALL_SCOPE:
            # The library, noted for this fighter the way any list is:
            # the tab is there for the thing no held list offers, which
            # is where a use restriction is likeliest to bite.
            chosen, view = None, all_gear(ALL_LABEL, for_use_notes=True)
        else:
            chosen = chosen_from(collections)
            view = browse(chosen) if chosen is not None else None
        if view is not None:
            view = with_use_notes(view, usability_for(computed))
        return Screen(gang, miniature, card, computed, collections, chosen, view)

    card = build_gang_card(gang, with_statlines=False)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    computed = compute_gang(card, index)
    collections = buyable_lists(
        access.collection
        for access in gang_collections(gang, card=card, computed=computed)
    )
    if list_param == STASH_SCOPE:
        chosen, view = None, None
    elif list_param == ALL_SCOPE:
        chosen, view = None, all_gear(ALL_LABEL)
    else:
        chosen = chosen_from(collections)
        # No usability notes: those are about a fighter, and the stash is
        # not one.
        view = browse(chosen) if chosen is not None else None
    return Screen(gang, None, card, computed, collections, chosen, view)


def render_update(
    request,
    gang,
    key,
    *,
    miniature=None,
    list_param="",
    expanded_key="",
    at="",
    closed=False,
    also="",
):
    """The partial update for one act on an equip screen.

    The row the act changed, the gang's money, and the set of accessory
    panels — each carrying the id of the element on the page it replaces.
    Every other row is left as it stands, which is what keeps the
    reader's filters, the section on screen, and the prices typed
    elsewhere.

    ``at`` is the page address, query string and all: every control on
    the redrawn row is built from it, so a row rendered without one hands
    back controls that have lost which list and section the reader is on.

    ``closed`` marks an act submitted from a confirmation panel; the
    update then also empties the dialog host, closing the panel.

    ``also`` is a second key the same act changed — fitting an accessory
    to a gun empties one row and fills another — drawn exactly as the
    first is. It must name a row of this screen: a key belonging to some
    other screen would be delivered as an instruction to remove a row
    that is not there.

    The screen is derived again rather than reused from the request,
    because the act changed the state this update reports on. That costs
    the same fixed handful of queries as a plain visit.

    A row of ``None`` means the screen no longer has one for this key — a
    listing always keeps a row, but a screen showing only what is held
    loses the row along with the last copy — and the update removes the
    row instead of redrawing it.
    """
    from n26.core.listing import listing_row, owned_row, owned_row_manage_only
    from n26.core.owned import possessions
    from n26.core.views.owned import accessorise_dialogs

    screen = _screen(gang, miniature=miniature, list_param=list_param)
    host = screen.host(at)
    held = possessions(host)
    refunds = not gang.credits_unlimited

    def row_for(row_key):
        copies = held.get(row_key)
        expanded = row_key == expanded_key
        if screen.view is None:
            # A screen showing only what is held draws a row for each
            # thing held and for nothing else, so parting with the last
            # copy takes the row away rather than turning it back into an
            # offer.
            return (
                owned_row_manage_only(
                    row_key, copies, refunds=refunds, expanded=expanded
                )
                if copies
                else None
            )
        line = next(
            (
                line
                for line in screen.view.all_lines()
                if _thing_key(line.thing) == row_key
            ),
            None,
        )
        if line is None:
            # The listing does not sell it, so the screen never had a row
            # for it and there is nothing to redraw.
            return None
        row = listing_row(line)
        return (
            owned_row(row, copies, refunds=refunds, expanded=expanded)
            if copies
            else row
        )

    rows = [(key, row_for(key))]
    if also and also != key:
        rows.append((also, row_for(also)))

    response = render(
        request,
        "n26/includes/equip_update.html",
        {
            "rows": rows,
            "gang": gang,
            # The strip this delivers replaces the one on the page, so it
            # is drawn with what that one had: without this the Trade
            # Points figure comes back as a number that leads nowhere.
            "trade_points_href": trade_points_href(gang, request.user),
            "held_label": host.held_label,
            "closed": closed,
            # The update always replaces the whole set of accessory
            # panels: a gun bought since the page was drawn has no panel
            # yet, and one parted with would leave a panel behind.
            "accessorise": accessorise_dialogs(request, host),
        },
    )
    return with_toasts(request, response)


def carried_confirmation(request):
    """Whether this submission came back from a confirmation panel."""
    return bool(request.POST.get(CONFIRM_FIELD))


def render_confirmation(request, confirmation):
    """A question, delivered into the dialog host of a page still standing.

    The whole-page answer is ``n26/confirm.html``; this is the same
    question for a screen updating in place, so a reader with scripting
    is not thrown out of the list they were buying from.
    """
    response = render(
        request,
        "n26/includes/equip_overspend.html",
        {"confirmation": confirmation},
    )
    return with_toasts(request, response)


def _buy_clicked(request, gang, holder, view, *, into, collection, at="", event=None):
    """One click on a Buy button, read and charged, whoever holds the thing.

    ``holder`` is what the purchase lands on — a fighter, or the gang's
    stash. Everything else about the click is the same on both screens,
    which is why it is read here: the line is found again in the list the
    server has just re-derived, the prices are bounded before anything is
    written, and a refusal buys nothing at all.

    ``into`` names the destination in the confirmation, and ``collection``
    is the list the click came from, for the event. ``event`` carries
    whatever else that screen knows about the purchase.

    ``at`` is the page the click came from: where a question the reader
    cancels puts them back.

    Three outcomes, and none of them is a response. The clicked line's
    key where the purchase went through; ``None`` where it was refused,
    its reason queued as a message; and a :class:`Confirmation` where it
    needs saying twice. How the caller answers each — a redirect, a
    partial update, a panel — is the caller's business, so nothing here
    knows about transport.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation

    key = request.POST.get("thing", "")
    line = next((row for row in view.all_lines() if _thing_key(row.thing) == key), None)
    if line is None:
        # Not on this list — a stale page or a tampered form. The
        # list itself is the answer either way.
        messages.error(request, "That item is not on this list.")
        return None
    picked = _parts_picked(request.POST, key, line)
    picks = _choices_picked(request.POST, key, line.choices)
    surcharge = sum(option.surcharge for option in picks)
    # Every price the click carries, read and bounded before anything
    # is written: one bad box buys nothing at all, rather than a gun
    # at a good price and its ammo at a refused one.
    try:
        paid = _price_typed(request.POST, _price_field(key), line)
        paid_for = [
            (part, _price_typed(request.POST, _price_field(key, index), part))
            for index, part in picked
        ]
    except BadPrice as refusal:
        messages.error(request, str(refusal))
        return None
    charge = _charge(line, paid, surcharge)
    # Asked before anything is written, and answered by the reader
    # rather than by a rule: an overspend of Trade Points is allowed,
    # and only doing it without meaning to is not.
    asked = _trade_points_asked(line, picked)
    confirmation = _overspend(request, gang, line, asked, at)
    if confirmation is not None:
        return confirmation
    try:
        with operation(gang, actor=request.user) as op:
            # The picked sets go to the operation, which materialises
            # them onto the thing caused by this purchase — so selling
            # the mount takes its guns with it. A pick-one set with
            # nothing picked is resolved there too, to the option that
            # comes as standard.
            bought = op.buy(
                holder,
                line=line,
                option=[option.default_set for option in picks],
                **charge,
            )
            # Onto the gun, not onto its holder: a profile belongs to
            # one particular weapon, and it is the same purchase
            # either way, so each part is charged at the price its own
            # listing was showing.
            for part, part_paid in paid_for:
                op.buy(bought, line=part, **_charge(part, part_paid))
    except Refusal as refusal:
        messages.error(request, str(refusal))
        return None
    except ValueError:
        # Two picks in one exclusive set, or a set this thing does
        # not offer — what ``resolve_selection`` refuses and the
        # indices cannot express. Treated the way a bad index is: a
        # broken link, not a rule to explain.
        raise Http404("No such option") from None
    # The confirmation names what left the bank, because with the
    # prices in the reader's hands the total is no longer something
    # the page can be read off for.
    spent = charge["paid"] + sum(part_paid for _, part_paid in paid_for)
    # One click, one event, whatever it bought. A gun with three paid
    # ammo types is one purchase to the player and should be one row
    # here — the parts are a count, not four writes.
    record(
        request,
        N26Noun.ASSIGNMENT,
        EventVerb.CREATE,
        bought,
        gang_id=str(gang.pk),
        thing=line.name,
        collection=collection,
        paid=spent,
        trade_points=asked,
        parts=len(paid_for),
        options=len(picks),
        **(event or {}),
    )
    # What was picked is named before what was ticked: an option is a
    # way the thing itself is built, while a paid round is something
    # extra riding along with it.
    extras = [
        *(option.name for option in picks),
        *(part.thing.name for part, _ in paid_for),
    ]
    # Trade Points are named beside the credits where any were spent,
    # because the tally they come off is not on the screen the reader
    # is being sent back to unless the gang is carrying an allowance.
    price = f"{spent}¢" + (f" and {asked} TP" if asked else "")
    if extras:
        messages.success(
            request,
            f"Bought {line.name} with {', '.join(extras)} for {into} — {price}.",
        )
    else:
        messages.success(request, f"Bought {line.name} for {into} — {price}.")
    return key


@login_required
def equip(request, pk):
    """Buy equipment for one fighter, from a list they can actually browse.

    Which list is URL state (``?list=<pk>``), picked from the collections
    ``collections_for`` finds — the fighter's own lists, their gang's,
    computed grants — kept down to the ones holding gear, plus the
    standard Trading Post when the library has one. Holding a collection
    and buying from it are different things: a fighter carries their
    skill sets the same way they carry their equipment list, and only one
    of the two is somewhere to buy from.

    The Buy buttons submit the *identity* of a line, never its price:
    the server re-browses the chosen collection and hands the found line
    whole to ``Operation.buy``, so a tampered form can name nothing that
    is not on the list. Each list is browsed on its own terms
    (``browse.terms_for``): one swept together by having Trade Point
    prices is a trading post and charges them, one an author wrote out
    by hand is a list and does not.

    The one number the form does decide is what the gang pays. Each row
    quotes its price in a box, and the figure in the box is what leaves
    the bank — the catalogue is a price list, not a fixed tariff, and a
    table that agrees a discount should not have to be argued with. It
    is still bounded here rather than only in the input: whole credits,
    nothing negative, nothing past ``PRICE_CEILING``, and a refusal buys
    nothing. What the gang *owns* is unaffected — see ``_charge``.

    A weapon's paid ammo and firing modes are ticked on the weapon's own
    listing and bought with it, in the same operation and onto the same
    gun. One click, one purchase, however many boxes are ticked: ammo is
    a way the gun you are buying is built, not a second thing on the
    list. Ammo for a gun a fighter already owns has no route here yet.

    Some things offer a group of options at purchase — a mount that comes
    with grenade launchers and offers plasma guns for fifteen more. It is
    picked on the listing, in the same click, and the pick travels to the
    assignment, so what the mount comes with is caused by the purchase
    and leaves with it. With nothing picked, a pick-one uses the default,
    which is what the listing was quoting. What a pick adds lands on the
    price *and* on the rating: a mount with plasma guns is a dearer
    mount, not a discounted one.

    Owning something is a *state of its listing*. Where the fighter
    already holds one, the listing says so instead of offering another:
    the count stands where Buy would be and opens it onto the copies
    themselves, each with the things that can happen to it — sold, handed
    on, taken off — and onto the ordinary row underneath them, so buying
    another is still one click. Read off the card this page already
    built, so a catalogue of hundreds of rows costs no query for it.

    What the screen draws is a ``Catalogue``: the browsed collection joined
    to what the fighter holds, built in one place and asserted on
    directly. The template asks a row what it is and what its controls
    mean, and never composes an identity the server would have to guess
    at.

    Anything owned that this list does not sell has no row and so no
    controls. That gap is known; where such a thing should be drawn is an
    open design question, and answering it from here would be answering
    it by accident.

    A purchase stays on the page: kitting out a fighter is a run of
    purchases, and the breadcrumb is the way back.
    """
    from n26.core.listing import build_catalogue
    from n26.core.owned import possessions
    from n26.core.views.owned import accessorise_dialogs, owned_dialog

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang

    wanted = request.GET.get("list", "")
    everything = wanted == ALL_SCOPE
    screen = _screen(gang, miniature=miniature, list_param=wanted)
    collections, chosen, view = screen.collections, screen.chosen, screen.view

    # Which of the picker's section tabs the reader was on — client state
    # the picker posts along and reads back from the URL. Echoed into
    # every address this page answers with, so buying from the third tab
    # lands the reader back on the third tab; an unknown name just leaves
    # the picker on its first.
    section = request.POST.get("section", request.GET.get("section", ""))[:100]
    expanded_key = request.POST.get("owned", request.GET.get("owned", ""))[:200]

    def here(collection):
        params = [
            *(
                [("list", ALL_SCOPE)]
                if everything
                else [("list", collection.pk)]
                if collection is not None
                else []
            ),
            *([("section", section)] if section else []),
            *([("owned", expanded_key)] if expanded_key else []),
        ]
        return f"{request.path}?{urlencode(params)}" if params else request.path

    if request.method == "POST" and view is not None:
        hx = is_htmx(request)
        key = _buy_clicked(
            request,
            gang,
            miniature,
            view,
            into=miniature.name,
            collection=ALL_LABEL if everything else chosen.name,
            at=here(chosen),
            event={"miniature_id": str(miniature.pk)},
        )
        if isinstance(key, Confirmation):
            # Asked as a whole page where there is no script to update
            # one, and as a panel over the list where there is.
            if not hx:
                return render(
                    request,
                    "n26/confirm.html",
                    {"gang": gang, "confirmation": key},
                )
            return render_confirmation(request, key)
        if not hx:
            # Without JavaScript a purchase lands back on the page it was
            # made from: kitting out is a run of purchases, and the
            # breadcrumb is the way out.
            return redirect(here(chosen))
        if key is None:
            # A refusal changes nothing on the page; the reason travels
            # as a toast.
            return no_update(request)
        return render_update(
            request,
            gang,
            key,
            miniature=miniature,
            list_param=wanted,
            expanded_key=expanded_key,
            at=here(chosen),
            # A purchase confirmed from the panel closes it on the way
            # out; one made straight from a row never opened one.
            closed=carried_confirmation(request),
        )

    # What this fighter is already carrying, keyed the way the rows are, so
    # a row asks one dictionary rather than the database. The dialogs open
    # over this page, on the list being read, and Cancel comes back to it,
    # so the page's own address is what the controls are built from.
    at = here(chosen)
    host = screen.host(at)
    owned = possessions(host)

    dialog = owned_dialog(request, host)
    if (panel := _panel_response(request, dialog)) is not None:
        return panel

    # The whole screen, as one structure: the browsed list joined to what
    # the fighter holds. A row is a row for something on sale or a row for
    # something they are carrying, and which it is is the structure's
    # answer rather than a question the template asks of the card.
    catalogue = (
        build_catalogue(
            view,
            owned,
            refunds=not gang.credits_unlimited,
            expanded_key=expanded_key,
        )
        if view is not None
        else None
    )
    # Which list is being browsed is a tab when there are several. With
    # one there is nothing to choose, so no strip is drawn — the search
    # box names the list it is searching, which is where a reader looks
    # to find out what they are buying from. The library tab is drawn
    # alone, though: a fighter holding no list at all is exactly who it
    # is for, and a reader on it should see where they are.
    tabs = fighter_tabs(collections, chosen, everything)
    rail = len(tabs) > 1 or everything
    # The whole catalogue posts back to the list it was drawn from — only
    # that: the picker's own state travels in the form, not in the address
    # it posts to.
    scope = ALL_SCOPE if everything else chosen.pk if chosen is not None else ""
    action = f"{request.path}?list={scope}" if scope else request.path
    browsing = ALL_BROWSING if everything else str(chosen or "")
    from n26.core.render import roster as gang_roster
    from n26.core.render import summarise_roster

    # The whole roster in the gang list's own order, one query: the
    # header's count is drawn from the tally it opens, which also lists
    # every model with its pinned rating — a reader equipping down a
    # roster is deciding against both.
    roster = gang_roster(gang)

    return render(
        request,
        "n26/equip.html",
        {
            "miniature": miniature,
            "gang": gang,
            # The rank beside the name in the shared model header — the
            # same line, said the same way, as the edit face draws it.
            "role": (
                miniature.membership.profile.category.name
                if miniature.membership.profile
                and miniature.membership.profile.category
                else ""
            ),
            "summary": summarise_roster(roster),
            "trade_points_href": trade_points_href(gang, request.user),
            "collections": collections,
            "collection_tabs": tabs,
            "rail": rail,
            "everything": everything,
            "action": action,
            "browsing": browsing,
            "chosen": chosen,
            "catalogue": catalogue,
            # This page holds every element a partial update replaces, so
            # its act controls submit through htmx — see
            # n26/includes/equip_hosts.html for the other half of the
            # opt-in.
            "htmx": True,
            # The confirmation the URL says is open, if any: sell, move or
            # remove one assignment on this fighter's card. A server state,
            # so it is a link, it survives a reload, and it is drawn rather than
            # revealed by a script.
            "dialog": dialog,
            # The accessory question for every gun the fighter is
            # carrying, drawn closed beside the rows. The one the address
            # names is drawn open, so the link works with no script; with
            # a script the click opens the panel that is already on the
            # page and never rebuilds the catalogue.
            "accessorise": accessorise_dialogs(request, host),
            **picker_context(catalogue, view, gang),
        },
    )


def picker_context(catalogue, view, gang=None):
    """What the collection picker needs to draw its strips and filters.

    The same on every catalogue, whoever is buying, so it is derived
    once: the strip of section tabs, the category filter's registration
    names, and the ends of the sliders.

    ``gang`` is handed over only so the listing can say whether the post
    is open to it. Nothing here reads its money.
    """
    sections = catalogue.sections if catalogue is not None else []
    # The sliders' ends are read off the browsed lines rather than the
    # catalogue's rows: a slider's job is to bound what the *list* asks, and
    # an owned row asks the same as it ever did.
    lines = list(view.all_lines()) if view is not None else []
    # Only what this catalogue prints. A slider over a figure the rows do
    # not draw is a control with nothing on screen to steer.
    trade_points = [
        line.trade_points
        for line in lines
        if line.shows_trade_points and line.trade_points is not None
    ]
    return {
        # The rules only open the Trading Post to a gang where a fighter
        # performed the Visit Trading Post action. This says so and stops
        # there: buying still works, because this edition informs rather
        # than polices, and a listing that vanished would leave a reader
        # with no way to find out why.
        "post_is_shut": bool(
            gang is not None
            and not gang.visiting_trading_post
            and any(line.charges_trade_points for line in lines)
        ),
        # Registration names — see the hire view: a row in an unnamed
        # category registers under its section's name, and a list that
        # omits one hides those rows client-side.
        #
        # Deduplicated, and not because of the sections: a category
        # name is only unique within its section, so two sections'
        # categories can register under one name. The filter keys on
        # the string and a repeated key draws neither.
        "categories": list(
            dict.fromkeys(
                category.name or section.name
                for section in sections
                for category in section.categories
            )
        ),
        "category_options": [
            {"value": name, "label": name}
            for name in dict.fromkeys(
                category.name
                for section in sections
                for category in section.categories
                if category.name
            )
        ],
        # One tab per section, as on the hire page. A section missing
        # from this list can never be the active tab and its rows
        # become unreachable, so every section drawn appears here.
        # Taken as they come: a browse draws a section once, so a name
        # cannot repeat, and deduplicating here would hide it if that
        # ever stopped being true.
        "sections": [section.name for section in sections],
        "price_floor": min((line.credits for line in lines), default=0),
        "price_ceiling": max((line.credits for line in lines), default=0),
        "tp_ceiling": max(trade_points, default=0),
        "has_trade_points": bool(trade_points),
        # The same bound the purchase enforces, so a browser can say no
        # before a click does. The input's max is a courtesy; the
        # check that counts is in the view.
        "price_cap": PRICE_CEILING,
    }


#: The library tab, on a model's screen and the gang's: not a collection,
#: so it names itself in the URL where a collection would name its id. A
#: ULID is never this word, so the two cannot collide.
ALL_SCOPE = "all"

#: What that tab is called. Not "All": beside a fighter's own lists that
#: reads as "all of this fighter's", and the tab is the opposite — what
#: no held list restricts it to.
ALL_LABEL = "Unrestricted"

#: What the tab is browsing, where a sentence names it — the search
#: box's placeholder.
ALL_BROWSING = "all equipment"

#: The stash-holdings tab — not a collection. Gear the current list does
#: not sell is reached from here, rather than drawn beside the catalogue.
STASH_SCOPE = "stash"

STASH_LABEL = "In stash"


def library_tab(everything):
    """The library tab, last on either screen."""
    return {
        "label": ALL_LABEL,
        "title": "",
        "href": f"?list={ALL_SCOPE}",
        "current": everything,
    }


def fighter_tabs(collections, chosen, everything):
    """The buyable collections and the library tab."""
    tabs = collection_tabs(collections, chosen)
    tabs.append(library_tab(everything))
    return tabs


def gang_tabs(collections, chosen, everything, *, stash=False):
    """The stash, buyable collections, and library tabs."""
    tabs = fighter_tabs(collections, chosen, everything)
    tabs.insert(
        0,
        {
            "label": STASH_LABEL,
            "title": "",
            "href": f"?list={STASH_SCOPE}",
            "current": stash,
        },
    )
    return tabs


@login_required
def equip_gang(request, pk):
    """Buy into the stash and manage what it holds.

    The chosen collection is URL state. ``all`` browses the library and
    ``stash`` lists every possession, including gear absent from narrower
    lists. Usability notes are omitted because they apply to fighters, not
    the stash.
    """
    from n26.core.listing import build_catalogue, build_stash_catalogue
    from n26.core.owned import possessions
    from n26.core.render import roster as gang_roster
    from n26.core.render import summarise_roster
    from n26.core.views.owned import accessorise_dialogs, owned_dialog

    gang = _own_gang_or_404(request, pk)

    # The collection picker posts its URL state back with a purchase.
    wanted = request.POST.get("list", request.GET.get("list", ""))
    stash_tab = wanted == STASH_SCOPE
    everything = wanted == ALL_SCOPE
    screen = _screen(gang, list_param=wanted)
    collections, chosen, view = screen.collections, screen.chosen, screen.view

    # Preserve the collection picker's section across purchases.
    section = request.POST.get("section", request.GET.get("section", ""))[:100]
    expanded_key = request.POST.get("owned", request.GET.get("owned", ""))[:200]

    params = []
    if stash_tab:
        params.append(("list", STASH_SCOPE))
    elif everything:
        params.append(("list", ALL_SCOPE))
    elif chosen is not None:
        params.append(("list", chosen.pk))
    if section:
        params.append(("section", section))
    if expanded_key:
        params.append(("owned", expanded_key))
    here = f"{request.path}?{urlencode(params)}" if params else request.path

    if request.method == "POST" and view is not None:
        hx = is_htmx(request)
        key = _buy_clicked(
            request,
            gang,
            gang.stash,
            view,
            into="the stash",
            collection=ALL_LABEL if everything else chosen.name,
            at=here,
        )
        if isinstance(key, Confirmation):
            if not hx:
                return render(
                    request,
                    "n26/confirm.html",
                    {"gang": gang, "confirmation": key},
                )
            return render_confirmation(request, key)
        if not hx:
            return redirect(here)
        if key is None:
            return no_update(request)
        return render_update(
            request,
            gang,
            key,
            list_param=wanted,
            expanded_key=expanded_key,
            at=here,
            closed=carried_confirmation(request),
        )

    host = screen.host(here)
    owned = possessions(host)
    refunds = not gang.credits_unlimited

    dialog = owned_dialog(request, host)
    if (panel := _panel_response(request, dialog)) is not None:
        return panel

    if stash_tab:
        catalogue = build_stash_catalogue(
            owned,
            STASH_LABEL,
            refunds=refunds,
            expanded_key=expanded_key,
        )
        browsing = STASH_LABEL
    elif view is not None:
        catalogue = build_catalogue(
            view,
            owned,
            refunds=refunds,
            expanded_key=expanded_key,
        )
        browsing = ALL_BROWSING if everything else str(chosen or "")
    else:
        catalogue = None
        browsing = ""

    return render(
        request,
        "n26/gang_equip.html",
        {
            "gang": gang,
            "action": here,
            "collection_tabs": gang_tabs(
                collections,
                chosen,
                everything,
                stash=stash_tab,
            ),
            "browsing": browsing,
            "catalogue": catalogue,
            "stash_tab": stash_tab,
            "everything": everything,
            # Opted in the same way as a model's own screen.
            "htmx": True,
            "held_label": host.held_label,
            "dialog": dialog,
            "accessorise": accessorise_dialogs(request, host),
            "summary": summarise_roster(gang_roster(gang)),
            "trade_points_href": trade_points_href(gang, request.user),
            **picker_context(catalogue, view, gang),
        },
    )
