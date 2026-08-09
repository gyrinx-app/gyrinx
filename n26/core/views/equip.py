"""Buying equipment for one fighter — the web face of :mod:`n26.core.browse`."""

import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.text import slugify

from n26.core.browse import UNCATEGORISED
from n26.core.owned import thing_key as _thing_key
from n26.core.views.permissions import _own_miniature_or_404

#: The most a till will take for one line. No price in the game comes
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


def _parts_field(key):
    """The input name the tickable parts of one line share.

    Scoped by the line, because one form holds the whole listing: without
    it, ticking warp rounds on the autogun row would arrive with the stub
    gun's press. Slugified, because that is what the template renders —
    read the raw key back and every box ticked in a real browser is
    silently ignored while a test posting the raw key still passes.
    """
    return f"{slugify(key)}:parts"


def _price_field(key, index=None):
    """The input name a line's price is typed into — the row's own, or
    one of its parts'.

    Scoped by the line for the same reason the tick boxes are: one form
    holds the whole listing, so a price typed on the autogun row must not
    arrive with the stub gun's press.
    """
    scope = slugify(key)
    return f"{scope}:price" if index is None else f"{scope}:parts:{index}:price"


def _parts_picked(data, key, line):
    """The parts a submission ticked on this line, each with the index it
    was drawn at, in the order drawn.

    Values are indices into the line the server has just re-derived, so a
    tampered form can name nothing the listing does not offer. A repeated
    index is refused as well: a checkbox cannot be ticked twice, and one
    press was never an order for two of the same ammo.

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


def _price_typed(data, field, line):
    """What this line is charged: the price typed for it, or the price it
    quoted where the form carried none.

    The number arrives from the browser, so it is read as a whole number
    of credits and nothing else. A negative one would hand the gang
    credits and an enormous one would not fit the ledger; both are
    refused rather than trimmed, because with money, charging a figure
    nobody typed is worse than charging nothing and saying so.

    An empty box is not an override — the row's own price stands, which
    is the number it was quoting before anyone touched it.
    """
    raw = data.get(field)
    if raw is None or not raw.strip():
        return line.credits
    raw = raw.strip()
    if not _WHOLE_CREDITS.fullmatch(raw) or int(raw) > PRICE_CEILING:
        raise BadPrice(
            f"{line.name}: a price is a whole number of credits, "
            f"from 0 to {PRICE_CEILING}."
        )
    return int(raw)


def _charge(line, paid):
    """What the ledger is told about a line bought at a set price.

    The price the listing quoted stays the list price and the gap becomes
    the discount, so ``paid = list - discount`` still holds and the entry
    says both what the listing asked and what the gang handed over.

    Rating follows the list price, never the payment. Rating is what the
    gang owns and it is pinned for good: haggling a sword down does not
    make it a lesser sword, and paying over the odds does not make it a
    better one. Only the credits leaving the bank move.
    """
    return {"paid": paid, "list_price": line.credits, "discount": line.credits - paid}


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


def collection_tabs(collections, chosen):
    """One tab per collection, in the order a fighter reaches them.

    Shortened names, unless two of them shorten to the same word: two
    tabs reading alike is worse than two long ones, and the strip is
    read as a set rather than a tab at a time, so the whole strip falls
    back together.
    """
    labels = [_tab_label(collection) for collection in collections]
    if len(set(labels)) != len(labels):
        labels = [str(collection) for collection in collections]
    return [
        {
            "label": label,
            "title": str(collection),
            "href": f"?list={collection.pk}",
            "current": chosen is not None and collection.pk == chosen.pk,
        }
        for label, collection in zip(labels, collections, strict=True)
    ]


def _row(line, owned=()):
    """One line as the template draws it: the identity its Buy submits,
    the box its price is typed into, and its parts as tickable inputs
    with price boxes of their own.

    A part prints its bare name — "warp round", not "warp round
    (Autogun)" — because it is drawn under the gun that already says so.

    ``owned`` is the copies of this thing the fighter is already carrying,
    which is what turns the row's Buy into a way into what they have.
    """
    key = _thing_key(line.thing)
    return {
        "line": line,
        "key": key,
        "owned": owned,
        "price_field": _price_field(key),
        "parts_field": _parts_field(key),
        "parts": [
            {
                "index": index,
                "line": part,
                "name": part.thing.name,
                "price_field": _price_field(key, index),
            }
            for index, part in enumerate(line.parts)
        ],
    }


@login_required
def equip(request, pk):
    """Buy equipment for one fighter, from a list they can actually browse.

    Which list is URL state (``?list=<pk>``), picked from the collections
    ``collections_for`` finds — the fighter's own lists, their gang's,
    computed grants — kept down to the ones holding gear, plus the
    standard Trading Post when the library has one. Holding a collection
    and shopping from it are different things: a fighter carries their
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
    the bank — the listing is a price list, not a fixed tariff, and a
    table that agrees a discount should not have to be argued with. It
    is still bounded here rather than only in the input: whole credits,
    nothing negative, nothing past ``PRICE_CEILING``, and a refusal buys
    nothing. What the gang *owns* is unaffected — see ``_charge``.

    A weapon's paid ammo and firing modes are ticked on the weapon's own
    row and bought with it, in the same operation and onto the same gun.
    One press, one purchase, however many boxes are ticked: ammo is a way
    the gun you are buying is built, not a second thing on the list.
    Ammo for a gun a fighter already owns has no route here yet.

    A row for something the fighter already has says so instead of
    offering another: the count opens the row onto the copies they are
    carrying, each with the three things that can happen to it — sold,
    handed on, taken off. That is read off the card this page already
    built, so a listing of hundreds of rows still costs no query for it.

    A purchase stays on the page: kitting out a fighter is a run of
    purchases, and the breadcrumb is the way back.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.access import collections_for
    from n26.core.browse import browse, usability_for, with_use_notes
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute
    from n26.core.operations import NotEnoughCredits, operation
    from n26.core.owned import owned_things
    from n26.core.views.owned import link_owned, owned_dialog
    from n26.library.models import Collection, Family, get_default_pack
    from n26.library.standard_content import TRADING_POST_COLLECTION

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang

    # One card build serves the whole page: which lists this fighter can
    # browse and how usable each line is are both read off the same
    # computed card.
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    computed = compute(card, index)

    held = [
        access.collection
        for access in collections_for(miniature, card=card, computed=computed)
    ]
    # A fighter's collections are not all places to buy kit. Which of them
    # this screen offers follows from what they contain, not from how the
    # fighter came by them: a collection of skills is somewhere to learn,
    # and holding one — even as a built-in — never makes it somewhere to
    # buy. Asked by family, so a new sort of gear puts its lists on this screen
    # without anyone editing it. One query, whatever they hold.
    shoppable = set(
        Collection.objects.filter(pk__in=[c.pk for c in held])
        .containing(Family.GEAR)
        .values_list("pk", flat=True)
    )
    collections = [c for c in held if c.pk in shoppable]
    # Pinned to the default pack: collection names are only unique per
    # pack, so a homebrew pack's own "Trading Post" must not shadow the
    # standard one here. A pack's post reaches a fighter the way any list
    # does — by being assigned or granted, which collections_for found.
    post = Collection.objects.filter(
        name=TRADING_POST_COLLECTION, pack=get_default_pack()
    ).first()
    if post is not None and post.pk not in {c.pk for c in collections}:
        collections.append(post)

    chosen = None
    wanted = request.GET.get("list")
    for collection in collections:
        if str(collection.pk) == wanted:
            chosen = collection
            break
    if chosen is None and collections:
        chosen = collections[0]

    view = None
    if chosen is not None:
        view = with_use_notes(browse(chosen), usability_for(computed))

    if request.method == "POST" and view is not None:
        key = request.POST.get("thing", "")
        line = next(
            (row for row in view.all_lines() if _thing_key(row.thing) == key), None
        )
        back = f"{request.path}?list={chosen.pk}"
        if line is None:
            # Not on this list — a stale page or a tampered form. The
            # list itself is the answer either way.
            messages.error(request, "That item is not on this list.")
            return redirect(back)
        picked = _parts_picked(request.POST, key, line)
        # Every price the press carries, read and bounded before anything
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
        try:
            with operation(gang, actor=request.user) as op:
                bought = op.buy(miniature, line=line, **_charge(line, paid))
                # Onto the gun, not onto the fighter: a profile belongs to
                # one particular weapon, and it is the same till either
                # way, so each part is charged at the price its own row
                # was showing.
                for part, part_paid in paid_for:
                    op.buy(bought, line=part, **_charge(part, part_paid))
        except NotEnoughCredits as refusal:
            messages.error(request, str(refusal))
            return redirect(back)
        # The confirmation names what left the bank, because with the
        # prices in the reader's hands the total is no longer something
        # the page can be read off for.
        spent = paid + sum(part_paid for _, part_paid in paid_for)
        # One press, one event, whatever it bought. A gun with three paid
        # ammo types is one purchase to the player and should be one row
        # here — the parts are a count, not four writes.
        record(
            request,
            N26Noun.ASSIGNMENT,
            EventVerb.CREATE,
            bought,
            gang_id=str(gang.pk),
            miniature_id=str(miniature.pk),
            thing=line.name,
            collection=chosen.name,
            paid=spent,
            parts=len(paid_for),
        )
        if paid_for:
            extras = ", ".join(part.thing.name for part, _ in paid_for)
            messages.success(
                request,
                f"Bought {line.name} with {extras} for {miniature.name} — {spent}¢.",
            )
        else:
            messages.success(
                request, f"Bought {line.name} for {miniature.name} — {spent}¢."
            )
        return redirect(back)

    # What this fighter is already carrying, keyed the way the rows are, so
    # a row asks one dictionary rather than the database. The links are
    # filled in here because the URL space is the view's business — the
    # dialogs open over this page, on the list being read, and Cancel
    # comes back to it.
    at = f"{request.path}?list={chosen.pk}" if chosen is not None else request.path
    owned = link_owned(owned_things(card), at)

    lines = list(view.all_lines()) if view is not None else []
    trade_points = [
        line.trade_points for line in lines if line.trade_points is not None
    ]
    # Each section paired with the name it goes by on screen. The grouping
    # leaves a homeless line's section unnamed, which is the truth about
    # the content; the picker draws its sections as tabs, and a tab needs
    # a word on it. Paired once so the strip, the registration names and
    # the heading cannot disagree — see the hire view, which does the same.
    named_sections = [
        (section.name or UNCATEGORISED, section)
        for section in (view.sections if view is not None else [])
    ]
    # Which list is being browsed is a tab when there are several. With
    # one there is nothing to choose, so no strip is drawn — the search
    # box names the list it is searching, which is where a reader looks
    # to find out what they are shopping.
    tabs = collection_tabs(collections, chosen)
    return render(
        request,
        "n26/equip.html",
        {
            "miniature": miniature,
            "gang": gang,
            "collections": collections,
            "collection_tabs": tabs,
            "chosen": chosen,
            # Each line paired with the key its Buy button submits and the
            # field name its parts tick under, so the template never
            # composes an identity the server would then have to guess at.
            "section_rows": [
                {
                    "name": name,
                    "first": index == 0,
                    "categories": [
                        {
                            "name": category.name,
                            "lines": [
                                _row(line, owned.get(_thing_key(line.thing), []))
                                for line in category.lines
                            ],
                        }
                        for category in section.categories
                    ],
                }
                for index, (name, section) in enumerate(named_sections)
            ],
            # The confirmation the URL says is open, if any: sell, move or
            # remove one row of this fighter's card. A server state, so it
            # is a link, it survives a reload, and it is drawn rather than
            # revealed by a script.
            "dialog": owned_dialog(
                request, card, at=at, miniature=miniature, gang=gang
            ),
            # Registration names — see the hire view: a row in an unnamed
            # category registers under its section's name, and a list that
            # omits one hides those rows client-side.
            "categories": list(
                dict.fromkeys(
                    category.name or name
                    for name, section in named_sections
                    for category in section.categories
                )
            ),
            "category_options": [
                {"value": name, "label": name}
                for name in dict.fromkeys(
                    category.name
                    for _, section in named_sections
                    for category in section.categories
                    if category.name
                )
            ],
            # One tab per section, as on the hire page. A section missing
            # from this list can never be the active tab and its rows
            # become unreachable, so every section is named above and every
            # one appears here — deduplicated, because the strip keys
            # its tabs by name and a repeated key draws neither.
            "sections": list(dict.fromkeys(name for name, _ in named_sections)),
            "cost_floor": min((line.credits for line in lines), default=0),
            "cost_ceiling": max((line.credits for line in lines), default=0),
            "tp_ceiling": max(trade_points, default=0),
            "has_trade_points": bool(trade_points),
            # The same bound the till enforces, so a browser can say no
            # before a press does. The input's max is a courtesy; the
            # check that counts is in the view.
            "price_ceiling": PRICE_CEILING,
        },
    )
