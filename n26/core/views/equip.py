"""Buying equipment for one fighter — the web face of :mod:`n26.core.browse`."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.text import slugify

from n26.core.browse import UNCATEGORISED
from n26.core.views.permissions import _own_miniature_or_404


def _thing_key(thing):
    """One string naming a browsed line's item — what the Buy buttons
    submit. Model label plus pk, the same pair ``browse`` dedupes on,
    because a pk alone is ambiguous across the assignable tables."""
    return f"{thing._meta.label_lower}:{thing.pk}"


def _parts_field(key):
    """The input name the tickable parts of one line share.

    Scoped by the line, because one form holds the whole listing: without
    it, ticking warp rounds on the autogun row would arrive with the stub
    gun's press. Slugified, because that is what the template renders —
    read the raw key back and every box ticked in a real browser is
    silently ignored while a test posting the raw key still passes.
    """
    return f"{slugify(key)}:parts"


def _parts_picked(data, key, line):
    """The parts a submission ticked on this line, in the order drawn.

    Values are indices into the line the server has just re-derived, so a
    tampered form can name nothing the listing does not offer. A repeated
    index is refused as well: a checkbox cannot be ticked twice, and one
    press was never an order for two of the same ammo.
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
        picked.append(line.parts[index])
    return picked


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


def _row(line):
    """One line as the template draws it: the identity its Buy submits,
    and its parts as tickable inputs.

    A part prints its bare name — "warp round", not "warp round
    (Autogun)" — because it is drawn under the gun that already says so.
    """
    key = _thing_key(line.thing)
    return {
        "line": line,
        "key": key,
        "parts_field": _parts_field(key),
        "parts": [
            {"index": index, "line": part, "name": part.thing.name}
            for index, part in enumerate(line.parts)
        ],
    }


@login_required
def equip(request, pk):
    """Buy equipment for one fighter, from a list they can actually browse.

    Which list is URL state (``?list=<pk>``), picked from
    ``collections_for`` — the fighter's own lists, their gang's, computed
    grants — plus the standard Trading Post when the library has one.

    The Buy buttons submit the *identity* of a line, never its price:
    the server re-browses the chosen collection and hands the found line
    whole to ``Operation.buy``, so what is paid is always the server's
    derivation and a tampered form can name nothing that is not on the
    list. Browsed on equipment-list terms for now — Trade Points are
    shown, not charged, because a TP budget is a session concept that
    does not exist yet.

    A weapon's paid ammo and firing modes are ticked on the weapon's own
    row and bought with it, in the same operation and onto the same gun.
    One press, one purchase, however many boxes are ticked: ammo is a way
    the gun you are buying is built, not a second thing on the shelf.
    Ammo for a gun a fighter already owns has no route here yet.

    A purchase stays on the page: kitting out a fighter is a run of
    purchases, and the breadcrumb is the way back.
    """
    from n26.core.access import collections_for
    from n26.core.browse import browse, usability_for, with_use_notes
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute
    from n26.core.operations import NotEnoughCredits, operation
    from n26.library.models import Collection, get_default_pack
    from n26.library.standard_content import TRADING_POST_COLLECTION

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang

    # One card build serves the whole page: which lists this fighter can
    # browse and how usable each line is are both read off the same
    # computed card.
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    computed = compute(card, index)

    collections = [
        access.collection
        for access in collections_for(miniature, card=card, computed=computed)
    ]
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
        try:
            with operation(gang, actor=request.user) as op:
                bought = op.buy(miniature, line=line)
                # Onto the gun, not onto the fighter: a profile belongs to
                # one particular weapon, and it is the same till either
                # way, so the price charged is the one the row quoted.
                for part in picked:
                    op.buy(bought, line=part)
        except NotEnoughCredits as refusal:
            messages.error(request, str(refusal))
            return redirect(back)
        if picked:
            extras = ", ".join(part.thing.name for part in picked)
            messages.success(
                request, f"Bought {line.name} with {extras} for {miniature.name}."
            )
        else:
            messages.success(request, f"Bought {line.name} for {miniature.name}.")
        return redirect(back)

    lines = list(view.all_lines()) if view is not None else []
    trade_points = [
        line.trade_points for line in lines if line.trade_points is not None
    ]
    # Each shelf paired with the name it goes by on screen. The grouping
    # leaves a homeless line's section unnamed, which is the truth about
    # the content; the picker draws its sections as tabs, and a tab needs
    # a word on it. Paired once so the strip, the registration names and
    # the heading cannot disagree — see the hire view, which does the same.
    shelves = [
        (section.name or UNCATEGORISED, section)
        for section in (view.sections if view is not None else [])
    ]
    # Which list is being browsed is a tab when there are several. With
    # one there is nothing to choose, so a strip of one tab would be a
    # control that does nothing — the lead says where you are shopping
    # instead.
    tabs = collection_tabs(collections, chosen)
    if len(tabs) > 1:
        lead = f"Buying for {gang.name} — what you buy lands on this fighter's card."
    elif chosen is not None:
        lead = (
            f"Buying for {gang.name} from {chosen} — what you buy lands on "
            "this fighter's card."
        )
    else:
        lead = f"Buying for {gang.name}."
    return render(
        request,
        "n26/equip.html",
        {
            "miniature": miniature,
            "gang": gang,
            "collections": collections,
            "collection_tabs": tabs,
            "chosen": chosen,
            "lead": lead,
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
                            "lines": [_row(line) for line in category.lines],
                        }
                        for category in section.categories
                    ],
                }
                for index, (name, section) in enumerate(shelves)
            ],
            # Registration names — see the hire view: a row in an unnamed
            # category registers under its section's name, and a list that
            # omits one hides those rows client-side.
            "categories": list(
                dict.fromkeys(
                    category.name or name
                    for name, section in shelves
                    for category in section.categories
                )
            ),
            "category_options": [
                {"value": name, "label": name}
                for name in dict.fromkeys(
                    category.name
                    for _, section in shelves
                    for category in section.categories
                    if category.name
                )
            ],
            # One tab per shelf, as on the hire page. A section missing
            # from this list can never be the active tab and its rows
            # become unreachable, so every shelf is named above and every
            # shelf appears here — deduplicated, because the strip keys
            # its tabs by name and a repeated key draws neither.
            "sections": list(dict.fromkeys(name for name, _ in shelves)),
            "cost_floor": min((line.credits for line in lines), default=0),
            "cost_ceiling": max((line.credits for line in lines), default=0),
            "tp_ceiling": max(trade_points, default=0),
            "has_trade_points": bool(trade_points),
            # Distinct from has_trade_points: an exclusive line has
            # trade_points=None ("E" is not a number), so a list of
            # exclusive-only items would otherwise never draw the toggle
            # that is the only way to filter them.
            "has_exclusive": any(line.is_exclusive for line in lines),
        },
    )
