"""Learning a skill — the standing half of the skills surface.

A founding pick is a question somebody asked ("a Leader starts with a
Primary skill") and it is answered at its own address. This is the other
half: what a fighter may learn at any time, which nobody asked and which
is not a question at all — it is their **grid**, the placements their
profile and subtypes carry, read as a list.

So the address names a fighter rather than a slot::

    /fighters/<model>/skills/?list=<collection>

and the screen is the same shape the choose page draws: the fighter's
own view of a collection, resectioned by their placements, with the
unplaced tier dropped — a skill nobody placed for them is not theirs to
learn, however visible it is on a browse (``n26.core.browse`` keeps it
there deliberately, and the roll-anything pick wants exactly that).

A fighter whose grid places nothing has no screen here, not an empty
one. The grid is the access; an unauthored grid is a content gap, and a
404 says so in the only way that stays true when it is filled in.

What pressing writes is ``Operation.learn``: free, recorded, and caused
by nothing, so what a fighter earned survives the row that opened the
set up to them.
"""

import dataclasses

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from n26.core.views.permissions import _own_miniature_or_404


def link_skills(*cards):
    """Point every card's Skills control at this fighter's learn screen.

    One query for a whole roster, and none per card: which collections
    hold what a model learns is asked once, and each card already knows
    which collections its own grid reaches. A card depicting nobody — a
    hire preview, a gallery sample — keeps an empty href and draws no
    control, which is what a print sheet wants too.
    """
    from n26.core.access import model_collections

    learnable = {str(collection.pk) for collection in model_collections()}
    for card in cards:
        if card.id and set(card.placed_in) & learnable:
            card.learn_href = reverse("n26-learn", args=[card.id])


def _known_on(card):
    """What this model already has, keyed the way a pick list keys its
    options — so a listing can say "already known" rather than let
    somebody learn the same skill twice in silence."""
    return {
        f"{node.assignable._meta.label_lower}:{node.assignable.pk}"
        for node in card.roots
        if not node.broadcast
    }


def _marked(offer, known):
    """The same offer, with the things this model already has said so.

    Said, never dropped: a known skill keeps its place in the listing so
    the reader can see it is covered, and the mark is why the POST's
    refusal of a second copy never surprises anyone.
    """
    for group in offer.groups:
        group.options = [
            option
            if option.key not in known
            else dataclasses.replace(
                option,
                detail="; ".join(filter(None, [option.detail, "already known"])),
            )
            for option in group.options
        ]
    return offer


@login_required
def learn(request, pk):
    """What this fighter may learn, and the press that learns it.

    GET asks and writes nothing. POST names one thing from the list the
    server has just re-derived — never a price, and never a free-text
    identity — and writes it as the fighter's own, at no charge.

    Nothing is removed from the listing: a skill the fighter's Type may
    not use keeps its place with a note on it, exactly as it does at the
    till, and a skill they already have is marked rather than hidden.
    The one press refused is a second copy of something they hold — by
    any route, a grant and an answered choice included — because a
    duplicate skill means nothing and a card reading "Marksman,
    Marksman" is a bug however honestly it got there.
    """
    from n26.analytics import EventVerb, N26Noun, record
    from n26.core.access import learnable_for
    from n26.core.browse import (
        browse,
        narrow,
        placements_for,
        regrouped_by_placement,
        usability_for,
        with_use_notes,
    )
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute
    from n26.core.operations import NotEnoughCredits, operation
    from n26.core.render import offer_from_view
    from n26.core.views.equip import collection_tabs

    miniature = _own_miniature_or_404(request, pk)
    gang = miniature.gang

    # One card build serves the whole page: the grid that decides which
    # collections are theirs, and how usable each line is, are both read
    # off the same computed card.
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    computed = compute(card, index)

    collections = learnable_for(computed)
    if not collections:
        raise Http404("No skills for this fighter")

    chosen = next(
        (c for c in collections if str(c.pk) == request.GET.get("list")),
        collections[0],
    )
    placements = placements_for(computed, chosen)
    listed = narrow(
        with_use_notes(
            regrouped_by_placement(
                browse(chosen),
                placements,
                fallback=chosen.default_section(),
                name=str(chosen),
            ),
            usability_for(computed),
        ),
        # Only the tiers their grid names. The browse keeps every
        # unplaced category under the fallback so nothing is hidden from
        # a reader shopping a list; here the tiers *are* the offer, and
        # another house's sets are not this fighter's to learn.
        sections=[placement.section.name for placement in placements.values()],
    )
    offer = _marked(offer_from_view(listed, label=str(chosen)), _known_on(card))
    back = reverse("n26-gang", args=[gang.pk])
    here = f"{request.path}?list={chosen.pk}"

    if request.method == "POST":
        wanted = request.POST.get("thing", "")
        picked = next(
            (
                option
                for group in offer.groups
                for option in group.options
                if option.key == wanted
            ),
            None,
        )
        if picked is None:
            # Not on this list — a stale page, or a press with nothing
            # selected. The list itself is the answer either way.
            messages.error(request, "That is not one of the things on offer.")
            return redirect(here)
        # A skill the model already has, by any route — learned, granted,
        # or the answer to a founding choice. A second copy means nothing
        # in the game and reads as a bug on the card, so this is refused
        # like a stale press rather than left to the owner: it is not a
        # judgement about the rules, there is simply nothing it could add.
        if picked.key in _known_on(card):
            messages.error(request, f"{miniature.name} already has {picked.name}.")
            return redirect(here)
        try:
            with operation(gang, actor=request.user) as op:
                learned = op.learn(miniature, picked.thing)
        except NotEnoughCredits as refusal:
            messages.error(request, str(refusal))
            return redirect(here)
        record(
            request,
            N26Noun.ASSIGNMENT,
            EventVerb.CREATE,
            learned,
            gang_id=str(gang.pk),
            miniature_id=str(miniature.pk),
            thing=picked.name,
            collection=chosen.name,
        )
        messages.success(request, f"{miniature.name} learned {picked.name}.")
        return redirect(back)

    return render(
        request,
        "n26/learn.html",
        {
            "gang": gang,
            "miniature": miniature,
            "chosen": chosen,
            "offer": offer,
            "action": here,
            "back": back,
            # Which collection, when a fighter's grid reaches more than
            # one. Drawn as tabs only then: with a single collection
            # there is nothing to choose, and the heading names it.
            "collection_tabs": collection_tabs(collections, chosen),
            # Not "lead". A cotton slot is a context variable, and any
            # component on the page with a slot of that name — the site
            # footer's columns have one — draws whatever the page
            # happens to have under it.
            "pick_lead": (
                f"What {miniature.name} may learn. Leaving this open costs nothing."
            ),
        },
    )
