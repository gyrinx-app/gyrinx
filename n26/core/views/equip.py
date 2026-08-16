"""Buying equipment — the web face of :mod:`n26.core.browse`.

Two screens, one purchase. A fighter's equip page buys onto that
fighter; the gang's buys into the stash, where the gang's spare kit
waits for whoever needs it. Both re-derive the clicked line from the
list on screen, charge what the box says, and land back where the click
came from, so the two anchors cannot come to disagree about what buying
means — the click is read once, in ``_buy_clicked``.
"""

import re
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render

from n26.core.listing import choice_field as _choice_field
from n26.core.listing import parts_field as _parts_field
from n26.core.listing import price_field as _price_field
from n26.core.owned import thing_key as _thing_key
from n26.core.views.permissions import _own_gang_or_404, _own_miniature_or_404

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


def _choices_picked(data, key, line):
    """The alternatives a submission picked on this line, group by group.

    Values are indices into the sets the server has just re-derived, so a
    tampered form can name nothing the line does not offer — and a group
    the line does not draw has no field to pick from.

    An empty value is a one-or-none set's "None": the reader took
    nothing, which is not a pick to pass on. A repeated index is refused
    like a repeated tick box — one click was never an order for two of the
    same swap.
    """
    picked = []
    for index, group in enumerate(line.choices):
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


def _buy_clicked(request, gang, holder, view, back, *, into, collection, event=None):
    """One click on a Buy button, read and charged, whoever holds the thing.

    ``holder`` is what the purchase lands on — a fighter, or the gang's
    stash. Everything else about the click is the same on both screens,
    which is why it is read here: the line is found again in the list the
    server has just re-derived, the prices are bounded before anything is
    written, and a refusal buys nothing at all.

    ``into`` names the destination in the confirmation, and ``collection``
    is the list the click came from, for the event. ``event`` carries
    whatever else that screen knows about the purchase.

    Always answers with a redirect to ``back``: a purchase stays on the
    page, because kitting out is a run of purchases and the breadcrumb is
    the way out.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation

    key = request.POST.get("thing", "")
    line = next((row for row in view.all_lines() if _thing_key(row.thing) == key), None)
    if line is None:
        # Not on this list — a stale page or a tampered form. The
        # list itself is the answer either way.
        messages.error(request, "That item is not on this list.")
        return redirect(back)
    picked = _parts_picked(request.POST, key, line)
    picks = _choices_picked(request.POST, key, line)
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
        return redirect(back)
    charge = _charge(line, paid, surcharge)
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
        return redirect(back)
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
    if extras:
        messages.success(
            request,
            f"Bought {line.name} with {', '.join(extras)} for {into} — {spent}¢.",
        )
    else:
        messages.success(request, f"Bought {line.name} for {into} — {spent}¢.")
    return redirect(back)


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
    is not on the list. Browsed on equipment-list terms for now — Trade
    Points are shown, not charged, because a TP budget is a session
    concept that does not exist yet.

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
    from n26.core.access import collections_for
    from n26.core.browse import browse, usability_for, with_use_notes
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute
    from n26.core.listing import build_catalogue
    from n26.core.owned import owned_things
    from n26.core.views.owned import accessorise_dialogs, owned_dialog

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang

    # One card build serves the whole page: which lists this fighter can
    # browse and how usable each line is are both read off the same
    # computed card.
    # ``with_options`` so each copy can name what it was bought with;
    # nothing else on this page reads it.
    card = build_card(miniature, with_options=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    computed = compute(card, index)

    collections = buyable_lists(
        access.collection
        for access in collections_for(miniature, card=card, computed=computed)
    )

    chosen = None
    wanted = request.GET.get("list")
    for collection in collections:
        if str(collection.pk) == wanted:
            chosen = collection
            break
    if chosen is None and collections:
        chosen = collections[0]

    # Which of the picker's section tabs the reader was on — client state
    # the picker posts along and reads back from the URL. Echoed into
    # every address this page answers with, so buying from the third tab
    # lands the reader back on the third tab; an unknown name just leaves
    # the picker on its first.
    section = request.POST.get("section", request.GET.get("section", ""))[:100]

    def here(collection):
        params = [
            *([("list", collection.pk)] if collection is not None else []),
            *([("section", section)] if section else []),
        ]
        return f"{request.path}?{urlencode(params)}" if params else request.path

    view = None
    if chosen is not None:
        view = with_use_notes(browse(chosen), usability_for(computed))

    if request.method == "POST" and view is not None:
        return _buy_clicked(
            request,
            gang,
            miniature,
            view,
            here(chosen),
            into=miniature.name,
            collection=chosen.name,
            event={"miniature_id": str(miniature.pk)},
        )

    # What this fighter is already carrying, keyed the way the rows are, so
    # a row asks one dictionary rather than the database. The dialogs open
    # over this page, on the list being read, and Cancel comes back to it,
    # so the page's own address is what the controls are built from.
    at = here(chosen)
    owned = owned_things(card, at)

    # The whole screen, as one structure: the browsed list joined to what
    # the fighter holds. A row is a row for something on sale or a row for
    # something they are carrying, and which it is is the structure's
    # answer rather than a question the template asks of the card.
    catalogue = (
        build_catalogue(view, owned, refunds=not gang.credits_unlimited)
        if view is not None
        else None
    )
    # Which list is being browsed is a tab when there are several. With
    # one there is nothing to choose, so no strip is drawn — the search
    # box names the list it is searching, which is where a reader looks
    # to find out what they are buying from.
    tabs = collection_tabs(collections, chosen)
    from n26.core.render import roster as gang_roster
    from n26.core.render import summarise_roster

    # The whole roster in the gang list's own order, one query: the
    # header's figures count it, and the roster tally beside them lists
    # every model with its pinned rating — a reader equipping down a
    # roster is deciding against both. The count is computed here
    # because a filter inside a cotton :attribute silently comes out as
    # nothing.
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
            "roster_count": len(roster),
            "summary": summarise_roster(roster),
            "collections": collections,
            "collection_tabs": tabs,
            "chosen": chosen,
            "catalogue": catalogue,
            # The confirmation the URL says is open, if any: sell, move or
            # remove one assignment on this fighter's card. A server state,
            # so it is a link, it survives a reload, and it is drawn rather than
            # revealed by a script.
            "dialog": owned_dialog(
                request, card, at=at, miniature=miniature, gang=gang
            ),
            # The accessory question for every gun the fighter is
            # carrying, drawn closed beside the rows. The one the address
            # names is drawn open, so the link works with no script; with
            # a script the click opens the panel that is already on the
            # page and never rebuilds the catalogue.
            "accessorise": accessorise_dialogs(request, card, at=at),
            **picker_context(catalogue, view),
        },
    )


def picker_context(catalogue, view):
    """What the collection picker needs to draw its strips and filters.

    The same on every catalogue, whoever is buying, so it is derived
    once: the strip of section tabs, the category filter's registration
    names, and the ends of the sliders.
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


