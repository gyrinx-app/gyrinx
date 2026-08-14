"""Learning a skill — the standing half of the skills surface.

A founding pick is a question somebody asked ("a Leader starts with a
Primary skill") and it is chosen for at its own address. This is the other
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

A fighter whose grid places nothing gets the screen anyway, saying
there is nothing for them to learn. The grid is the access and an
unauthored one is a content gap, but the address names a fighter rather
than the gap: it is theirs whether or not anybody has graded them, so
the switcher on the next fighter's screen can offer it without knowing
which of them have a grid.

What clicking writes is ``Operation.learn``: free, recorded, and caused
by nothing, so what a fighter earned survives the row that opened the
set up to them.

The same listing is offered a second way, as a box to tick on the
fighter's own edit page (``ticked_offer`` and ``apply_ticks``). One
screen learns a thing at a time and the other settles the whole list at
once, but both read the same grid through the same browse: two ways of
saying it, never two ideas of what a fighter may have.
"""

import dataclasses

from django.contrib import messages
from django.contrib.auth.decorators import login_required
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


def _key(thing):
    """How a pick list keys its options: the table and the row, because a
    bare primary key is ambiguous across the assignable tables."""
    return f"{thing._meta.label_lower}:{thing.pk}"


def _rows_on(card):
    """The stored row behind each thing this model holds, keyed the way a
    pick list keys its options — so a tick list can find what a cleared
    box refers to.

    The model's own rows only: what the gang holds rides every member's
    card and is not one fighter's to give up, and a line something has
    taken away is not held at all.
    """
    rows = {}
    for node in card.roots:
        if node.broadcast or node.suppressed or node.assignment is None:
            continue
        rows.setdefault(_key(node.assignable), node.assignment)
    return rows


def _grants_on(computed):
    """What a modifier gives this model and what gives it — skills and
    powers alike, keyed the same way.

    Nothing stored is behind these, so a surface offering things to tick
    draws them fixed rather than as rows an owner could clear.
    """
    return {
        _key(contribution.thing): contribution.source
        for contribution in (*computed.skills, *computed.powers)
    }


def ticked_offer(card, computed):
    """What this model may hold, as a list to tick rather than to click.

    The learn screen's own listing: the same browse of the same
    collections, resectioned by the same placements and narrowed to the
    same tiers, so the two surfaces cannot come to disagree about what is
    theirs. Skills and powers alike — a tier holds whatever the content
    swept into it, and a family of powers a fighter's grid places is as
    much theirs as a skill set is.

    The tiers are the ones their grid names, which for the published
    lists is Primary and Secondary; the unplaced fallback stays off,
    because another house's sets are not this fighter's. A tier their
    grid reaches nothing in simply has no heading.

    Ticked where the model already holds the thing, by any route. What a
    modifier grants says what grants it and is fixed: no row is behind
    it, so there is nothing a click here could take away.
    """
    from n26.core.access import learnable_for
    from n26.core.browse import (
        browse,
        narrow,
        placements_for,
        regrouped_by_placement,
        usability_for,
        with_use_notes,
    )
    from n26.core.render import ChoiceOffer, offer_from_view

    held = _rows_on(card)
    granted = _grants_on(computed)
    groups = []
    for collection in learnable_for(computed):
        placements = placements_for(computed, collection)
        listed = narrow(
            with_use_notes(
                regrouped_by_placement(
                    browse(collection),
                    placements,
                    fallback=collection.default_section(),
                    name=str(collection),
                ),
                usability_for(computed),
            ),
            sections=[placement.section.name for placement in placements.values()],
        )
        groups.extend(
            offer_from_view(
                listed, label=str(collection), held=held, granted=granted
            ).groups
        )
    return ChoiceOffer(label="", groups=groups)


