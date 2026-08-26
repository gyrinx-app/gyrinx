"""Buying equipment — the web face of :mod:`n26.core.browse`.

Two screens, one purchase. A fighter's equip page buys onto that
fighter; the gang's buys into the stash, where the gang's spare kit
waits for whoever needs it. Both re-derive the clicked line from the
list on screen, charge what the box says, and land back where the click
came from, so the two anchors cannot come to disagree about what buying
means — the click is read once, in ``_buy_clicked``.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
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


#: How long a confirmation stands before it goes away on its own. A
#: refusal is given nothing: the reason a click did nothing is worth more
#: than the corner it is written in, and four seconds is long enough to
#: miss it entirely.
TOAST_DURATION = 4000


def _spoken(request, response):
    """The same response, carrying whatever the request has to say.

    A page that is not rebuilt has nowhere to draw the alert block, so
    the queued messages ride back as an event the page raises as toasts.
    Reading the storage is what empties it, which is what should happen:
    these have now been said.
    """
    import json

    from django.contrib.messages import get_messages

    said = [
        {
            "variant": message.level_tag if message.level_tag else "info",
            "message": str(message),
            "duration": 0 if message.level_tag == "error" else TOAST_DURATION,
        }
        for message in get_messages(request)
    ]
    if said:
        response["HX-Trigger"] = json.dumps({"n26-said": said})
    return response


def _panel_asked(request, dialog):
    """The confirmation alone, where the click asked for that and not the page.

    Answers ``None`` for every other request, so a caller reads it as
    "this was not that kind of click" and carries on drawing the screen.

    The address is corrected to the one the click named, which is the
    address that draws this panel on a plain visit — so a reload still
    opens it, the link is still a link, and leaving puts the address back
    the same way. Replaced rather than pushed: opening a confirmation is
    not somewhere to go back to, and the panel's own way out already
    stands where the back button would.
    """
    if request.method != "GET" or not request.headers.get("HX-Request"):
        return None
    answer = render(request, "n26/includes/equip_panel.html", {"dialog": dialog})
    answer["HX-Replace-Url"] = request.get_full_path()
    return answer


@dataclass(frozen=True)
class Bought:
    """A purchase that went through, and what it was for.

    Answered instead of a redirect where the click asked for the part of
    the page that changed rather than the whole of it. The key is what
    the row is drawn under, which is all the caller needs to draw it
    again.
    """

    key: str


def screen_row(
    request, gang, key, *, miniature=None, list_param="", expanded_key="", at=""
):
    """The row one piece of content has on an equip screen, as it now stands.

    ``miniature`` names whose screen this is; without one it is the
    gang's. ``list_param`` is which listing the reader is on, in the
    words the address uses.

    ``at`` is the screen the row is going back to, query string and all.
    Every act a copy offers is built from it, so a row drawn without one
    hands back controls that have forgotten which list the reader is on
    and which section they were reading.

    The card is built again rather than reused, because the one a click
    arrives with describes the holder as they were before it. That is the
    same fixed handful of queries a plain visit costs, so this is not the
    expensive half of anything.

    Answers the row and what the screen calls holding something. A row of
    ``None`` means this screen has no row for it any more — a listing
    always keeps one, but a screen showing only what is held loses the
    row along with the last copy.
    """
    from n26.core.access import collections_for, gang_collections
    from n26.core.browse import all_gear, browse, usability_for, with_use_notes
    from n26.core.card import build_card, build_gang_card, build_modifier_index
    from n26.core.effects import compute, compute_gang
    from n26.core.listing import listing_row, owned_row, owned_row_manage_only
    from n26.core.owned import EquipHost, possessions

    def chosen_from(collections):
        """The list the address names, or the one a plain visit opens on."""
        named = next((c for c in collections if str(c.pk) == list_param), None)
        return named or (collections[0] if collections else None)

    if miniature is not None:
        card = build_card(miniature, with_options=True)
        index = build_modifier_index([node.assignable for node in card.all_nodes()])
        computed = compute(card, index)
        chosen = chosen_from(
            buyable_lists(
                access.collection
                for access in collections_for(miniature, card=card, computed=computed)
            )
        )
        view = (
            with_use_notes(browse(chosen), usability_for(computed))
            if chosen is not None
            else None
        )
        host = EquipHost.fighter(gang, card, miniature, at=at)
    else:
        card = build_gang_card(gang, with_statlines=False)
        index = build_modifier_index([node.assignable for node in card.all_nodes()])
        computed = compute_gang(card, index)
        host = EquipHost.stash(gang, card, at=at)
        if list_param == STASH_SCOPE:
            view = None
        elif list_param == ALL_SCOPE:
            view = all_gear(ALL_LABEL)
        else:
            chosen = chosen_from(
                buyable_lists(
                    access.collection
                    for access in gang_collections(gang, card=card, computed=computed)
                )
            )
            view = browse(chosen) if chosen is not None else None

    owned = possessions(host)
    copies = owned.get(key)
    refunds = not gang.credits_unlimited
    expanded = key == expanded_key

    # A screen showing only what is held draws a row for each thing held
    # and for nothing else, so parting with the last copy takes the row
    # away rather than turning it back into an offer.
    if view is None:
        row = (
            owned_row_manage_only(key, copies, refunds=refunds, expanded=expanded)
            if copies
            else None
        )
        return row, host.held_label, host

    line = next(
        (row for row in view.all_lines() if _thing_key(row.thing) == key),
        None,
    )
    if line is None:
        # The listing does not sell it, so this screen never had a row for
        # it — what is held that a list does not sell has nowhere to be
        # drawn, which is a gap this is not the place to close.
        return None, host.held_label, host

    row = listing_row(line)
    if copies:
        row = owned_row(row, copies, refunds=refunds, expanded=expanded)
    return row, host.held_label, host


def changed(request, gang, key, row, held_label, host, *, closed=False):
    """What an act on an equip screen sends back.

    The row it changed and the gang's own figures, each naming the place
    it stands in for. Every other row is left exactly as it is, which is
    what keeps the reader's filters, the section they were on, and the
    prices they had typed elsewhere.

    The accessory questions go too. They are drawn for every gun on the
    screen rather than per row, and the click that opens one names the
    panel it wants — so a gun that has just arrived would offer a control
    with nothing behind it, and one just parted with would leave a panel
    behind. Sending the set as it now stands answers both, and costs the
    single read it always did.

    ``closed`` says the act was one asked in a panel, so the panel goes
    with the answer.
    """
    from n26.core.render import roster as gang_roster
    from n26.core.render import summarise_roster
    from n26.core.views.owned import accessorise_dialogs

    return render(
        request,
        "n26/includes/equip_changed.html",
        {
            "row": row,
            "row_key": key,
            "gang": gang,
            "summary": summarise_roster(gang_roster(gang)),
            "held_label": held_label,
            "closed": closed,
            # Required, not optional: the answer always stands in for the
            # whole set of accessory questions, so a caller with no host to
            # read them from would quietly take every panel off the page.
            "accessorise": accessorise_dialogs(request, host),
        },
    )


def _buy_clicked(
    request, gang, holder, view, back, *, into, collection, event=None, fragment=False
):
    """One click on a Buy button, read and charged, whoever holds the thing.

    ``holder`` is what the purchase lands on — a fighter, or the gang's
    stash. Everything else about the click is the same on both screens,
    which is why it is read here: the line is found again in the list the
    server has just re-derived, the prices are bounded before anything is
    written, and a refusal buys nothing at all.

    ``into`` names the destination in the confirmation, and ``collection``
    is the list the click came from, for the event. ``event`` carries
    whatever else that screen knows about the purchase.

    Answers with a redirect to ``back``: a purchase stays on the page,
    because kitting out is a run of purchases and the breadcrumb is the
    way out.

    ``fragment`` is a click that asked for the part of the page that
    changed instead of the whole of it. It answers :class:`Bought` where
    the purchase went through and ``None`` where it did not — the reason
    is already queued as a message either way, so the caller says it in
    whatever way suits the answer it is building.
    """

    def answer():
        return None if fragment else redirect(back)

    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.operations import Refusal, operation

    key = request.POST.get("thing", "")
    line = next((row for row in view.all_lines() if _thing_key(row.thing) == key), None)
    if line is None:
        # Not on this list — a stale page or a tampered form. The
        # list itself is the answer either way.
        messages.error(request, "That item is not on this list.")
        return answer()
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
        return answer()
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
        return answer()
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
    return Bought(key) if fragment else redirect(back)


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
    from n26.core.owned import EquipHost, possessions
    from n26.core.views.owned import accessorise_dialogs, owned_dialog

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang

    # One card build serves the whole page: which lists this fighter can
    # browse and how usable each line is are both read off the same
    # computed card.
    # The options ride along because this page names what each copy was
    # bought with, which no other surface built from a card does.
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
    expanded_key = request.POST.get("owned", request.GET.get("owned", ""))[:200]

    def here(collection):
        params = [
            *([("list", collection.pk)] if collection is not None else []),
            *([("section", section)] if section else []),
            *([("owned", expanded_key)] if expanded_key else []),
        ]
        return f"{request.path}?{urlencode(params)}" if params else request.path

    view = None
    if chosen is not None:
        view = with_use_notes(browse(chosen), usability_for(computed))

    if request.method == "POST" and view is not None:
        # A click that asked for the row it changed rather than the page
        # around it. Without script the same button posts the same form
        # and is answered with the whole screen, so nothing here is the
        # only way to buy anything.
        piecemeal = bool(request.headers.get("HX-Request"))
        outcome = _buy_clicked(
            request,
            gang,
            miniature,
            view,
            here(chosen),
            into=miniature.name,
            collection=chosen.name,
            event={"miniature_id": str(miniature.pk)},
            fragment=piecemeal,
        )
        if not piecemeal:
            return outcome
        if outcome is None:
            # A refusal changes nothing, so nothing is swapped; the
            # reason travels as a message and is said as a toast.
            return _spoken(request, HttpResponse(status=204))
        row, held_label, host = screen_row(
            request,
            gang,
            outcome.key,
            miniature=miniature,
            list_param=str(chosen.pk) if chosen is not None else "",
            expanded_key=expanded_key,
            at=here(chosen),
        )
        return _spoken(
            request, changed(request, gang, outcome.key, row, held_label, host)
        )

    # What this fighter is already carrying, keyed the way the rows are, so
    # a row asks one dictionary rather than the database. The dialogs open
    # over this page, on the list being read, and Cancel comes back to it,
    # so the page's own address is what the controls are built from.
    at = here(chosen)
    host = EquipHost.fighter(gang, card, miniature, at=at)
    owned = possessions(host)

    dialog = owned_dialog(request, host)
    if (answer := _panel_asked(request, dialog)) is not None:
        return answer

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
    # to find out what they are buying from.
    tabs = collection_tabs(collections, chosen)
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
            "collections": collections,
            "collection_tabs": tabs,
            "chosen": chosen,
            "catalogue": catalogue,
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

#: The stash-holdings tab — not a collection. Gear the current list does
#: not sell is reached from here, rather than drawn beside the catalogue.
STASH_SCOPE = "stash"

STASH_LABEL = "In stash"


def gang_tabs(collections, chosen, everything, *, stash=False):
    """The stash, buyable collections, and library tabs."""
    tabs = collection_tabs(collections, chosen)
    tabs.append(
        {
            "label": ALL_LABEL,
            "title": "",
            "href": f"?list={ALL_SCOPE}",
            "current": everything,
        }
    )
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
    from n26.core.access import gang_collections
    from n26.core.browse import all_gear, browse
    from n26.core.card import build_gang_card, build_modifier_index
    from n26.core.effects import compute_gang
    from n26.core.listing import build_catalogue, build_stash_catalogue
    from n26.core.owned import EquipHost, possessions
    from n26.core.render import roster as gang_roster
    from n26.core.render import summarise_roster
    from n26.core.views.owned import accessorise_dialogs, owned_dialog

    gang = _own_gang_or_404(request, pk)

    # One card answers both collection access and possessions.
    card = build_gang_card(gang, with_statlines=False)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    computed = compute_gang(card, index)

    collections = buyable_lists(
        access.collection
        for access in gang_collections(gang, card=card, computed=computed)
    )

    # The collection picker posts its URL state back with a purchase.
    wanted = request.POST.get("list", request.GET.get("list", ""))
    stash_tab = wanted == STASH_SCOPE
    everything = wanted == ALL_SCOPE
    chosen = None
    if not stash_tab and not everything:
        for collection in collections:
            if str(collection.pk) == wanted:
                chosen = collection
                break
        if chosen is None and collections:
            chosen = collections[0]

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

    view = None
    if everything:
        view = all_gear(ALL_LABEL)
    elif chosen is not None:
        view = browse(chosen)

    if request.method == "POST" and view is not None:
        # As on a fighter's page: a click may ask for the row it changed
        # rather than the screen around it, and without script the same
        # button posts the same form and gets the whole page back.
        piecemeal = bool(request.headers.get("HX-Request"))
        outcome = _buy_clicked(
            request,
            gang,
            gang.stash,
            view,
            here,
            into="the stash",
            collection=ALL_LABEL if everything else chosen.name,
            fragment=piecemeal,
        )
        if not piecemeal:
            return outcome
        if outcome is None:
            return _spoken(request, HttpResponse(status=204))
        row, held_label, host = screen_row(
            request,
            gang,
            outcome.key,
            list_param=wanted,
            expanded_key=expanded_key,
            at=here,
        )
        return _spoken(
            request, changed(request, gang, outcome.key, row, held_label, host)
        )

    host = EquipHost.stash(gang, card, at=here)
    owned = possessions(host)
    refunds = not gang.credits_unlimited

    dialog = owned_dialog(request, host)
    if (answer := _panel_asked(request, dialog)) is not None:
        return answer

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
        browsing = ALL_LABEL if everything else str(chosen or "")
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
            "held_label": host.held_label,
            "dialog": dialog,
            "accessorise": accessorise_dialogs(request, host),
            "summary": summarise_roster(gang_roster(gang)),
            **picker_context(catalogue, view),
        },
    )