#: The gang screen's library tab: not a collection, so it names itself in
#: the URL where a collection would name its id. A ULID is never this
#: word, so the two cannot collide.
ALL_SCOPE = "all"

#: What that tab is called, on the tab and as the list being browsed.
ALL_LABEL = "All equipment"


def gang_tabs(collections, chosen, everything):
    """The lists the gang can buy from, and the whole library after them.

    The library tab comes last because it is the fallback: what a gang
    buys from is its own lists, and everything else is there for the
    thing no list carries.
    """
    tabs = collection_tabs(collections, None if everything else chosen)
    tabs.append(
        {
            "label": ALL_LABEL,
            "title": "",
            "href": f"?list={ALL_SCOPE}",
            "current": everything,
        }
    )
    return tabs


@login_required
def equip_gang(request, pk):
    """Buy equipment into the gang's stash.

    The gang's own end of the equip page. What is bought here belongs to
    the gang rather than to anyone on the roster: it lands in the stash,
    and the gang page is where it is handed to a fighter. The division is
    the anchor and nothing else — a fighter's page buys onto that
    fighter, this one buys into the store.

    Which list is URL state (``?list=``), and the lists are the gang's
    own: the collections it carries or was granted, kept to the ones
    holding gear, plus the standard Trading Post. There is no fighter
    here, so no line is marked usable or not — a restriction is about a
    model, and the stash is not one. The gang's card is built once and
    answers which lists it holds.

    ``?list=all`` is the whole library instead: every kind of gear a list
    could sell, filed under its own categories, for the thing no list
    carries. Built only when the address asks for it — it prices the
    library, which is not something to pay for on every visit.

    A row says what it sells and nothing about what the stash already
    holds. What the gang owns is drawn on the gang page, with the
    controls that act on it; a count here would need the same
    confirmations again, on a screen whose one act is buying.
    """
    from n26.core.access import gang_collections
    from n26.core.browse import all_gear, browse
    from n26.core.card import build_gang_card, build_modifier_index
    from n26.core.effects import compute_gang
    from n26.core.listing import build_catalogue

    gang = _own_gang_or_404(request, pk)

    # One card build serves the page: which lists the gang carries is read
    # off it, and building it twice is the easy mistake here.
    card = build_gang_card(gang, with_statlines=False)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    computed = compute_gang(card, index)

    collections = buyable_lists(
        access.collection
        for access in gang_collections(gang, card=card, computed=computed)
    )

    # Read from the POST as well as the URL: the form posts to the address
    # it was drawn at, and a click must buy from the list it was clicked
    # on whichever way the state arrived.
    wanted = request.POST.get("list", request.GET.get("list", ""))
    everything = wanted == ALL_SCOPE
    chosen = None
    if not everything:
        for collection in collections:
            if str(collection.pk) == wanted:
                chosen = collection
                break
        if chosen is None and collections:
            chosen = collections[0]

    # Which of the picker's section tabs the reader was on — client state
    # the picker posts along and reads back from the URL, as on a
    # fighter's page.
    section = request.POST.get("section", request.GET.get("section", ""))[:100]

    if everything:
        params = [("list", ALL_SCOPE)]
    elif chosen is not None:
        params = [("list", chosen.pk)]
    else:
        params = []
    if section:
        params.append(("section", section))
    here = f"{request.path}?{urlencode(params)}" if params else request.path

    view = None
    if everything:
        view = all_gear(ALL_LABEL)
    elif chosen is not None:
        view = browse(chosen)

    if request.method == "POST" and view is not None:
        return _buy_clicked(
            request,
            gang,
            gang.stash,
            view,
            here,
            into="the stash",
            collection=ALL_LABEL if everything else chosen.name,
        )

    # Nothing joined in about what is already held: a row that said so
    # would open onto the copies and their acts, and those confirmations
    # live on the gang page, over the stash they are about.
    catalogue = build_catalogue(view, {}) if view is not None else None

    return render(
        request,
        "n26/gang_equip.html",
        {
            "gang": gang,
            "action": here,
            "collection_tabs": gang_tabs(collections, chosen, everything),
            # What is being browsed, as the search box says it. A name
            # rather than the collection, because the library tab is no
            # collection and the box asks the same question of both.
            "browsing": ALL_LABEL if everything else str(chosen or ""),
            "catalogue": catalogue,
            # The roster's size, off the card that is already built: the
            # figures strip counts the models a purchase is decided
            # against, and every live member has a card here.
            "roster_count": len(card.members),
            **picker_context(catalogue, view),
        },
    )