def apply_ticks(op, miniature, card, computed, ticked):
    """Make what a model holds match what was ticked, and say what moved.

    The listing is derived again here rather than trusted from the page,
    so a stale form or a hand-made click can only name things that are on
    the list now. Nothing off the list is touched: a skill learned from a
    set the grid has since stopped reaching keeps its row, because it is
    not being offered and so cannot have been cleared.

    A newly ticked thing is learned — free, and caused by nothing, the
    same write the skills screen makes — and a cleared one is removed the
    way anything is taken off a card: archived, with the ledger still
    saying it was there. Granted things are on neither side of the
    difference, because a fixed box submits nothing and reading its
    silence as a clearing would take away the row of anything a modifier
    also grants.
    """
    offer = ticked_offer(card, computed)
    rows = _rows_on(card)
    granted = _grants_on(computed)

    # One entry per thing: two collections may both list a skill, and a
    # second sighting of a ticked one must not learn it twice.
    options = {}
    for group in offer.groups:
        for option in group.options:
            options.setdefault(option.key, option)

    learned, cleared = [], []
    for key, option in options.items():
        if key in granted:
            continue
        if key in ticked:
            if key not in rows:
                op.learn(miniature, option.thing)
                learned.append(option.name)
        elif key in rows:
            op.remove(rows[key])
            cleared.append(option.name)
    return learned, cleared


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
    """What this fighter may learn, and the click that learns it.

    GET asks and writes nothing. POST names one thing from the list the
    server has just re-derived — never a price, and never a free-text
    identity — and writes it as the fighter's own, at no charge.

    Nothing is removed from the listing: a skill the fighter's Type may
    not use keeps its place with a note on it, exactly as it does on the
    equip page, and a skill they already have is marked rather than
    hidden.
    The one click refused is a second copy of something they hold — by
    any route, a grant and a settled choice included — because a
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
    from n26.core.operations import Refusal, operation
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

    back = reverse("n26-gang", args=[gang.pk])

    collections = learnable_for(computed)
    if not collections:
        # Nobody has graded this fighter in a category, so there is
        # nothing they could learn — a gap in the content, and a page
        # that says so. Refusing instead would put a dead row in the
        # switcher every other fighter's skills screen draws.
        return render(
            request,
            "n26/learn.html",
            {
                "gang": gang,
                "miniature": miniature,
                "nothing_to_learn": True,
                "action": request.path,
                "back": back,
                # No act and no way out at the foot of the page: there is
                # nothing to submit, and a lone Cancel under a page that
                # asked nothing cancels nothing. The breadcrumb is the
                # way back to the gang.
                "submit_label": "",
                "cancel_url": "",
                "pick_lead": "",
            },
        )

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
            # Not on this list — a stale page, or a click with nothing
            # selected. The list itself is the reply either way.
            messages.error(request, "That is not one of the things on offer.")
            return redirect(here)
        # A skill the model already has, by any route — learned, granted,
        # or chosen for a founding choice. A second copy means nothing
        # in the game and reads as a bug on the card, so this is refused
        # like a stale click rather than left to the owner: it is not a
        # judgement about the rules, there is simply nothing it could add.
        if picked.key in _known_on(card):
            messages.error(request, f"{miniature.name} already has {picked.name}.")
            return redirect(here)
        try:
            with operation(gang, actor=request.user) as op:
                learned = op.learn(miniature, picked.thing)
        except Refusal as refusal:
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
            "nothing_to_learn": False,
            "chosen": chosen,
            "offer": offer,
            "action": here,
            "back": back,
            "submit_label": "Learn",
            "cancel_url": back,
            # Which collection, when a fighter's grid reaches more than
            # one. Drawn as tabs only then: with a single collection
            # there is nothing to choose, and the heading names it.
            "collection_tabs": collection_tabs(collections, chosen),
            # Not "lead". A cotton slot is a context variable, and any
            # component on the page with a slot of that name — the site
            # footer's columns have one — draws whatever the page
            # happens to have under it.
            "pick_lead": (f"Pick skills for {miniature.name}."),
        },
    )
